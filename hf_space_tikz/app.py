"""
Course Planner - TikZ static visual renderer (Hugging Face Docker Space).

Exposes:
  GET  /health  -> {"status": "ok", ...}
  POST /render  -> render a constrained TikZ snippet to SVG or PNG
  POST /generate -> start an async diagram job and return {"job_id": "..."}
  GET  /status/{job_id} -> poll for the generated SVG/PNG or an error

This service is intentionally separate from the Manim video renderer. It exists
to turn Gemini-generated TikZ code into textbook-style static visuals for
slides, worksheets, study guides, and all-in-one study sets.
"""

import base64
import html
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Literal

import requests
from fastapi import FastAPI
try:
    from fastapi import BackgroundTasks
except ImportError:  # test harness stubs only FastAPI
    class BackgroundTasks:
        def add_task(self, *args, **kwargs):
            return None
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    if __package__:
        from . import templates as tcatalog
    else:
        import templates as tcatalog
except Exception as _cat_exc:  # keep /render and /health alive even if catalog breaks
    tcatalog = None
    print(f"[catalog] engine import failed, catalog path disabled: {_cat_exc}", flush=True)

try:
    if __package__:
        from .catalog.elementary import generate as elementary_diagram
    else:
        from catalog.elementary import generate as elementary_diagram
except ImportError:
    elementary_diagram = None

_job_trace = threading.local()


def _diagnostic(stage: str, detail: str = "", **metadata) -> None:
    """Per-job, bounded diagnostics: no prompts, API keys, or cross-job model guesses."""
    events = getattr(_job_trace, "events", None)
    if events is None:
        return
    for key in GEMINI_KEYS:
        detail = detail.replace(key, "[redacted]")
    # A LaTeX log tail opens with package-loading noise; keep its "!" error
    # lines, which the first 500 characters never reached.
    error_at = detail.find("\n!")
    if len(detail) > 500 and error_at != -1:
        detail = detail[error_at + 1:]
    if "tikz" in metadata:
        metadata["tikz"] = _tikz_excerpt(metadata["tikz"], events)
        if not metadata["tikz"]:
            del metadata["tikz"]
    events.append({"stage": stage, "detail": detail[:500], **metadata})
    # Model retries used to push the routing decision and the reason a path
    # gave up out of the window; drop the oldest retry chatter first.
    while len(events) > 24:
        chatter = next((e for e in events if e["stage"].startswith("model-")), None)
        events.remove(chatter if chatter is not None else events[0])


_TIKZ_EXCERPT_CHARS = 2400      # per event: head and tail of the picture
_TIKZ_EXCERPT_BUDGET = 6000     # per job, across all events


def _tikz_excerpt(code: str, events: list) -> str:
    """The drawing code behind a failed or colliding attempt, so a compile error
    or a label collision can be reproduced from the job trace alone. Whitespace
    and comments are dropped; long code keeps its head and tail (a compile error at
    \\end{tikzpicture} can come from either); one job keeps at most the budget."""
    # TeX comments go first: a model's "let's recompute" notes pushed the cut
    # into the middle of its drawing code.
    lines = (re.sub(r"(?<!\\)%.*", "", line) for line in str(code or "").splitlines())
    code = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in lines if line.strip())
    for key in GEMINI_KEYS:
        code = code.replace(key, "[redacted]")
    if len(code) > _TIKZ_EXCERPT_CHARS:
        head = _TIKZ_EXCERPT_CHARS * 2 // 3
        code = code[:head] + "\n[...]\n" + code[-(_TIKZ_EXCERPT_CHARS - head):]
    room = _TIKZ_EXCERPT_BUDGET - sum(len(e.get("tikz", "")) for e in events)
    return code if len(code) <= room else ""


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
# Longest a single call may sit waiting for a cooling lane; the frontend gives
# each visual about five minutes in total.
GEMINI_MAX_WAIT = int(os.environ.get("GEMINI_MAX_WAIT", "60"))
# Every free-tier text model. Free daily quota is per project AND per model, so
# each is a separate allowance. Best Flash models first (small daily quota),
# then the Flash-Lite models (much larger quota), then the 2.5 models, which
# are announced to shut down in October 2026 (their lanes then 404 and rest for
# an hour), and last the hosted Gemma 4 models.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview,"
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash,gemini-2.5-flash-lite,"
        "gemma-4-31b-it,gemma-4-26b-a4b-it",
    ).split(",")
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
_last_success_model = None
_last_success_model_lock = threading.Lock()

jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "3600"))
TEMPLATE_REPAIR_ATTEMPTS = int(os.environ.get("TEMPLATE_REPAIR_ATTEMPTS", "3"))
# Render-based layout check: labels crossed by lines or overlapping each other,
# read from the compiled picture (the readiness verifier only sees TikZ source).
# Set TIKZ_LAYOUT_CHECK=0 to turn it off.
LAYOUT_CHECK_ENABLED = os.environ.get("TIKZ_LAYOUT_CHECK", "1").strip().lower() not in ("0", "false", "no", "off")

# Constrained catalog path (parallel rollout). Tried first; on no-match or render
# failure it falls through to the legacy pipeline, so enabling it can only improve
# on current behavior. Set TIKZ_USE_CATALOG=0 to force the legacy path only.
CATALOG_AVAILABLE = tcatalog is not None
CATALOG_ENABLED = CATALOG_AVAILABLE and os.environ.get(
    "TIKZ_USE_CATALOG", "1"
).strip().lower() not in ("0", "false", "no", "off")
# Template fit-check: the param-fill call also shows the model the template's
# caption+skeleton and asks it to VETO a wrong diagram family ('_fit': 'no'),
# in which case generation falls through to the reference-guided bespoke path
# (templates as guides). Set TIKZ_TEMPLATE_FIT_CHECK=0 to trust keyword routing
# unconditionally, as before.
FIT_CHECK_ENABLED = os.environ.get(
    "TIKZ_TEMPLATE_FIT_CHECK", "1"
).strip().lower() not in ("0", "false", "no", "off")
# CUTOVER (2026-07-08): the legacy regex-template layer (_deterministic_template,
# _topic_blueprint_hit, _structured_vector_direct_hit, _deterministic_fallback) is
# OFF by default. It keyword-matched with no fit-check and no readiness gate, and
# kept intercepting questions before the two-pass bespoke path could draw them
# correctly (e.g. every 3D cross-product question got the old single-vector or
# 2D-resultant diagram). Flow is now: catalog exact fit (model-vetoed) -> two-pass
# reference-guided bespoke -> blank. Set TIKZ_LEGACY_TEMPLATES=1 to re-enable the
# old layer as an intermediate fallback.
LEGACY_TEMPLATES_ENABLED = os.environ.get(
    "TIKZ_LEGACY_TEMPLATES", "0"
).strip().lower() in ("1", "true", "yes", "on")


class RenderReq(BaseModel):
    code: str = Field(..., description="TikZ snippet or full tikzpicture environment")
    format: Literal["svg", "png"] = "svg"
    theme: Literal["green", "mono"] = "green"
    target: Literal["slide", "worksheet", "guide", "flashcard", "generic"] = "generic"
    layout: bool = Field(False, description="Also report label collisions found in the rendered picture")
    preview: bool = Field(False, description="Also return a small PNG of the picture (preview_png, base64)")


class GenerateReq(BaseModel):
    title: str = ""
    brief: str = Field(..., description="Plain-language description of the visual to create")
    subject: str = "General"
    equation: str = ""
    format: Literal["svg", "png"] = "svg"
    theme: Literal["green", "mono"] = "green"
    target: Literal["slide", "worksheet", "guide", "flashcard", "generic"] = "generic"


# Gemini traffic is scheduled over lanes: one (key slot, model) pair each. A
# free-tier failure belongs to a lane, a key, or a model, so each cools down at
# its own level instead of one global block that, after a single 503, shut a
# model off for every key for 15 minutes:
#   - 429 quota is per key (Google project) and model: that lane cools for the
#     retryDelay Google returns, or an hour for a per-day quota;
#   - a 503 "high demand" is Google capacity for the model on every key: the
#     model cools briefly, 30 s doubling while it keeps failing, at most 5 min;
#   - a rejected key (403, invalid key) cools every lane on that key.
# Ready lanes are ranked by model preference, then by the fewest requests in
# the last minute, so parallel jobs spread over the keys. When no lane is ready
# the call waits for the soonest one rather than spending attempts on lanes
# already known to fail.
def _new_lane_state() -> dict:
    return {
        "lock": threading.Lock(),
        "lane_until": {},     # (key_idx, model) -> cooldown end
        "key_until": {},      # key_idx -> cooldown end
        "model_until": {},    # model -> cooldown end
        "model_streak": {},   # model -> consecutive capacity failures
        "recent": {},         # (key_idx, model) -> request start times, last 60 s
        "last": {},           # (key_idx, model) -> last outcome, for /health
    }


_lane_state = _new_lane_state()


def _lane_wait(key_idx: int, model: str, now: float) -> float:
    """Seconds until a lane may be used (0 = ready). Caller holds the lock."""
    until = max(
        _lane_state["lane_until"].get((key_idx, model), 0),
        _lane_state["key_until"].get(key_idx, 0),
        _lane_state["model_until"].get(model, 0),
    )
    return max(0.0, until - now)


def _pick_lane() -> tuple[int, str, float]:
    """Best lane as (key_idx, model, wait); a ready lane is reserved (wait 0)."""
    now = time.time()
    with _lane_state["lock"]:
        ranked = []
        for model_rank, model in enumerate(GEMINI_MODELS):
            for key_idx in range(len(GEMINI_KEYS)):
                lane = (key_idx, model)
                recent = [t for t in _lane_state["recent"].get(lane, []) if now - t < 60]
                _lane_state["recent"][lane] = recent
                wait = _lane_wait(key_idx, model, now)
                last_used = recent[-1] if recent else 0
                if wait:
                    ranked.append(((1, wait, model_rank, len(recent)), key_idx, model, wait))
                else:
                    ranked.append(((0, model_rank, len(recent), last_used), key_idx, model, 0.0))
        _rank, key_idx, model, wait = min(ranked)
        if not wait:
            _lane_state["recent"][(key_idx, model)].append(now)
        return key_idx, model, wait


def _cool_lane(key_idx: int, model: str, seconds: float, outcome: str) -> None:
    with _lane_state["lock"]:
        _lane_state["lane_until"][(key_idx, model)] = time.time() + seconds
        _lane_state["last"][(key_idx, model)] = outcome


def _cool_key(key_idx: int, seconds: float, outcome: str) -> None:
    with _lane_state["lock"]:
        _lane_state["key_until"][key_idx] = time.time() + seconds
        for model in GEMINI_MODELS:
            _lane_state["last"][(key_idx, model)] = outcome


def _cool_model(model: str, seconds: float | None, outcome: str, key_idx: int) -> float:
    """Cool a model on every key; None means the capacity back-off schedule."""
    with _lane_state["lock"]:
        if seconds is None:
            streak = _lane_state["model_streak"].get(model, 0) + 1
            _lane_state["model_streak"][model] = streak
            seconds = min(300, 30 * 2 ** (streak - 1))
        _lane_state["model_until"][model] = time.time() + seconds
        _lane_state["last"][(key_idx, model)] = outcome
        return seconds


def _lane_succeeded(key_idx: int, model: str) -> None:
    with _lane_state["lock"]:
        _lane_state["model_streak"][model] = 0
        _lane_state["last"][(key_idx, model)] = "ok"


def _quota_cooldown(res) -> tuple[float, bool]:
    """(seconds, per_day) for a 429, from Google's RetryInfo / QuotaFailure."""
    try:
        details = res.json().get("error", {}).get("details", []) or []
    except (ValueError, AttributeError):
        details = []
    delay, per_day = 0.0, "perday" in res.text.lower().replace(" ", "").replace("_", "")
    for item in details if isinstance(details, list) else []:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", str(item.get("retryDelay", "")))
        if match:
            delay = float(match.group(1))
        for violation in item.get("violations", []) or []:
            if "perday" in str(violation.get("quotaId", "")).lower():
                per_day = True
    if per_day:
        return 3600.0, True
    return (max(delay, 5.0) if delay else 60.0), False


def _available_models() -> list[str]:
    """Models with at least one ready lane, in preference order."""
    now = time.time()
    with _lane_state["lock"]:
        return [m for m in GEMINI_MODELS
                if any(not _lane_wait(k, m, now) for k in range(len(GEMINI_KEYS)))]


def _lane_report() -> list[dict]:
    """Per-lane readiness for /health; never includes key material."""
    now = time.time()
    with _lane_state["lock"]:
        return [
            {
                "key_slot": key_idx + 1,
                "model": model,
                "ready_in_s": round(_lane_wait(key_idx, model, now)),
                "requests_last_min": len([t for t in _lane_state["recent"].get((key_idx, model), []) if now - t < 60]),
                "last_outcome": _lane_state["last"].get((key_idx, model), ""),
            }
            for key_idx in range(len(GEMINI_KEYS))
            for model in GEMINI_MODELS
        ]


def _probe_model_access() -> list[dict]:
    out = []
    for key_idx, key in enumerate(GEMINI_KEYS):
        row = {"key_slot": key_idx + 1, "models": []}
        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            with _lane_state["lock"]:
                cooling = _lane_wait(key_idx, model, time.time()) > 0
            try:
                res = requests.get(url, headers={"x-goog-api-key": key}, timeout=(8, 20))
                row["models"].append({
                    "model": model,
                    "ok": res.status_code == 200,
                    "status": res.status_code,
                    "blocked_temporarily": cooling,
                })
            except requests.exceptions.RequestException as exc:
                row["models"].append({
                    "model": model,
                    "ok": False,
                    "status": "network",
                    "error": str(exc)[:120],
                    "blocked_temporarily": cooling,
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

    # One shared baseline scale keeps every generator's diagrams the same size
    # (the worksheet blueprint used to render larger at 1.12; it was a touch too big,
    # so the whole system now sits at 1.0). Flashcards render a little smaller so a
    # diagram fits inside the card. Nudge these if the global size needs tuning.
    scale = {
        "slide": "1.0",
        "worksheet": "1.0",
        "guide": "1.0",
        "flashcard": "0.82",
        "generic": "1.0",
    }.get(target, "1.0")
    # Worksheets always print on a white A4 sheet, so tick labels can knock out
    # a curve or asymptote passing through them (centred axes put the numbers
    # right where graphs cross). Other targets may sit on tinted backgrounds.
    # Worksheet tick labels carry a white knockout, and are drawn above the plots
    # (pgfplots' standard layers put them under "main", so curves crossed them
    # anyway).
    tick_labels = (
        r"\pgfplotsset{every tick label/.append style={fill=white,inner sep=1pt},"
        r"layers/cp worksheet/.define layer set={axis background,axis grid,axis ticks,axis lines,"
        r"pre main,main,axis tick labels,axis descriptions,axis foreground}{/pgfplots/layers/standard},"
        r"set layers=cp worksheet}"
        if target == "worksheet" else ""
    )

    return rf"""
\documentclass[tikz,border=6pt]{{standalone}}
\usepackage{{amsmath,amssymb}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.18}}
{tick_labels}
\usepgfplotslibrary{{statistics,fillbetween}}
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
% \cpanglelabel{{vertex}}{{direction}}{{mark radius}}{{half gap}}{{text}}: an angle label
% on its direction, out past its mark by its own measured extent that way and
% far enough to clear both sides of the gap by its extent across each (a fixed
% distance let wide labels' corners reach back over the mark). Sizes are in
% picture units: the label's pt over one unit's canvas length, measured
% without inner sep, as the layout check measures text. The label's
% inner and outer radius along its direction are left in \cplabelin and
% \cplabelout, for an arc drawn later to pass clear of it.
\newcommand{{\cpanglelabel}}[5]{{%
  \node[cp label,overlay,opacity=0,inner sep=0pt] (cpmL) at (0,0) {{#5}};
  \path let \p2=($(cpmL.north east)-(cpmL.south west)$), \p9=($(1,0)-(0,0)$),
    \n1={{(0.5*scalar(\x2)*abs(cos(#2))+0.5*scalar(\y2)*abs(sin(#2)))/scalar(\x9)}},
    \n2={{max(0.5*scalar(\x2)*abs(sin(#2+#4))+0.5*scalar(\y2)*abs(cos(#2+#4)),
             0.5*scalar(\x2)*abs(sin(#2-#4))+0.5*scalar(\y2)*abs(cos(#2-#4)))/scalar(\x9)}},
    \n3={{max(#3+\n1+0.06,(\n2+0.06)/sin(max(2,#4)))}} in
    node[cp label] at ($(#1)+({{#2}}:{{\n3}})$) {{#5}} \pgfextra{{\xdef\cplabelin{{\n3-\n1}}\xdef\cplabelout{{\n3+\n1}}}};}}
% \cpsidelabel[margin]{{P}}{{Q}}{{R}}{{fraction}}{{text}}: a label beside segment PQ at the
% fraction, on the side away from point R, out by its measured extent across
% the segment plus the margin (in picture units). An anchor on the label's
% border let a wide label's corner cross its own line.
\newcommand{{\cpsidelabel}}[6][0.06]{{%
  \node[cp label,overlay,opacity=0,inner sep=0pt] (cpmS) at (0,0) {{#6}};
  \path let \p1=($(#3)-(#2)$), \p3=($(#4)-(#2)$), \p2=($(cpmS.north east)-(cpmS.south west)$), \p9=($(1,0)-(0,0)$),
    \n1={{atan2(\y1,\x1)+ifthenelse(scalar(\x1)/100*scalar(\y3)-scalar(\y1)/100*scalar(\x3)>0,-90,90)}},
    \n2={{(0.5*scalar(\x2)*abs(cos(\n1))+0.5*scalar(\y2)*abs(sin(\n1)))/scalar(\x9)+#1}} in
    node[cp label] at ($(#2)!#5!(#3)+({{\n1}}:{{\n2}})$) {{#6}};}}
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
    # TeX wraps log lines at 79 characters; the layout records are longer.
    env["max_print_line"] = "100000"
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


# TeX commands whose first letter is a JSON escape. A model that writes "\tiny"
# unescaped in its JSON gets a TAB and "iny" back (tick labels read "iny6"),
# and "\node" becomes a newline and "ode".
_JSON_TEX_WORDS = {
    "t": {"tiny", "text", "textbf", "textit", "textrm", "texttt", "textsf", "textsc", "textup", "textnormal",
          "theta", "times", "tan", "tanh", "to", "top", "tau", "tfrac", "tilde", "triangle", "tikz", "tikzset",
          "therefore", "textwidth", "thinspace"},
    "n": {"node", "nabla", "neq", "not", "nu", "newline", "noindent", "normalsize", "nearrow", "neg", "nexists"},
    "r": {"right", "rightarrow", "rho", "rangle", "rbrace", "rceil", "rfloor", "rm", "rule", "raisebox"},
}


def _json_tex_escapes(text: str) -> str:
    """Restore the backslash of TeX commands a model left unescaped in JSON.
    \b (backspace) and \f (form feed) never occur in its output, so \beta,
    \frac or \foreach are always commands; \t, \n and \r are real tabs and
    line breaks unless the whole word is a known command. Only JSON text goes
    through here, before it is parsed."""
    def repair(m):
        lead, letter, rest = m.group(1), m.group(2), m.group(3)
        if letter in "bf" or letter + rest in _JSON_TEX_WORDS[letter]:
            return lead + "\\\\" + letter + rest
        return m.group(0)
    # an even run of backslashes before is escaped backslashes, not an escape
    text = re.sub(r"(?<!\\)((?:\\\\)*)\\([bfnrt])([A-Za-z]+)", repair, text)
    # an escape JSON does not define (\draw, \sqrt, \underline) failed the
    # whole response; it can only be a TeX command
    return re.sub(r'(?<!\\)((?:\\\\)*)\\(?=[^"\\/bfnrtu]|u(?![0-9a-fA-F]{4}))', r"\1\\\\", text)


def _is_gemma(model: str) -> bool:
    return model.startswith("gemma-")


def _gemini(prompt: str, as_json: bool = False, temperature: float = 0.25, images: list[str] | None = None):
    """images: base64 PNGs sent after the prompt to Gemini models. Gemma lanes get
    the prompt alone: image input on the hosted Gemma API is not established, and
    a refused Gemma request rests that model for an hour."""
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
    started = time.time()
    waited = 0.0
    sent = 0
    attempts = max(GEMINI_MAX_ATTEMPTS, len(GEMINI_KEYS) * len(GEMINI_MODELS))
    while sent < attempts:
        key_idx, model, wait = _pick_lane()
        remaining = GEMINI_DEADLINE - (time.time() - started)
        if wait:
            # Every lane is cooling: wait for the soonest one when the budget
            # allows, otherwise fail with the last real error.
            if wait >= remaining or waited + wait > GEMINI_MAX_WAIT:
                if sent == 0:
                    last_err = f"All Gemini keys and models are cooling down (next in {wait:.0f} s)."
                break
            _diagnostic("model-wait", f"{wait:.0f} s", model=model, key_slot=key_idx + 1)
            time.sleep(wait)
            waited += wait
            continue
        if remaining <= 0:
            break
        sent += 1
        key = GEMINI_KEYS[key_idx]
        _diagnostic("model-attempt", model=model, key_slot=key_idx + 1)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = body
        if images and not _is_gemma(model):
            payload = {**body, "contents": [{"parts": body["contents"][0]["parts"] + [
                {"inline_data": {"mime_type": "image/png", "data": image}} for image in images]}]}
        if _is_gemma(model) and "responseMimeType" in body["generationConfig"]:
            # Gemma's JSON-mode support is not established; the reply is parsed
            # from text below either way.
            payload = {**body, "generationConfig": {k: v for k, v in body["generationConfig"].items()
                                                    if k != "responseMimeType"}}
        try:
            res = requests.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
                timeout=GEMINI_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            last_err = f"Gemini network error: {str(exc)[:180]}"
            _diagnostic("model-network-error", last_err, model=model, key_slot=key_idx + 1, attempt=sent)
            print(f"[gemini] {last_err} - key slot {key_idx + 1}, {model}.", flush=True)
            _cool_lane(key_idx, model, 15, "network")
            continue

        low_body = res.text.lower()
        if res.status_code == 200:
            try:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                global _last_success_model
                with _last_success_model_lock:
                    _last_success_model = model
                _lane_succeeded(key_idx, model)
                _job_trace.last_model = model
                _job_trace.last_pictured = bool(images) and not _is_gemma(model)
                _diagnostic("model-success", model=model, key_slot=key_idx + 1)
                print(f"[gemini] success using model {model} on key slot {key_idx + 1}.", flush=True)
                if as_json:
                    return json.loads(_json_tex_escapes(_strip_fence(text)))
                return text
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_err = f"Gemini returned unusable output: {type(exc).__name__}"
                _diagnostic("model-unusable-output", last_err, model=model, key_slot=key_idx + 1)
                _cool_lane(key_idx, model, 5, "unusable output")
                continue

        last_err = f"Gemini API error {res.status_code}: {res.text[:220]}"
        _diagnostic("model-error", last_err, model=model, key_slot=key_idx + 1, http_status=res.status_code)
        status = res.status_code
        if status == 429:
            seconds, per_day = _quota_cooldown(res)
            _cool_lane(key_idx, model, seconds, "daily quota" if per_day else "minute quota")
        elif status == 503 and ("high demand" in low_body or "overloaded" in low_body or "capacity" in low_body):
            seconds = _cool_model(model, None, "high demand", key_idx)
            print(f"[gemini] {model} at capacity - resting it {seconds:.0f} s on every key.", flush=True)
        elif status == 404:
            _cool_model(model, 3600, "model not found", key_idx)
        elif status == 403 or (status == 400 and ("api key" in low_body or "api_key" in low_body)):
            _cool_key(key_idx, 3600, "key rejected")
        elif status == 400 and _is_gemma(model):
            # Gemma accepts fewer request options than Gemini; a refusal says
            # nothing about the Gemini lanes, so rest Gemma and carry on.
            _cool_model(model, 3600, "request refused", key_idx)
        elif status == 400:
            # The request itself was refused; every other lane would refuse it too.
            break
        else:
            _cool_lane(key_idx, model, 10, f"HTTP {status}")

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


def _repair_transport_escapes(text: str) -> str:
    r"""Repair LaTeX command names damaged by a layer interpreting \t, \f, etc."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("⟨", "<")
        .replace("⟩", ">")
        .replace("〈", "<")
        .replace("〉", ">")
    )
    text = re.sub(r"\b([A-Z])\s*([A-Z])\s*(?:→|⃗)", r"\\vec{\1\2}", text)
    text = re.sub(r"\b([A-Za-z])\s*(?:→|⃗)", r"\\vec{\1}", text)
    text = re.sub(r"\t\s*riangle\b", r"\\triangle", text)
    text = re.sub(r"\t\s*ext\s*\{", r"\\text{", text)
    text = re.sub(r"\t\s*ext(?=(?:less|greater|superscript|subscript|backslash|asciitilde|asciicircum)\b)", r"\\text", text)
    text = re.sub(r"\t\s*heta\b", r"\\theta", text)
    text = re.sub(r"\t\s*imes\b", r"\\times", text)
    text = re.sub(r"\t\s*an\b", r"\\tan", text)
    text = re.sub(r"\t\s*o\b", r"\\to", text)
    text = re.sub(r"\f\s*rac\b", r"\\frac", text)
    text = re.sub(r"\r\s*ight\b", r"\\right", text)
    text = re.sub(r"\n\s*abla\b", r"\\nabla", text)
    text = re.sub(
        r"(^|[\s([{])ext(?=(?:less|greater|superscript|subscript|backslash|asciitilde|asciicircum)\b)",
        r"\1\\text",
        text,
    )
    return text


def _raw_request_text(req: GenerateReq) -> str:
    return _repair_transport_escapes(" ".join([req.subject or "", req.title or "", req.equation or "", req.brief or ""]))


def _request_text(req: GenerateReq) -> str:
    text = _raw_request_text(req)
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


def _question_text(req: GenerateReq) -> str:
    """Same normalization as _request_text but from the QUESTION (title) only, never the
    worked answer/brief prose. Diagram TYPE must be decided from what the question asks —
    keying off the answer made near-identical questions diverge (a "calculate p-q" whose
    answer says "component-wise" drew a single-vector diagram; a "calculate 2u-3v" whose
    answer did not stayed blank). Keeps \\vec intact so a+b / p-q / 2u-3v are detectable.
    Falls back to the full request text when there is no title (non-worksheet callers)."""
    title = _repair_transport_escapes(req.title or "").strip()
    if not title:
        return _request_text(req)
    text = re.sub(r"\\text\s*\{\s*([^{}]+?)\s*\}", r" \1 ", title)
    text = text.replace("\\triangle", " triangle ").replace("\\angle", " angle ")
    text = text.replace("^\\circ", " degrees").replace("°", " degrees")
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
    m = re.search(r"(?:∠|\\angle\b|\bangle\s+|\?)([A-Z])\s*([A-Z])\s*([A-Z])\b", text)
    if m:
        return (m.group(1), m.group(2), m.group(3))
    m = re.search(r"\b([A-Z]{3})\b", text)
    if m and re.search(r"\b(?:triangle|law of sines|law of cosines|angle|side)\b", text, re.I):
        return tuple(m.group(1))  # type: ignore[return-value]
    # Infer from the letters naming the sides/angles: sides p,q,r with angles P,R imply
    # a triangle PQR. Vertex X is conventionally opposite side x, so uppercasing the side
    # letters gives the vertex set. Only trust this when it resolves to exactly 3 letters.
    letters: set[str] = set()
    for a in re.findall(r"(?:∠|\\angle\b|\bangle\s+|\?)([A-Z])\b", text):
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
    for name, value in re.findall(r"(?:∠|\\angle\b|\bangle\s+|\?)\s*([A-Z]{3})\s*(?:=|is|measures)?\s*(" + num + r")\s*(?:degrees?)?", text):
        lab = name[1].upper()
        if lab in vertices:
            out[lab] = _tex_label(value + "^\\circ" if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value.strip()) else value)
    for label, value in re.findall(r"(?:∠|\\angle\b|\bangle\s+|\?)\s*([A-Z])\s*(?:=|is|measures)?\s*(" + num + r")\s*(?:degrees?)?", text, re.I):
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
    # Side named by its endpoints in prose: "A and B are 120 m apart", "the distance
    # from A to B is 120 m" -> side AB. The compact loops above only catch "AB = 120",
    # so law-of-cosines lake/tower setups otherwise lose the given side to a bare letter.
    for x, y, value in re.findall(r"\b([A-Z])\s+and\s+([A-Z])\s+(?:are|is)\s+(" + num + r")\s*apart", text):
        out.setdefault(x + y, _tex_label(value))
    for x, y, value in re.findall(r"\bdistance\s+(?:from|between)\s+([A-Z])\s+(?:to|and)\s+([A-Z])\b[^0-9]*?(" + num + r")", text, re.I):
        out.setdefault(x + y, _tex_label(value))
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


