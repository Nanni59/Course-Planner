"""
Course Planner - TikZ static visual renderer (Hugging Face Docker Space).

Exposes:
  GET  /health  -> {"status": "ok", ...}
  POST /render  -> render a constrained TikZ snippet to SVG or PNG

This service is intentionally separate from the Manim video renderer. It exists
to turn Gemini-generated TikZ code into textbook-style static visuals for
slides, worksheets, study guides, and all-in-one study sets.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


app = FastAPI(title="Course Planner TikZ Renderer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_CODE_CHARS = int(os.environ.get("MAX_CODE_CHARS", "12000"))
RENDER_TIMEOUT = int(os.environ.get("RENDER_TIMEOUT", "25"))
MAX_OUTPUT_BYTES = int(os.environ.get("MAX_OUTPUT_BYTES", "1500000"))
GEMINI_TIMEOUT = (10, int(os.environ.get("GEMINI_READ_TIMEOUT", "90")))
GEMINI_MAX_ATTEMPTS = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "4"))
GEMINI_DEADLINE = int(os.environ.get("GEMINI_DEADLINE", "180"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-2.5-flash").split(",")
    if m.strip()
]
GEMINI_MODELS = list(dict.fromkeys([GEMINI_MODEL] + GEMINI_FALLBACK_MODELS))
GEMINI_KEYS = [
    k
    for k in (
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
        os.environ.get("GEMINI_API_KEY_3"),
        os.environ.get("GEMINI_API_KEY_4"),
    )
    if k
]
_key_idx = 0
_key_lock = threading.Lock()
_model_blocked_until: dict[tuple[object, str], float] = {}
_model_lock = threading.Lock()
_last_success_model = None
_last_success_model_lock = threading.Lock()


class RenderReq(BaseModel):
    code: str = Field(..., description="TikZ snippet or full tikzpicture environment")
    format: Literal["svg", "png"] = "svg"
    theme: Literal["green", "mono"] = "green"
    target: Literal["slide", "worksheet", "guide", "generic"] = "generic"


class GenerateReq(BaseModel):
    title: str = ""
    brief: str = Field(..., description="Plain-language description of the visual to create")
    subject: str = "General"
    equation: str = ""
    format: Literal["svg", "png"] = "svg"
    theme: Literal["green", "mono"] = "green"
    target: Literal["slide", "worksheet", "guide", "generic"] = "generic"


def _next_key_index() -> int:
    global _key_idx
    if not GEMINI_KEYS:
        return 0
    with _key_lock:
        idx = _key_idx
        _key_idx = (_key_idx + 1) % len(GEMINI_KEYS)
        return idx


def _model_block_key(model: str, key_idx: int | None = None):
    return ("*", model) if key_idx is None else (key_idx, model)


def _model_is_blocked(model: str, key_idx: int | None = None) -> bool:
    now = time.time()
    with _model_lock:
        if _model_blocked_until.get(_model_block_key(model, None), 0) > now:
            return True
        if key_idx is not None and _model_blocked_until.get(_model_block_key(model, key_idx), 0) > now:
            return True
    return False


def _available_models(key_idx: int | None = None) -> list[str]:
    models = [m for m in GEMINI_MODELS if not _model_is_blocked(m, key_idx)]
    return models or GEMINI_MODELS[:]


def _temporarily_block_model(model: str, seconds: int = 900, key_idx: int | None = None) -> None:
    with _model_lock:
        _model_blocked_until[_model_block_key(model, key_idx)] = time.time() + seconds


def _fallback_models_after(model: str, key_idx: int | None = None) -> list[str]:
    models = [m for m in GEMINI_MODELS if m != model and not _model_is_blocked(m, key_idx)]
    return models or [m for m in GEMINI_MODELS if m != model] or [model]


def _probe_model_access() -> list[dict]:
    out = []
    for key_idx, key in enumerate(GEMINI_KEYS):
        row = {"key_slot": key_idx + 1, "models": []}
        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            try:
                res = requests.get(url, headers={"x-goog-api-key": key}, timeout=(8, 20))
                row["models"].append({
                    "model": model,
                    "ok": res.status_code == 200,
                    "status": res.status_code,
                    "blocked_temporarily": _model_is_blocked(model, key_idx),
                })
            except requests.exceptions.RequestException as exc:
                row["models"].append({
                    "model": model,
                    "ok": False,
                    "status": "network",
                    "error": str(exc)[:120],
                    "blocked_temporarily": _model_is_blocked(model, key_idx),
                })
        out.append(row)
    return out


DANGEROUS_PATTERNS = [
    r"\\write18\b",
    r"\\input\b",
    r"\\include\b",
    r"\\openin\b",
    r"\\openout\b",
    r"\\read\b",
    r"\\write\b",
    r"\\usepackage\b",
    r"\\documentclass\b",
    r"\\end\s*\{document\}",
    r"\\catcode\b",
    r"\\csname\b",
    r"\\def\b",
    r"\\edef\b",
    r"\\gdef\b",
    r"\\xdef\b",
    r"\\let\b",
    r"\\newcommand\b",
    r"\\renewcommand\b",
    r"\\newread\b",
    r"\\newwrite\b",
    r"\\immediate\b",
    r"\\special\b",
    r"\\includegraphics\b",
    r"\\pgfdeclareimage\b",
    r"\\externalize\b",
    r"\\tikzexternalize\b",
    r"\\RequirePackage\b",
    r"\\ExplSyntaxOn\b",
]


ALLOWED_BEGIN_ENVIRONMENTS = {
    "tikzpicture",
    "axis",
    "scope",
}


def _plain_log(text: str, limit: int = 2400) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text or "")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact = "\n".join(lines[-30:])
    return compact[-limit:]


def _reject_reason(code: str) -> str | None:
    if not code.strip():
        return "TikZ code is empty."
    if len(code) > MAX_CODE_CHARS:
        return f"TikZ code is too long. Limit is {MAX_CODE_CHARS} characters."
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, code, flags=re.IGNORECASE):
            display = pattern.replace("\\\\", "\\")
            return f"Disallowed LaTeX command: {display}"
    for env in re.findall(r"\\begin\s*\{([^}]+)\}", code):
        if env not in ALLOWED_BEGIN_ENVIRONMENTS:
            return f"Disallowed LaTeX environment: {env}"
    return None


def _extract_tikz(code: str) -> str:
    code = code.strip()
    fenced = re.match(r"^```(?:tex|latex|tikz)?\s*([\s\S]*?)\s*```$", code, flags=re.IGNORECASE)
    if fenced:
        code = fenced.group(1).strip()

    match = re.search(r"\\begin\s*\{tikzpicture\}[\s\S]*?\\end\s*\{tikzpicture\}", code)
    if match:
        return match.group(0)

    return "\\begin{tikzpicture}\n" + code + "\n\\end{tikzpicture}"


def _template(tikz: str, theme: str, target: str) -> str:
    if theme == "mono":
        accent = "black"
        accent_two = "gray"
        fill = "gray!10"
    else:
        accent = "cpGreen"
        accent_two = "cpSage"
        fill = "cpMint"

    line_width = "1.15pt" if theme == "mono" else "1pt"
    dashed_width = "1pt" if theme == "mono" else "0.8pt"
    axis_width = "0.85pt" if theme == "mono" else "0.7pt"

    scale = {
        "slide": "1.0",
        "worksheet": "0.92",
        "guide": "0.95",
        "generic": "1.0",
    }.get(target, "1.0")

    return rf"""
