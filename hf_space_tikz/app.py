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
RENDER_TIMEOUT = int(os.environ.get("RENDER_TIMEOUT", "60"))
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
\usepgfplotslibrary{{statistics}}
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


# Curated example library, adapted from open sources (Active Calculus LaTeX source,
# tkz-euclide manual constructions translated to plain TikZ, Underleaf PGFPlots
# tutorials, TikZ.net Gaussian article) plus the original in-house patterns.
# Each entry: (section title, trigger keywords, compile-ready snippet). The prompt
# builder injects ONLY the sections whose keywords match the request, so adding
# examples here does not bloat unrelated prompts.
TIKZ_EXAMPLE_SECTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("CALCULUS / GRAPHING",
     ("graph", "tangent", "secant", "derivative", "integral", "curve", "slope",
      "quadratic", "parabola", "polynomial", "rate of change", "area under", "optimization"),
     r"""
\begin{tikzpicture}
\begin{axis}[xmin=-1,xmax=4,ymin=-1,ymax=6,axis lines=middle,xlabel={$x$},ylabel={$y$},
  grid=both,grid style={draw=gray!20},width=7cm,height=4.5cm,clip=false]
  \addplot[domain=-.5:3.4,samples=90,cp line] {0.45*(x-1)^2+1};
  \addplot[domain=.1:3.1,cp dashed] {0.9*x};
  \fill (axis cs:1,1) circle (1.6pt) node[below left] {$(a,f(a))$};
  \node[anchor=west] at (axis cs:2.4,2.2) {tangent};
\end{axis}
\end{tikzpicture}
"""),
    ("FUNCTION FAMILIES (ADVANCED FUNCTIONS)",
     ("exponential", "logarithm", "log(", "ln(", "sinusoidal", "periodic", "asymptote",
      "transformation", "radian", "function", "cubic", "reciprocal", "rational"),
     r"""
\begin{tikzpicture}
\begin{axis}[width=7.2cm,height=5cm,axis lines=middle,xlabel={$x$},ylabel={$y$},
  xmin=-3.4,xmax=3.6,ymin=-3.5,ymax=5.5,restrict y to domain=-3.5:5.5,samples=120,
  grid=both,grid style={draw=gray!15}]
  \addplot[cp line,domain=-2.2:2.2] {x^2} node[pos=.95,right] {\small $y=x^2$};
  \addplot[cp dashed,domain=-3.2:3.2] {sin(deg(x))} node[pos=.04,below] {\small $y=\sin x$};
  \addplot[cp line,densely dotted,domain=-3.2:1.6] {exp(x)} node[pos=.99,left] {\small $y=e^x$};
  \addplot[cp dashed,domain=0.08:3.2] {ln(x)} node[pos=.9,below] {\small $y=\ln x$};
\end{axis}
\end{tikzpicture}
Note: trig graphs of a real variable need deg(): sin(deg(x)). Avoid x=0 for ln and
division; restrict each curve's domain so it stays inside the axis window.
"""),
    ("VECTORS (2D)",
     ("vector", "resultant", "magnitude", "dot product", "unit vector", "parallelogram",
      "force", "velocity", "displacement", "component"),
     r"""
\begin{tikzpicture}[scale=.8]
  \coordinate (O) at (0,0); \coordinate (A) at (3,0); \coordinate (B) at (4.3,1.8);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {$\vec u$};
  \draw[cp line,-Stealth] (A)--(B) node[midway,right] {$\vec v$};
  \draw[cp dashed,-Stealth] (O)--(B) node[midway,above left] {$\vec u+\vec v$};
  \fill (O) circle (1.4pt) (A) circle (1.4pt) (B) circle (1.4pt);
\end{tikzpicture}

Parallelogram with both diagonals labelled:
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

Magnitude min/max, two separated rows:
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
"""),
    ("VECTORS & GEOMETRY (3D)",
     ("3d", "three-dimensional", "cross product", "triple product", "parallelepiped",
      "torque", "projection", "skew", "octant", "xyz"),
     r"""
Triangle PQR in 3D with edge vectors (area via cross product), Active Calculus style:
\begin{tikzpicture}[scale=.9]
  \draw[cp axis,-Stealth] (0,0,0) -- (2.6,0,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,0,0) -- (0,2.4,0) node[above] {$y$};
  \draw[cp axis,-Stealth] (0,0,0) -- (0,0,2.6) node[below left] {$z$};
  \coordinate (P) at (0.4,-0.7,0.2);
  \coordinate (Q) at (0.7,1.8,0.3);
  \coordinate (R) at (1.9,0.8,-0.5);
  \draw[cp line,-Stealth] (P) -- (Q) node[pos=.55,left] {$\vec v$};
  \draw[cp line,-Stealth] (P) -- (R) node[pos=.6,below] {$\vec w$};
  \draw[cp line] (Q) -- (R);
  \fill (P) circle (1.3pt) node[below] {$P$};
  \fill (Q) circle (1.3pt) node[above] {$Q$};
  \fill (R) circle (1.3pt) node[right] {$R$};
\end{tikzpicture}

Parallelepiped spanned by u, v, w (volume via scalar triple product):
\begin{tikzpicture}[scale=.85]
  \coordinate (O) at (0,0,0);
  \coordinate (U) at (0.5,1.5,1);
  \coordinate (V) at (1.9,0.6,-0.4);
  \coordinate (W) at (0.5,-1,0.6);
  \coordinate (UV) at ($(U)+(V)$); \coordinate (UW) at ($(U)+(W)$);
  \coordinate (VW) at ($(V)+(W)$); \coordinate (UVW) at ($(U)+(V)+(W)$);
  \draw[cp line,-Stealth] (O)--(U) node[pos=.6,left] {$\vec u$};
  \draw[cp line,-Stealth] (O)--(V) node[pos=.7,above] {$\vec v$};
  \draw[cp line,-Stealth] (O)--(W) node[pos=.7,below left] {$\vec w$};
  \draw[cp line] (U)--(UV)--(UVW)--(UW)--cycle;
  \draw[cp line] (V)--(UV) (W)--(UW);
  \draw[cp dashed] (V)--(VW)--(W) (VW)--(UVW);
\end{tikzpicture}
In 3D write coordinates as (x,y,z); node at (x,y,z) works directly.
"""),
    ("TRIANGLES & TRIG LAWS",
     ("triangle", "sine law", "cosine law", "law of sines", "law of cosines",
      "trigonometry", "angle", "obtuse", "acute", "ambiguous case"),
     r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4.4,0); \coordinate (C) at (1.2,2.2);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \node[below left] at (A) {$A$}; \node[below right] at (B) {$B$}; \node[above] at (C) {$C$};
  \node[below] at ($(A)!0.5!(B)$) {$c$};
  \node[left] at ($(A)!0.5!(C)$) {$b$};
  \node[right] at ($(B)!0.5!(C)$) {$a$};
  \pic[draw=black,angle radius=5mm,"$A$",angle eccentricity=1.35] {angle=B--A--C};
  \pic[draw=black,angle radius=5mm,"$C$",angle eccentricity=1.35] {angle=A--C--B};