def _numbers_stated(value: str, text: str) -> bool:
    """True when value has no number, or every number in it appears in text."""
    numbers = re.findall(r"\d+(?:\.\d+)?", str(value or ""))
    stated = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(text or ""))}
    return all(float(n) in stated for n in numbers)


def _first_number(value: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(m.group(0)) if m else None


def _solve_triangle(vertices: tuple[str, str, str], sides: dict[str, float], angles: dict[str, float]) -> dict[str, float] | None:
    """The three interior angles (degrees, keyed by vertex) from the givens, or
    None when they do not fix the shape. sides are keyed by their OPPOSITE
    vertex. Handles two angles, SSS, SAS and SSA (the acute case)."""
    vs = list(vertices)
    ang = {v: a for v, a in angles.items() if v in vs and 0 < a < 180}
    side = {v: x for v, x in sides.items() if v in vs and x and x > 0}
    if len(ang) >= 2:
        if len(ang) == 3:
            return ang if abs(sum(ang.values()) - 180) < 1 else None
        rest = 180 - sum(ang.values())
        missing = [v for v in vs if v not in ang]
        return {**ang, missing[0]: rest} if rest > 0 and len(missing) == 1 else None
    if len(side) == 2 and len(ang) == 1:
        (v, a), = ang.items()
        if v not in side:  # SAS: the angle between the two given sides
            (p, b), (q, c) = side.items()
            side[v] = math.sqrt(max(0.0, b * b + c * c - 2 * b * c * math.cos(math.radians(a))))
        else:  # SSA: the other given side's opposite angle by the sine law
            (w, b), = [(k, x) for k, x in side.items() if k != v]
            sin_w = b * math.sin(math.radians(a)) / side[v]
            if sin_w > 1:
                return None
            aw = math.degrees(math.asin(sin_w))
            (u,) = [k for k in vs if k not in (v, w)]
            return {v: a, w: aw, u: 180 - a - aw} if 180 - a - aw > 0 else None
    if len(side) == 3:
        (p, a), (q, b), (r, c) = side.items()
        if a + b <= c or a + c <= b or b + c <= a:
            return None
        def opposite(x, y, z):  # angle opposite x
            return math.degrees(math.acos(max(-1.0, min(1.0, (y * y + z * z - x * x) / (2 * y * z)))))
        return {p: opposite(a, b, c), q: opposite(b, a, c), r: opposite(c, a, b)}
    return None


def _unit_label(value: str) -> str:
    """8 cm -> 8\\,\\mathrm{cm}; anything else unchanged."""
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*([A-Za-z]+(?:/[A-Za-z]+)?)\s*", str(value or ""))
    return m.group(1) + r"\,\mathrm{" + m.group(2) + "}" if m else str(value or "")


def _triangle_asked(question: str, brief: str, vertices: tuple[str, str, str],
                    angles: dict[str, float], given_sides: set[str]) -> dict[str, str]:
    """What the question asks for, as {slot key: symbol}: an edge ("EF") or a
    vertex ("F"). The symbol is the one the brief names ("label EF as x"),
    the side's own letter ("find b"), else ?."""
    asked: dict[str, str] = {}
    m = re.search(r"\b(?:find|calculate|determine|work out|solve for|what is|how (?:long|far|wide|tall))\b(.*)", question, re.I)
    if not m:
        return asked
    clause = re.split(r"\bDiagram\s*:", m.group(1))[0]  # the question's ask, not the drawing notes
    verts = set(vertices)

    def symbol(names: list[str], default: str) -> str:
        for name in names:
            s = re.search(r"\b" + name + r"\b[^.;]{0,30}?\b(?:labell?ed|as)\s+([a-z]|\\theta)\b", brief)
            s = s or re.search(r"\blabel\s+" + name + r"\s+as\s+([a-z]|\\theta)\b", brief)
            if s:
                return s.group(1)
        return default

    for name in re.findall(r"(?:∠|\bangle\s+)([A-Z]{3}|[A-Z])\b", clause):
        v = name[1] if len(name) == 3 else name
        if v in verts:
            asked[v] = symbol([r"angle\s+" + name, name], "?")
    for pair in re.findall(r"\b([A-Z]{2})\b", clause):
        # not the arms of a named angle ("triangle DEF" once read as angle DEF)
        if set(pair) <= verts and pair[0] != pair[1] and not re.search(r"\bangle\s+\w?" + pair + r"\b", clause):
            asked[pair] = symbol([pair], "?")
    for letter in re.findall(r"(?:\b(?:find|side|length(?: of)?|calculate|determine)\s+)([a-z])(?=\s*(?:[.,?;]|$|and\b))", "find " + clause):
        v = letter.upper()
        if v in verts:
            a, b = [x for x in vertices if x != v]
            asked[a + b] = symbol([r"side\s+" + letter, letter], letter)
    if angles and re.search(r"\b(largest|smallest)\s+(?:interior\s+)?angle\b", clause, re.I):
        pick = max if re.search(r"largest", clause, re.I) else min
        v = pick(angles, key=angles.get)
        asked.setdefault(v, "?")
    if re.search(r"\b(third|remaining|unknown|missing)\s+side\b", clause, re.I):
        edges = [a + b for a, b in ((vertices[0], vertices[1]), (vertices[0], vertices[2]), (vertices[1], vertices[2]))]
        rest = [e for e in edges if e not in given_sides]
        if len(rest) == 1:
            asked.setdefault(rest[0], symbol([rest[0]], "?"))
    return asked


def _triangle_overrides(req: GenerateReq) -> dict[str, str]:
    """triangle_general: vertex names, and when the givens fix the triangle, its
    true shape (largest angle at the top, so the base is the longest side) and
    every label from the question: givens with values, the asked side or angle
    with its symbol, the rest blank. A slot the question does not settle keeps
    the model's value only when the shape is not solved."""
    text = _request_text(req)
    vertices = _triangle_vertices(text) or ("A", "B", "C")
    ta, tb, tc = vertices
    side_labels = _extract_triangle_sides(text, vertices)
    angle_labels = _extract_triangle_angles(text, vertices)
    overrides = {"A": ta, "B": tb, "C": tc}
    edges = {ta + tb: tc, ta + tc: tb, tb + tc: ta}  # edge -> opposite vertex
    sides = {edges[e]: _first_number(v) for e, v in side_labels.items() if re.search(r"\d", str(v))}
    angles = {v: _first_number(a) for v, a in angle_labels.items() if _first_number(a) is not None}
    solved = _solve_triangle(vertices, sides, angles)
    if not solved or set(solved) != set(vertices):
        # Not enough to fix the shape: only pin the parsed measures (a missed slot
        # overridden with a bare letter used to wipe a good model fill).
        for slot, edge in (("AB", ta + tb), ("AC", ta + tc), ("BC", tb + tc)):
            val = str(side_labels.get(edge, ""))
            if re.search(r"\d", val):
                overrides[slot] = _unit_label(_tex_label(val))
        for slot, vtx in (("ANG_A", ta), ("ANG_B", tb), ("ANG_C", tc)):
            if angle_labels.get(vtx):
                overrides[slot] = _tex_label(angle_labels[vtx])
        return overrides
    order = list(vertices)
    while solved[order[2]] < max(solved.values()) - 1e-9:
        order = order[1:] + order[:1]
    a, b, c = order
    given_edges = {e for e, v in side_labels.items() if re.search(r"\d", str(v))}
    asked = _triangle_asked(_question_text(req), _raw_request_text(req), vertices, solved, given_edges)

    def edge_label(p: str, q: str) -> str:
        for e in (p + q, q + p):
            if e in given_edges:
                return _unit_label(_tex_label(side_labels[e]))
            if e in asked:
                return asked[e]
        return ""

    overrides.update({
        "A": a, "B": b, "C": c,
        "DEG_A": _clean_number(round(solved[a], 2)), "DEG_B": _clean_number(round(solved[b], 2)),
        "AB": edge_label(a, b), "AC": edge_label(a, c), "BC": edge_label(b, c),
    })
    for slot, v in (("ANG_A", a), ("ANG_B", b), ("ANG_C", c)):
        overrides[slot] = _tex_label(angle_labels[v]) if v in angles else asked.get(v, "")
    return overrides


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
        r"angle of elevation|angle of depression|line of sight|triangular plot|"
        r"three sides|third side|largest interior angle|two sides of a triangle|"
        r"ladder|leans against|slides away|vertical wall)\b",
        low,
    ):
        return True
    # "angle CAB", "angle PQR" — a 3-letter vertex-named angle always implies a triangle.
    if re.search(r"(?:∠|\\angle\b|\bangle\s+|\?)[A-Z]{3}\b", text):
        return True
    # Two or more distinct single-letter named angles (e.g. "angle A ... angle B") plus a
    # "distance across"/side reference is the classic solve-the-triangle setup.
    named_angles = {a.upper() for a in re.findall(r"(?:∠|\\angle\b|\bangle\s+|\?)([A-Z])\b", text)}
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
        elevation = bool(
            re.search(r"\b(angle of elevation|angle of depression|line of sight)\b", low)
        ) and _has_triangle_measure(text)
        # Law-of-cosines / law-of-sines / SAS-SSS-ASA captions describe a generic
        # triangle even when they name no vertex letters (common in study-guide
        # captions like "SAS Configuration for Law of Cosines"). Draw a clean,
        # self-consistent A/B/C triangle for them instead of returning None, which
        # let the free-form Gemini path emit angle/label-inconsistent diagrams.
        config = bool(
            re.search(
                r"\b(law of cosines|cosine law|law of sines|sine law|sas|sss|asa|included angle|"
                r"triangular plot|three sides|third side|largest interior angle|two sides of a triangle)\b",
                low,
            )
        )
        if not (elevation or config):
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
    requested_angles = {x.upper() for x in re.findall(r"(?:∠|\\angle\b|\bangle\s+|\?)([A-Z])\b", text)}
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
    # Law of cosines / SAS: mark the included angle at apex C (between sides CA and
    # CB, i.e. opposite side c). Without this a "law of cosines / SAS" caption drew
    # a bare triangle with no angle, disagreeing with the caption. Only kicks in when
    # no specific angle was named above, so explicit measures still win.
    if not angle_lines and re.search(r"\b(law of cosines|cosine law|sas|included angle)\b", low):
        p1, mid, p2, _ = angle_specs[c]
        angle_lines.append(
            f'  \\pic[draw=black,angle radius=5mm,"${_tex_label(c)}$",angle eccentricity=1.35] {{angle={p1}--{mid}--{p2}}};'
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


def _travel_bearing_values_from_text(text: str) -> list[int]:
    repaired = _repair_transport_escapes(text)
    directions: list[tuple[int, int]] = []
    deg = r"(?:\s*(?:degrees?|deg|[°º˚∘]|\\circ|\^?\\circ))?"
    for m in re.finditer(
        # "on bearings of 050 and 160" names two at once
        r"\b(?:bearings?|headings?)\s*(?:of|=|is|at)?\s*0*([0-9]{1,3})" + deg + r"(?:\s*(?:,|and|,\s*and)\s*0*([0-9]{1,3})" + deg + r")?",
        repaired,
        re.I,
    ):
        directions.append((m.start(), int(float(m.group(1))) % 360))
        if m.group(2):
            directions.append((m.start(2), int(float(m.group(2))) % 360))
    for m in re.finditer(r"\b(?:due\s+)?(north|east|south|west)\b", repaired, re.I):
        window = repaired[max(0, m.start() - 24): m.end() + 24].lower()
        if "from north" in window or "clockwise from" in window:
            continue
        word = m.group(1).lower()
        value = {"north": 0, "east": 90, "south": 180, "west": 270}[word]
        directions.append((m.start(), value))
    directions.sort(key=lambda item: item[0])
    out: list[int] = []
    for _pos, value in directions:
        if not out or out[-1] != value:
            out.append(value)
    return out[:2]


def _bearing_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if (
        re.search(r"\beast\b", low)
        and re.search(r"\bnorth\b", low)
        and re.search(r"\b(up|vertical|height)\b", low)
        and not re.search(r"\b(bearing|heading|compass)\b", low)
    ):
        return None
    if not generic and not re.search(r"\b(bearing|navigation|north|east|compass|heading)\b", low):
        return None
    bearings = _travel_bearing_values_from_text(text)
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
  \draw[cp axis,-Stealth] (P)--($(P)+(0,1.15)$) node[above] {$N$};
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


def _single_vector_diagram(text: str) -> tuple[str, str]:
    """A single vector drawn from the origin with its horizontal/vertical component
    legs (a right triangle). This is the textbook picture for a *component form* or
    *magnitude* question — the hypotenuse is the vector (its length = the magnitude).
    Labels are symbolic (u_x, u_y / Δx, Δy) so they stay correct for R^2 or R^3 alike
    instead of plugging real numbers onto a 2D sketch of a 3D vector."""
    low = text.lower()
    u, _v, _r = _extract_vector_names(text)
    # A displacement between two named points ("the vector AB") reads best as \vec{AB}
    # with Δx, Δy component legs; a plain named vector uses its own letter subscripts.
    disp = (
        re.search(r"\\(?:vec|overrightarrow)\s*\{\s*([A-Z])\s*([A-Z])\s*\}", text)
        or re.search(r"\b(?:the\s+)?vector\s+([A-Z])([A-Z])\b", text)
    )
    if disp:
        name = r"\vec{" + disp.group(1) + disp.group(2) + "}"
        xlab, ylab = r"\Delta x", r"\Delta y"
    else:
        base_m = re.search(r"\\vec\{([A-Za-z])\}", u)
        base = base_m.group(1) if base_m else "u"
        name = u
        xlab, ylab = base + "_x", base + "_y"
    vlab = ("|" + name + "|") if "magnitude" in low else name
    found_2d = _first_2d_vector(text)
    px, py = _scaled_2d_vector_point(found_2d[1]) if found_2d else (2.8, 1.9)
    if found_2d:
        vlab = ("|" + rf"\vec{{{found_2d[0]}}}" + "|") if "magnitude" in low else rf"\vec{{{found_2d[0]}}}"
    xmin = min(-0.7, px - 0.7)
    xmax = max(3.5, px + 0.7)
    ymin = min(-0.7, py - 0.7)
    ymax = max(2.7, py + 0.7)
    elbow_x = px - 0.25 if px >= 0 else px + 0.25
    elbow_y = 0.25 if py >= 0 else -0.25
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.95]
  \coordinate (O) at (0,0); \coordinate (P) at (__PX__,__PY__); \coordinate (Px) at (__PX__,0);
  \draw[cp axis,-Stealth] (__XMIN__,0)--(__XMAX__,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,__YMIN__)--(0,__YMAX__) node[above] {$y$};
  \draw[cp dashed] (O)--(Px) node[midway,below] {$__XLAB__$};
  \draw[cp dashed] (Px)--(P) node[midway,right] {$__YLAB__$};
  \draw[cp line,-Stealth] (O)--(P) node[pos=.5,above left] {$__VLAB__$};
  \draw[cp line] (__ELX__,0)--(__ELX__,__ELY__)--(__PX__,__ELY__);
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        XLAB=xlab,
        YLAB=ylab,
        VLAB=vlab,
        PX=str(px),
        PY=str(py),
        XMIN=str(round(xmin, 3)),
        XMAX=str(round(xmax, 3)),
        YMIN=str(round(ymin, 3)),
        YMAX=str(round(ymax, 3)),
        ELX=str(round(elbow_x, 3)),
        ELY=str(round(elbow_y, 3)),
    )
    return tikz, "Vector shown from the origin with its horizontal and vertical components."


def _force_ramp_diagram(text: str) -> tuple[str, str] | None:
    low = text.lower()
    if not re.search(r"\b(ramp|incline|inclined|slope)\b", low):
        return None
    if re.search(r"\bprojection|project(?:ed)?\s+onto\b", low):
        return None
    angle = _angle_from_question(GenerateReq(brief=text), "25")
    try:
        angle_num = float(angle)
    except ValueError:
        angle_num = 25.0
    normal_angle = _clean_number(angle_num + 90)
    parallel_angle = _clean_number(angle_num + 180)
    if re.search(r"\b(tension|rope|cable|string|pulled?\s+up|pulling\s+up)\b", low):
        parallel_force = rf"\draw[cp line,-Stealth] (M)--++({_clean_number(angle_num)}:1.28) node[above] {{$T$}};"
    else:
        parallel_force = rf"\draw[cp dashed,-Stealth] (M)--++({parallel_angle}:1.15) node[pos=.48,above left] {{$mg\sin\theta$}};"
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4.4,0); \coordinate (C) at (4.4,2.05);
  \draw[cp axis] (A)--(B);
  \draw[cp line] (A)--(C);
  \draw[cp dashed] (B)--(C);
  \pic[draw=black,angle radius=7mm,"$__ANG__^\circ$",angle eccentricity=1.35] {angle=B--A--C};
  \coordinate (M) at ($(A)!0.56!(C)$);
  \draw[fill=gray!12,draw=black,rotate around={__ANG__:(M)}] ($(M)+(-.38,-.24)$) rectangle ($(M)+(.38,.24)$);
  \draw[cp line,-Stealth] (M)--++(0,-1.35) node[below] {$mg$};
  \draw[cp line,-Stealth] (M)--++(__NANG__:1.05) node[above left] {$N$};
  __PARALLEL_FORCE__
\end{tikzpicture}
""".strip(),
        ANG=angle,
        NANG=normal_angle,
        PARALLEL_FORCE=parallel_force,
    )
    return tikz, "Inclined-plane force diagram with weight, normal force, and ramp-parallel force."


def _tension_support_diagram(text: str) -> tuple[str, str] | None:
    low = text.lower()
    if not (
        re.search(r"\b(two\s+(?:wires|ropes|cables)|two light wires|suspended by two|supported by two)\b", low)
        or (re.search(r"\b(cable|wire|rope)\b", low) and re.search(r"\b(beam|sign|mass|object|supported|suspended)\b", low))
    ):
        return None
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*(?:\^?\\circ|degrees?|deg|Â°)", text, re.I)
    left = nums[0] if nums else "40"
    right = nums[1] if len(nums) > 1 else left
    if not nums:
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*(?:\^?\\circ|degrees?|deg|[°º˚∘]|Â°|âˆ˜)", text, re.I)
        left = nums[0] if nums else left
        right = nums[1] if len(nums) > 1 else right
    try:
        left_dir = _clean_number(180 - float(left))
        right_dir = _clean_number(float(right))
    except ValueError:
        left_dir, right_dir = "140", "40"
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (O) at (0,0);
  \coordinate (L) at (__LEFT_DIR__:2.15);
  \coordinate (R) at (__RIGHT_DIR__:2.15);
  \coordinate (LH) at ($(L)+(1,0)$);
  \coordinate (RH) at ($(R)+(-1,0)$);
  \draw[cp axis] (-2.8,0)--(2.8,0);
  \draw[cp line] (L)--(O)--(R);
  \draw[cp line,-Stealth] (O)--(__LEFT_DIR__:1.45) node[pos=.48,above] {$T_1$};
  \draw[cp line,-Stealth] (O)--(__RIGHT_DIR__:1.45) node[pos=.48,above] {$T_2$};
  \draw[cp line,-Stealth] (O)--(0,-1.45) node[below] {$W$};
  \node[draw,minimum width=.62cm,minimum height=.38cm,anchor=north] at (0,-1.45) {};
  \pic[draw=black,angle radius=5mm,"$__LEFT__^\circ$",angle eccentricity=1.35] {angle=O--L--LH};
  \pic[draw=black,angle radius=5mm,"$__RIGHT__^\circ$",angle eccentricity=1.35] {angle=RH--R--O};
\end{tikzpicture}
""".strip(),
        LEFT=left,
        RIGHT=right,
        LEFT_DIR=left_dir,
        RIGHT_DIR=right_dir,
    )
    return tikz, "Tension diagram for a suspended load or cable-supported object."


def _pulling_force_work_diagram(text: str) -> tuple[str, str] | None:
    low = text.lower()
    if not (
        re.search(r"\b(force|pull(?:ed|ing)?)\b", low)
        and re.search(r"\b(horizontal|surface|displacement|distance|work)\b", low)
        and re.search(r"\b(work|distance|displacement)\b", low)
    ):
        return None
    angle = _angle_from_question(GenerateReq(brief=text), "")
    if not angle:
        return None
    force_m = re.search(r"\b(?:force\s+of|force\s*=)\s*([-+]?\d+(?:\.\d+)?)\s*(N|newtons?)?\b", text, re.I)
    dist_m = re.search(r"\b(?:distance\s+of|moves?\s+(?:a\s+)?distance\s+of|displacement\s+of)\s*([-+]?\d+(?:\.\d+)?)\s*(m|metres?|meters?|km|cm)?\b", text, re.I)
    flab = "F"
    if force_m:
        unit = "N" if not force_m.group(2) or force_m.group(2).lower().startswith("n") else force_m.group(2)
        flab = rf"F={force_m.group(1)}\,\mathrm{{{unit}}}"
    dlab = "d"
    if dist_m:
        unit = dist_m.group(2) or "m"
        unit = "m" if unit.lower().startswith(("m", "met")) else unit
        dlab = rf"d={dist_m.group(1)}\,\mathrm{{{unit}}}"
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (O) at (0,0);
  \coordinate (D) at (3.45,0);
  \coordinate (F) at (__ANG__:2.85);
  \draw[cp axis,-Stealth] (O)--(D) node[midway,below] {$__DLAB__$};
  \draw[cp line,-Stealth] (O)--(F) node[pos=.68,above left] {$__FLAB__$};
  \pic[draw=black,angle radius=6mm,"$__ANG__^\circ$",angle eccentricity=1.35] {angle=D--O--F};
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        ANG=angle,
        FLAB=flab,
        DLAB=dlab,
    )
    return tikz, "Force and displacement diagram for work done by an angled pull."


def _vector_difference_diagram(text: str) -> tuple[str, str]:
    """Head-to-tail construction for a vector subtraction / linear combination
    (p - q, 2u - 3v): both operands from a shared origin, and the difference drawn
    from the tip of the second to the tip of the first. This is the textbook picture
    of the operation the question asks for, so p-q and 2u-3v get the SAME relevant
    diagram instead of one getting a single-vector picture and the other a blank."""
    u, v, _r = _extract_vector_names(text)
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \coordinate (O) at (0,0); \coordinate (A) at (3.3,0.5); \coordinate (B) at (1.1,2.2);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below right] {$__U__$};
  \draw[cp line,-Stealth] (O)--(B) node[midway,above left] {$__V__$};
  \draw[cp dashed,-Stealth] (B)--(A) node[midway,above] {$__D__$};
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        U=u,
        V=v,
        D=u + "-" + v,
    )
    return tikz, "Vector subtraction shown head-to-tail as the difference of the two vectors."


def _basis_coeff(expr: str, axis: str) -> float | None:
    m = re.search(
        r"([+-]?)\s*(\d+(?:\.\d+)?)?\s*(?:\\+vec\s*\{?\s*" + re.escape(axis) + r"\s*\}?|(?<![A-Za-z])" + re.escape(axis) + r"\b)",
        expr,
        re.I,
    )
    if not m:
        return None
    sign = -1.0 if m.group(1) == "-" else 1.0
    mag = float(m.group(2)) if m.group(2) else 1.0
    return sign * mag


def _standard_basis_3d_vector(text: str) -> tuple[str, tuple[float, float, float]] | None:
    repaired = _repair_transport_escapes(text)
    name_m = re.search(
        r"(?:\\+vec\s*\{?\s*([A-Za-z])\s*\}?|(?:algebraic\s+)?vector\s+([A-Za-z])|\b([A-Za-z]))\s*=",
        repaired,
        re.I,
    )
    if not name_m:
        name_m = re.search(r"(?:algebraic\s+)?vector\s+([A-Za-z])\s*=", repaired, re.I)
    if not name_m:
        name_m = re.search(r"(?:algebraic\s+)?vector\s+([A-Za-z])\b", repaired, re.I)
    if not name_m:
        return None
    tail = repaired[name_m.end(): name_m.end() + 180]
    coeffs = tuple(_basis_coeff(tail, axis) for axis in ("i", "j", "k"))
    if any(c is None for c in coeffs):
        return None
    return next(g for g in name_m.groups() if g), (float(coeffs[0]), float(coeffs[1]), float(coeffs[2]))


def _first_3d_vector(text: str) -> tuple[str, tuple[float, float, float]] | None:
    basis = _standard_basis_3d_vector(text)
    if basis:
        return basis
    bracket_pat = re.compile(
        r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*"
        r"(?:\\left\s*<|\\langle|<)\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*(?:\\right\s*>|\\rangle|>)",
        re.I,
    )
    bracket_match = bracket_pat.search(_repair_transport_escapes(text))
    if bracket_match:
        return bracket_match.group(1), tuple(float(bracket_match.group(i)) for i in (2, 3, 4))
    vec_pat = re.compile(
        r"(?:\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?|vector\s+([A-Za-z][A-Za-z0-9_]*))\s*=?\s*"
        r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        re.I,
    )
    match = vec_pat.search(_repair_transport_escapes(text))
    if not match:
        return None
    name = match.group(1) or match.group(2) or "u"
    coords = tuple(float(match.group(i)) for i in (3, 4, 5))
    return name, coords


