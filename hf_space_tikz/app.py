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
  cp axis/.style={{-{{Stealth[length=2.5mm]}}, line width=0.7pt, draw=black!70}},
  cp line/.style={{line width=1pt, draw={accent}}},
  cp dashed/.style={{line width=0.8pt, draw={accent_two}, dashed}},
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
    key_idx = _next_key_index()
    attempts = max(GEMINI_MAX_ATTEMPTS, len(GEMINI_KEYS) * len(GEMINI_MODELS))
    for attempt in range(attempts):
        key = GEMINI_KEYS[key_idx % len(GEMINI_KEYS)]
        model = GEMINI_MODELS[(attempt // max(1, len(GEMINI_KEYS))) % len(GEMINI_MODELS)]
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
            key_idx += 1
            time.sleep(min(2 + attempt, 8))
            continue

        if res.status_code == 200:
            try:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                if as_json:
                    return json.loads(_strip_fence(text))
                return text
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_err = f"Gemini returned unusable output: {type(exc).__name__}"
                time.sleep(min(2 + attempt, 8))
                continue

        last_err = f"Gemini API error {res.status_code}: {res.text[:220]}"
        if res.status_code in (400, 403, 404) and len(GEMINI_MODELS) <= 1 and len(GEMINI_KEYS) <= 1:
            break
        if res.status_code in (429, 500, 502, 503, 504):
            key_idx += 1
            time.sleep(min(2 + attempt, 8))
            continue
        key_idx += 1

    raise RuntimeError(last_err)


def _visual_prompt(req: GenerateReq, repair_log: str = "", previous_code: str = "") -> str:
    repair_block = ""
    if repair_log:
        repair_block = (
            "Previous TikZ failed. Fix it using this compile log: "
            + repair_log[:1200]
            + "\nPrevious TikZ:\n"
            + previous_code[:2500]
        )

    return f"""
You create compact TikZ textbook diagrams for Course Planner.

Return only JSON with:
  "tikz": a TikZ snippet or full tikzpicture environment
  "caption": one short sentence

Rules:
- Make a real diagram, not a formula poster. Use drawing primitives: axes, curves, arrows, shaded regions, points, vectors, trees, geometry, or relationships.
- Do not use standalone equation text as the visual. If an equation matters, use it only as a tiny label.
- Keep labels very short: 1 to 3 words, variables, or symbols. Avoid full sentences in nodes.
- Use safe TikZ/PGFPlots only. No documentclass, packages, begin document, external files, markdown fences, shell commands, or custom macros.
- Keep the drawing within a roughly 6 by 4 coordinate area so it fits slides and guides.
- Prefer the built-in styles when useful: cp axis, cp line, cp dashed, cp fill, cp point, cp label.
- If the request is not visual, return an empty tikz string and a brief caption.

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