\end{tikzpicture}
With this counter-clockwise A,B,C layout, interior angle pics are:
at A use {angle=B--A--C}; at B use {angle=C--B--A}; at C use {angle=A--C--B}.

Sides with given values:
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4.2,0); \coordinate (C) at (1.4,2.5);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \node[below left] at (A) {$A$}; \node[below right] at (B) {$B$}; \node[above] at (C) {$C$};
  \node[below] at ($(A)!0.5!(B)$) {$b=10$};
  \node[right] at ($(B)!0.5!(C)$) {$a=7$};
  \pic[draw=black,angle radius=6mm,"$45^\circ$",angle eccentricity=1.35] {angle=B--A--C};
  \pic[draw=black,angle radius=5mm,"$60^\circ$",angle eccentricity=1.35] {angle=A--C--B};
\end{tikzpicture}
"""),
    ("RIGHT TRIANGLES & CONSTRUCTIONS",
     ("right triangle", "right-angled", "pythagorean", "hypotenuse", "perpendicular",
      "altitude", "bisector", "midpoint", "construction", "elevation", "depression",
      "isosceles", "equilateral", "median"),
     r"""
Right triangle with a proper right-angle mark (tkz-euclide style, plain TikZ):
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4,0); \coordinate (C) at (0,3);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \pic[draw=black] {right angle=B--A--C};
  \node[below] at ($(A)!0.5!(B)$) {$c$};
  \node[left] at ($(A)!0.5!(C)$) {$b$};
  \node[above right] at ($(B)!0.5!(C)$) {$a$};
  \node[below left] at (A) {$A$}; \node[below right] at (B) {$B$}; \node[above] at (C) {$C$};
\end{tikzpicture}

Isosceles construction: altitude, right-angle mark, equal base angles:
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4,0); \coordinate (C) at (2,2.6); \coordinate (M) at (2,0);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \draw[cp dashed] (C)--(M) node[pos=.5,right] {$h$};
  \pic[draw=black] {right angle=B--M--C};
  \pic[draw=black,angle radius=5mm,"$\alpha$",angle eccentricity=1.4] {angle=B--A--C};
  \pic[draw=black,angle radius=5mm,"$\alpha$",angle eccentricity=1.4] {angle=C--B--A};
\end{tikzpicture}
"""),
    ("BEARINGS / NAVIGATION",
     ("bearing", "navigation", "heading", "compass", "north", "due east", "due west"),
     r"""
\begin{tikzpicture}[scale=.85]
  \coordinate (O) at (0,0);
  \draw[cp axis,-Stealth] (O)--(0,2.5) node[above] {$N$};
  \draw[cp axis,-Stealth] (O)--(2.4,0) node[right] {$E$};
  \draw[cp line,-Stealth] (O)--(55:2.6) node[above right] {$P_1$};
  \draw[cp line,-Stealth] (O)--(15:2.9) node[right] {$P_2$};
  \draw[cp dashed] (90:.55) arc[start angle=90,end angle=55,radius=.55];
  \draw[cp dashed] (90:.85) arc[start angle=90,end angle=15,radius=.85];
  \node at (73:.75) {$30^\circ$};
  \node at (48:1.05) {$75^\circ$};
\end{tikzpicture}
"""),
    ("3D LINES AND PLANES",
     ("plane", "intersection", "normal vector", "scalar equation", "cartesian equation",
      "parametric", "distance from a point"),
     r"""
\begin{tikzpicture}[scale=.85]
  \coordinate (O) at (0,0); \coordinate (X) at (3.0,-.3); \coordinate (Y) at (0,2.4); \coordinate (Z) at (-1.7,-1.2);
  \draw[cp axis,-Stealth] (O)--(X) node[right] {$x$};
  \draw[cp axis,-Stealth] (O)--(Y) node[above] {$y$};
  \draw[cp axis,-Stealth] (O)--(Z) node[left] {$z$};
  \fill[cp fill] (-.7,-.45)--(2.3,-.72)--(3.05,.35)--(.1,.62)--cycle;
  \draw[cp line] (-.7,-.45)--(2.3,-.72)--(3.05,.35)--(.1,.62)--cycle;
  \draw[cp line,-Stealth] (.3,-.85)--(1.9,1.65) node[above] {$L$};
  \node[below right] at (1.4,-.35) {$\Pi$};
\end{tikzpicture}
"""),
    ("UNIT CIRCLE",
     ("unit circle", "terminal arm", "radian", "special angle", "cast rule", "reference angle"),
     r"""
\begin{tikzpicture}[scale=1]
  \draw[cp axis] (-1.3,0)--(1.5,0) node[right] {$x$};
  \draw[cp axis] (0,-1.3)--(0,1.5) node[above] {$y$};
  \draw[cp line] (0,0) circle (1);
  \draw[cp dashed] (0,0)--(45:1) node[midway,above left] {$r$};
  \draw[cp dashed] (45:1)--({sqrt(2)/2},0) node[below] {$\cos\theta$};
  \node[right] at (45:1) {$(\cos\theta,\sin\theta)$};
\end{tikzpicture}
"""),
    ("DATA MANAGEMENT: HISTOGRAM",
     ("histogram", "frequency", "bins", "class interval", "tally", "data set"),
     r"""
\begin{tikzpicture}
\begin{axis}[width=7.2cm,height=4.6cm,ybar interval,xlabel={Value},ylabel={Frequency},
  ymin=0,xtick=data]
\addplot[hist={bins=8,data min=0,data max=80},fill=gray!25,draw=black]
  table[row sep=\\,y index=0] {
    data\\ 12\\ 18\\ 22\\ 25\\ 31\\ 34\\ 35\\ 41\\ 44\\ 47\\ 52\\ 55\\ 58\\ 63\\ 71\\ 76\\
  };
\end{axis}
\end{tikzpicture}
hist= needs table[row sep=\\ ,y index=0] with a "data\\" header row; the statistics
pgfplots library is preloaded.
"""),
    ("DATA MANAGEMENT: BOX PLOT",
     ("box plot", "boxplot", "box-and-whisker", "quartile", "median", "whisker",
      "interquartile", "iqr", "five-number"),
     r"""
\begin{tikzpicture}
\begin{axis}[width=7.2cm,height=3.2cm,boxplot/draw direction=x,xlabel={Mark},
  ytick={1},yticklabels={Scores}]
\addplot[boxplot prepared={median=72,lower quartile=64,upper quartile=81,
  lower whisker=48,upper whisker=95},fill=gray!20,draw=black] coordinates {};
\end{axis}
\end{tikzpicture}
Give the five summary values with boxplot prepared; list outliers (if any) as
coordinates {(0,103) (0,110)}.
"""),
    ("STATISTICS: NORMAL DISTRIBUTION",
     ("normal distribution", "gaussian", "bell curve", "standard deviation", "z-score",
      "probability density", "confidence", "normally distributed"),
     r"""