def _all_3d_vectors(text: str) -> list[tuple[str, tuple[float, float, float]]]:
    repaired = _repair_transport_escapes(text)
    found: list[tuple[str, tuple[float, float, float]]] = []
    for m in re.finditer(
        r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*"
        r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        repaired,
        re.I,
    ):
        if all(name != m.group(1) for name, _coords in found):
            found.append((m.group(1), tuple(float(m.group(i)) for i in (2, 3, 4))))
    for m in re.finditer(
        r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*"
        r"(?:\\left\s*<|\\langle|<)\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*(?:\\right\s*>|\\rangle|>)",
        repaired,
        re.I,
    ):
        if all(name != m.group(1) for name, _coords in found):
            found.append((m.group(1), tuple(float(m.group(i)) for i in (2, 3, 4))))
    basis = _standard_basis_3d_vector(repaired)
    if basis and all(name != basis[0] for name, _coords in found):
        found.insert(0, basis)
    return found


def _named_3d_points(text: str) -> dict[str, tuple[float, float, float]]:
    repaired = _repair_transport_escapes(text)
    out: dict[str, tuple[float, float, float]] = {}
    for m in re.finditer(
        r"\b([A-Z])\s*(?:=|:)?\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        repaired,
    ):
        out[m.group(1)] = tuple(float(m.group(i)) for i in (2, 3, 4))
    return out


def _named_2d_points(text: str) -> dict[str, tuple[float, float]]:
    repaired = _repair_transport_escapes(text)
    out: dict[str, tuple[float, float]] = {}
    for m in re.finditer(
        r"\b([A-Z])\s*(?:=|:)?\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        repaired,
    ):
        out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out


def _scale_3d_coords(coords: list[tuple[float, float, float]], target: float = 2.45) -> tuple[list[tuple[float, float, float]], float]:
    max_abs = max([abs(v) for xyz in coords for v in xyz] + [1.0])
    scale = target / max_abs
    return [tuple(round(v * scale, 3) for v in xyz) for xyz in coords], scale


def _fmt_num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _point_vector_3d_diagram(text: str) -> tuple[str, str] | None:
    points = _named_3d_points(text)
    if len(points) < 2:
        return None
    requested: list[tuple[str, str]] = []
    for m in re.finditer(r"\\(?:vec|overrightarrow)\s*\{\s*([A-Z])\s*([A-Z])\s*\}", _repair_transport_escapes(text)):
        if m.group(1) in points and m.group(2) in points:
            edge = (m.group(1), m.group(2))
            if edge not in requested:
                requested.append(edge)
    for m in re.finditer(r"\bvector\s+([A-Z])([A-Z])\b", text):
        if m.group(1) in points and m.group(2) in points:
            edge = (m.group(1), m.group(2))
            if edge not in requested:
                requested.append(edge)
    names = list(points)
    if not requested and len(names) >= 2:
        requested.append((names[0], names[1]))

    scaled, _scale = _scale_3d_coords([points[name] for name in names])
    scaled_points = dict(zip(names, scaled))
    all_vals = [v for xyz in scaled for v in xyz]
    low = min(all_vals + [0.0]) - 0.45
    high = max(all_vals + [0.0]) + 0.55
    node_lines = []
    for name in names:
        x, y, z = scaled_points[name]
        node_lines.append(
            rf"\coordinate ({name}) at ({_fmt_num(x)},{_fmt_num(y)},{_fmt_num(z)}); "
            rf"\node[cp point,label=above:{{$ {name} $}}] at ({name}) {{}};"
        )
    edge_lines = []
    for a, b in requested[:4]:
        edge_lines.append(
            rf"\draw[cp line,-Stealth] ({a}) -- ({b}) node[midway,above] {{$\vec{{{a}{b}}}$}};"
        )
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9, x={(-0.5cm,-0.3cm)}, y={(0.72cm,-0.25cm)}, z={(0cm,0.78cm)}]
  \draw[cp axis,-Stealth] (__LOW__,0,0) -- (__HIGH__,0,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,__LOW__,0) -- (0,__HIGH__,0) node[above] {$y$};
  \draw[cp axis,-Stealth] (0,0,__LOW__) -- (0,0,__HIGH__) node[above] {$z$};
  __NODES__
  __EDGES__
\end{tikzpicture}
""".strip(),
        LOW=_fmt_num(low),
        HIGH=_fmt_num(high),
        NODES="\n  ".join(node_lines),
        EDGES="\n  ".join(edge_lines),
    )
    return tikz, "3D point-to-point vector diagram using the given vertices."


def _point_vector_2d_diagram(text: str) -> tuple[str, str] | None:
    points = _named_2d_points(text)
    if len(points) < 2:
        return None
    repaired = _repair_transport_escapes(text)
    requested: list[tuple[str, str]] = []
    for m in re.finditer(r"\\(?:vec|overrightarrow)\s*\{\s*([A-Z])\s*([A-Z])\s*\}", repaired):
        if m.group(1) in points and m.group(2) in points:
            edge = (m.group(1), m.group(2))
            if edge not in requested:
                requested.append(edge)
    for m in re.finditer(r"\bvector\s+([A-Z])([A-Z])\b", repaired):
        if m.group(1) in points and m.group(2) in points:
            edge = (m.group(1), m.group(2))
            if edge not in requested:
                requested.append(edge)
    names = list(points)
    if not requested:
        requested.append((names[0], names[1]))
    max_abs = max([abs(v) for xy in points.values() for v in xy] + [1.0])
    scale = 2.8 / max_abs
    scaled_points = {
        name: (round(x * scale, 3), round(y * scale, 3))
        for name, (x, y) in points.items()
    }
    xs = [x for x, _y in scaled_points.values()] + [0.0]
    ys = [y for _x, y in scaled_points.values()] + [0.0]
    node_lines = [
        rf"\coordinate ({name}) at ({_fmt_num(x)},{_fmt_num(y)}); \node[cp point,label=above:{{$ {name} $}}] at ({name}) {{}};"
        for name, (x, y) in scaled_points.items()
    ]
    edge_lines = [
        rf"\draw[cp line,-Stealth] ({a}) -- ({b}) node[midway,above] {{$\vec{{{a}{b}}}$}};"
        for a, b in requested[:4]
    ]
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \draw[cp axis,-Stealth] (__XMIN__,0) -- (__XMAX__,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,__YMIN__) -- (0,__YMAX__) node[above] {$y$};
  __NODES__
  __EDGES__
\end{tikzpicture}
""".strip(),
        XMIN=_fmt_num(min(xs) - 0.65),
        XMAX=_fmt_num(max(xs) + 0.65),
        YMIN=_fmt_num(min(ys) - 0.65),
        YMAX=_fmt_num(max(ys) + 0.65),
        NODES="\n  ".join(node_lines),
        EDGES="\n  ".join(edge_lines),
    )
    return tikz, "2D point-to-point vector components diagram using the given initial and terminal points."


def _multi_3d_vector_diagram(text: str) -> tuple[str, str] | None:
    vectors = _all_3d_vectors(text)
    if len(vectors) < 2:
        return None
    scaled, _scale = _scale_3d_coords([coords for _name, coords in vectors])
    all_vals = [v for xyz in scaled for v in xyz]
    low = min(all_vals + [0.0]) - 0.45
    high = max(all_vals + [0.0]) + 0.55
    lines = []
    for idx, (name, _coords) in enumerate(vectors[:3]):
        x, y, z = scaled[idx]
        lines.append(rf"\coordinate ({name.upper()}) at ({_fmt_num(x)},{_fmt_num(y)},{_fmt_num(z)});")
        lines.append(rf"\draw[cp line,-Stealth] (0,0,0) -- ({name.upper()}) node[pos=.65,above] {{$\vec{{{name}}}$}};")
    relation = ""
    for rel_m in re.finditer(r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*([^.;]+)", _repair_transport_escapes(text)):
        rhs = re.split(r"\\\)|\)", rel_m.group(2), maxsplit=1)[0].strip()
        if re.match(r"^(?:\(|<|\\left\s*<)", rhs):
            continue
        if "\\vec" in rhs and any(op in rhs for op in ("+", "-")):
            relation = rf"\node[cp label,anchor=west] at (__HIGH__,__HIGH__,0) {{$\vec{{{rel_m.group(1)}}}={_safe_param_value(rhs, '')}$}};"
            break
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9, x={(-0.5cm,-0.3cm)}, y={(0.72cm,-0.25cm)}, z={(0cm,0.78cm)}]
  \draw[cp axis,-Stealth] (__LOW__,0,0) -- (__HIGH__,0,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,__LOW__,0) -- (0,__HIGH__,0) node[above] {$y$};
  \draw[cp axis,-Stealth] (0,0,__LOW__) -- (0,0,__HIGH__) node[above] {$z$};
  __LINES__
  __RELATION__
  \fill (0,0,0) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        LOW=_fmt_num(low),
        HIGH=_fmt_num(high),
        LINES="\n  ".join(lines),
        RELATION=relation.replace("__HIGH__", _fmt_num(high)),
    )
    return tikz, "3D coordinate diagram for the given vector operands."


def _directional_3d_motion_diagram(text: str) -> tuple[str, str] | None:
    low = _repair_transport_escapes(text).lower()
    if not (
        re.search(r"\beast\b", low)
        and re.search(r"\bnorth\b", low)
        and re.search(r"\b(up|vertical|height|altitude)\b", low)
    ):
        return None

    def dist(word: str) -> float | None:
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(?:km|m|metres?|meters?)?\s+" + word, low)
        return float(m.group(1)) if m else None

    east = dist("east")
    north = dist("north")
    up = dist("up") or dist("vertical") or dist("height") or dist("altitude")
    if east is None or north is None or up is None:
        return None
    text_for_vector = rf"\vec{{p}}=<{_fmt_num(east)},{_fmt_num(north)},{_fmt_num(up)}>"
    tikz, _caption = _vector_3d_diagram(text_for_vector)
    return tikz, "3D position vector from east, north, and vertical displacement components."


def _first_2d_vector(text: str) -> tuple[str, tuple[float, float]] | None:
    text = _repair_transport_escapes(text)
    bracket_pat = re.compile(
        r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*"
        r"(?:\\left\s*<|\\langle|<)\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*(?:\\right\s*>|\\rangle|>)",
        re.I,
    )
    bracket_match = bracket_pat.search(text)
    if bracket_match:
        return bracket_match.group(1), (float(bracket_match.group(2)), float(bracket_match.group(3)))
    vec_pat = re.compile(
        r"(?:\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?|vector\s+([A-Za-z][A-Za-z0-9_]*))\s*=?\s*"
        r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        re.I,
    )
    match = vec_pat.search(text)
    if not match:
        return None
    name = match.group(1) or match.group(2) or "u"
    return name, (float(match.group(3)), float(match.group(4)))


def _all_2d_vectors(text: str) -> list[tuple[str, tuple[float, float]]]:
    repaired = _repair_transport_escapes(text)
    found: list[tuple[str, tuple[float, float]]] = []
    patterns = [
        r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*"
        r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
        r"\\+vec\s*\{?\s*([A-Za-z][A-Za-z0-9_]*)\s*\}?\s*=\s*"
        r"(?:\\left\s*<|\\langle|<)\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*(?:\\right\s*>|\\rangle|>)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, repaired, re.I):
            if all(name != m.group(1) for name, _coords in found):
                found.append((m.group(1), (float(m.group(2)), float(m.group(3)))))
    return found


def _multi_2d_vector_diagram(text: str) -> tuple[str, str] | None:
    vectors = _all_2d_vectors(text)
    if len(vectors) < 2:
        return None
    coords = [xy for _name, xy in vectors]
    max_abs = max([abs(v) for xy in coords for v in xy] + [1.0])
    scale = 2.8 / max_abs
    scaled = [(round(x * scale, 3), round(y * scale, 3)) for x, y in coords]
    all_x = [x for x, _y in scaled] + [0.0]
    all_y = [y for _x, y in scaled] + [0.0]
    xmin, xmax = min(all_x) - 0.65, max(all_x) + 0.65
    ymin, ymax = min(all_y) - 0.65, max(all_y) + 0.65
    lines = []
    for idx, (name, _coords) in enumerate(vectors[:4]):
        x, y = scaled[idx]
        lines.append(
            rf"\draw[cp line,-Stealth] (0,0) -- ({_fmt_num(x)},{_fmt_num(y)}) "
            rf"node[pos=.72,above] {{$\vec{{{name}}}$}};"
        )
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9]
  \draw[cp axis,-Stealth] (__XMIN__,0) -- (__XMAX__,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,__YMIN__) -- (0,__YMAX__) node[above] {$y$};
  __LINES__
  \fill (0,0) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        XMIN=_fmt_num(xmin),
        XMAX=_fmt_num(xmax),
        YMIN=_fmt_num(ymin),
        YMAX=_fmt_num(ymax),
        LINES="\n  ".join(lines),
    )
    return tikz, "2D coordinate diagram for the given vector linear combination."


def _vector_3d_diagram(text: str) -> tuple[str, str]:
    found = _first_3d_vector(text)
    name, coords = found if found else ("u", (2.0, 1.4, 1.8))
    x, y, z = coords
    max_abs = max(abs(x), abs(y), abs(z), 1.0)
    scale = 2.4 / max_abs
    sx, sy, sz = (round(v * scale, 3) for v in (x, y, z))
    low = min(sx, sy, sz, 0.0) - 0.55
    high = max(sx, sy, sz, 0.0) + 1.35
    label = rf"\vec{{{name}}}"
    tikz = _fill(
        r"""
\begin{tikzpicture}[scale=.9, x={(-0.5cm,-0.3cm)}, y={(0.72cm,-0.25cm)}, z={(0cm,0.78cm)}]
  \draw[cp axis,-Stealth] (__LOW__,0,0) -- (__HIGH__,0,0) node[right] {$x$};
  \draw[cp axis,-Stealth] (0,__LOW__,0) -- (0,__HIGH__,0) node[above] {$y$};
  \draw[cp axis,-Stealth] (0,0,__LOW__) -- (0,0,__HIGH__) node[above] {$z$};
  \coordinate (P) at (__X__,__Y__,__Z__);
  \draw[cp line,-Stealth] (0,0,0)--(P) node[pos=.62,above right] {$__LABEL__$};
  \draw[cp dashed] (P)--(__X__,__Y__,0);
  \draw[cp dashed] (__X__,__Y__,0)--(__X__,0,0);
  \draw[cp dashed] (__X__,__Y__,0)--(0,__Y__,0);
  \fill (0,0,0) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
        LOW=_fmt_num(low),
        HIGH=_fmt_num(high),
        X=str(sx),
        Y=str(sy),
        Z=str(sz),
        LABEL=label,
    )
    return tikz, "3D vector shown in an xyz coordinate frame."


def _scaled_2d_vector_point(coords: tuple[float, float]) -> tuple[float, float]:
    x, y = coords
    max_abs = max(abs(x), abs(y), 1.0)
    scale = 2.6 / max_abs
    return round(x * scale, 3), round(y * scale, 3)


def _vector_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)          # full text (subject+title+brief) for extraction/guards
    low = text.lower()
    q = _question_text(req)            # QUESTION only — drives which diagram is drawn
    ql = q.lower()
    # A vector operation written symbolically in the question: a+b, p-q, 2u-3v. Detected on
    # the question so the worked answer's incidental wording can't flip the diagram.
    op_add = bool(re.search(r"\\vec\s*\{[a-zA-Z]\}\s*\+", q)) or bool(re.search(r"\b(resultant|sum)\b", ql))
    symbolic_sub = bool(re.search(r"\\vec\s*\{[a-zA-Z]\}\s*-\s*\d*\s*\\?vec", q))
    vector_sub_words = bool(re.search(r"\b(vector|vectors|\\vec|force|forces|velocity|velocities|displacement|resultant)\b", ql))
    op_sub = symbolic_sub or (vector_sub_words and bool(re.search(r"\b(subtract|difference)\b", ql)))
    if re.search(r"\bdifference\s+between\b", ql) and re.search(r"\bscalar\b", ql) and re.search(r"\bvector\b", ql):
        return None
    # Fire for genuine vector cues AND concrete vector-QUANTITY questions (magnitude,
    # component form, unit/position vectors, orthogonal/collinear) AND symbolic operations,
    # so the student reliably gets a relevant deterministic diagram instead of a Gemini
    # coin-flip. Quantity/op-only cues must not steal a triangle/trig question that merely
    # says "magnitude" (this fn runs before _triangle_template), so defer in that case.
    has_vec_word = re.search(r"\\vec|\b(vector|vectors|resultant|parallelogram|force|forces|velocity|velocities|displacement|equilibrium|tension|wires?|ropes?|cables?|supported|suspended|free[- ]?body|inclined plane)\b", ql)
    has_motion_resultant = re.search(r"\b(river|current|stream|boat|canoe|kayak|swimmer|ferry|airplane|aircraft|wind|ground speed|ground velocity)\b", ql)
    has_vec_quantity = re.search(r"\b(magnitude|component|unit vector|position vector|orthogonal|collinear|scalar multiple|dot product|projection)\b", ql)
    if not generic:
        if (
            re.search(r"\b(define|explain|describe|state)\b", ql)
            and re.search(r"\b(term|definition|relationship|in your own words)\b", ql)
            and not re.search(r"\b(calculate|find|determine|draw|sketch|graph|diagram|geometric shape)\b", ql)
        ):
            return None
        if not (has_vec_word or has_motion_resultant or has_vec_quantity or op_add or op_sub):
            return None
        if not has_vec_word and not op_add and not op_sub and _looks_like_triangle(text):
            return None
    # A linear-algebra transformation question ("maps the unit square to a parallelogram,
    # find the 2x2 matrix") trips the "parallelogram" trigger but is not vector addition.
    # If it reads as matrix/transformation work and carries no genuine vector cue, defer to
    # Gemini rather than drawing a vector parallelogram.
    if not generic and re.search(r"\b(matrix|matrices|determinant|linear transformation|transformation matrix|unit square|eigen\w*)\b", low) \
            and not re.search(r"\b(vector|vectors|resultant|force|velocity|displacement|magnitude|head[- ]to[- ]tail)\b", low):
        return None
    ramp = _force_ramp_diagram(q)
    if ramp:
        return ramp
    tension = _tension_support_diagram(q)
    if tension:
        return tension
    pull_work = _pulling_force_work_diagram(q)
    if pull_work:
        return pull_work
    directional_3d = _directional_3d_motion_diagram(q)
    if directional_3d:
        return directional_3d
    point_2d = _point_vector_2d_diagram(q)
    if point_2d:
        return point_2d
    point_3d = _point_vector_3d_diagram(q)
    if point_3d:
        return point_3d
    if _first_3d_vector(_raw_request_text(req)) and re.search(r"\b(magnitude|component|unit vector|position vector|orthogonal|collinear|scalar multiple|dot product|vector)\b", ql):
        return _vector_3d_diagram(_raw_request_text(req))
    if re.search(r"\b(linear combination|linear relationship|coplanar|span|component form|find the vector|find vector|express .*component|dot product)\b", ql):
        multi_3d = _multi_3d_vector_diagram(_raw_request_text(req))
        if multi_3d:
            return multi_3d
        multi_2d = _multi_2d_vector_diagram(_raw_request_text(req))
        if multi_2d:
            return multi_2d
    # Classify on the question, in priority order, so each type maps to ONE consistent
    # picture: sum/resultant -> parallelogram; subtraction/combination -> head-to-tail
    # difference; orthogonal -> right angle; collinear -> parallel arrows; a single vector
    # quantity (magnitude/component form/unit/position) -> vector-with-components; otherwise
    # the two-vector angle diagram.
    if op_sub and not op_add:
        return _vector_difference_diagram(text)
    if op_add and not (op_sub or "parallelogram" in ql):
        pass  # fall through to the parallelogram/resultant diagram below
    elif re.search(r"\b(orthogonal|perpendicular)\b", ql) and not re.search(r"\b(resultant|parallelogram)\b", ql):
        u, v, _r = _extract_vector_names(text)
        tikz = _fill(
            r"""
\begin{tikzpicture}[scale=.95]
  \coordinate (O) at (0,0); \coordinate (A) at (8:3.0); \coordinate (B) at (98:2.7);
  \draw[cp line,-Stealth] (O)--(A) node[pos=.62,below right] {$__U__$};
  \draw[cp line,-Stealth] (O)--(B) node[pos=.62,above left] {$__V__$};
  \pic[draw=black,angle radius=4mm] {right angle=A--O--B};
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}
""".strip(),
            U=u,
            V=v,
        )
        return tikz, "Two orthogonal vectors meeting at a right angle."
    elif re.search(r"\b(collinear|scalar multiple|parallel vectors?)\b", ql):
        u, v, _r = _extract_vector_names(text)
        tikz = _fill(
            r"""
\begin{tikzpicture}[scale=.95]
  \draw[cp line,-Stealth] (0,0.5)--(2.3,0.5) node[midway,above] {$__U__$};
  \draw[cp line,-Stealth] (0.4,-0.45)--(3.8,-0.45) node[midway,below] {$__V__$};
\end{tikzpicture}
""".strip(),
            U=u,
            V=v,
        )
        return tikz, "Collinear vectors are parallel — scalar multiples of each other."
    elif (re.search(r"\b(magnitude|component|unit vector|position vector)\b", ql)
            and not re.search(r"\b(angle between|between them|two vectors|two forces)\b", ql)):
        return _single_vector_diagram(text)
    angle_match = (
        re.search(r"\b([0-9]{1,3})(?:\s*degrees?)?\s*(?:between|angle)", low)
        or re.search(r"\bangle\s+between\b[^.。;:\n]{0,80}?\b(?:is|=|of)?\s*([0-9]{1,3})(?:\s*degrees?)?", low)
        or re.search(r"\bangle\s*(?:is|=)?\s*([0-9]{1,3})", low)
    )
    has_angle_context = bool(
        angle_match
        or re.search(r"\b(angle between|between the vectors|between them|two vectors|two forces|resultant of two|force|forces)\b", ql)
        or has_motion_resultant
    )
    if not (has_angle_context or op_add or op_sub or generic):
        return None
    angle = int(angle_match.group(1)) if angle_match else 55
    u, v, result = _extract_vector_names(text)
    magnitudes = _extract_vector_magnitudes(text)
    u_label = u + (r"\,=" + magnitudes[0] if magnitudes else "")
    v_label = v + (r"\,=" + magnitudes[1] if len(magnitudes) > 1 else "")
    if op_add or "parallelogram" in ql:
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
    if not generic and not re.search(r"\b(rectangle|circle|circumference|cylinder|cylindrical)\b", low):
        return None
    if "cylinder" in low or "cylindrical" in low:
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


def _discrete_sequence_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if not generic and not re.search(r"\b(modulo|clock arithmetic|arithmetic sequence|growing pattern|staircase|first few terms)\b", low):
        return None
    if re.search(r"\b(modulo|clock arithmetic)\b", low):
        nums = [int(n) for n in re.findall(r"\b\d+\b", low)]
        modulus = 12
        start = nums[1] if len(nums) > 1 and nums[0] == 12 else (nums[0] if nums else 9)
        move = nums[2] if len(nums) > 2 and nums[0] == 12 else (nums[1] if len(nums) > 1 else 5)
        end = (start + move) % modulus
        end = modulus if end == 0 else end
        start_angle = 90 - (start % 12) * 30
        end_angle = 90 - (end % 12) * 30
        tikz = _fill(
            r"""
\begin{tikzpicture}[scale=.75]
  \draw[cp line] (0,0) circle (2);
  \foreach \n in {1,...,12} {
    \node[font=\small] at ({90-\n*30}:1.72) {$\n$};
  }
  \draw[cp line,-Stealth] (0,0)--(__START_ANGLE__:1.25) node[midway,above] {start};
  \draw[cp dashed,-Stealth] (__START_ANGLE__:2.25) arc[start angle=__START_ANGLE__,end angle=__END_ANGLE__,radius=2.25];
  \fill[cp point] (__END_ANGLE__:2) circle (1.7pt) node[above right] {$__END__$};
\end{tikzpicture}
""".strip(),
            START_ANGLE=str(start_angle),
            END_ANGLE=str(end_angle),
            END=str(end),
        )
        return tikz, "Modulo-12 clock diagram showing the starting value and forward movement."
    return r"""
\begin{tikzpicture}[scale=.68]
  \foreach \x/\h in {0/1,1.6/2,3.2/3,4.8/4} {
    \foreach \y in {1,...,\h} {
      \draw[cp fill] (\x,\y*.42) rectangle ++(.55,.34);
    }
  }
  \node[below] at (.28,0) {$t_1$};
  \node[below] at (1.88,0) {$t_2$};
  \node[below] at (3.48,0) {$t_3$};
  \node[below] at (5.08,0) {$t_4$};
\end{tikzpicture}
""".strip(), "Arithmetic sequence block pattern showing the first few growing terms."


def _combinatorics_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    text = _request_text(req)
    low = text.lower()
    if not generic and not re.search(r"\b(combination|combinations|committee|choose|selected from|grouping diagram)\b", low):
        return None
    return r"""
\begin{tikzpicture}[scale=.85]
  \node[draw,circle,inner sep=1.6pt] (A) at (0,1.2) {$A$};
  \node[draw,circle,inner sep=1.6pt] (B) at (.9,1.2) {$B$};
  \node[draw,circle,inner sep=1.6pt] (C) at (1.8,1.2) {$C$};
  \node[draw,circle,inner sep=1.6pt] (D) at (2.7,1.2) {$D$};
  \draw[cp line] (-.35,.75) rectangle (3.05,1.65);
  \node[below] at (1.35,.75) {choose a group};
  \draw[cp dashed,-Stealth] (1.35,.55)--(1.35,-.25);
  \node[cp label] at (1.35,-.55) {order does not create a new committee};
\end{tikzpicture}
""".strip(), "Combination selection diagram for choosing an unordered committee."


def _deterministic_template(req: GenerateReq, generic: bool = False) -> tuple[str, str] | None:
    # Each template function owns its own trigger detection (returns None when it does
    # not apply), so a bearing/vector/circle question is never force-fitted to a triangle.
    ordered = (
        _statistics_template,
        _bearing_template,
        _vector_template,
        _triangle_template,
        _geometry_template,
        _discrete_sequence_template,
        _combinatorics_template,
    )
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
    skip_model_critic = caption.startswith(("Modulo-12 clock", "Arithmetic sequence block", "Combination selection"))
    rendered = (
        _verified_render(req, tikz, source="regex-template", run_critic=not skip_model_critic)
        if check_semantics else
        _render(RenderReq(code=tikz, format=req.format, theme=req.theme, target=req.target))
    )
    if rendered.get("ok"):
        rendered["tikz"] = rendered.get("tikz", tikz)
        rendered["caption"] = caption
    return rendered


def _safe_param_value(value, default: str = "") -> str:
    value = _repair_transport_escapes(str(value if value is not None else default))
    value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    value = re.sub(r"[;&]", " ", value)
    value = re.sub(r"[^A-Za-z0-9_+\-*/=.,:(){}\\\\^\\s/|°]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or default


def _safe_number(value, default: str = "0") -> str:
    value = str(value if value is not None else default).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return match.group(0) if match else default


def _safe_tikz_lines(value, default: str = "") -> str:
    value = _repair_transport_escapes(str(value if value is not None else default))
    if re.search(r"\\(?:write18|input|include|openin|openout|read|write|def|let|newcommand|usepackage|documentclass)\b", value, re.I):
        return default
    lines = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        if "\\pic" in line and "angle=" in line:
            lines.append(line)
    return "\n  ".join(lines) or default


def _format_tikz(template: str, params: dict, defaults: dict, numeric_keys: set[str] | None = None) -> str:
    numeric_keys = numeric_keys or set()
    clean = {}
    for key, default in defaults.items():
        if key == "angle_lines":
            clean[key] = _safe_tikz_lines(params.get(key), str(default))
        else:
            clean[key] = _safe_number(params.get(key), str(default)) if key in numeric_keys else _safe_param_value(params.get(key), str(default))
    return template.format(**clean)


def _param_blueprint(req: GenerateReq, hit: tuple[str, str]) -> dict | None:
    _tikz, caption = hit
    cap = caption.lower()
    text = _request_text(req).lower()
    if "triangle" in cap:
        angle_lines = "\n  ".join(line.strip() for line in _tikz.splitlines() if "\\pic" in line and "angle=" in line)
        return {
            "name": "triangle",
            "caption": caption,
            "numeric": set(),
            "defaults": {"A": "A", "B": "B", "C": "C", "AB": "c", "AC": "b", "BC": "a", "angle_lines": angle_lines},
            "template": r"""\begin{{tikzpicture}}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4.2,0); \coordinate (C) at (1.35,2.35);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \node[below left] at (A) {{$ {A} $}};
  \node[below right] at (B) {{$ {B} $}};
  \node[above] at (C) {{$ {C} $}};
  \node[below] at ($(A)!0.5!(B)$) {{$ {AB} $}};
  \node[left] at ($(A)!0.5!(C)$) {{$ {AC} $}};
  \node[right] at ($(B)!0.5!(C)$) {{$ {BC} $}};
  {angle_lines}