\documentclass[tikz,border=6pt]{{standalone}}
\usepackage{{amsmath,amssymb}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.18}}
\usetikzlibrary{{arrows.meta,calc,decorations.pathreplacing,patterns,positioning,angles,quotes,intersections,3d}}
\definecolor{{cpGreen}}{{HTML}}{{3F8F46}}
\definecolor{{cpSage}}{{HTML}}{{6AA96F}}
\definecolor{{cpMint}}{{HTML}}{{E7F5E8}}
\tikzset{{
  every picture/.style={{scale={scale}, transform shape}},
  cp axis/.style={{-{{Stealth[length=2.5mm]}}, line width={axis_width}, draw=black!75}},
  cp line/.style={{line width={line_width}, draw={accent}}},
  cp dashed/.style={{line width={dashed_width}, draw={accent_two}, dashed}},
  cp fill/.style={{fill={fill}, draw={accent}}},
  cp point/.style={{circle, fill={accent}, inner sep=1.7pt}},
  cp label/.style={{font=\small}},
}}
\begin{{document}}
{tikz}
\end{{document}}
""".strip()


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        upper = name.upper()
        if any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "GEMINI")):
            env.pop(name, None)
    return env


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=_clean_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=RENDER_TIMEOUT,
        check=False,
    )


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json|tex|latex|tikz)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _gemini(prompt: str, as_json: bool = False, temperature: float = 0.25):
    if not GEMINI_KEYS:
        raise RuntimeError("No Gemini API key is set on the Space.")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
        },
    }
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    last_err = "Gemini call failed."
    backoff = 2
    started = time.time()
    key_idx = _next_key_index()
    attempts = max(GEMINI_MAX_ATTEMPTS, len(GEMINI_KEYS) * len(GEMINI_MODELS))
    for attempt in range(attempts):
        if time.time() - started > GEMINI_DEADLINE:
            break
        key_idx = key_idx % len(GEMINI_KEYS)
        key = GEMINI_KEYS[key_idx]
        models = _available_models(key_idx)
        model = models[0]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            res = requests.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
                timeout=GEMINI_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            last_err = f"Gemini network error: {str(exc)[:180]}"
            print(f"[gemini] {last_err} - attempt {attempt + 1}/{attempts}, rotating key.", flush=True)
            key_idx = (key_idx + 1) % len(GEMINI_KEYS)
            time.sleep(backoff)
            backoff = min(backoff * 2, 20)
            continue

        low_body = res.text.lower()
        if res.status_code == 200:
            try:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                global _last_success_model
                with _last_success_model_lock:
                    _last_success_model = model
                print(f"[gemini] success using model {model} on key slot {key_idx + 1}.", flush=True)
                if as_json:
                    return json.loads(_strip_fence(text))
                return text
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_err = f"Gemini returned unusable output: {type(exc).__name__}"
                time.sleep(backoff)
                backoff = min(backoff * 2, 20)
                continue

        last_err = f"Gemini API error {res.status_code}: {res.text[:220]}"
        if res.status_code == 429:
            key_idx = (key_idx + 1) % len(GEMINI_KEYS)
            if (attempt + 1) % max(1, len(GEMINI_KEYS)) == 0:
                time.sleep(backoff)
                backoff = min(backoff * 2, 20)
            continue
        if res.status_code == 404 and len(GEMINI_MODELS) > 1:
            _temporarily_block_model(model, seconds=3600, key_idx=key_idx)
            key_idx = (key_idx + 1) % len(GEMINI_KEYS)
            print(f"[gemini] {last_err} - trying another key/model.", flush=True)
            continue
        if res.status_code in (400, 403) and len(GEMINI_KEYS) > 1:
            _temporarily_block_model(model, seconds=1800, key_idx=key_idx)
            key_idx = (key_idx + 1) % len(GEMINI_KEYS)
            print(f"[gemini] {last_err} - trying another key/model.", flush=True)
            continue
        if res.status_code in (429, 500, 502, 503, 504):
            if res.status_code == 503 and len(GEMINI_MODELS) > 1 and (
                "high demand" in low_body or "overloaded" in low_body or "capacity" in low_body
            ):
                _temporarily_block_model(model, seconds=900, key_idx=None)
                print(f"[gemini] {last_err} - temporarily falling back from {model}.", flush=True)
                continue
            key_idx = (key_idx + 1) % len(GEMINI_KEYS)
            time.sleep(backoff)
            backoff = min(backoff * 2, 20)
            continue
        if len(GEMINI_MODELS) <= 1 and len(GEMINI_KEYS) <= 1:
            break
        key_idx = (key_idx + 1) % len(GEMINI_KEYS)

    raise RuntimeError(last_err)


TIKZ_EXAMPLE_LIBRARY = r"""
Use these compact patterns as quality targets. Adapt coordinates and labels to the user's problem.