\begin{tikzpicture}[declare function={gauss(\x,\m,\s)=1/(\s*sqrt(2*pi))*exp(-((\x-\m)^2)/(2*\s^2));}]
\begin{axis}[width=7.2cm,height=4.2cm,axis lines=middle,xlabel={$x$},ylabel={density},
  xmin=-4,xmax=4,ymin=0,ymax=0.45,samples=120,ytick=\empty,xtick={-2,-1,0,1,2}]
  \addplot[cp fill,draw=none,domain=-1:1] {gauss(x,0,1)} \closedcycle;
  \addplot[cp line,domain=-4:4] {gauss(x,0,1)};
  \node at (axis cs:0,0.13) {\small $68\%$};
  \node[anchor=west] at (axis cs:1.6,0.34) {\small $\mu=0,\ \sigma=1$};
\end{axis}
\end{tikzpicture}
Define helper functions ONLY with declare function={...} inside the tikzpicture or
axis options; anything placed outside the tikzpicture environment is stripped.
"""),
)

# Sections injected when nothing matches the request text (general STEM default).
DEFAULT_EXAMPLE_SECTIONS = ("CALCULUS / GRAPHING", "VECTORS (2D)", "TRIANGLES & TRIG LAWS")
MAX_EXAMPLE_SECTIONS = 6


def _example_blocks(req: GenerateReq) -> str:
    """Pick only the example sections relevant to this request.

    Keyword-routing keeps the prompt compact and makes each example salient: a
    histogram question sees histogram patterns, not bearings. Falls back to a
    general trio when nothing matches.
    """
    text = _request_text(req).lower()
    picked = [(name, block) for name, keys, block in TIKZ_EXAMPLE_SECTIONS
              if any(k in text for k in keys)]
    if not picked:
        wanted = set(DEFAULT_EXAMPLE_SECTIONS)
        picked = [(name, block) for name, _keys, block in TIKZ_EXAMPLE_SECTIONS if name in wanted]
    picked = picked[:MAX_EXAMPLE_SECTIONS]
    parts = ["Use these compact patterns as quality targets. Adapt coordinates, labels, and values to the user's problem."]
    for name, block in picked:
        parts.append(name + ":\n" + block.strip())
    return "\n\n".join(parts)


def _request_text(req: GenerateReq) -> str:
    text = " ".join([req.subject or "", req.title or "", req.equation or "", req.brief or ""])
    text = re.sub(r"\\text\s*\{\s*([^{}]+?)\s*\}", r" \1 ", text)
    text = text.replace("\\triangle", " triangle ")
    text = text.replace("\\angle", " angle ")
    text = text.replace("^\\circ", " degrees")
    text = text.replace("°", " degrees")
    # Drop inline/display math delimiters so extractors see "bearing of 040", "p = 8m",
    # etc. as plain tokens instead of "bearing of \(040" where a \( blocks the match.
    text = re.sub(r"\\[()\[\]]", " ", text)
    text = text.replace("$", " ")
    return re.sub(r"\s+", " ", text).strip()


def _tex_label(value: str, default: str = "") -> str:
    value = re.sub(r"\s+", " ", str(value or default)).strip()
    value = value.strip("$")
    value = re.sub(r"\\text\s*\{\s*([^{}]+?)\s*\}", r" \1", value)
    value = value.replace(" degrees", "^\\circ").replace(" degree", "^\\circ")
    value = value.replace("°", "^\\circ")
    value = re.sub(r"[^A-Za-z0-9_+\-*/=.,:()\\\\^{}\\s/]", "", value).strip()
    return value or default


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("__" + key + "__", value)
    return template


def _triangle_vertices(text: str) -> tuple[str, str, str] | None:
    m = re.search(r"(?:triangle|tri\.?)\s*([A-Z])\s*([A-Z])\s*([A-Z])\b", text)
    if m:
        return (m.group(1), m.group(2), m.group(3))
    m = re.search(r"\b([A-Z]{3})\b", text)
    if m and re.search(r"\b(?:triangle|law of sines|law of cosines|angle|side)\b", text, re.I):
        return tuple(m.group(1))  # type: ignore[return-value]
    # Infer from the letters naming the sides/angles: sides p,q,r with angles P,R imply
    # a triangle PQR. Vertex X is conventionally opposite side x, so uppercasing the side
    # letters gives the vertex set. Only trust this when it resolves to exactly 3 letters.
    letters: set[str] = set()
    for a in re.findall(r"\bangle\s+([A-Z])\b", text):
        letters.add(a.upper())
    for s in re.findall(r"\b([a-z])\s*(?:=|is|measures)\s*[-+]?\d", text):
        letters.add(s.upper())
    for s in re.findall(r"\bsides?\s+([a-z])\b", text):
        letters.add(s.upper())
    if len(letters) == 3:
        return tuple(sorted(letters))  # type: ignore[return-value]
    return None


def _number_with_unit_re() -> str:
    return r"[-+]?\d+(?:\.\d+)?(?:\s*(?:cm|mm|m|km|in|ft|yd|mi|units?|N|newtons?|m/s|km/h|mph))?"


def _extract_triangle_angles(text: str, vertices: tuple[str, str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    num = _number_with_unit_re()
    for label, value in re.findall(r"\bangle\s*([A-Z])\s*(?:=|is|measures)?\s*(" + num + r")\s*(?:degrees?)?", text, re.I):
        lab = label.upper()
        if lab in vertices:
            out[lab] = _tex_label(value + "^\\circ" if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value.strip()) else value)
    return out


def _extract_triangle_sides(text: str, vertices: tuple[str, str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    num = _number_with_unit_re()
    for label, value in re.findall(r"\b(?:side|length)?\s*([a-z]|[A-Z]{2})\s*(?:=|is|measures|has length)?\s*(" + num + r")", text):
        out[label] = _tex_label(value)
    for label, value in re.findall(r"\b([a-z]|[A-Z]{2})\s*=\s*(" + num + r")", text):
        out.setdefault(label, _tex_label(value))
    a, b, c = vertices
    defaults = {
        (b + c): out.get(a.lower(), a.lower()),
        (a + c): out.get(b.lower(), b.lower()),
        (a + b): out.get(c.lower(), c.lower()),
    }
    edge_labels = {
        a + b: out.get(a + b) or out.get(b + a) or defaults[a + b],
        a + c: out.get(a + c) or out.get(c + a) or defaults[a + c],
        b + c: out.get(b + c) or out.get(c + b) or defaults[b + c],
    }
    return edge_labels


def _has_triangle_measure(text: str) -> bool:
    num = _number_with_unit_re()
    return bool(
        re.search(r"\bangle\s+[A-Z]\s*(?:=|is|measures)?\s*" + num, text, re.I)
        or re.search(r"\b(?:side|length)?\s*(?:[a-z]|[A-Z]{2})\s*(?:=|is|measures|has length)\s*" + num, text)
        or re.search(r"\b(?:distance|height|length)\s+(?:of|is|=|measures)?\s*" + num, text, re.I)
    )


def _looks_like_triangle(text: str) -> bool:
    low = text.lower()
    if re.search(
        r"\b(triangle|law of sines|law of cosines|cosine law|sine law|"
        r"angle of elevation|angle of depression|line of sight)\b",
        low,
    ):
        return True
    # "angle CAB", "angle PQR" — a 3-letter vertex-named angle always implies a triangle.
    if re.search(r"\bangle\s+[A-Z]{3}\b", text):
        return True
    # Two or more distinct single-letter named angles (e.g. "angle A ... angle B") plus a
    # "distance across"/side reference is the classic solve-the-triangle setup.
    named_angles = {a.upper() for a in re.findall(r"\bangle\s+([A-Z])\b", text)}
    if len(named_angles) >= 2:
        return True
    if "distance across" in low and named_angles:
        return True
    return False


def _triangle_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if not generic and not _looks_like_triangle(text):
        return None
    vertices = _triangle_vertices(text)
    if not vertices:
        if not re.search(r"\b(angle of elevation|angle of depression|line of sight)\b", low) or not _has_triangle_measure(text):
            return None
        vertices = ("A", "B", "C")
    a, b, c = vertices
    side = _extract_triangle_sides(text, vertices)
    angles = _extract_triangle_angles(text, vertices)
    angle_lines = []
    # The fixed skeleton A=(0,0), B=(4.2,0), C=(1.35,2.35) is counter-clockwise oriented,
    # and TikZ's \pic{angle=P1--V--P2} sweeps CCW from ray V→P1 to ray V→P2. Each entry
    # below is ordered so that CCW sweep covers the INTERIOR angle at that vertex. Vertex B
    # (bottom-right) must be C--B--A, not A--B--C, or the arc wraps around the outside as an
    # exterior angle (~320° instead of the interior ~40°).
    angle_specs = {
        a: ("B", "A", "C", "0.72,0.24"),
        b: ("C", "B", "A", "3.42,0.26"),
        c: ("A", "C", "B", "1.45,1.86"),
    }
    for vertex, value in angles.items():
        p1, mid, p2, _ = angle_specs[vertex]
        angle_lines.append(
            f'  \\pic[draw=black,angle radius=5mm,"${_tex_label(value)}$",angle eccentricity=1.35] {{angle={p1}--{mid}--{p2}}};'
        )
    requested_angles = {x.upper() for x in re.findall(r"\bangle\s+([A-Z])\b", text)}
    if not angle_lines and requested_angles:
        vertex = next((x for x in (a, b, c) if x in requested_angles), None)
        if vertex:
            p1, mid, p2, _ = angle_specs[vertex]
            angle_lines.append(
                f'  \\pic[draw=black,angle radius=5mm,"${vertex}$",angle eccentricity=1.35] {{angle={p1}--{mid}--{p2}}};'
            )
    if not angle_lines and re.search(r"\b(angle of elevation|angle of depression)\b", low):
        vertex = c if "law of cosines" in low or "cosine law" in low else a
        p1, mid, p2, _ = angle_specs[vertex]
        angle_lines.append(
            f'  \\pic[draw=black,angle radius=5mm,"${vertex}$",angle eccentricity=1.35] {{angle={p1}--{mid}--{p2}}};'
        )
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4.2,0); \coordinate (C) at (1.35,2.35);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \node[below left] at (A) {$__A__$};
  \node[below right] at (B) {$__B__$};
  \node[above] at (C) {$__C__$};
  \node[below] at ($(A)!0.5!(B)$) {$__AB__$};
  \node[left] at ($(A)!0.5!(C)$) {$__AC__$};
  \node[right] at ($(B)!0.5!(C)$) {$__BC__$};
__ANGLES__
\end{tikzpicture}
""".strip(),
        A=a,
        B=b,
        C=c,
        AB=_tex_label(side.get(a + b, c.lower())),
        AC=_tex_label(side.get(a + c, b.lower())),
        BC=_tex_label(side.get(b + c, a.lower())),
        ANGLES="\n".join(angle_lines),
    )
    return tikz, "Triangle diagram with interior angle and side labels."