\end{{tikzpicture}}""",
        }
    if "bearing" in cap:
        return {
            "name": "bearing",
            "caption": caption,
            "numeric": {"a1", "a2", "m1", "m2", "b1", "b2"},
            "defaults": {"a1": "45", "a2": "-25", "m1": "67.5", "m2": "32.5", "b1": "45", "b2": "115", "l1": "45^\\circ", "l2": "115^\\circ"},
            "template": r"""\begin{{tikzpicture}}[scale=.85]
  \coordinate (O) at (0,0);
  \coordinate (P) at ({a1}:2.45);
  \coordinate (Q) at ($(P)+({a2}:2.1)$);
  \draw[cp axis,-Stealth] (O)--(0,2.4) node[above] {{$N$}};
  \draw[cp axis,-Stealth] (O)--(2.3,0) node[right] {{$E$}};
  \draw[cp line,-Stealth] (O)--(P) node[midway,above right] {{$ {l1} $}};
  \draw[cp line,-Stealth] (P)--(Q) node[midway,above] {{$ {l2} $}};
  \draw[cp dashed] (O)--(Q) node[midway,below] {{$d$}};
  \draw[cp dashed] (90:.62) arc[start angle=90,end angle={a1},radius=.62];
  \node at ({m1}:.88) {{$ {b1}^\circ $}};
  \draw[cp dashed] ($(P)+(0,.58)$) arc[start angle=90,end angle={a2},radius=.58];
  \node at ($(P)+({m2}:.84)$) {{$ {b2}^\circ $}};
\end{{tikzpicture}}""",
        }
    if "subtraction" in cap:
        return {
            "name": "vector_difference",
            "caption": caption,
            "numeric": set(),
            "defaults": {"u": "\\vec{u}", "v": "\\vec{v}", "d": "\\vec{u}-\\vec{v}"},
            "template": r"""\begin{{tikzpicture}}[scale=.9]
  \coordinate (O) at (0,0); \coordinate (A) at (3.3,0.5); \coordinate (B) at (1.1,2.2);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below right] {{$ {u} $}};
  \draw[cp line,-Stealth] (O)--(B) node[midway,above left] {{$ {v} $}};
  \draw[cp dashed,-Stealth] (B)--(A) node[midway,above] {{$ {d} $}};
  \fill (O) circle (1.3pt) node[below left] {{$O$}};
\end{{tikzpicture}}""",
        }
    if "3d vector" in cap or "xyz coordinate" in cap:
        found = _first_3d_vector(_raw_request_text(req))
        name, coords = found if found else ("u", (2.0, 1.4, 1.8))
        x, y, z = coords
        max_abs = max(abs(x), abs(y), abs(z), 1.0)
        scale = 2.4 / max_abs
        defaults = {
            "x": f"{x * scale:.3g}",
            "y": f"{y * scale:.3g}",
            "z": f"{z * scale:.3g}",
            "label": rf"\vec{{{name}}}",
        }
        return {
            "name": "vector_3d",
            "caption": caption,
            "numeric": {"x", "y", "z"},
            "defaults": defaults,
            "template": r"""\begin{{tikzpicture}}[scale=.9]
  \draw[cp axis,-Stealth] (0,0,0) -- (2.8,0,0) node[right] {{$x$}};
  \draw[cp axis,-Stealth] (0,0,0) -- (0,2.4,0) node[above] {{$y$}};
  \draw[cp axis,-Stealth] (0,0,0) -- (0,0,2.6) node[below left] {{$z$}};
  \coordinate (P) at ({x},{y},{z});
  \draw[cp line,-Stealth] (0,0,0)--(P) node[pos=.62,above right] {{$ {label} $}};
  \draw[cp dashed] (P)--({x},{y},0);
  \draw[cp dashed] ({x},{y},0)--({x},0,0);
  \draw[cp dashed] ({x},{y},0)--(0,{y},0);
  \fill (0,0,0) circle (1.3pt) node[below left] {{$O$}};
\end{{tikzpicture}}""",
        }
    if "components" in cap:
        found_2d = _first_2d_vector(_raw_request_text(req))
        if found_2d:
            name, coords = found_2d
            px, py = _scaled_2d_vector_point(coords)
            raw_x, raw_y = coords
            defaults = {
                "px": f"{px:g}",
                "py": f"{py:g}",
                "xmin": f"{min(-0.7, px - 0.7):.3g}",
                "xmax": f"{max(3.5, px + 0.7):.3g}",
                "ymin": f"{min(-0.7, py - 0.7):.3g}",
                "ymax": f"{max(2.7, py + 0.7):.3g}",
                "xlab": f"{name}_x",
                "ylab": f"{name}_y",
                "vlab": rf"\vec{{{name}}}",
            }
        else:
            defaults = {"px": "2.8", "py": "1.9", "xmin": "-0.7", "xmax": "3.5", "ymin": "-0.7", "ymax": "2.7", "xlab": "u_x", "ylab": "u_y", "vlab": "\\vec{u}"}
        return {
            "name": "vector_components",
            "caption": caption,
            "numeric": {"px", "py", "xmin", "xmax", "ymin", "ymax"},
            "defaults": defaults,
            "template": r"""\begin{{tikzpicture}}[scale=1.1]
  \coordinate (O) at (0,0); \coordinate (P) at ({px},{py}); \coordinate (Px) at ({px},0);
  \draw[cp axis,-Stealth] ({xmin},0)--({xmax},0) node[right] {{$x$}};
  \draw[cp axis,-Stealth] (0,{ymin})--(0,{ymax}) node[above] {{$y$}};
  \draw[cp dashed] (O)--(Px) node[midway,below] {{$ {xlab} $}};
  \draw[cp dashed] (Px)--(P) node[midway,right] {{$ {ylab} $}};
  \draw[cp line,-Stealth] (O)--(P) node[pos=.5,above left] {{$ {vlab} $}};
\end{{tikzpicture}}""",
        }
    if "orthogonal" in cap:
        return {
            "name": "vector_orthogonal",
            "caption": caption,
            "numeric": set(),
            "defaults": {"u": "\\vec{u}", "v": "\\vec{v}"},
            "template": r"""\begin{{tikzpicture}}[scale=.95]
  \coordinate (O) at (0,0); \coordinate (A) at (8:3.0); \coordinate (B) at (98:2.7);
  \draw[cp line,-Stealth] (O)--(A) node[pos=.62,below right] {{$ {u} $}};
  \draw[cp line,-Stealth] (O)--(B) node[pos=.62,above left] {{$ {v} $}};
  \pic[draw=black,angle radius=4mm] {{right angle=A--O--B}};
\end{{tikzpicture}}""",
        }
    if "collinear" in cap:
        return {
            "name": "vector_collinear",
            "caption": caption,
            "numeric": set(),
            "defaults": {"u": "\\vec{u}", "v": "\\vec{v}"},
            "template": r"""\begin{{tikzpicture}}[scale=.95]
  \draw[cp line,-Stealth] (0,0.5)--(2.3,0.5) node[midway,above] {{$ {u} $}};
  \draw[cp line,-Stealth] (0.4,-0.45)--(3.8,-0.45) node[midway,below] {{$ {v} $}};
\end{{tikzpicture}}""",
        }
    if "vector" in cap:
        return {
            "name": "vector_resultant" if "resultant" in cap else "vector_angle",
            "caption": caption,
            "numeric": {"angle"},
            "defaults": {"angle": "55", "u": "\\vec{u}", "v": "\\vec{v}", "r": "\\vec{u}+\\vec{v}"},
            "template": r"""\begin{{tikzpicture}}[scale=.82]
  \coordinate (O) at (0,0); \coordinate (A) at (3.2,0); \coordinate (B) at ({angle}:2.2); \coordinate (C) at ($(A)+(B)$);
  \draw[cp dashed] (A)--(C)--(B);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {{$ {u} $}};
  \draw[cp line,-Stealth] (O)--(B) node[midway,left] {{$ {v} $}};
  \draw[cp line,-Stealth] (O)--(C) node[pos=.58,above] {{$ {r} $}};
  \pic[draw=black,angle radius=5mm,"${angle}^\circ",angle eccentricity=1.35] {{angle=A--O--B}};
\end{{tikzpicture}}""",
        }
    if "normal distribution" in cap:
        return {"name": "normal", "caption": caption, "numeric": set(), "defaults": {"center_label": "\\mu", "shade_label": "68\\%"}, "template": r"""\begin{{tikzpicture}}[declare function={{gauss(\x,\m,\s)=1/(\s*sqrt(2*pi))*exp(-((\x-\m)^2)/(2*\s^2));}}]
\begin{{axis}}[width=6.4cm,height=3.5cm,axis lines=middle,xlabel={{$x$}},ylabel={{density}},xmin=-3.6,xmax=3.6,ymin=0,ymax=0.45,samples=120,ytick=\empty,xtick={{-2,-1,0,1,2}},xticklabels={{$-2\sigma$,$-\sigma$,${center_label}$,$\sigma$,$2\sigma$}}]
  \addplot[cp fill,draw=none,domain=-1:1] {{gauss(x,0,1)}} \closedcycle;
  \addplot[cp line,domain=-3.5:3.5] {{gauss(x,0,1)}};
  \node at (axis cs:0,0.13) {{\small ${shade_label}$}};
\end{{axis}}
\end{{tikzpicture}}"""}
    if "box" in cap:
        return {"name": "boxplot", "caption": caption, "numeric": {"min", "q1", "median", "q3", "max"}, "defaults": {"min": "15", "q1": "35", "median": "55", "q3": "75", "max": "95"}, "template": r"""\begin{{tikzpicture}}
\begin{{axis}}[width=6.4cm,height=2.8cm,boxplot/draw direction=x,xmin=0,xmax=100,ytick={{1}},yticklabels={{data}},xlabel={{Value}}]
  \addplot[boxplot prepared={{median={median},lower quartile={q1},upper quartile={q3},lower whisker={min},upper whisker={max}}},draw=black,fill=gray!20] coordinates {{}};
\end{{axis}}
\end{{tikzpicture}}"""}
    if "histogram" in cap:
        return {"name": "histogram", "caption": caption, "numeric": set(), "defaults": {"bars": "(1,2) (2,5) (3,4) (4,3) (5,2)"}, "template": r"""\begin{{tikzpicture}}
\begin{{axis}}[width=6.4cm,height=3.5cm,ybar,bar width=9pt,ymin=0,ymax=6,xtick={{1,2,3,4,5}},xticklabels={{0--2,3--5,6--8,9--11,12+}},x tick label style={{font=\scriptsize}},xlabel={{Class interval}},ylabel={{Frequency}}]
  \addplot[fill=gray!25,draw=black] coordinates {{{bars}}};
\end{{axis}}
\end{{tikzpicture}}"""}
    if "cylinder" in cap or "circle" in cap or "rectangle" in cap:
        name = "cylinder" if "cylinder" in cap else ("circle" if "circle" in cap else "rectangle")
        templates = {
            "cylinder": r"""\begin{{tikzpicture}}[scale=.85]
  \draw[cp line] (0,0) ellipse (1.25 and .35);
  \draw[cp line] (-1.25,0)--(-1.25,2.4) (1.25,0)--(1.25,2.4);
  \draw[cp line] (0,2.4) ellipse (1.25 and .35);
  \draw[cp dashed] (0,2.4)--(1.25,2.4) node[midway,above] {{$ {r} $}};
  \draw[cp dashed,<->] (1.65,0)--(1.65,2.4) node[midway,right] {{$ {h} $}};
\end{{tikzpicture}}""",
            "circle": r"""\begin{{tikzpicture}}[scale=.9]
  \coordinate (O) at (0,0);
  \draw[cp line] (O) circle (1.45);
  \draw[cp line] (O)--(35:1.45) node[midway,above] {{$ {r} $}};
  \draw[cp dashed] (-1.45,0)--(1.45,0) node[midway,below] {{$ {d} $}};
\end{{tikzpicture}}""",
            "rectangle": r"""\begin{{tikzpicture}}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (3.8,0); \coordinate (C) at (3.8,2.1); \coordinate (D) at (0,2.1);
  \draw[cp line] (A)--(B)--(C)--(D)--cycle;
  \node[below] at ($(A)!0.5!(B)$) {{$ {l} $}};
  \node[right] at ($(B)!0.5!(C)$) {{$ {w} $}};
  \draw[cp dashed] (A)--(C) node[midway,above left] {{$ {d} $}};
\end{{tikzpicture}}""",
        }
        return {"name": name, "caption": caption, "numeric": set(), "defaults": {"r": "r", "h": "h", "d": "d", "l": "l", "w": "w"}, "template": templates[name]}
    if "calculus tangent" in cap:
        return {
            "name": "calculus_tangent",
            "caption": caption,
            "numeric": {"a", "b"},
            "defaults": {"a": "1", "b": "3", "curve": "f(x)", "point": "(1,1)"},
            "template": r"""\begin{{tikzpicture}}
\begin{{axis}}[xmin=-1,xmax=4,ymin=-1,ymax=7,axis lines=middle,xlabel={{$x$}},ylabel={{$y$}},grid=both,grid style={{draw=gray!20}},width=7cm,height=4.4cm,clip=false]
  \addplot[domain=-.5:3.5,samples=100,cp line] {{x^2}};
  \addplot[domain=.1:3.3,cp dashed] {{2*{a}*(x-{a})+{a}^2}};
  \addplot[domain={a}:{b},cp dashed] {{{a}+{b}}*(x-{a})+{a}^2};
  \fill (axis cs:{a},{a}^2) circle (1.5pt) node[above left] {{$ {point} $}};
  \node[anchor=west] at (axis cs:2.4,2.2) {{\small tangent}};
\end{{axis}}
\end{{tikzpicture}}""",
        }
    if "linear transformation" in cap:
        return {
            "name": "linear_transform",
            "caption": caption,
            "numeric": set(),
            "defaults": {"u": "\\vec{u}", "v": "\\vec{v}", "area": "|\\det T|"},
            "template": r"""\begin{{tikzpicture}}[scale=.85]
  \coordinate (O) at (0,0); \coordinate (A) at (2.4,0.2); \coordinate (B) at (.8,1.8); \coordinate (C) at ($(A)+(B)$);
  \draw[cp axis,-Stealth] (-.3,0)--(3.6,0) node[right] {{$x$}};
  \draw[cp axis,-Stealth] (0,-.3)--(0,2.5) node[above] {{$y$}};
  \draw[cp fill] (O)--(A)--(C)--(B)--cycle;
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {{$ {u} $}};
  \draw[cp line,-Stealth] (O)--(B) node[midway,left] {{$ {v} $}};
  \node at ($(O)!0.5!(C)$) {{$ {area} $}};
\end{{tikzpicture}}""",
        }
    return None


def _topic_blueprint_hit(req: GenerateReq) -> tuple[str, str] | None:
    text = _request_text(req).lower()
    if re.search(r"\b(tangent|secant|derivative|parabola|curve|sketch|graph)\b", text):
        return "", "Calculus tangent/secant curve sketch."
    if re.search(r"\b(linear transformation|unit square|transformation matrix|parallelogram)\b", text):
        return "", "Linear transformation of a unit square into a parallelogram."
    return None


def _param_prompt(req: GenerateReq, spec: dict, repair_log: str = "", previous_params: dict | None = None) -> str:
    return json.dumps({
        "role": "Return only minified JSON. Do not return TikZ. Fill values for this fixed TikZ template.",
        "question": _raw_request_text(req)[:2600],
        "template_name": spec["name"],
        "keys": list(spec["defaults"].keys()),
        "defaults": spec["defaults"],
        "rules": [
            "Return a flat JSON object with exactly these keys when possible.",
            "Use strings for every value.",
            "Preserve LaTeX backslashes by writing JSON escapes, e.g. \\\\vec{u}, \\\\theta, \\\\circ.",
            "Do not include markdown fences or explanatory text.",
            "For worksheet visuals, never place a final answer, solved coordinate tuple, solved component expression, magnitude value, or equation result on the diagram. Use only givens from the question, symbolic labels, or ? for the requested unknown.",
            "For angle_lines, return zero or more complete TikZ angle-pic lines only, or an empty string.",
            "For bars, return PGFPlots coordinate pairs like (1,2) (2,5).",
        ],
        "previous_params": previous_params or {},
        "repair_log": repair_log[:1200],
    }, ensure_ascii=False)


def _customize_template_and_render(req: GenerateReq, hit: tuple[str, str], source: str = "template") -> dict:
    spec = _param_blueprint(req, hit)
    if not spec:
        return _render_template(req, hit, check_semantics=True)
    rendered: dict = {"ok": False, "error": "Parameterized template did not render."}
    params = dict(spec["defaults"])
    repair_log = ""
    for attempt in range(TEMPLATE_REPAIR_ATTEMPTS + 1):
        try:
            raw_params = _gemini(_param_prompt(req, spec, repair_log=repair_log, previous_params=params), as_json=True, temperature=0.05)
            if isinstance(raw_params, dict):
                params.update(raw_params)
        except Exception as exc:
            print(f"[template-json] {source} parameter Gemini failure: {str(exc)[:220]}", flush=True)
            if attempt == 0:
                # Fall back to the regex-filled deterministic diagram, never to raw LLM TikZ.
                return _render_template(req, hit, check_semantics=True)
        tikz = _format_tikz(spec["template"], params, spec["defaults"], spec["numeric"])
        print(f"[template-json] {source}:{spec['name']} params={json.dumps(params, ensure_ascii=False)[:1600]}", flush=True)
        rendered = _verified_render(req, tikz, source=f"{source}:{spec['name']}")
        if rendered.get("ok"):
            rendered["tikz"] = rendered.get("tikz", tikz)
            rendered["caption"] = spec["caption"]
            rendered["customized"] = "json-" + spec["name"]
            return rendered
        repair_log = rendered.get("log") or rendered.get("error") or "TikZ render failed."
    return rendered


def _diagram_spec_prompt(req: GenerateReq, references: str | None) -> str:
    """First pass of the two-pass bespoke pipeline (same design as the Manim Space,
    which produces its accuracy by DESIGNING before coding): the model plans WHAT
    to draw - diagram family, objects, label placement, answer-safety - before any
    TikZ exists. The plan is then implemented by the _visual_prompt code pass."""
    return f"""You are planning a compact TikZ textbook diagram BEFORE any code is written. Design the diagram that best illustrates this question for a student who has NOT solved it yet.

Return ONLY minified JSON with exactly these keys:
  "diagram_type": one short phrase naming the diagram family, e.g. "function curve with tangent line at a point", "right triangle for a leaning ladder", "two vectors from a common origin with the angle marked"
  "objects": array of 3-8 short strings, each ONE drawable element with rough placement, e.g. "solid curve through the origin rising to the right", "dashed tangent line touching the curve at the marked point", "small right-angle mark at the base"
  "labels": array of objects {{"text": "...", "where": "...", "answer_safe": true|false}} - answer_safe is false when the text would reveal a value the student is asked to find (it must then be drawn as ? or a bare symbol)
  "givens": array of the values the question states (these may appear on the diagram)
  "unknowns": array of the requested results (these must NEVER appear solved on the diagram)
  "reference": short name of which reference pattern below to imitate structurally, or "none"

Rules:
- Plan a real diagram, not a formula poster; every object must be drawable with axes, curves, arrows, points, shaded regions, or geometry.
- Keep it compact: roughly 6 by 4 units, 3-8 objects, labels short (symbols or 1-3 words).
- The diagram shows the SETUP of the problem using only given information.
- Two vectors that span an angle, parallelogram, or cross product must be drawn clearly non-collinear (at least ~30 degrees apart on screen) so the shape does not collapse to a sliver.
- For a cross-product result arrow, work out the true direction with the right-hand rule BEFORE placing it (e.g. j x i points along -z, i x j along +z); never draw it opposite.
- In a named angle such as AOB, the middle letter O is the vertex. Unless the question explicitly says exterior, reflex, or major angle, plan the smaller interior angle between the two rays. In circle theorems, a stated angle AOB = 80 degrees means the 80-degree interior sector, never the 280-degree sector; an inscribed angle ACB must be marked between CA and CB inside the inscribed triangle.
- No code, no commentary - JSON only.

QUESTION:
{_raw_request_text(req)[:2200]}

REFERENCE PATTERNS (structural style guides):
{(references or "")[:4000]}
""".strip()


def _visual_prompt(req: GenerateReq, repair_log: str = "", previous_code: str = "", references: str | None = None,
                   spec: str = "") -> str:
    repair_block = ""
    if repair_log:
        repair_block = (
            "Previous TikZ failed. Fix it using this compile log: "
            + repair_log[:1200]
            + "\nPrevious TikZ:\n"
            + previous_code[:2500]
        )
    spec_block = ""
    if (spec or "").strip():
        spec_block = (
            "APPROVED DIAGRAM PLAN (implement this EXACTLY - you already designed it; "
            "honour the diagram type, draw every listed object, place every label as "
            "planned, and render every answer_safe=false label as ? or a bare symbol):\n"
            + spec[:2400]
        )

    target_rules = ""
    if req.target == "worksheet":
        target_rules = """
Worksheet-specific rules:
- Prefer compact landscape compositions about 5.5 units wide by 3 units tall.
- Avoid tall compass-style diagrams unless the problem explicitly needs directions.
- Keep vector diagrams close to the question: short arrows, clear arrowheads, labels just outside the strokes.
- Do not reveal the answer on worksheet diagrams. Show only the setup and the givens already visible in the question. Label requested results, unknown magnitudes, missing components, and final vectors with a symbol or ? rather than a solved value.
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
- Apply the same rule to circle theorems: the middle letter is always the vertex, and ordinary named angles use the smaller interior sector. For angle AOB = 80 degrees, mark the 80-degree sector between OA and OB, not the exterior 280-degree sector. For angle ACB, put the mark between CA and CB inside the inscribed triangle. Use small \\pic angle marks; never hand-draw a loop or raw arc around O or C.
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

{spec_block}

Reference patterns:
{references if references is not None else _example_blocks(req)}

Subject: {req.subject[:160]}
Title: {req.title[:240]}
Equation, if any: {req.equation[:500]}
Visual brief: {req.brief[:1800]}
Target: {req.target}

{repair_block}
""".strip()


def _semantic_visual_issue(req: GenerateReq, tikz: str) -> str | None:
    original = _raw_request_text(req)
    hay = original.lower()
    named_circle_angles = re.findall(r'(?:∠|(?i:\\angle\s*|\bangle\s+))([A-Z]{3})\b', original)
    is_named_circle_theorem = (
        bool(named_circle_angles)
        and ('circle' in hay or 'circumference' in hay)
        and any(term in hay for term in ('centre', 'center', 'inscribed', 'circumference'))
    )
    is_triangle = not is_named_circle_theorem and (
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
        and not any(term in hay for term in ("bearing", "navigation", "compass", "circle", "chord", "arc", "sector"))
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

    if is_named_circle_theorem and not any(term in hay for term in ('exterior angle', 'reflex angle', 'major angle')):
        if re.search(r'\\draw[^;\n]*\barc\s*(?:\[|\()', tikz):
            return (
                "Named circle-theorem angles must use small TikZ angle pics inside their two rays, not raw arc paths. "
                "For angle AOB = 80 degrees mark the 80-degree interior sector, never the exterior 280-degree sector."
            )
        pic_keys = {
            (middle, frozenset((first, last)))
            for first, middle, last in re.findall(
                r'\\pic\s*\[[^\]]*\]\s*\{angle=([A-Z])--([A-Z])--([A-Z])\}', tikz
            )
        }
        missing = [
            name for name in named_circle_angles
            if (name[1], frozenset((name[0], name[2]))) not in pic_keys
        ]
        if missing:
            return (
                "Circle angle marks must use the named angle's middle letter as the vertex and stay inside the two rays. "
                f"Missing correct interior angle pic(s): {', '.join(sorted(set(missing)))}."
            )
        for value, unit in re.findall(r'angle\s+radius\s*=\s*([0-9.]+)\s*(cm|mm)?', tikz, flags=re.IGNORECASE):
            radius_mm = float(value) * (10 if (unit or 'cm').lower() == 'cm' else 1)
            if radius_mm > 7:
                return "Circle-theorem angle marks are too large. Use small interior angle pics with radius between 4mm and 7mm."

    if is_triangle:
        requested_labels: set[str] = set()
        # Only treat a three-letter group as triangle vertex labels when it is
        # explicitly introduced as a triangle ("triangle ABC", "In ABC", "△ABC").
        # The keyword is case-insensitive but the LABELS must be genuinely uppercase:
        # the old IGNORECASE [A-Z]{3} matched lowercase, so "triangle with" captured
        # "WIT" and "right triangle with..." harvested phantom labels (the live
        # "GIRTW" failure), which then rejected the valid generic A/B/C triangle.
        for match in re.findall(r"(?i:triangle|\\triangle|in)\s+([A-Z]{3})\b", original):
            requested_labels.update(match)
        for match in re.findall(r"△\s*([A-Z]{3})\b", original):
            requested_labels.update(match)
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


def _extract_tikz_block(text: str) -> str:
    text = _strip_fence(text or "")
    match = re.search(r"\\begin\s*\{tikzpicture\}[\s\S]*?\\end\s*\{tikzpicture\}", text)
    return match.group(0).strip() if match else ""


def _heuristic_visual_correction(req: GenerateReq, tikz: str) -> tuple[str, str] | None:
    original = _raw_request_text(req)
    has_3d_vector = bool(_first_3d_vector(original))
    looks_flat_vector = (
        has_3d_vector
        and "\\begin{axis}" not in tikz
        and re.search(r"node\[[^\]]*\]\s*\{\$y\$\}", tikz)
        and not re.search(r"node\[[^\]]*\]\s*\{\$z\$\}", tikz)
    )
    if looks_flat_vector:
        corrected, _caption = _vector_3d_diagram(original)
        return corrected, "3D vector was being forced into a 2D component diagram; pivoted to xyz frame."
    if has_3d_vector and re.search(r"\\coordinate\s*\(P\)\s*at\s*\([^,()]+,[^,()]+\);", tikz):
        corrected, _caption = _vector_3d_diagram(original)
        return corrected, "3D vector used a 2D coordinate pair; pivoted to xyz frame."
    found_2d = _first_2d_vector(original)
    if found_2d:
        (_name, (raw_x, raw_y)) = found_2d
        expected_x = 0 if abs(raw_x) < 1e-9 else (1 if raw_x > 0 else -1)
        expected_y = 0 if abs(raw_y) < 1e-9 else (1 if raw_y > 0 else -1)
        geometry_code = re.sub(r"\$[^$]*\$", "", tikz)
        geometry_code = re.sub(r"node(?:\[[^\]]*\])?\s*\{[^{}]*\}", "node{}", geometry_code)
        coords = [
            (float(x), float(y))
            for x, y in re.findall(r"\((-?(?:\d+(?:\.\d+)?|\.\d+))\s*,\s*(-?(?:\d+(?:\.\d+)?|\.\d+))\)", geometry_code)
        ]
        def same_direction(value: float, expected: int) -> bool:
            if expected == 0:
                return abs(value) < 1e-6
            return value * expected > 0
        has_matching_endpoint = any(
            (abs(x) > 0.15 or abs(y) > 0.15)
            and same_direction(x, expected_x)
            and same_direction(y, expected_y)
            for x, y in coords
        )
        if not has_matching_endpoint:
            corrected, _caption = _single_vector_diagram(original)
            return corrected, (
                f"2D vector signs were not physically plotted in the correct quadrant; "
                f"expected ({raw_x:g}, {raw_y:g})."
            )
    return None


def _critic_prompt(req: GenerateReq, tikz: str) -> str:
    return f"""