CALCULUS / GRAPHING:
\begin{tikzpicture}
\begin{axis}[xmin=-1,xmax=4,ymin=-1,ymax=6,axis lines=middle,xlabel={$x$},ylabel={$y$},
  grid=both,grid style={draw=gray!20},width=7cm,height=4.5cm,clip=false]
  \addplot[domain=-.5:3.4,samples=90,cp line] {0.45*(x-1)^2+1};
  \addplot[domain=.1:3.1,cp dashed] {0.9*x};
  \fill (axis cs:1,1) circle (1.6pt) node[below left] {$(a,f(a))$};
  \node[anchor=west] at (axis cs:2.4,2.2) {tangent};
\end{axis}
\end{tikzpicture}

VECTORS:
\begin{tikzpicture}[scale=.8]
  \coordinate (O) at (0,0); \coordinate (A) at (3,0); \coordinate (B) at (4.3,1.8);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {$\vec u$};
  \draw[cp line,-Stealth] (A)--(B) node[midway,right] {$\vec v$};
  \draw[cp dashed,-Stealth] (O)--(B) node[midway,above left] {$\vec u+\vec v$};
  \fill (O) circle (1.4pt) (A) circle (1.4pt) (B) circle (1.4pt);
\end{tikzpicture}

VECTOR MAGNITUDE MIN/MAX:
\begin{tikzpicture}[scale=.8]
  \coordinate (A) at (0,1.1); \coordinate (B) at (1.4,1.1); \coordinate (C) at (4.2,1.1);
  \node[anchor=east] at (-.15,1.1) {\small same};
  \draw[cp line,-Stealth] (A)--(B) node[midway,above] {$\vec u$};
  \draw[cp line,-Stealth] (B)--(C) node[midway,above] {$\vec v$};
  \draw[cp dashed,-Stealth] (A)--(C) node[midway,below] {$|\vec u|+|\vec v|$};
  \coordinate (D) at (0,0); \coordinate (E) at (2.8,0); \coordinate (F) at (1.4,0);
  \node[anchor=east] at (-.15,0) {\small opposite};
  \draw[cp line,-Stealth] (D)--(E) node[midway,above] {$\vec v$};
  \draw[cp line,-Stealth] (E)--(F) node[midway,above] {$\vec u$};
  \draw[cp dashed,-Stealth] (D)--(F) node[midway,below] {$\bigl||\vec v|-|\vec u|\bigr|$};