def _format_vector_name(base: str, subscript: str = "") -> str:
    base = re.sub(r"[^A-Za-z]", "", base or "u")[:1] or "u"
    if subscript:
        return f"\\vec{{{base}}}_{{{_tex_label(subscript)}}}"
    return f"\\vec{{{base}}}"


def _extract_vector_names(text: str) -> tuple[str, str, str]:
    found: list[str] = []
    for base, sub in re.findall(r"\\vec\s*\{?\s*([A-Za-z])\s*\}?\s*(?:_\s*\{?\s*([A-Za-z0-9]+)\s*\}?)?", text):
        found.append(_format_vector_name(base, sub))
    for base, sub in re.findall(r"\b(?:vector|force|velocity|displacement)\s+([A-Za-z])(?![A-Za-z])\s*(?:_\s*\{?\s*([A-Za-z0-9]+)\s*\}?)?", text, re.I):
        found.append(_format_vector_name(base, sub))
    unique: list[str] = []
    for item in found:
        if item not in unique:
            unique.append(item)
    low = text.lower()
    if len(unique) < 2 and re.search(r"\b(two forces?|force vectors?)\b", low):
        unique = (unique + [r"\vec{F}_{1}", r"\vec{F}_{2}"])[:2]
    if len(unique) < 2 and re.search(r"\b(two velocities|velocity vectors?)\b", low):
        unique = (unique + [r"\vec{v}_{1}", r"\vec{v}_{2}"])[:2]
    if len(unique) < 2 and re.search(r"\b(displacement vectors?|two displacements?)\b", low):
        unique = (unique + [r"\vec{d}_{1}", r"\vec{d}_{2}"])[:2]
    if len(unique) < 2:
        unique = (unique + [r"\vec{u}", r"\vec{v}"])[:2]
    result = r"\vec{R}" if re.search(r"\bresultant\b", low) else unique[0] + "+" + unique[1]
    return unique[0], unique[1], result


def _extract_vector_magnitudes(text: str) -> list[str]:
    num = _number_with_unit_re()
    values: list[str] = []
    patterns = [
        r"\bmagnitude\s+of\s+[^,.;]{0,50}?\s+(?:is|=)\s*(" + num + r")",
        r"\bmagnitudes?\s+(?:are|of)?\s*(" + num + r")\s*(?:and|,)\s*(" + num + r")",
    ]
    for pat in patterns:
        for match in re.findall(pat, text, re.I):
            if isinstance(match, tuple):
                values.extend(_tex_label(part) for part in match if part)
            else:
                values.append(_tex_label(match))
    return values[:2]