You are a rigorous Mathematics and LaTeX/TikZ Geometric Validator. Your job is to review a proposed TikZ diagram snippet against the specific math question it is supposed to illustrate.

Important LaTeX context: this snippet is compiled inside the Course Planner wrapper, which already defines the styles cp axis, cp line, cp dashed, cp fill, cp point, and cp label. Do not flag those cp styles as undefined or non-compilable.

Examine the code for the following logical and structural failures:
1. Dimension Mismatches: Is a 3D vector or coordinate point being forced into a 2D template, resulting in zero-valued axes or flat, degenerate triangles? (e.g., a vector like (-3,0,4) rendered on a flat 2D right triangle with a height label of 0).
2. Geometric Impossible Shapes: Does the TikZ code attempt to draw lines, triangles, or graphs that contradict the constants or variables given in the text?
3. Label Clashes: Are labels overlapping axes or placed at mathematically incorrect positions?
4. Sign and Direction Integrity: Do all vector components, coordinate points, line slopes, and plotted endpoints physically match the signs in the question text? A negative x component must point left of the y-axis, a negative y component must point below the x-axis, and mixed-sign vectors must land in the correct quadrant or octant. Do not accept a diagram that merely labels a positive arrow with a negative coordinate.
5. Layout and Clipping: After enlarging the diagram, are axes, labels, arrowheads, plotted points, and curves still inside the visible drawing area without clipping?
6. Answer Leakage: If this is a worksheet diagram and the question asks the student to find, calculate, determine, express, solve, or write a value, does the proposed diagram reveal that final value, solved coordinate tuple, component expression, magnitude, or equation result? A worksheet visual may show givens from the question and the geometric setup, but requested answers must be shown only as symbols or question marks.

If the proposed TikZ code is perfectly accurate, respond with EXACTLY: "VALID".
If there is a flaw, write a short explanation of the mistake, followed by a corrected, fully compilable raw TikZ block wrapper. When correcting a sign or quadrant mismatch, rewrite the actual coordinate endpoints, axis bounds, or vector targets, not only the text labels. When correcting answer leakage, remove or replace the solved label with a symbolic label or ? while preserving the visual setup.

Original Worksheet Question Text:
{_raw_request_text(req)[:2800]}

Proposed TikZ Code Block:
{tikz[:6000]}
""".strip()


def _critic_acceptance_prompt(req: GenerateReq, original_tikz: str, corrected_tikz: str, critic_text: str) -> str:
    return f"""
You are a strict second-pass validator for Course Planner TikZ critic corrections.

The Course Planner LaTeX wrapper already defines these custom styles: cp axis, cp line, cp dashed, cp fill, cp point, cp label. A correction must NOT be accepted merely because another critic claimed those styles are undefined.

Return EXACTLY one of:
ACCEPT
REJECT: short reason

Accept only if the corrected TikZ is mathematically closer to the worksheet question, does not reveal requested answers, preserves the diagram's intended topic, and does not introduce avoidable layout/label issues. If uncertain, reject and keep the original.

Worksheet Question:
{_raw_request_text(req)[:1800]}

Original TikZ:
{original_tikz[:3000]}

First Critic Text:
{critic_text[:1200]}

Proposed Corrected TikZ:
{corrected_tikz[:3000]}
""".strip()


def _local_reject_critic_correction(req: GenerateReq, original_tikz: str, corrected_tikz: str, critic_text: str) -> str | None:
    verdict_low = str(critic_text or "").lower()
    corrected_low = str(corrected_tikz or "").lower()
    if "undefined" in verdict_low and "cp " in verdict_low and re.search(r"\bcp\s+(?:axis|line|dashed|fill|point|label)\b", verdict_low):
        return "critic falsely treated Course Planner cp styles as undefined"
    if re.search(r"\\(?:documentclass|usepackage|begin\s*\{document\}|end\s*\{document\})\b", corrected_tikz, re.I):
        return "correction included document/package wrapper commands"
    if "\\begin{tikzpicture" not in corrected_tikz:
        return "correction did not include a tikzpicture"
    issue = _semantic_visual_issue(req, corrected_tikz)
    if issue:
        return "correction failed semantic audit: " + issue
    original_has_z = bool(re.search(r"\{\$z\$\}|node\[[^\]]*\]\s*\{\$z\$\}", original_tikz))
    corrected_has_z = bool(re.search(r"\{\$z\$\}|node\[[^\]]*\]\s*\{\$z\$\}", corrected_tikz))
    if original_has_z and not corrected_has_z and _first_3d_vector(_raw_request_text(req)):
        return "correction removed the z-axis from a 3D vector diagram"
    return None


def _accept_critic_correction(req: GenerateReq, original_tikz: str, corrected_tikz: str, critic_text: str, source: str) -> tuple[bool, str]:
    local_reject = _local_reject_critic_correction(req, original_tikz, corrected_tikz, critic_text)
    if local_reject:
        return False, local_reject
    if not GEMINI_KEYS:
        if "deterministic-template" in source or "topic-template" in source:
            return False, "verifier unavailable for deterministic correction"
        return True, "accepted by local checks"
    try:
        verdict = _gemini(
            _critic_acceptance_prompt(req, original_tikz, corrected_tikz, critic_text),
            as_json=False,
            temperature=0.0,
        ).strip()
    except Exception as exc:
        if "deterministic-template" in source or "topic-template" in source:
            return False, "verifier unavailable: " + str(exc)[:160]
        return True, "accepted by local checks after verifier error: " + str(exc)[:120]
    if verdict == "ACCEPT":
        return True, "verified by second pass"
    return False, verdict[:220] or "second pass rejected correction"


def _verify_visual_accuracy(req: GenerateReq, tikz: str, source: str = "draft") -> tuple[str, str]:
    heuristic = _heuristic_visual_correction(req, tikz)
    if heuristic:
        corrected, reason = heuristic
        print(f"[critic] heuristic correction for {source}: {reason}", flush=True)
        return corrected, reason
    if not GEMINI_KEYS:
        print(f"[critic] skipped model critic for {source}: no Gemini key configured.", flush=True)
        return tikz, ""
    try:
        verdict = _gemini(_critic_prompt(req, tikz), as_json=False, temperature=0.05)
    except Exception as exc:
        print(f"[critic] model critic unavailable for {source}: {str(exc)[:220]}", flush=True)
        return tikz, ""
    if verdict.strip() == "VALID":
        print(f"[critic] {source}: VALID", flush=True)
        return tikz, ""
    corrected = _extract_tikz_block(verdict)
    if corrected:
        accepted, reason = _accept_critic_correction(req, tikz, corrected, verdict, source)
        if accepted:
            print(f"[critic] {source}: accepted corrected diagram ({reason}). Reason/log: {verdict[:800]}", flush=True)
            return corrected, verdict[:800]
        print(f"[critic] {source}: rejected critic correction ({reason}). Keeping draft. Reason/log: {verdict[:800]}", flush=True)
        return tikz, "critic correction rejected: " + reason
    print(f"[critic] {source}: flagged issue but returned no TikZ block; keeping draft. Response: {verdict[:800]}", flush=True)
    return tikz, verdict[:800]


def _enlarge_visual_code(req: GenerateReq, tikz: str) -> str:
    factor = 1.22 if req.target == "worksheet" else 1.1

    def scale_option(match):
        value = float(match.group(1))
        return f"scale={value * factor:.3g}"

    def cm_dim(match):
        key, value = match.group(1), float(match.group(2))
        return f"{key}={value * factor:.3g}cm"

    out = re.sub(r"scale\s*=\s*([0-9.]+)", scale_option, tikz)
    out = re.sub(r"\b(width|height)\s*=\s*([0-9.]+)\s*cm\b", cm_dim, out)
    out = re.sub(
        r"\\begin\{tikzpicture\}(?!\[)",
        lambda _m: rf"\begin{{tikzpicture}}[scale={factor:.3g}]",
        out,
        count=1,
    )
    return out


def _worksheet_answer_safe_tikz(req: GenerateReq, tikz: str) -> str:
    """Worksheet visuals should illustrate the setup, not solve the exercise.

    The frontend sends only the question text, but a template customizer can still
    over-label a diagram with a derived coordinate tuple, component expression, or
    magnitude. Strip those answer-style labels right before compilation.
    """
    if req.target != "worksheet":
        return tikz
    original_compact = re.sub(r"\s+", "", _raw_request_text(req))
    original_text = _raw_request_text(req)
    out = str(tikz or "")

    # A vector label like \vec{u}=(3,-2,6) is readable but often duplicates or
    # reveals the requested component form. Keep the arrow label only.
    out = re.sub(
        r"(\\vec\s*\{\s*[A-Za-z]{1,3}\s*\})\s*=\s*\([^$}\n;]*\)",
        r"\1",
        out,
    )
    # Never put the requested magnitude value on the worksheet diagram.
    out = re.sub(
        r"(\|\s*\\vec\s*\{\s*[A-Za-z]{1,3}\s*\}\s*\|)\s*=\s*[^$}\n;]+",
        r"\1",
        out,
    )

    def scrub_math_label(match: re.Match) -> str:
        body = match.group(1)
        clean = body
        clean = re.sub(
            r"(\\vec\s*\{\s*[A-Za-z]{1,3}\s*\})\s*=\s*\([^)]*\)",
            r"\1",
            clean,
        )
        clean = re.sub(
            r"(\|\s*\\vec\s*\{\s*[A-Za-z]{1,3}\s*\}\s*\|)\s*=\s*.*",
            r"\1",
            clean,
        )

        def tuple_guard(tuple_match: re.Match) -> str:
            tuple_text = tuple_match.group(0)
            tuple_compact = re.sub(r"\s+", "", tuple_text)
            return tuple_text if tuple_compact in original_compact else "?"

        clean = re.sub(r"\(\s*[-+]?\d+(?:\.\d+)?(?:\s*,\s*[-+]?\d+(?:\.\d+)?){1,2}\s*\)", tuple_guard, clean)

        unit_component_answer = (
            re.search(r"\\(?:vec|mathbf)\s*\{\s*[ijk]\s*\}", clean)
            and re.search(r"[-+]?\d", clean)
            and ("+" in clean or "-" in clean)
        )
        # Judge what follows the "=": a rate written \frac{dr}{dt} = 3 cm/s is
        # a given (the guard hid it as ?), a \frac or \sqrt value is a result
        # unless the question states its numbers, and a rate's value the
        # question does not state is the answer (\frac{dA}{dt} = 60\pi).
        lhs, _eq, rhs = clean.partition("=")

        def plain(text: str) -> str:
            return re.sub(r"\\(?:mathrm|text|,|;|!)|[\s{}$]", "", text)
        result_stated = bool(plain(rhs)) and plain(rhs) in plain(original_text)
        rhs_numbers = re.findall(r"\d+(?:\.\d+)?", rhs)
        rate_stated = bool(rhs_numbers) and all(
            float(n) in {float(x) for x in re.findall(r"\d+(?:\.\d+)?", original_text)} for n in rhs_numbers)
        derived_expression = (
            "=" in clean
            and not re.search(r"\^\s*\\circ", clean)
            and (
                (re.search(r"\\(?:sqrt|frac|pm)|\([^)]*,[^)]*\)", rhs) and not result_stated)
                or (re.search(r"\\frac\s*\{\s*d", lhs) and re.search(r"\d", rhs) and not rate_stated)
            )
        )
        if unit_component_answer or derived_expression:
            clean = "?"
        return "{$" + clean.strip() + "$}"

    out = re.sub(r"\{\$((?:[^{}]|\{[^{}]*\}){1,180})\$\}", scrub_math_label, out)
    if out != tikz:
        print("[answer-guard] stripped answer-style labels from worksheet TikZ", flush=True)
    return out


def _verified_render(req: GenerateReq, tikz: str, source: str = "draft", run_critic: bool = True) -> dict:
    tikz = _worksheet_answer_safe_tikz(req, tikz)
    # The semantic checks guard model drawings (raw arcs a model drew outside
    # an angle, a stray generic triangle). A catalog template's structure is
    # fixed, and its triangles mark angles with arcs computed from the shape:
    # the arc check rejected every triangle template.
    semantic_issue = None if source.startswith("catalog") else _semantic_visual_issue(req, tikz)
    if semantic_issue:
        return {"ok": False, "error": semantic_issue, "log": semantic_issue}
    enlarged_tikz = _enlarge_visual_code(req, tikz)
    # Catalog templates are structurally trusted (the model only filled values), so
    # the model critic is skipped for them; bespoke Gemini TikZ still runs the critic.
    if run_critic:
        checked_tikz, critic_note = _verify_visual_accuracy(req, enlarged_tikz, source=source)
    else:
        checked_tikz, critic_note = enlarged_tikz, ""
    if checked_tikz != enlarged_tikz:
        checked_tikz = _worksheet_answer_safe_tikz(req, checked_tikz)
        checked_tikz = _enlarge_visual_code(req, checked_tikz)
        semantic_issue = _semantic_visual_issue(req, checked_tikz)
        if semantic_issue:
            return {"ok": False, "error": semantic_issue, "log": semantic_issue}
    rendered = _render(RenderReq(code=checked_tikz, format=req.format, theme=req.theme, target=req.target, layout=True))
    if rendered.get("layout", {}).get("issues"):
        # Catalog and exact renderers fix their own label placement; the model
        # cannot move these labels, so collisions are reported, not repaired.
        # A catalog picture is reproducible from its catalog-params event; its
        # code would only spend the trace's code budget.
        code = {} if source.startswith("catalog") else {"tikz": checked_tikz}
        _diagnostic("layout", _layout_summary(rendered["layout"]), source=source, **code)
    if rendered.get("ok"):
        rendered["tikz"] = checked_tikz
        if critic_note:
            rendered["critic"] = critic_note
    elif critic_note:
        rendered["critic"] = critic_note
    return rendered


# ---- Render-based layout check ------------------------------------------------
# The document gets a second page: the same picture with every node's text made
# invisible (fills kept). Page 1 logs each node's four corners and inner sep, so
# ink inside a label's text box on page 2 is a line crossing that label, while a
# white-filled label drawn over a line correctly counts as clear. Overlapping
# labels come straight from the logged boxes; pdftotext names the labels.
_LAYOUT_INSTRUMENT = r"""
\makeatletter
\newif\ifcp@log \cp@logtrue
\newcount\cp@count \newcount\cp@depth
\def\cp@acc{}\def\cp@isx{0pt}\def\cp@isy{0pt}
\def\cp@corner#1#2{\pgfpointanchor{#1}{#2}\edef\cp@acc{\cp@acc\space\strip@pt\pgf@x\space\strip@pt\pgf@y}}
\def\cp@lognode{\ifcp@log\pgfutil@ifundefined{pgf@sh@ns@\tikzlastnode}{}{\cp@lognodeyes}\fi}
\def\cp@lognodeyes{\begingroup\pgftransformreset\def\cp@acc{}%
  \cp@corner{\tikzlastnode}{south west}\cp@corner{\tikzlastnode}{south east}%
  \cp@corner{\tikzlastnode}{north east}\cp@corner{\tikzlastnode}{north west}%
  \typeout{CPNODE \tikzlastnode\space|\cp@acc\space\cp@isx\space\cp@isy\space\iftikz@is@matrix M\else N\fi}%
  \endgroup}