\end{tikzpicture}

VECTOR PARALLELOGRAM DIAGONALS:
\begin{tikzpicture}[scale=.8]
  \coordinate (A) at (0,0); \coordinate (B) at (3,0); \coordinate (D) at (.9,1.8); \coordinate (C) at (3.9,1.8);
  \draw[cp line] (A)--(B)--(C)--(D)--cycle;
  \draw[cp line,-Stealth] (A)--(B) node[midway,below] {$\vec u$};
  \draw[cp line,-Stealth] (A)--(D) node[midway,left] {$\vec v$};
  \draw[cp dashed,-Stealth] (A)--(C) node[pos=.62,above] {$\vec u+\vec v$};
  \draw[cp dashed,-Stealth] (B)--(D) node[pos=.55,below left] {$\vec v-\vec u$};
  \node[below left] at (A) {$A$}; \node[below right] at (B) {$B$};
  \node[above right] at (C) {$C$}; \node[above left] at (D) {$D$};
\end{tikzpicture}

GEOMETRY:
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4,0); \coordinate (C) at (1.1,2.4);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \node[below left] at (A) {$A$}; \node[below right] at (B) {$B$}; \node[above] at (C) {$C$};
  \pic[draw=black,angle radius=7mm,"$\theta$",angle eccentricity=1.35] {angle=B--A--C};
\end{tikzpicture}

TRIGONOMETRY:
\begin{tikzpicture}[scale=1]
  \draw[cp axis] (-1.3,0)--(1.5,0) node[right] {$x$};
  \draw[cp axis] (0,-1.3)--(0,1.5) node[above] {$y$};
  \draw[cp line] (0,0) circle (1);
  \draw[cp dashed] (0,0)--(45:1) node[midway,above left] {$r$};
  \draw[cp dashed] (45:1)--({sqrt(2)/2},0) node[below] {$\cos\theta$};
  \node[right] at (45:1) {$(\cos\theta,\sin\theta)$};