def _bearing_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if not generic and not re.search(r"\b(bearing|navigation|north|east|compass|heading)\b", low):
        return None
    bearings = [int(float(x)) % 360 for x in re.findall(r"\b(?:bearing|heading)\s*(?:of|=|is)?\s*([0-9]{1,3})(?:\s*degrees?)?", low)]
    if not bearings:
        bearings = [int(float(x)) % 360 for x in re.findall(r"\b([0-9]{2,3})\s*(?:degrees?|°)\s*(?:bearing|from north|clockwise)", low)]
    bearings = bearings[:2] or [45, 115]
    # Distances must carry a length unit — otherwise the bare 2-3 digit bearing values
    # (e.g. "040", "110") get mistaken for leg lengths and labelled onto the vectors.
    distances = re.findall(
        r"([-+]?\d+(?:\.\d+)?\s*(?:km|cm|mm|nautical miles?|nmi|nm|mi|miles?|m|ft|yd))\b",
        text,
        re.IGNORECASE,
    )
    distances = [re.sub(r"\s+", "", d.strip()) for d in distances][:2]
    b1 = bearings[0]
    b2 = bearings[1] if len(bearings) > 1 else min(165, b1 + 55)
    a1 = 90 - b1
    a2 = 90 - b2
    label1 = _tex_label(distances[0] if distances else f"{b1}^\\circ")
    label2 = _tex_label(distances[1] if len(distances) > 1 else f"{b2}^\\circ")
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.85]
  \coordinate (O) at (0,0);
  \coordinate (P) at (__A1__:2.45);
  \coordinate (Q) at ($(P)+(__A2__:2.1)$);
  \draw[cp axis,-Stealth] (O)--(0,2.4) node[above] {$N$};
  \draw[cp axis,-Stealth] (O)--(2.3,0) node[right] {$E$};
  \draw[cp line,-Stealth] (O)--(P) node[midway,above right] {$__L1__$};
  \draw[cp line,-Stealth] (P)--(Q) node[midway,above] {$__L2__$};
  \draw[cp dashed] (O)--(Q) node[midway,below] {$d$};
  \draw[cp dashed] (90:.62) arc[start angle=90,end angle=__A1__,radius=.62];
  \node at (__M1__:.88) {$__B1__^\circ$};
  \draw[cp dashed] ($(P)+(0,.58)$) arc[start angle=90,end angle=__A2__,radius=.58];
  \node at ($(P)+(__M2__:.84)$) {$__B2__^\circ$};
  \fill (O) circle (1.3pt) node[below left] {$A$};
  \fill (P) circle (1.3pt) node[above left] {$B$};
  \fill (Q) circle (1.3pt) node[right] {$C$};
\end{tikzpicture}
""".strip(),
        A1=str(a1),
        A2=str(a2),
        M1=str((90 + a1) / 2),
        M2=str((90 + a2) / 2),
        B1=str(b1),
        B2=str(b2),
        L1=label1,
        L2=label2,
    )
    return tikz, "Bearing diagram with north reference rays and travel vectors."


def _vector_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if not generic and not re.search(r"\b(vector|resultant|parallelogram|force|velocity|displacement)\b", low):
        return None
    # A linear-algebra transformation question ("maps the unit square to a parallelogram,
    # find the 2x2 matrix") trips the "parallelogram" trigger but is not vector addition.
    # If it reads as matrix/transformation work and carries no genuine vector cue, defer to
    # Gemini rather than drawing a vector parallelogram.
    if not generic and re.search(r"\b(matrix|matrices|determinant|linear transformation|transformation matrix|unit square|eigen\w*)\b", low) \
            and not re.search(r"\b(vector|vectors|resultant|force|velocity|displacement|magnitude|head[- ]to[- ]tail)\b", low):
        return None
    angle_match = (
        re.search(r"\b([0-9]{1,3})(?:\s*degrees?)?\s*(?:between|angle)", low)
        or re.search(r"\bangle\s+between\b[^.。;:\n]{0,80}?\b(?:is|=|of)?\s*([0-9]{1,3})(?:\s*degrees?)?", low)
        or re.search(r"\bangle\s*(?:is|=)?\s*([0-9]{1,3})", low)
    )
    angle = int(angle_match.group(1)) if angle_match else 55
    u, v, result = _extract_vector_names(text)
    magnitudes = _extract_vector_magnitudes(text)
    u_label = u + (r"\,=" + magnitudes[0] if magnitudes else "")
    v_label = v + (r"\,=" + magnitudes[1] if len(magnitudes) > 1 else "")
    if "parallelogram" in low or "resultant" in low or "sum" in low:
        tikz = _fill(
            r"""
\begin{tikzpicture}[scale=.82]
  \coordinate (O) at (0,0); \coordinate (A) at (3.2,0); \coordinate (B) at (__ANGLE__:2.2); \coordinate (C) at ($(A)+(B)$);
  \draw[cp dashed] (A)--(C)--(B);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {$__U_LABEL__$};
  \draw[cp line,-Stealth] (O)--(B) node[midway,left] {$__V_LABEL__$};
  \draw[cp line,-Stealth] (O)--(C) node[pos=.58,above] {$__R_LABEL__$};
  \pic[draw=black,angle radius=5mm,"$__ANGLE__^\circ$",angle eccentricity=1.35] {angle=A--O--B};
  \fill (O) circle (1.3pt);
\end{tikzpicture}
""".strip(),
            U_LABEL=u_label,
            V_LABEL=v_label,
            R_LABEL=result,
            ANGLE=str(angle),
        )
        return tikz, "Vector resultant shown with a parallelogram construction."
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (O) at (0,0); \coordinate (A) at (3.2,0); \coordinate (B) at (__ANGLE__:3.0);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {$__U_LABEL__$};
  \draw[cp line,-Stealth] (O)--(B) node[midway,above left] {$__V_LABEL__$};
  \pic[draw=black,angle radius=5mm,"$__ANGLE__^\circ$",angle eccentricity=1.35] {angle=A--O--B};
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        U_LABEL=u_label,
        V_LABEL=v_label,
        ANGLE=str(angle),
    )
    return tikz, "Vector angle diagram with both vectors from a shared tail."


# Statistics triggers as named constants so the entry gate and the per-diagram branch
# checks below can't drift apart. Deliberately excludes bare "median" (a triangle median)
# and "skew" (skew lines) — a box plot needs quartile/whisker/IQR context — and "gaussian"
# only when it is not "gaussian elimination" (linear algebra).
_STATS_NORMAL_RE = re.compile(
    r"\b(normal distribution|normally distributed|bell curve|standard deviation|"
    r"z-score|empirical rule|68-95-99\.?7)\b|\bgaussian\b(?!\s+elimination)"
)
_STATS_BOXPLOT_RE = re.compile(
    r"\b(box[- ]?(?:and[- ]?)?whisker|box plot|boxplot|quartile|interquartile|"
    r"iqr|five-number)\b"
)


def _statistics_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if not generic and not (
        re.search(r"\b(histogram|frequency distribution|skewness)\b", low)
        or _STATS_NORMAL_RE.search(low)
        or _STATS_BOXPLOT_RE.search(low)
    ):
        return None
    if _STATS_NORMAL_RE.search(low):
        return r"""