% Angle-pic labels are created as \node() with an empty name, so nothing can
% find them afterwards; this is the angles library's foreground step with a
% unique name given to that label node.
\def\tikz@lib@angle@foreground#1--#2--#3\pgf@stop{%
  \path [name prefix ..] [pic actions, fill=none, shade=none]
  ([shift={(\tikz@start@angle@temp:\tikz@lib@angle@rad pt)}]#2.center)
    arc [start angle=\tikz@start@angle@temp, end
    angle=\tikz@end@angle@temp, radius=\tikz@lib@angle@rad pt];
  \ifx\tikzpictext\relax\else%
    \global\advance\cp@count by 1\relax
    \def\pgf@temp{\node(cpa\the\cp@count)[name prefix
      ..,at={([shift={({.5*\tikz@start@angle@temp+.5*\tikz@end@angle@temp}:\pgfkeysvalueof{/tikz/angle
            eccentricity}*\tikz@lib@angle@rad pt)}]#2.center)}]}
    \expandafter\pgf@temp\expandafter[\tikzpictextoptions]{\tikzpictext};%
  \fi
}%
\tikzset{every node/.append style={
  execute at begin node={\xdef\cp@isx{\the\dimexpr\pgfkeysvalueof{/pgf/inner xsep}\relax}\xdef\cp@isy{\the\dimexpr\pgfkeysvalueof{/pgf/inner ysep}\relax}},
  append after command={\pgfextra{\cp@lognode}}},
  % only the outermost picture ends the log: pgfplots draws legend images as
  % nested pictures
  every picture/.append style={execute at begin picture={\global\advance\cp@depth by 1\relax},
    execute at end picture={\global\advance\cp@depth by -1\relax
    \ifnum\cp@depth=0\ifcp@log\begingroup\pgftransformreset\def\cp@acc{}%
    \cp@corner{current bounding box}{south west}\cp@corner{current bounding box}{north east}%
    \typeout{CPBBOX\cp@acc}\endgroup\global\cp@logfalse\fi\fi}}}
\makeatother
"""
_LAYOUT_BORDER_PT = 6.0   # standalone border in _template
_LAYOUT_DPI = 150
_LAYOUT_INK = 170         # grey level counted as ink: black and gray lines, not light grids or fills
_LAYOUT_MIN_INK = 8       # pixels of ink inside a text box before a label counts as crossed
_LAYOUT_EDGE_PT = 0.5     # tolerance at the text box edge: a tick mark ending at its label is normal
_LAYOUT_MIN_TEXT = 0.07   # share of its text box a label's own glyphs must darken (visible labels measured 0.10+; a clipped one 0.045)
_LAYOUT_MIN_SPAN = 0.45   # share of its box width the glyphs of a label with 2+ characters on a line must span (visible 0.64+; clipped 0.09-0.36)


def _layout_document(doc: str) -> str:
    head, body = doc.split("\\begin{document}", 1)
    body = body.rsplit("\\end{document}", 1)[0]
    hidden = "{\\tikzset{every node/.append style={text opacity=0}}" + body + "}\n"
    return head + _LAYOUT_INSTRUMENT + "\\begin{document}" + body + "\n" + hidden + "\\end{document}"


def _layout_nodes(log: str) -> tuple[list, tuple | None]:
    """(nodes, bbox) from the instrumented log; nodes are (name, corners, isx, isy)."""
    nodes, after_cells = [], False
    for m in re.finditer(r"^CPNODE (\S+) \|(.*)$", log, re.M):
        vals = m.group(2).split()
        if len(vals) < 11:
            continue
        # Matrix cells (legends) are logged in the matrix's own frame before it is
        # placed; the matrix itself is the node logged right after its cells.
        if vals[10] == "M":
            after_cells = True
            continue
        if after_cells:
            after_cells = False
            continue
        if m.group(1).startswith("cpm"):
            continue  # invisible copies typeset only to measure a label
        c = [float(v) for v in vals[:8]]
        isx, isy = (float(v.replace("pt", "")) for v in vals[8:10])
        nodes.append((m.group(1), [(c[0], c[1]), (c[2], c[3]), (c[4], c[5]), (c[6], c[7])], isx, isy))
    bb = re.search(r"^CPBBOX (.*)$", log, re.M)
    bbox = tuple(float(v) for v in bb.group(1).split()) if bb else None
    return nodes, bbox


def _layout_inset(quad: list, dx: float, dy: float) -> list | None:
    """Shrink a (possibly rotated) node box along its own axes; None if nothing is left."""
    (x0, y0), (x1, y1), _, (x3, y3) = quad
    lu, lv = math.hypot(x1 - x0, y1 - y0), math.hypot(x3 - x0, y3 - y0)
    if lu <= 2 * dx or lv <= 2 * dy:
        return None
    ux, uy, vx, vy = (x1 - x0) / lu, (y1 - y0) / lu, (x3 - x0) / lv, (y3 - y0) / lv
    return [(x0 + ux * a + vx * b, y0 + uy * a + vy * b)
            for a, b in ((dx, dy), (lu - dx, dy), (lu - dx, lv - dy), (dx, lv - dy))]


def _layout_inside(poly: list, x: float, y: float) -> bool:
    sign = None
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if cross:
            if sign is None:
                sign = cross > 0
            elif (cross > 0) != sign:
                return False
    return True


def _layout_area(poly: list) -> float:
    n = len(poly)
    return abs(sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))) / 2 if n > 2 else 0.0


def _layout_overlap(a: list, b: list) -> float:
    """Area shared by two convex quads (Sutherland-Hodgman clipping)."""
    def ccw(poly):
        return poly if sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                           for i in range(len(poly))) >= 0 else poly[::-1]
    out, clipper = ccw(a), ccw(b)
    for i in range(len(clipper)):
        (ax, ay), (bx, by) = clipper[i], clipper[(i + 1) % len(clipper)]
        side = lambda p: (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) >= 0
        def cut(p, q):
            d = (p[0] - q[0]) * (ay - by) - (p[1] - q[1]) * (ax - bx)
            t = ((p[0] - ax) * (ay - by) - (p[1] - ay) * (ax - bx)) / d
            return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
        points, out = out, []
        for j in range(len(points)):
            p, q = points[j], points[(j + 1) % len(points)]
            if side(q):
                if not side(p):
                    out.append(cut(p, q))
                out.append(q)
            elif side(p):
                out.append(cut(p, q))
        if not out:
            return 0.0
    return _layout_area(out)


def _layout_line_chars(words: list) -> int:
    """Characters on the longest text line of a label (words as pdftotext boxes):
    \\frac{3}{9} is two one-character lines, dr/dt two of two."""
    lines: list[list] = []
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        mid, tall = (w[1] + w[3]) / 2, w[3] - w[1]
        if lines and abs(mid - lines[-1][0]) < 0.5 * tall:
            lines[-1][1] += len(w[4].replace(" ", ""))
        else:
            lines.append([mid, len(w[4].replace(" ", ""))])
    return max((n for _mid, n in lines), default=0)


def _layout_analyse(log: str, words: list, raster: tuple, shown: bytes | None = None) -> dict:
    """Label collisions from the page-1 log, the page-1 words (bp, top-left origin)
    and the text-hidden page-2 raster (width, height, grey bytes at _LAYOUT_DPI).
    With the page-1 raster (`shown`, same size), a label whose glyphs darken
    almost nothing is reported as covered, e.g. by a fill drawn after it."""
    nodes, bbox = _layout_nodes(log)
    if not bbox:
        return {"labels": 0, "issues": []}
    llx, _lly, _urx, ury = bbox
    width, height, pixels = raster
    k = _LAYOUT_DPI / 72.27

    def to_px(x, y):
        return ((x - llx + _LAYOUT_BORDER_PT) * k, (ury + _LAYOUT_BORDER_PT - y) * k)

    def to_bp(x, y):
        return ((x - llx + _LAYOUT_BORDER_PT) * 72 / 72.27, (ury + _LAYOUT_BORDER_PT - y) * 72 / 72.27)

    labels = []
    for _name, quad, isx, isy in nodes:
        box = _layout_inset(quad, isx + _LAYOUT_EDGE_PT, isy + _LAYOUT_EDGE_PT)
        if not box:
            continue  # empty nodes: points, coordinates
        box_bp = [to_bp(*p) for p in box]
        inside = [w for w in words if _layout_inside(box_bp, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2)]
        text = " ".join(w[4] for w in inside).strip()
        if text:
            labels.append((text, box, _layout_line_chars(inside)))
    issues = []
    for text, box, line_chars in labels:
        poly = [to_px(*p) for p in box]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        (x0, y0), (x1, y1) = poly[0], poly[1]
        run = (x1 - x0) ** 2 + (y1 - y0) ** 2 or 1.0
        ink = glyphs = area = 0
        low, high = 1.0, 0.0  # extent of the visible glyphs along the text direction
        for yy in range(max(0, int(min(ys))), min(height, int(max(ys)) + 1)):
            row = yy * width
            for xx in range(max(0, int(min(xs))), min(width, int(max(xs)) + 1)):
                if not _layout_inside(poly, xx + 0.5, yy + 0.5):
                    continue
                area += 1
                if pixels[row + xx] < _LAYOUT_INK:
                    ink += 1
                if shown is not None and shown[row + xx] + 60 < pixels[row + xx]:
                    glyphs += 1
                    along = ((xx + 0.5 - x0) * (x1 - x0) + (yy + 0.5 - y0) * (y1 - y0)) / run
                    low, high = min(low, along), max(high, along)
        if ink >= _LAYOUT_MIN_INK:
            issues.append({"kind": "line-through-label", "labels": [text], "ink": ink})
        # Glyph extent is measured between pixel centres, a pixel short of the
        # real extent, which is a fifth of a one-digit label's box.
        span = high - low + 1 / math.sqrt(run)
        if shown is not None and (glyphs < max(4, _LAYOUT_MIN_TEXT * area)
                                  or (line_chars >= 2 and span < _LAYOUT_MIN_SPAN)):
            # covered by something drawn later, or clipped (e.g. by an axis window):
            # too little of it shows, or what shows spans only part of its box.
            # The span test needs two characters on one line: a stacked
            # one-digit fraction is one digit wide in a padded box (visible 3/9
            # measured 0.46 and was reported as cut off).
            issues.append({"kind": "label-hidden", "labels": [text]})
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            shared = _layout_overlap(labels[i][1], labels[j][1])
            if shared > 2 and shared > 0.05 * min(_layout_area(labels[i][1]), _layout_area(labels[j][1])):
                issues.append({"kind": "labels-overlap", "labels": [labels[i][0], labels[j][0]], "area": round(shared, 1)})
    return {"labels": len(labels), "issues": issues}


def _layout_summary(layout: dict) -> str:
    parts = []
    for issue in layout.get("issues", []):
        if issue["kind"] == "line-through-label":
            parts.append(f'a line runs through the label "{issue["labels"][0]}"')
        elif issue["kind"] == "label-hidden":
            parts.append(f'the label "{issue["labels"][0]}" is covered or cut off')
        else:
            parts.append(f'the labels "{issue["labels"][0]}" and "{issue["labels"][1]}" overlap')
    return "; ".join(parts)


def _layout_check(work: Path, stem: str) -> dict | None:
    """Run the analysis on a compiled instrumented document; None if it cannot."""
    log = (work / f"{stem}.log").read_text(encoding="utf-8", errors="replace")
    pdf = work / f"{stem}.pdf"
    pages = []
    for page in (1, 2):
        raster = work / f"{stem}_layout{page}"
        if _run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(_LAYOUT_DPI), "-gray", "-singlefile",
                 str(pdf), str(raster)], work).returncode:
            return None
        data = raster.with_suffix(".pgm").read_bytes()
        head = re.match(rb"P5\s+(\d+)\s+(\d+)\s+(\d+)\s", data)
        if not head:
            return None
        pages.append((int(head.group(1)), int(head.group(2)), data[head.end():]))
    if pages[0][:2] != pages[1][:2]:
        return None
    text = _run(["pdftotext", "-f", "1", "-l", "1", "-bbox", str(pdf), "-"], work).stdout
    words = [tuple(float(v) for v in m.groups()[:4]) + (html.unescape(m.group(5)),)
             for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', text)]
    return _layout_analyse(log, words, pages[1], shown=pages[0][2])


_PREVIEW_DPI = 110            # small enough for the readiness check, large enough to read labels
_PREVIEW_MAX_BYTES = 400_000


def _preview_png(work: Path, pdf_path: Path) -> str | None:
    """Page 1 as a small PNG (base64) for the readiness check to look at; None
    when it cannot be made, and the check then reads the code alone."""
    out = work / "preview.png"
    result = _run(["pdftocairo", "-f", "1", "-l", "1", "-singlefile", "-png", "-r", str(_PREVIEW_DPI),
                   str(pdf_path), str(out.with_suffix(""))], work)
    if result.returncode != 0 or not out.exists() or out.stat().st_size > _PREVIEW_MAX_BYTES:
        return None
    return base64.b64encode(out.read_bytes()).decode("ascii")


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
        document = _template(tikz, req.theme, req.target)
        pdflatex = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", tex_path.name]
        inspect = req.layout and LAYOUT_CHECK_ENABLED
        tex_path.write_text(_layout_document(document) if inspect else document, encoding="utf-8")
        compile_result = _run(pdflatex, work)
        if inspect and (compile_result.returncode != 0 or not pdf_path.exists()):
            # The instrumentation must never cost a diagram: compile it plainly.
            inspect = False
            pdf_path.unlink(missing_ok=True)
            tex_path.write_text(document, encoding="utf-8")
            compile_result = _run(pdflatex, work)
        if compile_result.returncode != 0 or not pdf_path.exists():
            return {
                "ok": False,
                "error": "TikZ compile failed.",
                "log": _plain_log(compile_result.stdout),
            }
        layout = None
        if inspect:
            try:
                layout = _layout_check(work, stem)
            except Exception as exc:  # a failed check reports nothing; the render stands
                print(f"[layout] check failed: {str(exc)[:160]}", flush=True)
        preview = _preview_png(work, pdf_path) if req.preview else None

        if req.format == "png":
            convert_result = _run(
                ["pdftocairo", "-f", "1", "-l", "1", "-singlefile", "-png", "-r", "180", str(pdf_path), str(png_path.with_suffix(""))],
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
            result = {
                "ok": True,
                "format": "png",
                "mime": "image/png",
                "base64": payload,
            }
            if layout is not None:
                result["layout"] = layout
            if preview:
                result["preview_png"] = preview
            return result

        convert_result = _run(["pdf2svg", str(pdf_path), str(svg_path), "1"], work)
        if convert_result.returncode != 0 or not svg_path.exists():
            return {
                "ok": False,
                "error": "SVG conversion failed.",
                "log": _plain_log(convert_result.stdout),
            }
        if svg_path.stat().st_size > MAX_OUTPUT_BYTES:
            return {"ok": False, "error": "Rendered SVG is too large."}
        svg = svg_path.read_text(encoding="utf-8", errors="replace")
        result = {
            "ok": True,
            "format": "svg",
            "mime": "image/svg+xml",
            "svg": svg,
        }
        if layout is not None:
            result["layout"] = layout
        if preview:
            result["preview_png"] = preview
        return result
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
        "lanes": _lane_report(),
        "catalog_available": CATALOG_AVAILABLE,
        "catalog_enabled": CATALOG_ENABLED,
        "elementary_available": elementary_diagram is not None,
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
    """Customize and render a KEYWORD-MATCHED deterministic diagram.

    IMPORTANT: this must NOT force a generic triangle. A question with no matching
    shape (a quadratic, an algebra proof, a "state the property" question) should
    get NO visual rather than an irrelevant triangle repeated across the worksheet.
    So we only fall back to a template whose own trigger actually matches the
    request; if nothing matches, we return None and the question stays blank.
    """
    fallback = _deterministic_template(req, generic=False)
    if not fallback:
        return None
    rendered = _customize_template_and_render(req, fallback, source="fallback-template")
    if rendered.get("ok"):
        rendered["fallback"] = "customized-deterministic"
        return rendered
    return None


def _catalog_param_prompt(req: GenerateReq, spec: dict, repair_log: str = "", previous_params: dict | None = None,
                          caption: str = "", skeleton: str = "") -> str:
    # The model sees the template itself (caption + skeleton), not just key names:
    # filling blanks for an unseen diagram produced incoherent values, and keyword
    # routing sometimes hands over a template whose diagram FAMILY is wrong for the
    # question. The '_fit' verdict lets the model reject those, so the caller can
    # fall through to the reference-guided path (templates as guides, not a cage).
    return json.dumps({
        "role": "Return only minified JSON. Do NOT return TikZ. First judge whether this fixed TikZ template fits the question, then fill its parameter values.",
        "question": _raw_request_text(req)[:2600],
        "template": spec["template_id"],
        "template_caption": caption[:300],
        "template_skeleton": skeleton[:2000],
        "keys": spec["keys"],
        "fields": spec["fields"],
        "defaults": spec["defaults"],
        "rules": [
            "First: judge fit at the diagram-FAMILY level. Set key '_fit' to 'yes' when this kind of diagram genuinely illustrates the question (schematic/generic shapes and example curves are fine). Set '_fit' to 'no' when the diagram type is wrong for the question (e.g. vector arrows for a tangent-line question, a statistics bell curve for a 'normal line to a curve' question, a journey diagram for two objects leaving one point) OR when the template's FIXED geometry contradicts the question's specific values and cannot be fixed by filling labels - e.g. this skeleton draws the cross-product arrow pointing UP, but the question's product actually points DOWN (j x i = -k), or the skeleton's fixed orientation/sign disagrees with the givens. Add '_why' with a short reason.",
            "Then return the same flat JSON object with exactly the listed keys; every value is a string. If '_fit' is 'no', the other keys may be omitted.",
            "type 'number' -> a plain number as a string; type 'label' -> a short LaTeX label, preserving backslashes as JSON escapes (\\\\vec{u}, \\\\theta, \\\\circ); type 'tikz' -> only the specific lines the field describes, or an empty string.",
            "Use only values given in the question or symbolic labels. Never place a solved final answer, computed magnitude, solved coordinate tuple, or equation result on a worksheet diagram; use ? or a symbol for any requested unknown.",
            "No markdown fences and no commentary.",
        ],
        "previous_params": previous_params or {},
        "repair_log": repair_log[:1200],
    }, ensure_ascii=False)


def _plain_vector_symbol(name: str) -> str:
    name = str(name or "").strip()
    if not name:
        return r"\vec{u}"
    m = re.match(r"([A-Za-z])\s*([0-9]?)$", name)
    if not m:
        return r"\vec{" + re.sub(r"[^A-Za-z]", "", name[:1] or "u") + "}"
    base, sub = m.groups()
    return rf"\vec{{{base}}}" + (rf"_{{{sub}}}" if sub else "")


def _vector_names_from_question(req: GenerateReq, default: tuple[str, str] = ("u", "v")) -> tuple[str, str]:
    text = _question_text(req)
    if re.search(r"\bF\s*_?\s*1\b", text, re.I) and re.search(r"\bF\s*_?\s*2\b", text, re.I):
        return "F1", "F2"
    patterns = [
        r"\bvectors?\s+\\?vec\s*\{?\s*([A-Za-z])\s*\}?\s+and\s+\\?vec\s*\{?\s*([A-Za-z])\s*\}?",
        r"\bvectors?\s+([A-Za-z])\s+and\s+([A-Za-z])\b",
        r"\bunit\s+vectors?\s+([A-Za-z])\s+and\s+([A-Za-z])\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return (
                re.sub(r"\s+", "", m.group(1)).replace("_", ""),
                re.sub(r"\s+", "", m.group(2)).replace("_", ""),
            )
    expr = re.search(r"\b([A-Za-z])\s*[-+]\s*([A-Za-z])\b", text)
    if expr:
        return expr.group(1), expr.group(2)
    return default


def _two_magnitudes_from_question(req: GenerateReq) -> tuple[str, str]:
    text = _question_text(req)
    m = re.search(
        r"\bmagnitudes?\s+(?:of\s+)?(?:are\s+|is\s+)?([-+]?\d+(?:\.\d+)?)\s*(?:and|,)\s*([-+]?\d+(?:\.\d+)?)",
        text,
        re.I,
    )
    if m:
        return m.group(1), m.group(2)
    nums = re.findall(r"\bF\s*_?\s*[12]\s*=\s*([-+]?\d+(?:\.\d+)?\s*[A-Za-z]*)", text, re.I)
    if len(nums) >= 2:
        return nums[0].replace(" ", ""), nums[1].replace(" ", "")
    return "", ""


def _angle_from_question(req: GenerateReq, default: str = "") -> str:
    text = _question_text(req)
    m = re.search(r"\bangle\b[^.?!;]{0,80}?([-+]?\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|\\circ)?", text, re.I)
    if not m:
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|\\circ)", text, re.I)
    if not m:
        deg = r"(?:degrees?|deg|[°º˚∘]|Â°|âˆ˜|\\circ|\^?\\circ)"
        m = re.search(r"\bangle\b[^.?!;]{0,80}?([-+]?\d+(?:\.\d+)?)\s*" + deg + r"?", text, re.I)
        if not m:
            m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*" + deg, text, re.I)
    return m.group(1) if m else default


def _speed_after_word(text: str, word: str) -> str:
    m = re.search(r"\b" + re.escape(word) + r"\b[^.?!;]{0,80}?([-+]?\d+(?:\.\d+)?)\s*(km\s*/?\s*h|km/h|m\s*/?\s*s|m/s|mph|knots?)?", text, re.I)
    if not m:
        return ""
    unit = re.sub(r"\s+", "", m.group(2) or "")
    return m.group(1) + (unit if unit else "")


def _bearing_n_e(text: str) -> tuple[str, str, str]:
    m = re.search(r"\bN\s*([-+]?\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|\\circ)?\s*E\b", text, re.I)
    if not m:
        return "60", "75", "30^\\circ"
    bearing = m.group(1)
    airang = 90 - float(bearing)
    mid = (90 + airang) / 2
    return (
        str(airang).rstrip("0").rstrip("."),
        str(mid).rstrip("0").rstrip("."),
        bearing + "^\\circ",
    )


def _bearing_values_from_text(text: str) -> list[int]:
    bearings = [
        int(float(x)) % 360
        for x in re.findall(
            r"\b(?:bearing|heading)\s*(?:of|=|is|at)?\s*0*([0-9]{1,3})(?:\s*(?:degrees?|deg|\\circ))?",
            text,
            re.I,
        )
    ]
    if not bearings:
        bearings = [
            int(float(x)) % 360
            for x in re.findall(
                r"\b0*([0-9]{2,3})\s*(?:degrees?|deg|\\circ)?\s*(?:bearing|from north|clockwise)",
                text,
                re.I,
            )
        ]
    return bearings[:2]


def _distance_labels_from_text(text: str) -> list[str]:
    labels: list[str] = []
    for num, unit in re.findall(
        # not a speed: "40 km/h" is no distance
        r"\b([-+]?\d+(?:\.\d+)?)\s*(nautical\s+miles?|miles?|km|cm|mm|nmi|nm|mi|yd|ft|m)\b(?!\s*/|\s+per\b)",
        text,
        re.I,
    ):
        unit_tex = re.sub(r"\s+", r"\\,", unit.strip().lower())
        labels.append(rf"{num}\,\mathrm{{{unit_tex}}}")
    return labels[:2]


def _clean_number(value: float | int) -> str:
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _label_with_magnitude(symbol: str, mag: str) -> str:
    return symbol + (f"={mag}" if mag else "")


_NUM = r"\s*(-?\d+(?:\.\d+)?)\s*"


def _named_vectors(text: str) -> list[tuple[str, tuple[float, ...]]]:
    """Named 2D/3D vectors given by components, in question order: u = (2, 1),
    \\vec{v} = <1, -2, 3>, w = [0, 4] or \\langle 1, 2 \\rangle."""
    text = _repair_transport_escapes(text).replace("−", "-")
    found: list[tuple[str, tuple[float, ...]]] = []
    for m in re.finditer(
        r"(\\+vec\s*\{?\s*)?\b([A-Za-z])(?:_?\{?(\d)\}?)?\s*\}?\s*=\s*"
        r"(?:\(|\[|<|⟨|\\left\s*[(<\[]|\\langle)" + _NUM + "," + _NUM + r"(?:," + _NUM + r")?"
        r"(?:\)|\]|>|⟩|\\right\s*[)>\]]|\\rangle)",
        text,
    ):
        if m.group(2).isupper() and not m.group(1):
            continue  # "A = (1, 2)" is usually a point, not a vector
        name = m.group(2) + (m.group(3) or "")
        coords = tuple(float(g) for g in m.groups()[3:] if g is not None)
        if all(name != other for other, _coords in found):
            found.append((name, coords))
    return found


def _arith_tree(expr: str, var: str = ""):
    """A plain arithmetic expression in one variable (pi and implicit
    multiplication allowed: 2(x - pi/4), 0.5t, pi t/6, x^2 - 4) as a Python
    AST, or None for anything else. Nothing is ever executed: only numbers,
    the variable and + - * / ^ are accepted."""
    import ast
    text = str(expr or "").replace("−", "-").replace("\\pi", " pi ").replace("π", " pi ")
    text = re.sub(r"\\(?:left|right)", "", text).replace("\\cdot", "*").replace("{", "(").replace("}", ")")
    text = re.sub(r"\\frac\s*\(([^()]*)\)\s*\(([^()]*)\)", r"((\1)/(\2))", text).replace("²", "^2").replace("³", "^3")
    if re.search(r"[^0-9A-Za-z.+\-*/^()\s]", text):
        return None
    names = set(re.findall(r"[A-Za-z]+", text)) - {"pi"}
    if names - ({var} if var else set()):
        return None
    tokens = re.findall(r"\d+(?:\.\d+)?|\.\d+|pi|[A-Za-z]|[-+*/^()]", text)
    out: list[str] = []
    for tok in tokens:
        if out and (re.fullmatch(r"[\d.]+|pi|[A-Za-z]|\)", out[-1]) and re.fullmatch(r"[\d.]+|pi|[A-Za-z]|\(", tok)):
            out.append("*")
        out.append("**" if tok == "^" else tok)
    try:
        tree = ast.parse("".join(out), mode="eval").body
    except SyntaxError:
        return None
    ok = (ast.Constant, ast.Name, ast.UnaryOp, ast.BinOp, ast.USub, ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Load)
    if not all(isinstance(n, ok) for n in ast.walk(tree)):
        return None
    if any(isinstance(n, ast.Constant) and not isinstance(n.value, (int, float)) for n in ast.walk(tree)):
        return None
    return tree


def _arith_eval(tree, at: float = 0.0) -> float | None:
    import ast

    def ev(node):
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            return math.pi if node.id == "pi" else at
        if isinstance(node, ast.UnaryOp):
            return -ev(node.operand) if isinstance(node.op, ast.USub) else ev(node.operand)
        a, b = ev(node.left), ev(node.right)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
        if abs(b) > 6 or abs(a) > 1e6:
            raise ValueError("power too large")
        return a ** b
    try:
        value = ev(tree)
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    return value if isinstance(value, float) and math.isfinite(value) else None


def _arith_pgf(tree, var: str) -> str:
    """The expression for pgfplots in x, every operation parenthesised (pgfmath
    reads -x^2 as (-x)^2)."""
    import ast
    if isinstance(tree, ast.Constant):
        return _clean_number(tree.value)
    if isinstance(tree, ast.Name):
        return "pi" if tree.id == "pi" else "x"
    if isinstance(tree, ast.UnaryOp):
        return ("(-" if isinstance(tree.op, ast.USub) else "(") + _arith_pgf(tree.operand, var) + ")"
    op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^"}[type(tree.op)]
    return "(" + _arith_pgf(tree.left, var) + op + _arith_pgf(tree.right, var) + ")"


def _arith_value(expr: str, var: str = "", at: float = 0.0) -> float | None:
    tree = _arith_tree(expr, var)
    return None if tree is None else _arith_eval(tree, at)


def _sinusoid_from_text(text: str) -> dict[str, float] | None:
    """A, B, C, D of the question's y = A sin(B(x - C)) + D, a cosine converted
    to that sine form (cos u = sin(u + pi/2)), so the graph starts where the
    question's function does. None unless every sine or cosine in the text is
    in such an equation and they all agree (a worksheet's diagram description
    repeats the question's equation)."""
    text = _repair_transport_escapes(str(text or "")).replace("−", "-")
    calls = [c.start(1) for c in re.finditer(r"(?<![A-Za-z])(sin|cos)\s*(?:\\left)?\(", text)]
    waves = [(m.start(2), _sinusoid_at(text, m)) for m in re.finditer(r"=\s*([^=]*?)\\?(?<![A-Za-z])(sin|cos)\s*(?:\\left)?\(", text)]
    if not calls or sorted(pos for pos, _w in waves) != calls or any(w is None for _p, w in waves):
        return None
    first = waves[0][1]
    if any(any(abs(w[k] - first[k]) > 1e-9 for k in first) for _p, w in waves[1:]):
        return None
    return first


def _sinusoid_at(text: str, m: re.Match) -> dict[str, float] | None:
    lead, fn = m.group(1), m.group(2)
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    if depth:
        return None
    arg = re.sub(r"\\right$", "", text[m.end():i - 1].strip())
    tail = re.match(r"\s*([-+]\s*\d+(?:\.\d+)?)?(?=\s*(?:[,.;:?$]|\s+[A-Za-z]|$))", text[i:])
    if tail is None:
        return None
    lead_m = re.fullmatch(r"\s*(?:(\d+(?:\.\d+)?)\s*([-+])\s*)?([-+]?\s*\d*(?:\.\d+)?)\s*\*?\s*", lead)
    if not lead_m:
        return None
    var_m = re.search(r"\b([a-zA-Z])\b|(?<=\d)([a-zA-Z])\b|θ", arg.replace("pi", " "))
    var = (var_m.group(1) or var_m.group(2)) if var_m and (var_m.group(1) or var_m.group(2)) else ""
    if not var:
        return None
    f0, f1 = _arith_value(arg, var, 0.0), _arith_value(arg, var, 1.0)
    f2 = _arith_value(arg, var, 2.0)
    if f0 is None or f1 is None or f2 is None or abs((f2 - f1) - (f1 - f0)) > 1e-9:
        return None  # not linear in the variable
    b = f1 - f0
    if abs(b) < 1e-9:
        return None
    coef = lead_m.group(3).replace(" ", "")
    a = -1.0 if coef == "-" else 1.0 if coef in ("", "+") else float(coef)
    d = 0.0
    if lead_m.group(1):  # 4 + 2 sin(3x), 4 - 2 sin(3x)
        d = float(lead_m.group(1))
        if lead_m.group(2) == "-":
            a = -a
    if tail.group(1):
        d += float(tail.group(1).replace(" ", ""))
    c = -f0 / b
    if b < 0:  # sin(-u) = -sin(u), cos(-u) = cos(u)
        b = -b
        if fn == "sin":
            a = -a
    if fn == "cos":
        c -= math.pi / (2 * b)
    return {"A": a, "B": b, "C": c, "D": d}


def _integral_overrides(req: GenerateReq, params: dict) -> dict[str, str]:
    """definite_integral_shaded from the question: its bounds, its function when
    it states one, and when it only says where the curve crosses the x-axis, a
    curve that crosses exactly there (the model drew one crossing at x = 2 for
    a stated x = 1). The window fits the curve, stated crossings get ticks, and
    the area label sits in the largest region above the axis."""
    text = _request_text(req)
    question = _question_text(req)
    num = r"(-?\d+(?:\.\d+)?)"
    out: dict[str, str] = {}
    bounds = (re.search(r"\bfrom\s+x\s*=\s*" + num + r"\s+to\s+x\s*=\s*" + num, question, re.I)
              or re.search(r"\bbetween\s+x\s*=\s*" + num + r"\s+and\s+x\s*=\s*" + num, question, re.I)
              or re.search(r"\bfrom\s+" + num + r"\s+to\s+" + num + r"\b", question, re.I))
    lo_hi = None
    # an accumulation function: F(x) = integral of f(t) from a to x is the area
    # up to a moving endpoint, drawn against t with the endpoint labelled x
    accumulate = re.search(r"\bintegral\s+of\s+(.+?)\s+(?:dt\s+)?from\s+(-?\d+(?:\.\d+)?)\s+to\s+([a-z])\b", question, re.I)
    if accumulate and accumulate.group(3) != "t":
        var = next((v for v in "tsuv" if re.search(r"\b" + v + r"\b|\d" + v + r"\b", accumulate.group(1))), "")
        tree = _arith_tree(accumulate.group(1).replace(var, "x") if var else accumulate.group(1), "x")
        if var and tree is not None:
            lo = float(accumulate.group(2))
            end = accumulate.group(3)
            b = _first_number(params.get("B", ""))
            hi = b if b is not None and b > lo else lo + 2
            out.update({"XVAR": var, "A": _clean_number(lo), "B": _clean_number(hi),
                        "A_LABEL": "$" + _clean_number(lo) + "$", "B_LABEL": "$" + end + "$",
                        "CURVE": _arith_pgf(tree, "x")})
            named = re.search(r"\b([A-Z])\s*\(\s*" + end + r"\s*\)", question)
            if named:
                out["AREA_LABEL"] = "$" + named.group(1) + "(" + end + ")$"
            bounds = None
            lo_hi = (lo, hi)
    if bounds:
        lo, hi = float(bounds.group(1)), float(bounds.group(2))
        if lo < hi:
            lo_hi = (lo, hi)
            out.update({"A": _clean_number(lo), "B": _clean_number(hi),
                        "A_LABEL": "$" + _clean_number(lo) + "$", "B_LABEL": "$" + _clean_number(hi) + "$"})
    if lo_hi is None:
        a, b = _first_number(params.get("A", "")), _first_number(params.get("B", ""))
        if a is None or b is None or a >= b:
            return out
        lo_hi = (a, b)
    lo, hi = lo_hi
    tree = _arith_tree(out["CURVE"], "x") if "CURVE" in out else None
    stated = None if tree is not None else re.search(r"\b(?:f|g|y)\s*(?:\(\s*x\s*\))?\s*=\s*(.+?)(?=\s*(?:,|;|\bfrom\b|\bbetween\b|\bon\b|\bover\b|\bfor\b|\band\b|\.\s|\.?$))", question)
    if stated:
        tree = _arith_tree(stated.group(1), "x")
    roots = []
    cross = re.search(r"\bcross(?:es|ing)?\s+the\s+x-?\s*axis\s+(?:only\s+)?at\s+((?:x\s*=\s*-?\d+(?:\.\d+)?(?:\s*(?:,|and|,\s*and)\s*)?)+)", text, re.I)
    if cross:
        roots = sorted({float(r) for r in re.findall(num, cross.group(1)) if lo < float(r) < hi})
    if tree is None:
        model = _arith_tree(str(params.get("CURVE", "")), "x")
        if roots:
            # the side of the axis the curve starts on, when the text says (the
            # model's curve crossed at the stated x = 1 but upside down)
            below_first = re.search(r"\b(below|negative)\b", text, re.I)
            above_first = re.search(r"\b(above|positive)\b", text, re.I)
            stated_sign = (-1.0 if below_first and (not above_first or below_first.start() < above_first.start())
                           else 1.0 if above_first else 0.0)

            def fits(t) -> bool:
                span = hi - lo
                xs = [lo + span * i / 400 for i in range(401)]
                ys = [_arith_eval(t, x) for x in xs]
                if any(y is None for y in ys):
                    return False
                changes = [xs[i] for i in range(400) if ys[i] * ys[i + 1] < 0 or (ys[i + 1] == 0 and 0 < i + 1 < 400)]
                first = _arith_eval(t, (lo + roots[0]) / 2) or 0.0
                return (len(changes) == len(roots) and all(abs(c - r) <= span / 200 + 1e-9 for c, r in zip(changes, roots))
                        and first * (stated_sign or first) > 0)
            if model is None or not fits(model):
                sign = stated_sign or 1.0
                body = "*".join(f"({_clean_number(r)}-x)" for r in roots) + f"*(x-({_clean_number(lo - 1)}))"
                probe = _arith_tree(body, "x")
                peak = max(abs(_arith_eval(probe, lo + (hi - lo) * i / 200) or 0) for i in range(201)) or 1.0
                scale = sign * 3.0 / peak
                out["CURVE"] = f"{_clean_number(round(scale, 4))}*{body}"
                tree = _arith_tree(out["CURVE"], "x")
            else:
                tree = model
        else:
            tree = model
    else:
        out["CURVE"] = _arith_pgf(tree, "x")
    if roots:
        out["EXTRA_TICKS"] = "".join("," + _clean_number(r) for r in roots)
        out["EXTRA_TICK_LABELS"] = "".join(",$" + _clean_number(r) + "$" for r in roots)
    if tree is None:
        return out
    pad = max(0.5, 0.15 * (hi - lo))
    xmin, xmax = lo - pad, hi + pad
    xs = [xmin + (xmax - xmin) * i / 300 for i in range(301)]
    ys = [_arith_eval(tree, x) for x in xs]
    if any(y is None for y in ys):
        return out
    below = [t for t in [lo, hi] + roots if (_arith_eval(tree, t) or 0.0) < -1e-9]
    if below:
        out["TICK_DOWN"] = "min(" + ",".join(f"abs(round(\\tick*100)-({round(t * 100)}))" for t in below) + ",1)"
    ymin, ymax = min(0.0, min(ys)), max(0.0, max(ys))
    ypad = max(0.5, 0.15 * (ymax - ymin))
    out.update({"XMIN": _clean_number(round(xmin, 3)), "XMAX": _clean_number(round(xmax, 3)),
                "YMIN": _clean_number(round(ymin - ypad, 3)), "YMAX": _clean_number(round(ymax + ypad, 3))})
    # the label in the largest stretch above the axis when the area is signed
    inner = [(lo + (hi - lo) * i / 200, _arith_eval(tree, lo + (hi - lo) * i / 200) or 0.0) for i in range(201)]
    if any(y > 0 for _x, y in inner) and any(y < 0 for _x, y in inner):
        best, run = (0.0, 0, 0), []
        for i, (_x, y) in enumerate(inner + [(hi, -1.0)]):
            if y > 0:
                run.append(i)
            elif run:
                area = sum(inner[j][1] for j in run)
                if area > best[0]:
                    best = (area, run[0], run[-1])
                run = []
        if best[0] > 0:
            out.update({"LF0": _clean_number(round(best[1] / 200, 3)), "LF1": _clean_number(round(best[2] / 200, 3))})
    return out


def _two_functions(text: str):
    """The two functions a question names (y = ..., f(x) = ..., g(x) = ...) as
    pgfplots expressions with their legend labels, and where they cross
    (sampled over -20..20, refined); None unless exactly two parse."""
    found = []
    for m in re.finditer(r"\b(?:y|f\s*\(\s*x\s*\)|g\s*\(\s*x\s*\))\s*=\s*(.+?)(?=\s*(?:,|;|\band\b|\bgraphically\b|\bon\b|\bfor\b|\.\s|\.?$|\bDiagram\b))", text):
        tree = _arith_tree(m.group(1), "x")
        if tree is not None and all(_arith_pgf(tree, "x") != pgf for pgf, _l in found):
            found.append((_arith_pgf(tree, "x"), "$" + re.sub(r"\s+", "", m.group(0)) + "$"))
    if len(found) != 2:
        return None
    ft, gt = _arith_tree(found[0][0], "x"), _arith_tree(found[1][0], "x")

    def diff(x: float) -> float:
        return (_arith_eval(ft, x) or 0.0) - (_arith_eval(gt, x) or 0.0)
    cross = []
    xs = [-20 + i * 0.05 for i in range(801)]
    for i in range(800):
        lo, hi = xs[i], xs[i + 1]
        if diff(lo) == 0:
            cross.append(lo)
        elif diff(lo) * diff(hi) < 0:
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (lo, mid) if diff(lo) * diff(mid) <= 0 else (mid, hi)
            cross.append((lo + hi) / 2)
    return found[0], found[1], cross


def _catalog_local_param_overrides(req: GenerateReq, template_id: str, params: dict | None = None) -> dict[str, str]:
    """Deterministic repairs for exact catalog matches.

    Gemini is useful for filling open-ended template values, but for common vector
    worksheets it often over-edits labels (e.g. "vecu", "e + 58"). These overrides
    keep exact-template diagrams tied to the question's givens and symbolic labels.
    """
    overrides: dict[str, str] = {}
    a, b = _vector_names_from_question(req)
    avec, bvec = _plain_vector_symbol(a), _plain_vector_symbol(b)
    mag_a, mag_b = _two_magnitudes_from_question(req)
    angle = _angle_from_question(req)
    angle_label = f"{angle}^\\circ" if angle else ""

    if template_id == "airplane_wind_ground_velocity":
        text = _question_text(req)
        air = _speed_after_word(text, "airspeed") or _speed_after_word(text, "air speed")
        wind = _speed_after_word(text, "wind")
        airang, _mid, bearing_label = _bearing_n_e(text)
        windang = "0"
        if re.search(r"\bfrom\s+the\s+east\b", text, re.I):
            windang = "180"
        elif re.search(r"\bfrom\s+the\s+north\b", text, re.I):
            windang = "270"
        elif re.search(r"\bfrom\s+the\s+south\b", text, re.I):
            windang = "90"
        overrides.update({
            "AIRANG": airang,
            "WINDANG": windang,
            "AIRLAB": (air or "500km/h").replace("km/h", r"\,\mathrm{km/h}"),
            "WINDLAB": (wind or "80km/h").replace("km/h", r"\,\mathrm{km/h}"),
            "GROUNDLAB": r"\vec{v}_g",
            "BEARINGLAB": bearing_label,
        })
    elif template_id == "boat_current_resultant":
        text = _question_text(req)
        # every speed in the question; the current's is the one after current/
        # flow/stream, the boat's the other (only "travelling" and "still water"
        # were read, so "heads across at 4 m/s" was left to the model)
        speeds = [(m.start(), m.group(1) + re.sub(r"\s+", "", m.group(2)).replace("perhour", "/h"))
                  for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(km\s*/\s*h|km\s+per\s+hour|m\s*/\s*s|mph|knots?)\b", text, re.I)]
        at = next((pos for pos, _v in speeds if re.search(r"\b(?:current|flow\w*|stream\w*|river\s+moves)\b", text[max(0, pos - 60):pos], re.I)), None)
        current = dict(speeds).get(at, "")
        boat = next((v for pos, v in speeds if pos != at), "") if current else ""
        if not current:
            boat = _speed_after_word(text, "travelling") or _speed_after_word(text, "traveling") or _speed_after_word(text, "still water")
            current = _speed_after_word(text, "flows") or _speed_after_word(text, "current")
        width_m = re.search(r"\b(?:river\s+)?(?:is\s+)?([-+]?\d+(?:\.\d+)?)\s*(km|m|cm|mi|ft)\s+wide\b", text, re.I)
        if width_m:
            overrides["WIDTHLAB"] = width_m.group(1) + r"\,\mathrm{" + width_m.group(2) + "}"
        if boat:
            overrides["BOATLAB"] = _unit_label(boat)
        if current:
            overrides["CURRENTLAB"] = _unit_label(current)
        overrides["RESULTLAB"] = r"\vec{v}_g"
    elif template_id == "bearing_two_leg":
        text = _question_text(req)
        bearings = _travel_bearing_values_from_text(text) or _bearing_values_from_text(text)
        if bearings:
            b1 = bearings[0]
            b2 = bearings[1] if len(bearings) > 1 else min(359, b1 + 55)
            # The skeleton derives directions from the bearings. Leg labels are
            # distances only: repeating the bearing there printed every angle
            # twice.
            overrides.update({"B1": str(b1), "B2": str(b2)})
            distances = _distance_labels_from_text(text)
            for slot, distance in zip(("L1", "L2"), distances):
                overrides[slot] = distance
            if len(distances) == 2:
                overrides.update({"LEN1": _clean_number(_first_number(distances[0])),
                                  "LEN2": _clean_number(_first_number(distances[1]))})
    elif template_id == "bearing_two_objects":
        text = _question_text(req)
        bearings = _travel_bearing_values_from_text(text) or _bearing_values_from_text(text)
        if len(bearings) == 2:
            overrides.update({"B1": str(bearings[0]), "B2": str(bearings[1])})
        distances = _distance_labels_from_text(text)
        speeds = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:km\s*/\s*h|km\s+per\s+hour|kph|mph|knots?|m\s*/\s*s)\b", text, re.I)
        if len(distances) == 2:
            overrides.update({"L1": distances[0], "L2": distances[1],
                              "LEN1": _clean_number(_first_number(distances[0])),
                              "LEN2": _clean_number(_first_number(distances[1]))})
        elif len(speeds) == 2:
            # same time for both, so the legs are in the ratio of the speeds. They
            # are labelled with the speeds: speed x time is the student's step (a
            # model labelled the legs 40 km and 60 km).
            units = re.findall(r"\b\d+(?:\.\d+)?\s*(km\s*/\s*h|km\s+per\s+hour|kph|mph|knots?|m\s*/\s*s)\b", text, re.I)
            overrides.update({"LEN1": _clean_number(float(speeds[0])), "LEN2": _clean_number(float(speeds[1])),
                              "L1": _unit_label(speeds[0] + re.sub(r"\s+", "", units[0]).replace("perhour", "/h")),
                              "L2": _unit_label(speeds[1] + re.sub(r"\s+", "", units[1]).replace("perhour", "/h"))})
        else:
            # a distance the question does not state is a result, not a label
            for slot, symbol in (("L1", "d_1"), ("L2", "d_2")):
                if not _numbers_stated(str((params or {}).get(slot, "")), text):
                    overrides[slot] = symbol
    elif template_id in {"vector_add_head_to_tail", "vector_add_parallelogram"}:
        overrides.update({"ULAB": avec, "VLAB": bvec, "SUM": avec + "+" + bvec})
    elif template_id == "vector_resultant_from_angle":
        rname = "r"
        m = re.search(r"\bresultant\s+([A-Za-z])\s*=", _question_text(req), re.I)
        if m:
            rname = m.group(1)
        overrides.update({
            "ALAB": _label_with_magnitude(avec, mag_a),
            "BLAB": _label_with_magnitude(bvec, mag_b),
            "RLAB": _plain_vector_symbol(rname) if rname != "r" else avec + "+" + bvec,
        })
        if angle:
            overrides.update({"ANG": angle, "ANGLAB": angle_label})
    elif template_id == "angle_between_vectors":
        vectors = _named_vectors(_question_text(req))
        if len(vectors) >= 2 and len(vectors[0][1]) == len(vectors[1][1]):
            (na, va), (nb, vb) = vectors[:2]
            overrides.update({"ALAB": _plain_vector_symbol(na), "BLAB": _plain_vector_symbol(nb)})
            if len(va) == 2:
                # The skeleton draws the true directions from the components.
                overrides.update({"AX": _clean_number(va[0]), "AY": _clean_number(va[1]),
                                  "BX": _clean_number(vb[0]), "BY": _clean_number(vb[1])})
            else:
                # 3D: the included angle, computed here rather than by the model,
                # drawn with the first vector along the x-axis.
                dot = sum(x * y for x, y in zip(va, vb))
                norms = math.sqrt(sum(x * x for x in va)) * math.sqrt(sum(y * y for y in vb))
                if norms:
                    ang = math.degrees(math.acos(max(-1.0, min(1.0, dot / norms))))
                    overrides.update({"ANG": _clean_number(round(ang, 1)),
                                      "AX": "0", "AY": "0", "BX": "0", "BY": "0"})
    elif template_id == "vector_projection":
        vectors = [v for v in _named_vectors(_question_text(req)) if len(v[1]) == 2]
        if len(vectors) >= 2:
            named = dict(vectors)
            # "projection of u onto v": u is projected, v is the line; else question order
            m = re.search(r"\bprojection\s+of\s+(?:\\+vec\s*\{?\s*)?([A-Za-z])\b.*?\bon(?:to)?\s+(?:\\+vec\s*\{?\s*)?([A-Za-z])\b",
                          _question_text(req), re.I)
            nu, nv = (m.group(1), m.group(2)) if m and m.group(1) in named and m.group(2) in named else (vectors[0][0], vectors[1][0])
            (ux, uy), (vx, vy) = named[nu], named[nv]
            overrides.update({"UX": _clean_number(ux), "UY": _clean_number(uy), "VX": _clean_number(vx), "VY": _clean_number(vy),
                              "ULAB": _plain_vector_symbol(nu), "VLAB": _plain_vector_symbol(nv),
                              "PROJLAB": r"\mathrm{proj}_{" + _plain_vector_symbol(nv) + "}" + _plain_vector_symbol(nu)})
    elif template_id == "cross_product_parallelogram":
        vectors = [v for v in _named_vectors(_question_text(req)) if len(v[1]) == 3]
        if len(vectors) >= 2:
            (na, a3), (nb, b3) = vectors[:2]
            overrides.update({k: _clean_number(v) for k, v in zip(("AX", "AY", "AZ", "BX", "BY", "BZ"), a3 + b3)})
            overrides.update({"ALAB": _plain_vector_symbol(na), "BLAB": _plain_vector_symbol(nb),
                              "CROSSLAB": _plain_vector_symbol(na) + r"\times" + _plain_vector_symbol(nb)})
    elif template_id == "3d_vector_components":
        vectors = [v for v in _named_vectors(_question_text(req)) if len(v[1]) == 3]
        if vectors:
            name, (x, y, z) = vectors[0]
            values = [_clean_number(c) for c in (x, y, z)]
            overrides.update(dict(zip(("XVAL", "YVAL", "ZVAL"), values)))
            overrides.update(dict(zip(("XVALLABEL", "YVALLABEL", "ZVALLABEL"), values)))
            overrides["LAB"] = _plain_vector_symbol(name)
    elif template_id == "vector_difference_from_angle":
        overrides.update({
            "ALAB": _label_with_magnitude(avec, mag_a),
            "BLAB": _label_with_magnitude(bvec, mag_b),
            "DIFFLAB": avec + "-" + bvec,
        })
        if angle:
            overrides.update({"ANG": angle, "ANGLAB": angle_label})
    elif template_id == "vector_subtraction_as_addition":
        dname = "d"
        m = re.search(r"\b([A-Za-z])\s*=\s*" + re.escape(a) + r"\s*-\s*" + re.escape(b), _question_text(req), re.I)
        if m:
            dname = m.group(1)
        dvec = _plain_vector_symbol(dname)
        overrides.update({
            "PLAB": avec,
            "NQLAB": "-" + bvec,
            "DLAB": dvec,
            "REL": dvec + "=" + avec + "+(-" + bvec + ")",
        })
    elif template_id == "vector_linear_combination":
        text = _question_text(req)
        m_vec = re.search(r"\\vec\s*\{\s*([A-Za-z])\s*\}\s*([+-])\s*(\d+)\s*\\vec\s*\{\s*([A-Za-z])\s*\}", text)
        m = re.search(r"\b([-+]?\d+)\s*([A-Za-z])\s*([+-])\s*(\d+)\s*([A-Za-z])\b", text)
        c1, n1, op, c2, n2 = ("2", a, "-", "3", b)
        if m_vec:
            n1, op, c2, n2 = m_vec.groups()
            c1 = "1"
        elif m:
            c1, n1, op, c2, n2 = m.groups()
        v1, v2 = _plain_vector_symbol(n1), _plain_vector_symbol(n2)
        c1_label = "" if c1 == "1" else c1
        signed_second = (op + c2 + v2).replace("+-", "-")
        neg_angle = str((float(angle or 60) + (180 if op == "-" else 0)) % 360)
        overrides.update({
            "ULAB": c1_label + v1,
            "VLAB": signed_second,
            "RLAB": c1_label + v1 + op + c2 + v2,
            "NEGANG": neg_angle.rstrip("0").rstrip("."),
        })
        if angle:
            overrides.update({"ANG": angle, "ANGLAB": angle_label})
    elif template_id == "force_equilibrium_closed_polygon":
        overrides.update({
            "F1LAB": r"\vec{F}_1",
            "F2LAB": r"\vec{F}_2",
            "F3LAB": r"\vec{F}_3",
            "SUM_LAB": r"\vec{F}_1+\vec{F}_2+\vec{F}_3=\vec{0}",
        })
    elif template_id == "vector_zero_sum_opposites":
        overrides.update({
            "ALAB": avec,
            "BLAB": bvec + "=-" + avec,
            "SUM_LAB": avec + "+" + bvec + r"=\vec{0}",
        })
    elif template_id == "vector_closed_triangle_sum":
        overrides["SUM_LAB"] = r"\overrightarrow{AB}+\overrightarrow{BC}+\overrightarrow{CA}=\vec{0}"
    elif template_id == "triangle_general":
        overrides.update(_triangle_overrides(req))
    elif template_id == "definite_integral_shaded":
        overrides.update(_integral_overrides(req, params or {}))
    elif template_id == "function_intersection_two_curves":
        # both functions from the question, the window around their crossings
        pair = _two_functions(_question_text(req))
        if pair:
            (f, flab), (g, glab), cross = pair
            if cross:
                overrides.update({"XMIN": _clean_number(math.floor(min(cross)) - 3), "XMAX": _clean_number(math.ceil(max(cross)) + 3)})
            overrides.update({"F": f, "G": g, "F_LABEL": flab, "G_LABEL": glab})
    elif template_id == "area_between_curves":
        # both curves from the question; the shading runs between the outer
        # crossings, which get no label
        pair = _two_functions(_question_text(req))
        if pair:
            (f, flab), (g, glab), cross = pair
            overrides.update({"F": f, "G": g, "F_LABEL": flab, "G_LABEL": glab})
            if len(cross) >= 2:
                a, b = min(cross), max(cross)
                pad = max(1.0, 0.3 * (b - a))
                xmin, xmax = a - pad, b + pad
                ft, gt = _arith_tree(f, "x"), _arith_tree(g, "x")
                ys = [v for x in (xmin + (xmax - xmin) * i / 200 for i in range(201))
                      for v in (_arith_eval(ft, x), _arith_eval(gt, x)) if v is not None]
                inner = [v for x in (a + (b - a) * i / 100 for i in range(101))
                         for v in (_arith_eval(ft, x), _arith_eval(gt, x)) if v is not None]
                lo_y, hi_y = min(inner + [0.0]), max(inner + [0.0])
                # the window keeps the region whole and the curves a little past it,
                # not every far-off value of a steep curve
                lo_y, hi_y = max(min(ys), lo_y - 0.5 * (hi_y - lo_y) - 1), min(max(ys), hi_y + 0.3 * (hi_y - lo_y) + 1)
                overrides.update({"A": _clean_number(round(a, 4)), "B": _clean_number(round(b, 4)),
                                  "XMIN": _clean_number(round(xmin, 2)), "XMAX": _clean_number(round(xmax, 2)),
                                  "YMIN": _clean_number(round(lo_y, 2)), "YMAX": _clean_number(round(hi_y, 2))})
    elif template_id == "number_line_blank":
        span = re.search(r"\bnumber\s+line\b[^.]{0,40}?\bfrom\s+(-?\d+)\s+to\s+(-?\d+)", _request_text(req), re.I)
        if span and int(span.group(1)) < int(span.group(2)):
            overrides.update({"XMIN": span.group(1), "XMAX": span.group(2)})
    elif template_id == "related_rates_circle":
        text = _question_text(req)
        rate = re.search(r"\bradius\b[^.?]{0,60}?\b(?:increas|grow|expand)\w*\s+(?:at|by)\s+(?:a\s+(?:constant\s+)?rate\s+of\s+)?"
                         r"(\d+(?:\.\d+)?)\s*([a-z]+\s*/\s*[a-z]+)", text, re.I)
        if rate:
            unit = re.sub(r"\s+", "", rate.group(2))
            overrides["DR_LABEL"] = r"$\frac{dr}{dt}=" + rate.group(1) + r"\,\mathrm{" + unit + "}$"
    elif template_id == "sinusoid_amplitude_period":
        if (re.search(r"\b(?:state|find|determine|identify|give|write|what|calculate)\b", _question_text(req), re.I)
                and re.search(r"\b(?:amplitude|period|midline|range|maximum|minimum|max|min)\b", _question_text(req), re.I)):
            # asked for any of these, the arrows carry symbols: amplitude,
            # midline and period labels together gave the range away
            overrides.update({"AMPLITUDE_LABEL": "$A$", "PERIOD_LABEL": "$P$", "MIDLINE_LABEL": "midline"})
        named = re.search(r"\b[A-Za-z]\s*\(\s*([a-z])\s*\)\s*=", _question_text(req))
        if named and named.group(1) != "x":
            overrides["XVAR"] = named.group(1)
        wave = _sinusoid_from_text(_question_text(req))
        if wave:
            overrides.update({slot: _clean_number(round(wave[key], 4) + 0.0) for slot, key in (
                ("AMPLITUDE_VALUE", "A"), ("FREQUENCY_VALUE", "B"), ("PHASE_SHIFT_VALUE", "C"), ("MIDLINE_VALUE", "D"))})
    elif template_id == "right_triangle":
        # a symbol on the wall the question never asks about reads as a second
        # unknown (an h appeared when the question asked for the foot's distance)
        if (not re.search(r"\b(?:high|height|tall|up\s+the|vertical\s+(?:distance|height)|how\s+far\s+up|altitude|depth)\b", _question_text(req), re.I)
                and not re.search(r"\d", str((params or {}).get("HEIGHTLAB", "")))):
            overrides["HEIGHTLAB"] = ""
        # The one acute angle the question gives sets the drawn shape and its label.
        found = {float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*degrees?\b", _question_text(req), re.I)} - {90.0}
        if len(found) == 1:
            (deg,) = found
            if 0 < deg < 90 and re.search(r"\b(?:with|from|and)\s+the\s+(?:wall|vertical)\b", _question_text(req), re.I):
                # an angle with the wall is the top angle; the base angle is the rest
                overrides.update({"ANGLE_DEG": _clean_number(90 - deg), "ANGLAB": "",
                                  "TOPANGLAB": _clean_number(deg) + "^\\circ"})
            elif 0 < deg < 90:
                overrides.update({"ANGLE_DEG": _clean_number(deg), "ANGLAB": _clean_number(deg) + "^\\circ",
                                  "TOPANGLAB": ""})
    elif template_id == "circle_chord_arc":
        text = _question_text(req)
        angle = _angle_from_question(req, "110")
        radius = re.search(r"\bradius\s+(?:of\s+)?(?:is\s*)?([-+]?\d+(?:\.\d+)?)\s*(cm|mm|m|km|in|ft|yd|mi)?", text, re.I)
        overrides.update({
            "ANGLE": angle,
            "ARCMID": str(round(float(angle) / 2, 3)).rstrip("0").rstrip(".") if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", angle) else "55",
            "ANGLELAB": angle + "^\\circ",
            "CHORDLAB": "c",
            "ARCLAB": "s",
        })
        if radius:
            unit = radius.group(2) or ""
            overrides["RLABEL"] = radius.group(1) + (r"\,\mathrm{" + unit + "}" if unit else "")
    elif template_id in {"network_graph", "complete_graph_sketch"}:
        text = _question_text(req)
        found = False
        for edge in ("AB", "AC", "BC", "BD", "CE", "DE", "AE"):
            ends = edge[0] + r"\s*(?:to|-|–|—|:)?\s*" + edge[1] + "|" + edge[1] + r"\s*(?:to|-|–|—|:)?\s*" + edge[0]
            m = re.search(r"\b(?:" + ends + r")\b\s*(?:is|:|=)?\s*([-+]?\d+(?:\.\d+)?)", text, re.I)
            if m and template_id == "network_graph":
                overrides["W" + edge] = m.group(1)
                found = True
        if found and "WAE" not in overrides:
            # The question lists its edges and AE is not among them.
            overrides["WAE"] = ""
        if template_id == "complete_graph_sketch":
            m = re.search(r"\bK_?\{?(\d+)\}?", text)
            if m:
                overrides["LABEL"] = "K_{" + m.group(1) + r"}\text{: every pair connected}"

    return overrides


def _catalog_render(req: GenerateReq, tmpl: dict, params: dict, source: str) -> dict:
    """Render a filled catalog template; when the picture shows label collisions
    and the template offers other label placements, try them in order and keep
    the first clean one (else the one with the fewest collisions)."""
    best = None
    options = tcatalog.alternatives(tmpl)
    for alternative in range(options):
        filled = tcatalog.fill(tmpl, params, target=req.target, alternative=alternative, question=_question_text(req))
        rendered = _verified_render(req, filled, source=source, run_critic=False)
        if not rendered.get("ok"):
            return rendered if best is None else best  # a placement that breaks the compile is no option
        count = len(rendered.get("layout", {}).get("issues", []))
        if best is None or count < best_count:
            best, best_index, best_count = rendered, alternative, count
        if count == 0 or "layout" not in rendered:
            break
        if options > 1:
            # A template without alternatives has only its layout event: it
            # used to read "placement 1 collides", as if others had been tried.
            _diagnostic("layout-alternative", f"placement {alternative + 1} of {options} collides", template=tmpl["id"])
    else:
        if options > 1:
            _diagnostic("layout-alternative", f"no clean placement; kept placement {best_index + 1} "
                        f"({best_count} collision{'s' if best_count != 1 else ''})", template=tmpl["id"])
    return best


def _catalog_generate(req: GenerateReq) -> dict | None:
    """Constrained path: route to a catalog template, let Gemini judge whether it
    actually fits the question (it sees the caption + skeleton) and fill ONLY the
    declared parameter values, assemble deterministically, then render (skipping
    the model critic - structure is fixed). Returns None when no template matches
    (caller falls through to the legacy/reference path) or when the matched
    template ultimately fails to render. Returns {"ok": False, "unfit": True, ...}
    when the model vetoes the routed template's diagram family - the caller then
    skips ALL keyword-matched templates and uses the reference-guided path."""
    if not CATALOG_ENABLED or tcatalog is None:
        return None
    tmpl = tcatalog.route(_question_text(req), req.subject)
    if not tmpl:
        # A triangle-shaped question that names no exact keyword (e.g. a surveyor SAS
        # setup: "angle ACB = 52, distance to A 250 m, distance to B 310 m") still
        # deserves the labelled triangle rather than a bespoke fallback or a blank.
        # _looks_like_triangle catches the 3-letter vertex angle / multi-angle cases
        # that keyword routing cannot see. EXCEPTION: when the question gives named
        # coordinate vertices like P(1,1,1), Q(2,3,4) the generic sine-law triangle
        # is the wrong picture (it drew default A/B/C with side arcs for "area of the
        # triangle with vertices P,Q,R") - the bespoke path plots the real triangle.
        has_coordinate_vertices = len(re.findall(
            r"\b[A-Z]\s*\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)?\s*\)",
            _question_text(req),
        )) >= 2
        if not has_coordinate_vertices and _looks_like_triangle(_question_text(req)):
            tmpl = tcatalog.get("triangle_general")
            if tmpl and not tcatalog._compatible(tmpl, _question_text(req).lower()):
                tmpl = None
        if not tmpl:
            return None
    spec = tcatalog.ai_spec(tmpl)
    _diagnostic("catalog-route", template=tmpl["id"])
    # A template marked always_fits is the only safe picture for what routes to
    # it: the model once judged the blank number line unfit because the brief
    # asked for the solution, and the drawing that replaced it was the answer.
    fit_check = FIT_CHECK_ENABLED and not tmpl.get("always_fits")
    caption = tmpl.get("caption", "")
    # The model sees the default label placement, never the alternatives slot.
    skeleton = str(tmpl.get("skeleton", "")).replace("@@ALT@@", (tmpl.get("layout_alternatives") or [""])[0])
    params = dict(spec["defaults"])
    if not spec["defaults"]:
        # Static templates still need a confirmed family match before shipping.
        if fit_check:
            try:
                raw = _gemini(
                    _catalog_param_prompt(req, spec, caption=caption, skeleton=skeleton),
                    as_json=True,
                    temperature=0.05,
                )
                if isinstance(raw, dict) and str(raw.get("_fit", "yes")).strip().lower().startswith("n"):
                    _diagnostic("catalog-unfit", str(raw.get('_why', '')), template=tmpl['id'])
                    print(f"[catalog] {tmpl['id']} judged UNFIT for question: {str(raw.get('_why', ''))[:200]}", flush=True)
                    return {"ok": False, "unfit": True, "template": tmpl["id"], "why": str(raw.get("_why", ""))[:300]}
                if not isinstance(raw, dict) or str(raw.get('_fit', '')).strip().lower() != 'yes':
                    raise ValueError("Template fit response did not confirm a match.")
            except Exception as exc:
                _diagnostic("catalog-fit-error", str(exc), template=tmpl['id'])
                return None
        filled = tcatalog.fill(tmpl, {}, target=req.target, question=_question_text(req))
        rendered = _catalog_render(req, tmpl, {}, source=f"catalog-static:{tmpl['id']}")
        if rendered.get("ok"):
            rendered["tikz"] = rendered.get("tikz", filled)
            rendered["caption"] = caption
            rendered["customized"] = "catalog-static:" + tmpl["id"]
            return rendered
        return None
    repair_log = ""
    rendered: dict = {"ok": False, "error": "catalog template did not render."}
    for attempt in range(TEMPLATE_REPAIR_ATTEMPTS + 1):
        try:
            raw = _gemini(
                _catalog_param_prompt(req, spec, repair_log=repair_log, previous_params=params,
                                      caption=caption, skeleton=skeleton),
                as_json=True,
                temperature=0.05,
            )
            if isinstance(raw, dict):
                # Honor the model's fit verdict on the first pass only (repair passes
                # are about compile errors; a mid-repair flip-flop would waste work).
                if (
                    fit_check
                    and attempt == 0
                    and str(raw.get("_fit", "yes")).strip().lower().startswith("n")
                ):
                    print(f"[catalog] {tmpl['id']} judged UNFIT for question: {str(raw.get('_why', ''))[:200]}", flush=True)
                    _diagnostic("catalog-unfit", str(raw.get('_why', '')), template=tmpl['id'])
                    return {"ok": False, "unfit": True, "template": tmpl["id"], "why": str(raw.get("_why", ""))[:300]}
                if fit_check and attempt == 0 and str(raw.get('_fit', '')).strip().lower() != 'yes':
                    raise ValueError("Template fit response did not confirm a match.")
                if any(k not in raw for k in spec['defaults']) and not tmpl.get("always_fits"):
                    raise ValueError("Template response omitted required drawing parameters.")
                params.update({k: v for k, v in raw.items() if k in spec["defaults"]})
            else:
                raise ValueError("Template parameters must be a JSON object.")
        except Exception as exc:
            print(f"[catalog] {tmpl['id']} param Gemini failure: {str(exc)[:200]}", flush=True)
            _diagnostic("catalog-parameter-error", str(exc), template=tmpl['id'])
            return None  # Default labels/values are not the student's givens.
        filled = tcatalog.fill(tmpl, params, target=req.target, question=_question_text(req))
        params.update(_catalog_local_param_overrides(req, tmpl["id"], params))
        filled = tcatalog.fill(tmpl, params, target=req.target, question=_question_text(req))
        print(f"[catalog] {tmpl['id']} params={json.dumps(params, ensure_ascii=False)[:1200]}", flush=True)
        _diagnostic("catalog-params", json.dumps(params, ensure_ascii=False), template=tmpl["id"])
        rendered = _catalog_render(req, tmpl, params, source=f"catalog:{tmpl['id']}")
        if rendered.get("ok"):
            rendered["tikz"] = rendered.get("tikz", filled)
            rendered["caption"] = caption
            rendered["customized"] = "catalog:" + tmpl["id"]
            return rendered
        repair_log = rendered.get("log") or rendered.get("error") or "TikZ render failed."
        _diagnostic("catalog-render-error", repair_log, template=tmpl['id'], tikz=filled)
    return rendered if rendered.get("ok") else None


def _format_reference_blocks(refs: list) -> str | None:
    """Render catalog templates as structural references for the fallback prompt."""
    if not refs:
        return None
    parts = [
        "Use these catalog diagrams as the STRUCTURAL reference. Keep their style, "
        "axis setup, cp styles, label placement, and answer-safety; ADAPT the "
        "coordinates, values, and labels to the user's problem. Do not invent "
        "unusual structure - stay close to whichever reference best fits."
    ]
    for r in refs:
        parts.append(f"{r.get('caption', '')}\n{r.get('skeleton', '')}")
    return "\n\n".join(parts)


def _catalog_references(req: GenerateReq, k: int = 3) -> list:
    if not CATALOG_ENABLED or tcatalog is None:
        return []
    try:
        return tcatalog.route_top(_question_text(req), req.subject, k=k)
    except Exception:
        return []


_READINESS_RULES = """The Course Planner wrapper predefines the styles cp axis, cp line, cp dashed, cp fill, cp point, cp label. Do NOT flag those as undefined.

When rendered pictures are attached (one per version, in order), check the picture as well as the code: shaded regions, marked angles, plotted curves and points must be where the question puts them. Without a picture, judge from the code.

A visual is READY only if ALL of these hold:
- Correct type: the diagram is the right kind of visual for the question and actually illustrates it (not a formula poster, not an unrelated shape).
- Consistent: it agrees with the givens in the question (labels, counts, signs, angles, and quantities match). A shaded region must be exactly the region the question describes (FAIL shading that spills outside the region between two curves). For cross products, the drawn result vector must obey the right-hand rule for the two drawn vectors (e.g. j x i points along -z, NOT +z); FAIL a cross-product arrow pointing the wrong way.
- Interior angles: in a named angle XYZ, Y is the vertex. Unless the question explicitly asks for an exterior, reflex, or major angle, the mark and its label must lie in the smaller interior sector between YX and YZ. For circle theorems, FAIL angle AOB = 80 degrees if the diagram marks the exterior 280-degree sector, and FAIL angle ACB if its mark is outside the inscribed triangle rather than between CA and CB.
- Answer-safe: it does not reveal a value the student is asked to find (a solved magnitude, coordinate, angle, or final answer); such values appear only as a symbol or ?, and placeholders like ? or (?, ?) are correct. Values STATED IN THE QUESTION are givens and may be labelled, including given vectors, points, coordinates, and lengths (e.g. v = <2, 3, 4> when the question gives it). Guide lines, dashed drops, or tick labels that locate an unknown point on the axes reveal its coordinates: FAIL them unless the question gives that point. When the student must solve an inequality or show its solution, a circle or dot at the boundary and shading or an arrow in one direction IS the answer: FAIL it, even if the description asks for it. A label (axis tick numbers aside) may show only numbers the question states: FAIL a label with a value the student has to work out, including an intermediate result such as a Venn region count, a branch probability, a constraint equation or a distance computed from speed and time, even if the description asks for it.
- Legible: labels are not degenerate - nothing tiny, collapsed, overlapping, or cramped into the origin. FAIL a diagram whose supposedly independent vectors are drawn nearly collinear, or whose parallelogram/triangle collapses to a sliver."""


def _readiness_prompt(req: GenerateReq, tikz: str) -> str:
    return f"""You are a strict readiness checker for a math worksheet diagram. Given the QUESTION and a proposed TikZ visual, decide if the visual is READY to show to a student.

{_READINESS_RULES}

Respond with EXACTLY "PASS" if the visual is READY, otherwise "FAIL: <one short reason>".

QUESTION:
{_raw_request_text(req)[:2200]}

PROPOSED TikZ:
{tikz[:5000]}
""".strip()


def _readiness_pair_prompt(req: GenerateReq, first: str, second: str, reports: tuple[str, str]) -> str:
    return f"""You are a strict readiness checker for a math worksheet diagram. Given the QUESTION and two versions of a TikZ visual (A, then B: a draft and its revision), decide which, if either, is READY to show to a student.

{_READINESS_RULES}

Label problems an automatic check found in the rendered pictures:
A: {reports[0] or "none"}
B: {reports[1] or "none"}

Judge both versions by the same rules. Respond with EXACTLY "PASS A" or "PASS B", naming the better version that is READY (the one with fewer label problems when both are, A on a tie), or "FAIL: <one short reason>" if neither is READY.

QUESTION:
{_raw_request_text(req)[:2200]}

VERSION A TikZ:
{first[:4000]}

VERSION B TikZ:
{second[:4000]}
""".strip()


def _readiness_call(prompt: str, images: list[str]) -> str:
    """One verifier call; a request refused with the pictures attached is retried
    once without them, so a model that rejects images cannot blank a diagram."""
    try:
        return _gemini(prompt, as_json=False, temperature=0.0, **({"images": images} if images else {})).strip()
    except Exception as exc:
        if images and "error 400" in str(exc):
            _diagnostic("readiness-picture-refused", str(exc))
            return _gemini(prompt, as_json=False, temperature=0.0).strip()
        raise


def _readiness_verdict(req: GenerateReq, tikz: str, image: str | None = None) -> tuple[str, str]:
    """Readiness gate for a custom drawing: its code and, when given, its rendered
    picture. A verifier outage is not a PASS."""
    if not GEMINI_KEYS:
        return "FAIL", "verifier unavailable"
    try:
        out = _readiness_call(_readiness_prompt(req, tikz), [image] if image else [])
    except Exception as exc:
        return "FAIL", "verifier error: " + str(exc)[:120]
    if out.upper() == "PASS":
        return "PASS", ""
    return "FAIL", out[:220] or "readiness check failed"


def _readiness_choice(req: GenerateReq, codes: tuple[str, str], images: tuple, reports: tuple[str, str]) -> tuple[int | None, str]:
    """One verifier call comparing two versions of a drawing: (index of the
    version to ship, "") or (None, reason). Judging them in separate calls let
    one verdict fail a label the other passed."""
    if not GEMINI_KEYS:
        return None, "verifier unavailable"
    try:
        out = _readiness_call(_readiness_pair_prompt(req, codes[0], codes[1], reports),
                              [i for i in images if i] if all(images) else [])
    except Exception as exc:
        return None, "verifier error: " + str(exc)[:120]
    m = re.match(r"\W*PASS\W*([AB])?\b", out.upper())
    if m:
        return (1 if m.group(1) == "B" else 0), ""
    return None, out[:220] or "readiness check failed"


# TikZ option names with spaces that models write hyphenated. TikZ reads an
# unknown "line-width=.1pt" as an arrow spec ("Unknown arrow tip kind 'line'"),
# and the repair repeated the typo. Only a key followed by "=" is touched.
_KEY_TYPOS = re.compile(
    r"\b(line|inner|outer|text|minimum|dash|fill|draw|rounded)-"
    r"(width|sep|xsep|ysep|height|depth|cap|join|pattern|opacity|corners)(?=\s*=)"
)


def _fix_key_typos(tikz: str) -> str:
    return _KEY_TYPOS.sub(r"\1 \2", tikz)


def _ship_reference(rendered: dict, enlarged: str, caption: str) -> dict:
    rendered.pop("preview_png", None)  # for the verifier only; the client gets the picture itself
    rendered["tikz"] = enlarged
    rendered["caption"] = caption
    rendered["customized"] = "reference-fallback"
    return rendered


def _issue_count(candidate: tuple) -> int:
    return len(candidate[0].get("layout", {}).get("issues", []))


def _verifier_facts() -> dict:
    """The model that answered the job's last Gemini call and whether it was sent
    the picture, for the readiness event (the trace left both to be inferred)."""
    facts = {"model": getattr(_job_trace, "last_model", None), "picture": getattr(_job_trace, "last_pictured", False)}
    _job_trace.last_model, _job_trace.last_pictured = None, False
    return facts if facts["model"] else {}


def _judge_reference(req: GenerateReq, rendered: dict, enlarged: str, caption: str) -> tuple[str, str]:
    """Readiness verdict for one rendered model drawing (code and picture); a
    pass is ready to ship. Its code goes in the trace unless a layout event
    already has it, so a problem the checks missed can still be traced."""
    verdict, reason = _readiness_verdict(req, enlarged, rendered.get("preview_png"))
    logged = bool(rendered.get("layout", {}).get("issues"))
    _diagnostic("readiness", reason or verdict, **_verifier_facts(), **({} if logged else {"tikz": enlarged}))
    if verdict == "PASS":
        _ship_reference(rendered, enlarged, caption)
        print(f"[reference] PASS ({reason or 'ready'})", flush=True)
    return verdict, reason


def _judge_reference_pair(req: GenerateReq, pair: list) -> tuple[int | None, str]:
    """One readiness verdict over a colliding draft and its repair, the one with
    fewer label problems first: (index to ship, "") or (None, reason)."""
    index, reason = _readiness_choice(
        req,
        (pair[0][1], pair[1][1]),
        (pair[0][0].get("preview_png"), pair[1][0].get("preview_png")),
        (_layout_summary(pair[0][0].get("layout", {})), _layout_summary(pair[1][0].get("layout", {}))),
    )
    unlogged = [c for c in pair if not c[0].get("layout", {}).get("issues")]
    if index is not None and not pair[index][0].get("layout", {}).get("issues"):
        unlogged = [pair[index]]
    detail = reason if index is None else "PASS " + "AB"[index]
    _diagnostic("readiness", detail, **_verifier_facts(), **({"tikz": unlogged[0][1]} if unlogged else {}))
    return index, reason


def _reference_generate(req: GenerateReq) -> dict | None:
    """Reference-guided fallback for problems with no exact template (and for
    questions whose keyword-routed template the model vetoed). Two-pass, mirroring
    the Manim Space pipeline: the model first PLANS the diagram (family, objects,
    labels, answer-safety), then implements the plan as TikZ with the catalog's
    closest templates as the structural scaffold; the result is compiled, then
    gated by the LLM readiness checker. Policy: repair once, then blank (a
    verified-safe diagram or none - never a shaky one)."""
    references = _format_reference_blocks(_catalog_references(req, k=3))
    plan = ""
    try:
        plan_raw = _gemini(_diagram_spec_prompt(req, references), as_json=True, temperature=0.3)
        if isinstance(plan_raw, dict) and plan_raw.get("diagram_type"):
            plan = json.dumps(plan_raw, ensure_ascii=False)
            print(f"[reference] plan: {str(plan_raw.get('diagram_type'))[:120]}", flush=True)
    except Exception as exc:
        # Spec-free fallback, same as the Manim pipeline: a missing plan
        # degrades quality, never availability.
        print(f"[reference] plan Gemini failure (drafting spec-free): {str(exc)[:160]}", flush=True)
        _diagnostic("planning-error", str(exc))
    tikz = ""
    caption = ""
    repair_log = ""
    colliding = None  # a draft set aside for label collisions, kept in case the repair fails
    for attempt in range(2):  # initial draft + one repair
        try:
            spec = _gemini(
                _visual_prompt(req, repair_log=repair_log, previous_code=tikz, references=references, spec=plan),
                as_json=True,
                temperature=0.2,
            )
        except Exception as exc:
            print(f"[reference] generation Gemini failure: {str(exc)[:180]}", flush=True)
            _diagnostic("generation-error", str(exc))
            return {"ok": False, "error": "Diagram code generation failed: " + str(exc)[:300]}
        if not isinstance(spec, dict):
            _diagnostic("invalid-code-response", "Expected a JSON object containing TikZ.")
            return {"ok": False, "error": "The model returned an invalid diagram response."}
        tikz = _fix_key_typos(_strip_fence(str(spec.get("tikz", ""))))
        caption = str(spec.get("caption", caption)).strip()
        if not tikz:
            _diagnostic("empty-code", "The model returned no drawing code.")
            return {"ok": False, "error": "The model returned no drawing code."}
        safe = _worksheet_answer_safe_tikz(req, tikz)
        semantic_issue = _semantic_visual_issue(req, safe)
        if semantic_issue:
            repair_log = semantic_issue
            _diagnostic("semantic-rejection", repair_log, tikz=safe)
            continue
        enlarged = _enlarge_visual_code(req, safe)
        rendered = _render(RenderReq(code=enlarged, format=req.format, theme=req.theme, target=req.target,
                                     layout=True, preview=True))
        if not rendered.get("ok"):
            repair_log = rendered.get("log") or rendered.get("error") or "TikZ compile failed."
            _diagnostic("render-error", repair_log, tikz=enlarged)
            continue
        collisions = _layout_summary(rendered.get("layout", {}))
        if collisions:
            _diagnostic("layout", collisions, tikz=enlarged)
            if attempt == 0:
                # The rendered picture shows label collisions the source-reading
                # readiness check cannot see: spend the one repair on them. The
                # repair and this draft are then judged, fewer collisions first.
                print(f"[reference] layout collisions, repairing: {collisions[:200]}", flush=True)
                repair_log = (
                    "In the rendered diagram, " + collisions + ". Move each of those labels "
                    "(anchor, position or offset) so no line, curve or axis passes through it and "
                    "no two labels overlap; keep everything else the same."
                )
                colliding = (rendered, enlarged, caption)
                continue
        draft = colliding
        if draft:
            # The repair of a colliding draft: one verdict over both, the one with
            # fewer label problems first (the repair on a tie). Separate verdicts
            # failed the repair's "(?, ?)" and passed the same label in its draft,
            # which then shipped with more collisions.
            pair = sorted([(rendered, enlarged, caption), draft], key=_issue_count)
            colliding = None
            index, reason = _judge_reference_pair(req, pair)
            if index is not None:
                chosen = pair[index]
                if chosen is draft:
                    _diagnostic("layout-choice", f"shipped the draft ({_issue_count(draft)} label problems) "
                                f"over its repair ({_issue_count(pair[1 - index])})")
                return _ship_reference(*chosen)
        else:
            verdict, reason = _judge_reference(req, rendered, enlarged, caption)
            if verdict == "PASS":
                return rendered
        if reason.startswith('verifier'):
            return {"ok": False, "error": "Diagram verification unavailable: " + reason}
        repair_log = "The previous diagram failed the readiness check: " + reason
        print(f"[reference] readiness FAIL, {'repairing' if attempt == 0 else 'blanking'}: {reason}", flush=True)
    if colliding:
        # The repair of a colliding draft produced nothing usable: the draft itself,
        # whose only fault was label placement, still gets its readiness check.
        rendered, enlarged, caption = colliding
        verdict, _reason = _judge_reference(req, rendered, enlarged, caption)
        if verdict == "PASS":
            _diagnostic("layout-choice", "shipped the draft: its repair produced no usable drawing")
            return rendered
    return {"ok": False, "error": repair_log[:500] or "No verified diagram was produced."}


def _question_should_stay_blank(req: GenerateReq) -> bool:
    ql = _question_text(req).lower()
    if (
        re.search(r"\bdifference\s+between\b", ql)
        and re.search(r"\bscalar\b", ql)
        and re.search(r"\bvector\b", ql)
        and not re.search(r"\b(draw|sketch|graph|diagram|construct|illustrate)\b", ql)
    ):
        return True
    if (
        re.search(r"\b(define|explain|describe)\b", ql)
        and not re.search(r"\b(calculate|compute|find|determine|draw|sketch|graph|diagram|show|construct|resolve)\b", ql)
    ):
        return True
    # 'State ...' blanks only conceptual requests ("state the property/definition").
    # "State the magnitude of a x b if |a|=8, |b|=5, angle 30" is a computation in
    # disguise and deserves its diagram (was wrongly blanked 2026-07-08).
    if (
        re.search(r"\bstate\b", ql)
        and re.search(r"\bstate\s+(?:[a-z]+\s+){0,4}?(?:propert|definition|rule|law|theorem|condition|relationship|formula|identit|principle|notation)", ql)
        and not re.search(r"\b(calculate|compute|find|determine|draw|sketch|graph|diagram|show|construct|resolve)\b", ql)
    ):
        return True
    return False


def _structured_vector_direct_hit(req: GenerateReq) -> tuple[str, str] | None:
    ql = _question_text(req).lower()
    if re.search(r"\b(bearing|heading|navigation|compass)\b", ql):
        return None
    hit = _vector_template(req)
    if not hit:
        return None
    _tikz, caption = hit
    prefixes = (
        "2D coordinate diagram",
        "3D coordinate diagram",
        "3D point-to-point vector",
        "2D point-to-point vector",
        "3D position vector",
        "3D vector shown",
        "Vector shown from the origin",
        "Inclined-plane force",
        "Tension diagram",
        "Force and displacement",
    )
    if caption.startswith(prefixes):
        return hit
    return None


def _number_line_solution(req: GenerateReq) -> bool:
    """The student shows a solution (an inequality's) on a number line."""
    text = _question_text(req)
    return bool(re.search(r"\bnumber[\s-]line\b", text, re.I)
                and re.search(r"[<>≤≥]|\\(?:le|ge|leq|geq|lt|gt)\b|inequalit|solution|\bsolve", text, re.I))


def _generate_visual_sync(req: GenerateReq) -> dict:
    try:
        if _question_should_stay_blank(req):
            return {"ok": False, "tikz": "", "caption": "", "error": "No diagram was produced."}

        if elementary_diagram is not None:
            exact = elementary_diagram(_question_text(req))
            if exact:
                _diagnostic("elementary-route", template=exact["template"])
                rendered = _verified_render(req, exact["tikz"], source="elementary", run_critic=False)
                if rendered.get("ok"):
                    rendered["customized"] = "elementary:" + exact["template"]
                    return rendered
                _diagnostic("elementary-render-error", rendered.get("log") or rendered.get("error", ""))

        # 0) Constrained catalog path (parallel rollout). Route -> fit-check ->
        #    fill declared params -> render. On no-match or failure, fall through
        #    to legacy. When the MODEL judges the keyword-routed template unfit
        #    for the question, skip the legacy keyword templates too (they repeat
        #    the same keyword mistake) and go straight to the reference-guided
        #    bespoke path; if that fails, blank beats wrong.
        if CATALOG_ENABLED:
            try:
                catalog_rendered = _catalog_generate(req)
                if catalog_rendered and catalog_rendered.get("ok"):
                    return catalog_rendered
                if _number_line_solution(req):
                    # the solution marked on a number line is the answer; blank
                    # beats a model drawing of it
                    _diagnostic("number-line-blank", "No model drawing for a solution on a number line.")
                    return {"ok": False, "tikz": "", "caption": "", "error": "No diagram was produced."}
                if catalog_rendered and catalog_rendered.get("unfit"):
                    reference_rendered = _reference_generate(req)
                    if reference_rendered:
                        return reference_rendered
                    return {"ok": False, "tikz": "", "caption": "", "error": "No diagram was produced."}
            except Exception as cat_exc:
                print(f"[catalog] path errored, using legacy pipeline: {str(cat_exc)[:200]}", flush=True)

        # 1) LEGACY regex-template layer - disabled by default since the 2026-07-08
        #    cutover (no fit-check, no readiness gate; kept intercepting questions
        #    the bespoke path draws correctly). TIKZ_LEGACY_TEMPLATES=1 re-enables.
        if LEGACY_TEMPLATES_ENABLED:
            structured_hit = _structured_vector_direct_hit(req)
            if structured_hit:
                rendered = _render_template(req, structured_hit, check_semantics=False)
                if rendered.get("ok"):
                    rendered["customized"] = "structured-deterministic"
                    return rendered

            template_hit = _deterministic_template(req)
            if template_hit:
                rendered = _customize_template_and_render(req, template_hit, source="deterministic-template")
                if rendered.get("ok"):
                    return rendered
                print(
                    "[generate] customized deterministic template failed, trying bespoke Gemini path: "
                    + str(rendered.get("error") or rendered.get("log") or "")[:220],
                    flush=True,
                )

            topic_hit = _topic_blueprint_hit(req)
            if topic_hit:
                rendered = _customize_template_and_render(req, topic_hit, source="topic-template")
                if rendered.get("ok"):
                    return rendered
                print(
                    "[generate] parameterized topic template failed, trying bespoke Gemini path: "
                    + str(rendered.get("error") or rendered.get("log") or "")[:220],
                    flush=True,
                )

        # 2) No exact template matched. Reference-guided fallback: the catalog's
        #    closest templates scaffold a bespoke diagram, which is then gated by the
        #    LLM readiness checker (repair once, else blank - a verified diagram or
        #    none, never a shaky one). Replaces the old unconstrained bespoke path.
        reference_rendered = _reference_generate(req)
        if reference_rendered:
            return reference_rendered

        tikz = ""
        caption = ""
        rendered: dict = {"ok": False, "error": "No diagram was produced."}

        # 3) Last resort (legacy only): retry a matched deterministic blueprint.
        #    Post-cutover the answer is blank - a verified diagram or none.
        if LEGACY_TEMPLATES_ENABLED:
            fallback_rendered = _deterministic_fallback(req)
            if fallback_rendered:
                return fallback_rendered

        rendered["tikz"] = tikz
        rendered["caption"] = caption
        return rendered
    except Exception as exc:
        if LEGACY_TEMPLATES_ENABLED:
            try:
                fallback_rendered = _deterministic_fallback(req)
                if fallback_rendered:
                    return fallback_rendered
            except Exception:
                pass
        return {"ok": False, "error": str(exc)[:500]}


def _cleanup_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        stale = [job_id for job_id, data in jobs.items() if data.get("created", 0) < cutoff]
        for job_id in stale:
            jobs.pop(job_id, None)


def _set_job(job_id: str, **values) -> None:
    if values.get('error'):
        error = str(values['error'])
        for key in GEMINI_KEYS:
            error = error.replace(key, '[redacted]')
        values['error'] = error[:500]
    with _jobs_lock:
        job = jobs.get(job_id)
        if job is not None:
            job.update(values)


def _run_generate_job(job_id: str, req: GenerateReq) -> None:
    _set_job(job_id, status="processing", error="")
    _job_trace.events = []
    _job_trace.last_model, _job_trace.last_pictured = None, False
    try:
        result = _generate_visual_sync(req)
        if result.get("ok"):
            _set_job(
                job_id,
                status="completed",
                ok=True,
                svg=result.get("svg", ""),
                base64=result.get("base64", ""),
                format=result.get("format", req.format),
                mime=result.get("mime", "image/svg+xml" if req.format == "svg" else "image/png"),
                error="",
                source=result.get("customized", ""),
                diagnostics=list(_job_trace.events),
            )
            return
        _set_job(
            job_id,
            status="failed",
            ok=False,
            svg="",
            base64="",
            error=result.get("error") or result.get("log") or "TikZ generation failed.",
            diagnostics=list(_job_trace.events),
        )
    except Exception as exc:
        _diagnostic("job-error", str(exc))
        _set_job(job_id, status="failed", ok=False, error=str(exc)[:500], svg="", base64="", diagnostics=list(_job_trace.events))
    finally:
        del _job_trace.events


@app.post("/generate")
def generate(req: GenerateReq, background_tasks: BackgroundTasks):
    _cleanup_jobs()
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "ok": False,
            "svg": "",
            "base64": "",
            "error": "",
            "created": time.time(),
        }
    background_tasks.add_task(_run_generate_job, job_id, req)
    return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)


@app.get("/status/{job_id}")
def status(job_id: str):
    with _jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return JSONResponse({"status": "failed", "error": "Unknown or expired job id."}, status_code=404)
        if job.get("status") == "completed":
            out = {"status": "completed", "svg": job.get("svg", ""), "error": "",
                   "job_id": job_id, "diagnostics": job.get("diagnostics", []), "source": job.get("source", "")}
            if job.get("base64"):
                out["base64"] = job.get("base64", "")
            return out
        if job.get("status") == "failed":
            return {"status": "failed", "svg": "", "error": job.get("error", "TikZ generation failed."),
                    "job_id": job_id, "diagnostics": job.get("diagnostics", [])}
        return {"status": job.get("status", "pending"), "svg": "", "error": ""}


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