\end{tikzpicture}
""".strip()


def _visual_prompt(req: GenerateReq, repair_log: str = "", previous_code: str = "") -> str:
    repair_block = ""
    if repair_log:
        repair_block = (
            "Previous TikZ failed. Fix it using this compile log: "
            + repair_log[:1200]
            + "\nPrevious TikZ:\n"
            + previous_code[:2500]
        )

    target_rules = ""
    if req.target == "worksheet":
        target_rules = """
Worksheet-specific rules:
- Prefer compact landscape compositions about 5.5 units wide by 3 units tall.
- Avoid tall compass-style diagrams unless the problem explicitly needs directions.
- Keep vector diagrams close to the question: short arrows, clear arrowheads, labels just outside the strokes.
- Do not leave large empty margins inside the drawing; center the math object tightly.
""".strip()

    return f"""
You create compact TikZ textbook diagrams for Course Planner.

Return only JSON with:
  "tikz": a TikZ snippet or full tikzpicture environment
  "caption": one short sentence

Rules:
- Make a real diagram, not a formula poster. Use drawing primitives: axes, curves, arrows, shaded regions, points, vectors, trees, geometry, or relationships.
- Do not use standalone equation text as the visual. If an equation matters, use it only as a tiny label.
- Keep labels very short: 1 to 3 words, variables, or symbols. Avoid full sentences in nodes.
- Prefer clean black/gray textbook styling. Do not use green unless the user specifically asks for color.
- Use safe TikZ/PGFPlots only. No documentclass, packages, begin document, external files, markdown fences, shell commands, or custom macros.
- Keep the drawing within a roughly 6 by 4 coordinate area so it fits slides and guides.
- Prefer the built-in styles when useful: cp axis, cp line, cp dashed, cp fill, cp point, cp label.
- For graphing, calculus, quadratic, coordinate-plane, or worksheet visuals, include visible x/y axes, tick marks or a light grid, axis labels, and coordinate labels for key points.
- For quadratic/parabola visuals, label intercepts and the vertex when known or inferable.
- Place labels with small offsets so they do not overlap curves, axes, or points.
- For tangent/secant/integral visuals, label the relevant point(s), interval endpoint(s), tangent/secant line, and shaded region where applicable.
- Avoid abstract unlabeled curves for worksheet questions; students need coordinates and readable reference points.
- For vectors, use clear head-to-tail or parallelogram construction. Put arrowheads on every vector and avoid ambiguous floating labels.
- For vector min/max questions, use two separated horizontal rows: "same" and "opposite". Put case words at the far left, never above the arrows, and keep result labels below dashed resultants.
- For parallelogram diagonal questions, place labels outside the crossing: label AC as u+v above the solid/dashed diagonal and BD as v-u or u-v below/left of the other diagonal. Never stack multiple formulas at the center.
- Avoid long phrase labels such as "Maximum Resultant" inside small diagrams; use short labels and let the worksheet question carry the wording.
- Before returning, mentally inspect the diagram: no label may sit on a line crossing, arrowhead, point marker, or another label. Move it with above/below/left/right/pos/anchor if needed.
- For geometry and trigonometry, use named points, angle marks, and side labels. Avoid decorative shapes without mathematical meaning.
- If the request is not visual, return an empty tikz string and a brief caption.

{target_rules}

Reference patterns:
{TIKZ_EXAMPLE_LIBRARY}

Subject: {req.subject[:160]}
Title: {req.title[:240]}
Equation, if any: {req.equation[:500]}
Visual brief: {req.brief[:1800]}
Target: {req.target}