\begin{tikzpicture}[declare function={gauss(\x,\m,\s)=1/(\s*sqrt(2*pi))*exp(-((\x-\m)^2)/(2*\s^2));}]
\begin{axis}[width=6.4cm,height=3.5cm,axis lines=middle,xlabel={$x$},ylabel={density},
  xmin=-3.6,xmax=3.6,ymin=0,ymax=0.45,samples=120,ytick=\empty,
  xtick={-2,-1,0,1,2},xticklabels={$-2\sigma$,$-\sigma$,$\mu$,$\sigma$,$2\sigma$}]
  \addplot[cp fill,draw=none,domain=-1:1] {gauss(x,0,1)} \closedcycle;
  \addplot[cp line,domain=-3.5:3.5] {gauss(x,0,1)};
  \node at (axis cs:0,0.13) {\small $68\%$};
\end{axis}
\end{tikzpicture}
""".strip(), "Normal distribution curve with the central one-standard-deviation region shaded."
    if _STATS_BOXPLOT_RE.search(low):
        return r"""
\begin{tikzpicture}
\begin{axis}[width=6.4cm,height=2.8cm,boxplot/draw direction=x,
  xmin=0,xmax=100,ytick={1},yticklabels={data},xlabel={Value}]
  \addplot[boxplot prepared={median=55,lower quartile=35,upper quartile=75,
    lower whisker=15,upper whisker=95},draw=black,fill=gray!20] coordinates {};
  \node[anchor=south] at (axis cs:35,1.23) {\small $Q_1$};
  \node[anchor=south] at (axis cs:55,1.23) {\small median};
  \node[anchor=south] at (axis cs:75,1.23) {\small $Q_3$};
\end{axis}
\end{tikzpicture}
""".strip(), "Box-and-whisker plot with quartiles and median marked."
    return r"""
\begin{tikzpicture}
\begin{axis}[width=6.4cm,height=3.5cm,ybar,bar width=9pt,ymin=0,ymax=6,
  xtick={1,2,3,4,5},xticklabels={0--2,3--5,6--8,9--11,12+},
  x tick label style={font=\scriptsize},xlabel={Class interval},ylabel={Frequency}]
  \addplot[fill=gray!25,draw=black] coordinates {(1,2) (2,5) (3,4) (4,3) (5,2)};
\end{axis}
\end{tikzpicture}
""".strip(), "Histogram sketch showing class intervals and frequencies."


def _geometry_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    # Require an actual shape this template can draw. Bare "area"/"volume"/"geometry" matched
    # non-geometry questions ("area of the transformed shape" in a matrix problem) and forced
    # a rectangle. Shapes with no skeleton here (cone/sphere/prism) are left to Gemini instead
    # of being mis-drawn as a rectangle.
    if not generic and not re.search(r"\b(rectangle|circle|circumference|cylinder)\b", low):
        return None
    if "cylinder" in low:
        return r"""
\begin{tikzpicture}[scale=.85]
  \draw[cp line] (0,0) ellipse (1.25 and .35);
  \draw[cp line] (-1.25,0)--(-1.25,2.4) (1.25,0)--(1.25,2.4);
  \draw[cp line] (0,2.4) ellipse (1.25 and .35);
  \draw[cp dashed] (0,2.4)--(1.25,2.4) node[midway,above] {$r$};
  \draw[cp dashed,<->] (1.65,0)--(1.65,2.4) node[midway,right] {$h$};
\end{tikzpicture}
""".strip(), "Cylinder sketch with radius and height labels."
    if "circle" in low or "circumference" in low:
        return r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (O) at (0,0);
  \draw[cp line] (O) circle (1.45);
  \draw[cp line] (O)--(35:1.45) node[midway,above] {$r$};
  \draw[cp dashed] (-1.45,0)--(1.45,0) node[midway,below] {$d$};
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(), "Circle sketch with radius and diameter."
    return r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (3.8,0); \coordinate (C) at (3.8,2.1); \coordinate (D) at (0,2.1);
  \draw[cp line] (A)--(B)--(C)--(D)--cycle;
  \node[below] at ($(A)!0.5!(B)$) {$l$};
  \node[right] at ($(B)!0.5!(C)$) {$w$};
  \draw[cp dashed] (A)--(C) node[midway,above left] {$d$};
\end{tikzpicture}
""".strip(), "Rectangle sketch with length, width, and diagonal."


def _deterministic_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    # Each template function owns its own trigger detection (returns None when it does
    # not apply), so a bearing/vector/circle question is never force-fitted to a triangle.
    ordered = (_statistics_template, _bearing_template, _vector_template, _triangle_template, _geometry_template)
    for fn in ordered:
        hit = fn(req, generic=False)
        if hit:
            return hit
    # Generic last resort (used when Gemini is unavailable): produce the best-guess
    # shape so the question still gets *a* diagram rather than nothing.
    if generic:
        for fn in ordered:
            hit = fn(req, generic=True)
            if hit:
                return hit
    return None


def _render_template(req: GenerateReq, hit: tuple[str, str], check_semantics: bool = True) -> dict:
    tikz, caption = hit
    # Template callers pass check_semantics=True so slot-filled skeletons are
    # audited for topic relevance before rendering.
    semantic_issue = _semantic_visual_issue(req, tikz) if check_semantics else None
    rendered = (
        {"ok": False, "error": semantic_issue, "log": semantic_issue}
        if semantic_issue
        else _render(RenderReq(code=tikz, format=req.format, theme=req.theme, target=req.target))
    )
    if rendered.get("ok"):
        rendered["tikz"] = tikz
        rendered["caption"] = caption
    return rendered


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
- Keep triangle angle marks small and inside the shape. For triangle angle marks, use \\pic[draw=black,...] {{angle=side--vertex--side}}; do not hand-draw them with \\draw ... arc. Exterior angle arcs are allowed only for questions that explicitly say exterior angle.
- For law of sines/cosines questions, include the given side lengths and angle values in the triangle when the question provides them.
- Match the triangle's named vertices exactly. If the question says triangle PQR, label the vertices P, Q, and R only; do not switch to A, B, C. If the question asks for angle R, place the angle mark at vertex R and label it R or the given degree measure.
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
- Never draw or preserve a triangle as a generic placeholder. Use a triangle only for explicit triangle, law-of-sines/cosines, named side/angle, elevation/depression, bearing, or triangle-method vector problems. If the rough TikZ idea is a triangle but the question is calculus, statistics, matrix algebra, or another non-triangle topic, discard it.
- For vectors, use clear head-to-tail or parallelogram construction. Put arrowheads on every vector and avoid ambiguous floating labels.
- For vector angle-between questions, draw both vectors from the same tail and mark the smaller interior sector between them. Use a small angle radius around 4mm to 6mm; never draw a loop around the outside of the vector tail.
- For vector min/max questions, use two separated horizontal rows: "same" and "opposite". Put case words at the far left, never above the arrows, and keep result labels below dashed resultants.
- For parallelogram diagonal questions, place labels outside the crossing: label AC as u+v above the solid/dashed diagonal and BD as v-u or u-v below/left of the other diagonal. Never stack multiple formulas at the center.
- Avoid long phrase labels such as "Maximum Resultant" inside small diagrams; use short labels and let the worksheet question carry the wording.
- Before returning, mentally inspect the diagram: no label may sit on a line crossing, arrowhead, point marker, or another label. Move it with above/below/left/right/pos/anchor if needed.
- For geometry, trigonometry, law of sines, and law of cosines, use named points, interior angle marks, and side labels. Avoid decorative shapes without mathematical meaning.
- Preserve the problem's exact vertex labels. Do not use generic A/B/C labels for a triangle named PQR, XYZ, or any other label set. If the question states angle R, the angle marker must be at vertex R, not at a generic C vertex.
- For any triangle angle mark, use TikZ angle pics, not raw arc paths: \\pic[draw=black,angle radius=5mm,"$60^\\circ$",angle eccentricity=1.35] {{angle=B--A--C}};. The vertex is the middle coordinate, so angle=B--A--C marks the angle at A. Never use \\draw (...) arc (...) for triangle angles, because it often creates exterior-looking arcs. Never draw exterior-looking angle arcs unless the question explicitly asks for an exterior angle.
- Put triangle angle labels inside the measured angle, close to the vertex, with a small radius around 4mm to 6mm. If the angle is at C, use angle=A--C--B; if it is at B, use angle=A--B--C; if it is at A, use angle=B--A--C.
- For bearing or navigation questions, draw short N/E reference rays and put clockwise bearing arcs inside the sector from North to the travel vector. Avoid large empty compass circles.
- For parallelogram, diagonal, and vector-geometry questions, show the named diagonal or resultant, not just the outline. Put side/angle labels outside strokes and keep the interior crossing uncluttered.
- For 3D geometry, planes, spheres, skew lines, projections, normals, and line-plane questions, use a sparse isometric sketch with x/y/z axes when helpful, one gray plane if needed, and labels outside intersections. Do not use red or blue labels unless color is explicitly requested.
- Mark right angles with \\pic[draw=black] {{right angle=B--A--C}}; (vertex in the middle), never with a hand-drawn small square.
- Define helper functions ONLY with declare function={{...}} inside the tikzpicture or axis options. Never place \\pgfmathdeclarefunction or any command outside the tikzpicture environment - it will be stripped and the compile will fail.
- The pgfplots statistics library is preloaded. For histograms use \\addplot[hist={{bins=...,data min=...,data max=...}}] table[row sep=\\\\,y index=0] {{...}} with a "data\\\\" header row inside a ybar interval axis. For box plots use boxplot prepared={{median=...,lower quartile=...,upper quartile=...,lower whisker=...,upper whisker=...}} with boxplot/draw direction set on the axis.
- In 3D, write coordinates as (x,y,z) and place labels with node at (x,y,z); calc expressions like ($(U)+(V)$) work for vertex sums.
- For plots of trig functions of a real variable use sin(deg(x)); restrict domains so ln, division, and exponentials stay inside the axis window.
- If an existing rough TikZ idea is colored, cluttered, formula-only, missing the requested visual element, or has exterior-looking angle arcs, replace it with a clean diagram instead of preserving it.
- If the request is not visual, return an empty tikz string and a brief caption.

{target_rules}

Reference patterns:
{_example_blocks(req)}

Subject: {req.subject[:160]}
Title: {req.title[:240]}
Equation, if any: {req.equation[:500]}
Visual brief: {req.brief[:1800]}
Target: {req.target}