{repair_block}
""".strip()


def _render(req: RenderReq) -> dict:
    reason = _reject_reason(req.code)
    if reason:
        return {"ok": False, "error": reason}

    tikz = _extract_tikz(req.code)
    reason = _reject_reason(tikz)
    if reason:
        return {"ok": False, "error": reason}

    work = Path(tempfile.mkdtemp(prefix="cp_tikz_"))
    try:
        stem = "visual_" + uuid.uuid4().hex[:10]
        tex_path = work / f"{stem}.tex"
        pdf_path = work / f"{stem}.pdf"
        svg_path = work / f"{stem}.svg"
        png_path = work / f"{stem}.png"
        tex_path.write_text(_template(tikz, req.theme, req.target), encoding="utf-8")

        compile_result = _run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                tex_path.name,
            ],
            work,
        )
        if compile_result.returncode != 0 or not pdf_path.exists():
            return {
                "ok": False,
                "error": "TikZ compile failed.",
                "log": _plain_log(compile_result.stdout),
            }

        if req.format == "png":
            convert_result = _run(
                ["pdftocairo", "-singlefile", "-png", "-r", "180", str(pdf_path), str(png_path.with_suffix(""))],
                work,
            )
            if convert_result.returncode != 0 or not png_path.exists():
                return {
                    "ok": False,
                    "error": "PNG conversion failed.",
                    "log": _plain_log(convert_result.stdout),
                }
            if png_path.stat().st_size > MAX_OUTPUT_BYTES:
                return {"ok": False, "error": "Rendered PNG is too large."}
            payload = base64.b64encode(png_path.read_bytes()).decode("ascii")
            return {
                "ok": True,
                "format": "png",
                "mime": "image/png",
                "base64": payload,
            }

        convert_result = _run(["pdf2svg", str(pdf_path), str(svg_path)], work)
        if convert_result.returncode != 0 or not svg_path.exists():
            return {
                "ok": False,
                "error": "SVG conversion failed.",
                "log": _plain_log(convert_result.stdout),
            }
        if svg_path.stat().st_size > MAX_OUTPUT_BYTES:
            return {"ok": False, "error": "Rendered SVG is too large."}
        svg = svg_path.read_text(encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "format": "svg",
            "mime": "image/svg+xml",
            "svg": svg,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"TikZ render timed out after {RENDER_TIMEOUT} seconds."}
    finally:
        shutil.rmtree(work, ignore_errors=True)


@app.get("/health")
def health():
    tools = {}
    for name in ("pdflatex", "pdf2svg", "pdftocairo"):
        tools[name] = bool(shutil.which(name))
    return {
        "status": "ok",
        "service": "tikz-renderer",
        "tools": tools,
        "max_code_chars": MAX_CODE_CHARS,
        "timeout": RENDER_TIMEOUT,
        "gemini_configured": bool(GEMINI_KEYS),
        "gemini_models": GEMINI_MODELS,
        "gemini_key_slots": len(GEMINI_KEYS),
        "model_candidates": _available_models(),
        "last_success_model": _last_success_model,
    }


@app.get("/models")
def models():
    return {
        "configured_model_order": GEMINI_MODELS,
        "key_slots": len(GEMINI_KEYS),
        "last_success_model": _last_success_model,
        "access": _probe_model_access() if GEMINI_KEYS else [],
    }


@app.post("/render")
def render(req: RenderReq):
    result = _render(req)
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.post("/generate")
def generate(req: GenerateReq):
    try:
        spec = _gemini(_visual_prompt(req), as_json=True, temperature=0.25)
        tikz = _strip_fence(str(spec.get("tikz", "")))
        caption = str(spec.get("caption", "")).strip()
        if not tikz:
            return JSONResponse({"ok": False, "skipped": True, "error": "No diagram was appropriate.", "caption": caption}, status_code=400)

        rendered = _render(RenderReq(code=tikz, format=req.format, theme=req.theme, target=req.target))
        if not rendered.get("ok"):
            repaired = _gemini(
                _visual_prompt(req, repair_log=rendered.get("log") or rendered.get("error") or "", previous_code=tikz),
                as_json=True,
                temperature=0.15,
            )
            tikz = _strip_fence(str(repaired.get("tikz", tikz)))
            caption = str(repaired.get("caption", caption)).strip()
            rendered = _render(RenderReq(code=tikz, format=req.format, theme=req.theme, target=req.target))

        if not rendered.get("ok"):
            rendered["tikz"] = tikz
            rendered["caption"] = caption
            return JSONResponse(rendered, status_code=400)

        rendered["tikz"] = tikz
        rendered["caption"] = caption
        return JSONResponse(rendered, status_code=200)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:500]}, status_code=500)