{repair_block}
""".strip()


def _semantic_visual_issue(req: GenerateReq, tikz: str) -> str | None:
    hay = " ".join([req.subject, req.title, req.equation, req.brief]).lower()
    original = " ".join([req.subject, req.title, req.equation, req.brief])
    is_triangle = (
        _looks_like_triangle(original)
        or any(term in hay for term in ("triangle", "law of sines", "law of cosines"))
        or bool(re.search(r"\b(?:side|angle)\s+[abc]\b", hay))
    )
    cycle_draws = re.findall(r"\\draw[^\n;]*--\s*cycle\s*;", tikz)
    has_plain_triangle_cycle = any(
        len(re.findall(r"\([A-Za-z]\)", draw)) == 3
        for draw in cycle_draws
    )
    has_triangle_angle_pic = bool(re.search(r"\\pic\s*\[[^\]]*\]\s*\{angle=[A-Za-z]--[A-Za-z]--[A-Za-z]\}", tikz))
    has_vector_arrows = bool(re.search(r"(?:-|=)\s*Stealth|->|<-", tikz))
    has_axes_or_plot = "\\begin{axis}" in tikz or re.search(r"\baxis\s+lines\b|\\addplot|\\draw[^\n;]*(?:->|-Stealth)[^\n;]*node[^\n;]*\{\$x\$\}", tikz)
    if (
        not is_triangle
        and has_plain_triangle_cycle
        and (has_triangle_angle_pic or not has_vector_arrows)
        and not has_axes_or_plot
    ):
        return (
            "The request is not a triangle problem, so do not draw or preserve a generic triangle. "
            "Use the relevant visual type for the topic, or return an empty tikz string if no safe visual applies."
        )
    if is_triangle and "exterior angle" not in hay and re.search(r"\barc\s*(?:\[|\()", tikz):
        return (
            "Triangle and law-of-sines/cosines visuals must mark angles with TikZ angle pics, "
            "not raw arc paths. Raw arcs often render as exterior angle marks. Use examples like "
            "\\pic[draw=black,angle radius=5mm,\"$60^\\circ$\",angle eccentricity=1.35] {angle=B--A--C};"
        )
    is_vector_angle = (
        ("angle" in hay)
        and any(term in hay for term in ("vector", "force", "resultant"))
        and not any(term in hay for term in ("bearing", "navigation", "compass"))
    )
    if is_vector_angle and re.search(r"\barc\s*(?:\[|\()", tikz):
        return (
            "Vector angle diagrams must mark the small interior angle sector between vectors from a shared tail. "
            "Do not use raw arc paths that can wrap outside the vector diagram."
        )
    if is_triangle:
        for radius in re.findall(r"angle\s+radius\s*=\s*([0-9.]+)\s*(cm|mm)?", tikz, flags=re.IGNORECASE):
            value = float(radius[0])
            unit = (radius[1] or "cm").lower()
            radius_mm = value * 10 if unit == "cm" else value
            if radius_mm > 7:
                return "Triangle angle marks are too large. Use small interior angle pics with angle radius between 4mm and 6mm."
    if is_vector_angle:
        for radius in re.findall(r"angle\s+radius\s*=\s*([0-9.]+)\s*(cm|mm)?", tikz, flags=re.IGNORECASE):
            value = float(radius[0])
            unit = (radius[1] or "cm").lower()
            radius_mm = value * 10 if unit == "cm" else value
            if radius_mm > 7:
                return "Vector angle marks are too large. Use a small interior sector with angle radius between 4mm and 6mm."

    if is_triangle:
        requested_labels: set[str] = set()
        for match in re.findall(r"(?:triangle|\\triangle)\s*([A-Z]{3})", original, flags=re.IGNORECASE):
            requested_labels.update(match.upper())
        for match in re.findall(r"\b([A-Z])([A-Z])([A-Z])\b", original):
            triplet = "".join(match)
            if any(word in hay for word in ("side", "angle", "triangle", "law of")):
                requested_labels.update(triplet)
        if requested_labels:
            drawn_labels = set(re.findall(r"\{\s*\$?([A-Z])\$?\s*\}", tikz))
            stray = sorted(label for label in drawn_labels if label in {"A", "B", "C", "P", "Q", "R", "X", "Y", "Z"} and label not in requested_labels)
            missing = sorted(label for label in requested_labels if label not in drawn_labels)
            if stray or missing:
                return (
                    "Triangle labels must match the problem exactly. "
                    f"Use only requested labels {''.join(sorted(requested_labels))}; "
                    f"missing={''.join(missing) or 'none'}, stray={''.join(stray) or 'none'}."
                )

        requested_angles = set(re.findall(r"(?:∠|\\angle\s*)\s*([A-Z])", original))
        if requested_angles:
            pic_labels = set(re.findall(r"\\pic\s*\[[^\]]*\"\$?([A-Z])\$?\"", tikz))
            wrong_angles = sorted(label for label in pic_labels if label in {"A", "B", "C", "P", "Q", "R", "X", "Y", "Z"} and label not in requested_angles and requested_labels and label in requested_labels)
            if wrong_angles:
                return (
                    "Triangle angle labels must match the angle named in the question. "
                    f"Requested angle label(s): {''.join(sorted(requested_angles))}; wrong interior label(s): {''.join(wrong_angles)}."
                )
    return None


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


def _deterministic_fallback(req: GenerateReq) -> dict | None:
    """Render a KEYWORD-MATCHED deterministic diagram when Gemini is unavailable.

    IMPORTANT: this must NOT force a generic triangle. A question with no matching
    shape (a quadratic, an algebra proof, a "state the property" question) should
    get NO visual rather than an irrelevant triangle repeated across the worksheet.
    So we only fall back to a template whose own trigger actually matches the
    request; if nothing matches, we return None and the question stays blank.
    """
    fallback = _deterministic_template(req, generic=False)
    if not fallback:
        return None
    rendered = _render_template(req, fallback, check_semantics=True)
    if rendered.get("ok"):
        rendered["fallback"] = "deterministic"
        return rendered
    return None


@app.post("/generate")
def generate(req: GenerateReq):
    try:
        # 1) Trust a matching deterministic template and render it directly. This keeps
        #    common triangle/bearing/vector/geometry questions off the Gemini path
        #    entirely, so a Gemini "high demand" outage can't starve them of visuals.
        template_hit = _deterministic_template(req)
        if template_hit:
            rendered = _render_template(req, template_hit, check_semantics=True)
            if rendered.get("ok"):
                return JSONResponse(rendered, status_code=200)

        # 2) Otherwise ask Gemini for bespoke TikZ. Any Gemini failure (exhausted
        #    retries during a 503 storm, network timeout) is caught so we can still
        #    fall back to a deterministic diagram instead of returning a bare 500.
        rendered: dict = {"ok": False, "error": "No diagram was produced."}
        tikz = ""
        caption = ""
        try:
            spec = _gemini(_visual_prompt(req), as_json=True, temperature=0.25)
            tikz = _strip_fence(str(spec.get("tikz", "")))
            caption = str(spec.get("caption", "")).strip()
            if tikz:
                semantic_issue = _semantic_visual_issue(req, tikz)
                rendered = (
                    {"ok": False, "error": semantic_issue, "log": semantic_issue}
                    if semantic_issue
                    else _render(RenderReq(code=tikz, format=req.format, theme=req.theme, target=req.target))
                )
                if not rendered.get("ok"):
                    repaired = _gemini(
                        _visual_prompt(req, repair_log=rendered.get("log") or rendered.get("error") or "", previous_code=tikz),
                        as_json=True,
                        temperature=0.15,
                    )
                    tikz = _strip_fence(str(repaired.get("tikz", tikz)))
                    caption = str(repaired.get("caption", caption)).strip()
                    semantic_issue = _semantic_visual_issue(req, tikz)
                    rendered = (
                        {"ok": False, "error": semantic_issue, "log": semantic_issue}
                        if semantic_issue
                        else _render(RenderReq(code=tikz, format=req.format, theme=req.theme, target=req.target))
                    )
        except Exception as gem_exc:
            rendered = {"ok": False, "error": f"Gemini unavailable: {str(gem_exc)[:200]}"}
            print(f"[generate] Gemini path failed, trying deterministic fallback: {str(gem_exc)[:180]}", flush=True)

        if rendered.get("ok"):
            rendered["tikz"] = tikz
            rendered["caption"] = caption
            return JSONResponse(rendered, status_code=200)

        # 3) Last resort: a deterministic diagram so the question is not left blank.
        fallback_rendered = _deterministic_fallback(req)
        if fallback_rendered:
            return JSONResponse(fallback_rendered, status_code=200)

        rendered["tikz"] = tikz
        rendered["caption"] = caption
        return JSONResponse(rendered, status_code=400)
    except Exception as exc:
        # Even an unexpected error shouldn't leave a visual-worthy question blank.
        try:
            fallback_rendered = _deterministic_fallback(req)
            if fallback_rendered:
                return JSONResponse(fallback_rendered, status_code=200)
        except Exception:
            pass
        return JSONResponse({"ok": False, "error": str(exc)[:500]}, status_code=500)


def _warm_latex_caches() -> None:
    """Compile one tiny diagram at startup so pdflatex builds its font caches.

    The first pdflatex run on a fresh replica can take minutes while TeX font
    caches are generated. Without this warm-up, the first real render after a
    redeploy exceeds RENDER_TIMEOUT, the deterministic-template path "fails",
    /generate falls through to the much slower Gemini loop, and the frontend
    gives up — worksheets ship with no visuals at all.
    """
    code = r"\begin{tikzpicture}\draw[cp line] (0,0)--(1,0);\node at (0.5,0.4) {$x^{2}\;\theta$};\end{tikzpicture}"
    stats_code = (
        r"\begin{tikzpicture}\begin{axis}[width=5cm,height=3cm,boxplot/draw direction=x]"
        r"\addplot[boxplot prepared={median=5,lower quartile=3,upper quartile=7,"
        r"lower whisker=1,upper whisker=9},draw=black] coordinates {};\end{axis}\end{tikzpicture}"
    )
    for label, snippet in (("LaTeX cache", code), ("pgfplots statistics", stats_code)):
        try:
            out = _render(RenderReq(code=snippet, format="svg", theme="mono", target="generic"))
            print(f"[warmup] {label} warm-up ok={out.get('ok')} err={str(out.get('error') or '')[:120]}", flush=True)
        except Exception as exc:
            print(f"[warmup] {label} warm-up failed: {exc}", flush=True)


threading.Thread(target=_warm_latex_caches, daemon=True).start()
