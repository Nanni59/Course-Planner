"""
Course Planner — Manim render server (Hugging Face Docker Space).

Exposes:
  GET  /health          -> {"status": "ok"}                 (the site pings this to wake/check)
  POST /generate        body {"prompt","subject","question"} -> {"job_id": "..."} (starts a
                          background render thread and returns immediately)
  GET  /status/{job_id} -> {"status","progress","result","error"}  (poll for live progress;
                          result on done = {video_url, captions, filename})
  GET  /video/{name}    -> the silent rendered MP4, served for <video src> (supports Range)

Pipeline: Gemini writes a full MainScene script -> render -> repair loop (max 3). The MP4 is
left INTENTIONALLY SILENT — there is no server-side TTS or audio mux. The scene's own
add_subcaption() lines (frame-locked to the animation via Manim's .srt timeline) are returned
as a structured `captions` array of {text, start} so the site can render interactive closed
captions and speak each beat with the browser's native window.speechSynthesis as it plays.

Gemini keys are read from GEMINI_API_KEY (+ optional GEMINI_API_KEY_2/_3/_4) Space
*secrets* — never hardcoded. On a 429 rate-limit the call rotates to the next key.
"""

import os
import re
import ast
import json
import glob
import time
import uuid
import shutil
import tempfile
import threading
import traceback
import subprocess

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# Collect up to 4 keys (primary first); skip any that aren't set. Load is spread across ALL keys
# round-robin: every gemini() call STARTS on the next key in rotation (see _next_key_index), and
# within a call a 429/timeout advances to the following key. This balances the per-key quota across
# the spec + code + repair calls of each render (and across concurrent renders), so no single key
# is the bottleneck and one rate-limited key never fails a render while others remain.
KEYS = [k for k in (os.environ.get(n) for n in
        ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4")) if k]
_key_idx = 0
_key_lock = threading.Lock()


def _next_key_index():
    """Round-robin pointer: return the index to START the next gemini() call on, then advance the
    shared pointer. Thread-safe so concurrent render threads each take a different key."""
    global _key_idx
    if not KEYS:
        return 0
    with _key_lock:
        i = _key_idx
        _key_idx = (_key_idx + 1) % len(KEYS)
        return i
# gemini-3-flash-preview writes the best free-tier video-lesson animations (richer,
# better-laid-out scenes) while staying free and using the same generateContent API. Preview
# models can still hit capacity spikes, so the renderer automatically falls back to stable free
# models on overload. Override with GEMINI_MODEL and GEMINI_FALLBACK_MODELS in the Space env.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")  # free tier
FALLBACK_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite"
).split(",") if m.strip()]
MODELS = list(dict.fromkeys([MODEL] + FALLBACK_MODELS))
_model_blocked_until = {}
_model_lock = threading.Lock()
MAX_REPAIRS = 3
MAX_ACTIVE_JOBS = int(os.environ.get("MAX_ACTIVE_JOBS", "1"))
RENDER_TIMEOUT = int(os.environ.get("RENDER_TIMEOUT", "600"))
MAX_PROMPT_CHARS = int(os.environ.get("MAX_PROMPT_CHARS", "20000"))
MAX_QUESTION_CHARS = int(os.environ.get("MAX_QUESTION_CHARS", "4000"))
MAX_SUBJECT_CHARS = int(os.environ.get("MAX_SUBJECT_CHARS", "120"))
FALLBACK_RENDER_ON_FAILURE = os.environ.get("FALLBACK_RENDER_ON_FAILURE", "1").lower() not in ("0", "false", "no")

# In-memory job store for non-blocking renders. POST /generate starts a background
# thread and returns a job_id; the site polls GET /status/{job_id} for live progress.
jobs = {}
_jobs_lock = threading.Lock()

# Rendered silent MP4s are written here (one "<job_id>.mp4" per finished job) and served
# by GET /video/{name}, so the site loads them as a streamable <video src> instead of a
# huge base64 blob in the status payload. Cleaned up with their job after an hour.
VIDEO_DIR = os.path.join(tempfile.gettempdir(), "cp_videos")
os.makedirs(VIDEO_DIR, exist_ok=True)


def _set(job_id, **kw):
    """Thread-safe update of a job's state."""
    with _jobs_lock:
        j = jobs.get(job_id)
        if j is not None:
            j.update(kw)


def _cleanup_jobs():
    """Drop jobs older than an hour (and delete their served MP4s) so neither the job dict
    nor VIDEO_DIR can grow without bound."""
    cutoff = time.time() - 3600
    with _jobs_lock:
        stale = [j for j, v in jobs.items() if v.get("created", 0) < cutoff]
        for jid in stale:
            jobs.pop(jid, None)
    for jid in stale:
        try:
            os.remove(os.path.join(VIDEO_DIR, jid + ".mp4"))
        except OSError:
            pass


def _active_job_count():
    active = {"pending", "planning", "rendering", "captioning"}
    with _jobs_lock:
        return sum(1 for j in jobs.values() if j.get("status") in active)


def _render_env():
    """Run generated Manim scenes without deployment/API secrets in their environment."""
    env = os.environ.copy()
    for name in list(env):
        upper = name.upper()
        if any(marker in upper for marker in ("GEMINI", "API_KEY", "TOKEN", "SECRET", "PASSWORD")):
            env.pop(name, None)
    return env


app = FastAPI(title="Course Planner Manim Renderer")

# The static site (GitHub Pages) calls this server cross-origin. The endpoint only
# returns a rendered math video and never exposes the key, so "*" is acceptable.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenReq(BaseModel):
    prompt: str
    subject: str = "General"
    question: str = ""  # optional "focus especially on answering this" hint


# --------------------------------------------------------------------------- Gemini
# Network policy. The free tier can be slow (a full MainScene script is a long completion)
# and occasionally drops a connection or returns a transient 5xx/429. A single failed call
# used to fail the WHOLE render (the "Read timed out" error the site surfaced). So instead of
# one shot, gemini() RETRIES transient failures — read timeouts, connection resets, 5xx and
# 429 — with exponential backoff, rotating to the next key each time, until it succeeds, runs
# out of attempts, or passes an overall wall-clock deadline (so a hung Gemini can't make a
# render hang for the site's full 20-minute poll budget).
GEMINI_TIMEOUT = (15, 180)    # (connect, read) seconds per individual request
GEMINI_MAX_ATTEMPTS = 4       # transient retries (incl. key rotations) before giving up
GEMINI_DEADLINE = 420         # seconds: stop retrying a single gemini() call after this


def _available_models():
    now = time.time()
    with _model_lock:
        models = [m for m in MODELS if _model_blocked_until.get(m, 0) <= now]
    return models or MODELS[:]


def _temporarily_block_model(model, seconds=900):
    with _model_lock:
        _model_blocked_until[model] = time.time() + seconds


def _fallback_models_after(model):
    now = time.time()
    with _model_lock:
        models = [m for m in MODELS if m != model and _model_blocked_until.get(m, 0) <= now]
    return models or [m for m in MODELS if m != model] or [model]


def gemini(prompt, as_json=False, temperature=0.4):
    if not KEYS:
        raise RuntimeError("No Gemini API key is set on the Space.")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    last_err = "Gemini call failed."
    backoff = 3
    started = time.time()
    idx = _next_key_index()   # round-robin: this call starts on the next key in rotation
    models = _available_models()
    for attempt in range(GEMINI_MAX_ATTEMPTS):
        if time.time() - started > GEMINI_DEADLINE:
            break
        key = KEYS[idx]
        model = models[0]
        url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(model)
        try:
            r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                              json=body, timeout=GEMINI_TIMEOUT)
        except requests.exceptions.RequestException as e:
            # Read timeout / connection reset / DNS blip — transient. Rotate key and back off.
            last_err = "Gemini request failed (network/timeout): {}".format(str(e)[:200])
            print("[gemini] {} — attempt {}/{}, retrying.".format(
                last_err, attempt + 1, GEMINI_MAX_ATTEMPTS), flush=True)
            idx = (idx + 1) % len(KEYS)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue

        low_body = r.text.lower()
        if r.status_code == 429:
            last_err = "Gemini API error 429 (rate limited): {}".format(r.text[:200])
            idx = (idx + 1) % len(KEYS)
            # Only pause once a full cycle of keys has been tried, so multi-key setups stay fast.
            if (attempt + 1) % max(1, len(KEYS)) == 0:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
            continue
        if r.status_code == 404 and len(MODELS) > 1:
            last_err = "Gemini API model {} was not found: {}".format(model, r.text[:200])
            _temporarily_block_model(model, seconds=3600)
            models = _fallback_models_after(model)
            backoff = 3
            print("[gemini] {} — falling back to {}.".format(last_err, models[0]), flush=True)
            continue
        if r.status_code in (500, 502, 503, 504):
            last_err = "Gemini API error {} (server): {}".format(r.status_code, r.text[:200])
            if r.status_code == 503 and len(MODELS) > 1 and (
                    "high demand" in low_body or "overloaded" in low_body or "capacity" in low_body):
                _temporarily_block_model(model, seconds=900)
                models = _fallback_models_after(model)
                backoff = 3
                print("[gemini] {} — falling back to {} for this call.".format(
                    last_err, models[0]), flush=True)
                continue
            print("[gemini] {} — attempt {}/{}, retrying.".format(
                last_err, attempt + 1, GEMINI_MAX_ATTEMPTS), flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if r.status_code != 200:
            raise RuntimeError("Gemini API error {}: {}".format(r.status_code, r.text[:300]))

        try:
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            # Empty/blocked candidate (e.g. a safety stop or truncated payload) — the next
            # sample usually succeeds, so retry rather than fail the render outright.
            last_err = "Gemini returned no usable text ({}): {}".format(type(e).__name__, r.text[:200])
            print("[gemini] {} — attempt {}/{}, retrying.".format(
                last_err, attempt + 1, GEMINI_MAX_ATTEMPTS), flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue

        if as_json:
            t = re.sub(r"^```(?:json)?", "", txt.strip()).strip()
            t = re.sub(r"```$", "", t).strip()
            return json.loads(t)
        return txt

    raise RuntimeError(last_err)


# ------------------------------------------------ dynamic Manim code generation
# Instead of filling three fixed templates, Gemini writes a complete Manim script from
# scratch per topic, guided by the system prompt below (Manim best practices + strict
# rules). The existing render -> repair loop re-prompts Gemini with the render-error tail
# until the script compiles or we give up. Inspired by github.com/Yusuke710/manim-skill.
MANIM_SYSTEM_PROMPT = r'''You are an expert mathematical animator and pedagogical engineer specializing in the Manim (Community Edition) library. Your mission is to convert educational concepts into visually flawless, cinematic, clear 3Blue1Brown-style animations. The concept to animate is: {topic} (subject: {subject}){question_line}.

Output ONLY executable Python code inside a single ```python markdown block. No introductory text, explanations, or conclusions outside the code block.
{spec_block}
### 0. NON-NEGOTIABLE OUTPUT CONTRACT (overrides everything below if in conflict)
These keep the render + auto-repair pipeline working — violating any one fails the build:
- Import line is exactly `from manim import *` and nothing else.
- Define exactly ONE scene class, named EXACTLY `MainScene`: `class MainScene(Scene):` (or `class MainScene(MovingCameraScene):` when you need camera moves). Never any other class name — the renderer invokes `MainScene` by name.
- All code lives inside `MainScene.construct(self)`. No top-level execution, no `if __name__` block.
- NEVER call `self.add()` — every mobject must enter the scene through `self.play(...)` so nothing is static.
- Use only standard Manim CE mobjects/animations. No external assets, no file/network/image loading, no SVGs, no downloaded fonts.
- If the topic includes notes from attached source materials or images, treat them as FACTS ONLY. The renderer cannot access those attachments. Do NOT recreate, import, load, trace, or reference the original picture/file; redraw only the underlying idea with simple Manim primitives such as lines, dots, arrows, axes, polygons, labels, and formulas.
- SECURITY: Never import or reference `os`, `sys`, `subprocess`, `socket`, `requests`, `urllib`, `pathlib`, `shutil`, `tempfile`, `importlib`, `builtins`, `inspect`, `ctypes`, `pickle`, or any file/network/process/environment APIs. Never call `open`, `eval`, `exec`, `compile`, `__import__`, `globals`, `locals`, or `vars`.
- Target runtime 50–70 seconds. Render quality is `-qh` (1080p).
- PIPELINE NARRATION MANDATE: At every scene phase and major animation block, call `self.add_subcaption("...")` with the spoken narrative for that beat — this single string IS both the audio the website speaks and the on-screen closed caption, so narration and visuals stay locked together. Write it the way a presenter would SAY it: words, not symbols ("x squared", not "x^2"). If a formula genuinely belongs in the caption, wrap ONLY that formula in inline-LaTeX `\( ... \)` delimiters, e.g. `self.add_subcaption(r"This gives the area \(\pi r^2\).")` — the site typesets the `\(...\)` and still reads the whole line aloud. Use a raw string `r"..."` for any subcaption containing a backslash. On-screen Text/Tex captions in the bottom zone do NOT replace this.

### 1. CORE COMPOSITION & LAYOUT RULES
- BACKGROUND: Keep the default deep dark background. Use high-contrast, modern palettes and avoid muddy or low-contrast combinations.
- CORE COLORS ONLY: Use only these standard Manim global color constants: BLUE, GREEN, RED, YELLOW, ORANGE, PURPLE, PINK, TEAL, MAROON, WHITE, BLACK, GREY.
- HEX CODES FOR CUSTOM PALETTES: For any custom/neon color, never type it as a name constant (do NOT use CYAN, MAGENTA, GOLD, etc.). Always pass it as a raw hex string, e.g. color="#00FFFF" (cyan), color="#FF00FF" (magenta), color="#FFD700" (gold).
- ALIGNMENT: Never guess absolute coordinates like `VGroup(a, b).shift(LEFT * 2.3)`. Use relationships: `.next_to(target, DIRECTION, buff=...)`, `.align_to(target, DIRECTION)`, `.arrange(DIRECTION, buff=...)`, and `.to_edge(...)` / `.move_to(...)` for anchoring.
- PACKAGING: Group related terms, expressions, and text blocks into a `VGroup` before shifting or animating them, so loose components do not drift or overlap.
- TEXT RENDERING: Use `MathTex` for ALL equations, variables and formulas. Use raw strings `r"..."` for every `MathTex`/`Tex` to avoid LaTeX escape errors, e.g. `MathTex(r"\frac{a}{b}")` not `MathTex("\frac{a}{b}")`. For plain-language titles, labels, and explanatory words, prefer `Text(..., font="DejaVu Sans")` so the video feels closer to the app's Century Gothic UI; do NOT use `Tex` for normal English titles because it creates an old serif look. Keep readable scaling like `.scale(0.7)`.

### 2. VISUAL FOCAL GUIDANCE (THE EYE-TRACKING PRINCIPLE)
Static, motionless scenes are forbidden. Every structural transition must guide the eye:
- FORMULA TRANSFORMS: When an equation evolves into a new step, do not fade it out — morph it with `TransformMatchingShapes(old_eq, new_eq)`, `TransformMatchingTex(old_eq, new_eq)`, or `ReplacementTransform(old_eq, new_eq)`.
- CALLOUT HIGHLIGHTS: To address a specific variable, term, or segment, wrap it with a temporary `SurroundingRectangle(target, color="#FFD700", stroke_width=2)`, animated on/off with `Create` then `FadeOut`.
- EMPHASIS HOOKS: Use `self.play(Indicate(target))` or `self.play(Flash(point))` when a critical step or intersection occurs.

### 3. CONTINUOUS TRACKING & DYNAMIC KINEMATICS
- VALUE TRACKERS: For graphs, shapes, or quantities that change over time, drive them with a `ValueTracker(initial_value)`.
- RUNTIME UPDATERS: Attach dynamic layout with `.add_updater(lambda m: m.next_to(...))` or `always_redraw(...)` — e.g. a dot moving along a curve redraws its dashed projection lines to the axes in real time. Define every variable an updater references BEFORE attaching the updater, and remove conflicting updaters before reusing an object.
- SMOOTH PATHS: Prefer sweeping motion like `MoveAlongPath(dot, graph_curve)` and smooth camera pans over harsh jumps or sudden cuts.

### 4. PACING & MOTION (NO DEAD/FROZEN FRAMES)
The website speaks each `add_subcaption(...)` beat in the browser and AUTOMATICALLY pauses the video on that beat until its spoken line finishes. So you must NEVER pad the animation with long static `self.wait()` holds to "leave room for narration" — padding now shows on screen as a frozen frame. Let the browser do the waiting.
- FILL TIME WITH MOTION, NOT WAITS: Carry each phase with animation (`run_time=...`) lasting roughly its budgeted duration. Keep every `self.wait(...)` short — at most ~0.5s of punctuation between beats — and NEVER hold a static frame longer than ~1s.
- CONTINUOUS ANIMATION: Prefer one flowing motion over "animate briefly, then sit still." Give a transform/sweep a longer `run_time` instead of a short animation followed by a long wait. Sustain motion with `ValueTracker` sweeps, `MoveAlongPath`, and `Create(..., run_time=...)`.
- ONE IDEA PER BEAT: Emit `self.add_subcaption(...)` immediately before the animation it describes, so the spoken line and its motion happen together. Do not crowd several ideas into one play call.
- The very last beat may end with a single `self.wait(1)` to let the final line land — nothing longer.

### 5. ANIMATION TOOLKIT — reach for what fits the topic
- Geometry: `Polygon`, `Circle`, `Line`, `Arc` — label with `MathTex`.
- Equations: `Write(MathTex(...))`, then `TransformMatchingTex`/`TransformMatchingShapes` to morph between steps.
- Graphs: `Axes`, `axes.plot(lambda x: ..., x_range=[a, b])`, `Create(graph, run_time=2)`, `Dot` with `MoveAlongPath`. For Riemann sums use EXACTLY `axes.get_riemann_rectangles(graph, x_range=[a, b], dx=0.5, input_sample_type="left")` — the sampling argument is `input_sample_type` (one of "left"/"right"/"center"), NOT `sample_points_func`, and the count is controlled by `dx`, not `n_rects`. For the area under a curve use `axes.get_area(graph, x_range=[a, b])`.
- Vectors: `Arrow`, `GrowArrow`, `.animate.shift()` for tip-to-tail addition.
- Step-by-step working: write each `MathTex` line one at a time, shifting earlier lines `UP`.
- Bullets: `FadeIn(item, shift=RIGHT)` one at a time with `self.wait(0.4)` between.
- Matrices: Manim's `Matrix` mobject. Number lines: `NumberLine` with a `Dot` animating along it.

### 6. SYNTAX SANITIZATION & ANTI-CRASH PROTOCOLS
- Initialize every local variable before any animation or updater references it.
- Use current Manim CE syntax: `Create` (not the removed `ShowCreation`) for non-text mobjects, `FadeOut` (not `FadeOutAndShift`). Do not stack conflicting updaters on the same object.
- Use raw strings for all LaTeX, and only LaTeX/macros that ship with a standard TeX install.
- CAMERA METHOD BOUNDARIES: Never call `self.camera.set_theta()`, `self.camera.set_phi()`, or `self.camera.set_gamma()` — these 3D methods do not exist on standard or moving cameras and will crash the render.
- SCENE SEPARATION: Default to a 2D layout using standard `Scene` inheritance (`class MainScene(Scene):`). Do not introduce 3D scene elements, 3D axes (`ThreeDAxes`), or camera rotations unless the concept explicitly calls for a 3D visual or surface plot.
- 2D CAMERA MANIPULATION: If zoom or panning is needed, use `class MainScene(MovingCameraScene):` and animate the frame via `self.camera.frame.animate.scale(...)` or `self.camera.frame.animate.move_to(...)`. Never call 3D methods on a 2D camera object.
- TEXT LEGIBILITY PROTECTION: Formulas, labels, and captions must never be bound to a 3D coordinate frame or subjected to 3D perspective distortion — do not translate text along a Z-axis, never apply 3D camera tilts/rotations to text, and never place text on a rotated 3D surface. All text mobjects stay as flat 2D overlays fixed against the screen camera plane for absolute readability.
- RATE FUNCTIONS: For `rate_func=` use ONLY these names, which `from manim import *` reliably exposes: `smooth` (the default ease — prefer it), `linear`, `rush_into`, `rush_from`, `there_and_back`, `slow_into`, `double_smooth`, or `wiggle`. Do NOT use `ease_in_out` or any Penner `ease_*` name (e.g. `ease_in_out_sine`, `ease_out_cubic`) — they are not importable as bare names here and crash with NameError. When in doubt, omit `rate_func` entirely (Manim defaults to `smooth`). Never invent a rate-function name.
- NO INVENTED ARGUMENTS OR METHODS: Use only documented ManimCE method names and keyword arguments. Do NOT guess or invent keyword arguments (a wrong kwarg raises `TypeError: unexpected keyword argument` and fails the render). If you are unsure whether an argument exists, OMIT it and rely on the default. Stick to simple, well-established calls; prefer building a shape manually in a helper (see §9) over a fancy built-in you are unsure of.
- NO NONE OBJECTS IN PLAY: Never pass an expression, variable, or function call that evaluates to `None` into `self.play()`. Every argument inside `self.play(...)` must be a valid Manim animation (e.g. `Write(...)`, `FadeIn(...)`, `Create(...)`, `Transform(...)`) or an active `.animate` chain. A helper that builds a mobject must return it (see §9), and you must wrap that returned mobject in an animation — `self.play(Create(make_thing()))`, never `self.play(make_thing())` when the helper returns `None`.

### 7. THREE-ZONE LAYOUT STANDARD (mandatory)
Partition the screen canvas into three non-overlapping vertical zones to guarantee visual breathing room — never let content from one zone overlap another:
- TOP ZONE: static headers, titles, or the active formula. Anchor with `.to_edge(UP, buff=0.5)`.
- CENTER ZONE: reserved exclusively for geometric systems, axes, graphs, and the main animation.
- BOTTOM ZONE: dynamic on-screen narration captions. Position every distinct subtitle/explanation text block with `.to_edge(DOWN, buff=0.6)` at a readable scale (e.g. `.scale(0.65)`), and `FadeOut` the previous caption before showing the next so they never stack.
- ONE OCCUPANT PER ANCHOR — FADE BEFORE REPLACE: Only ONE title or formula may sit in the TOP zone at a time. Before introducing a new title/formula there, `FadeOut` the old one (or `ReplacementTransform`/`TransformMatchingTex` the old INTO the new). NEVER `Write` a second formula onto an anchor while the first is still on screen — that is the #1 cause of overlapping text. The same applies everywhere: if a new mobject would land where another already sits, remove, fade, or move the old one first.
- LABEL PLACEMENT (no collisions): Place every point/curve/segment label with `.next_to(target, DIRECTION, buff>=0.15)` so it sits CLEAR of the curve, the axes, the triangle, and especially the TOP-zone formula — a label must never overlap an equation or another label. Keep labels small (`font_size` 22–28). Before adding a label, picture its bounding box and make sure nothing already occupies that spot.
- DON'T FILL THE FRAME: Leave margins. If the center animation is large, keep the top formula short or `.scale(...)` it down so the two never touch; shrink or reposition rather than letting elements pile up.

### 8. PHASE ARCHITECTURE (follow the Specification)
Implement the phases EXACTLY as enumerated in the APPROVED SPECIFICATION above — same names, same order, and the same per-phase DURATION budgets. Mark each with a banner comment carrying its name and budget, e.g. `# ----- Phase 2: Varying Slope (12s) -----`. Within a phase, the `self.play(run_time=...)` calls (plus tiny waits) should sum to roughly that phase's budgeted seconds, and the whole scene to the Specification's total (target 50–70s). Emit a `self.add_subcaption(...)` for each beat inside its phase. Where the Specification's layout shows the slate must reset between phases, clear it with `self.play(FadeOut(*self.mobjects))`.
(If no Specification is provided above, fall back to four phases — Setup, Core Concept, Development, Conclusion — sized to sum to ~60s.)

### 9. PROCEDURAL HELPER METHODS (mandatory)
For structures that need iteration or repetition — Riemann series, matrix grids, summation steps, coordinate ticks, custom math groups — do NOT write nested loops inline inside `construct`. Instead define standalone, cleanly scoped helper methods on the SAME `MainScene` class, placed BELOW `construct` (e.g. `def build_step_rectangles(self, ...):` or `def make_vector_field(self, ...):`), each returning a clean `VGroup` or mobject. Keep the `construct` flow highly scannable, with heavy object-assembly logic isolated in these helpers. Do not add any class other than `MainScene`.
- MANDATORY HELPER RETURN STATEMENTS: Every procedural helper method on `MainScene` MUST end with an explicit `return` that hands back a fully formed Mobject, VGroup, or Graph. Never omit the `return`, and never let a helper implicitly return `None` — a helper whose result is fed to `self.play(...)` and returns `None` raises `Scene.play() got None`.

### §10 REFERENCE ARCHITECTURE EXAMPLES (ANIMG PARADIGMS)
Study these premium implementations for their LAYOUT PARTITIONING (three zones), USE OF UPDATERS (ValueTracker + always_redraw), CHRONOLOGICAL PHASE COMMENTING, and OBJECT SCOPING (VGroup grouping + class-level helper methods). They are PATTERN references, NOT copy-paste templates: they predate this contract, so §0–§9 ALWAYS override them. When you reuse a pattern you MUST: (a) name YOUR class exactly `MainScene` — ignore the example class names; (b) NEVER use `self.add()` — introduce every mobject through `self.play(...)`; (c) emit `self.add_subcaption(...)` at each beat (the examples omit it — you must not); (d) follow the 4-phase banner structure of §8; (e) use raw strings for LaTeX and the CORE-COLORS/hex policy of §1; (f) import only `from manim import *` and use current ManimCE API per §6 (treat any older calls such as `get_graph` as illustrative only). The lessons to copy are the STRUCTURE and MOTION, not the literal class headers or `self.add` calls.

----- REFERENCE 1: Geometric Series -----
from manim import *


class GeometricSeries(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        # ── Phase 1: Introduction ─────────────────────────────────────────────
        title = Text("Geometric Series", font_size=44, color=WHITE).to_edge(UP)
        formula = MathTex(r"S = \frac{a}{1 - r}", font_size=42).next_to(title, DOWN, buff=0.3)
        params = MathTex(r"a = 1,\quad r = \tfrac{1}{2},\quad S = 2",
                          font_size=34, color=YELLOW).next_to(formula, DOWN, buff=0.25)

        self.play(Write(title), run_time=1.5)
        self.play(Write(formula), run_time=1.5)
        self.play(Write(params), run_time=1.5)
        self.wait(1)

        # ── Setup: square parameters ──────────────────────────────────────────
        # We'll draw rectangles of fixed height but halving width
        RECT_HEIGHT = 2.0       # Manim units tall
        SCALE = 3.0             # 1 unit = 3 Manim units wide for the first square
        START_X = -3.0          # left edge of first square
        BASE_Y = -1.0           # bottom y of rectangles

        COLORS = [BLUE, GREEN, YELLOW, ORANGE, RED, PURPLE, PINK]
        n_terms = 7
        terms = [1 / (2 ** i) for i in range(n_terms)]

        # "Target" dashed boundary at x = START_X + 2*SCALE = 3.0
        target_x = START_X + 2 * SCALE
        target_line = DashedLine(
            start=[target_x, BASE_Y - 0.2, 0],
            end=[target_x, BASE_Y + RECT_HEIGHT + 0.2, 0],
            color=WHITE, stroke_width=1.5, dash_length=0.15
        )
        target_label = MathTex(r"2", font_size=22, color=WHITE).next_to(
            [target_x, BASE_Y - 0.2, 0], DOWN, buff=0.15
        )
        self.play(Create(target_line), Write(target_label), run_time=1)

        # Running sum label
        sum_val = 0.0
        sum_label = always_redraw(lambda: MathTex(
            r"\text{Sum} \approx " + f"{sum_val:.4f}",
            font_size=32, color=WHITE
        ).to_edge(DOWN).shift(UP * 0.3))

        self.add(sum_label)

        # ── Phases 2 & 3: Draw rectangles one by one ──────────────────────────
        current_x = START_X
        rectangles = VGroup()
        fraction_labels = VGroup()
        partial_sum_labels = VGroup()

        series_text_parts = []  # will build up "1 + 1/2 + 1/4 + ..."

        for i, term in enumerate(terms):
            width = term * SCALE
            rect = Rectangle(
                width=width,
                height=RECT_HEIGHT,
                fill_color=COLORS[i % len(COLORS)],
                fill_opacity=0.7,
                stroke_color=WHITE,
                stroke_width=1.5,
            )
            rect.move_to([current_x + width / 2, BASE_Y + RECT_HEIGHT / 2, 0])

            # Fraction label inside rectangle
            if term == 1:
                frac_str = r"1"
            elif term >= 0.01:
                denom = int(round(1 / term))
                frac_str = rf"\frac{{1}}{{{denom}}}"
            else:
                frac_str = r"\cdots"

            frac_lbl = MathTex(frac_str, font_size=max(14, 28 - i * 3),
                                color=WHITE).move_to(rect.get_center())

            # Partial sum
            sum_val += term
            partial_lbl = MathTex(
                f"{sum_val:.3f}", font_size=20, color=YELLOW
            ).next_to(rect, UP, buff=0.1)

            self.play(
                FadeIn(rect, shift=UP * 0.15),
                Write(frac_lbl),
                run_time=0.8 if i > 0 else 1.5
            )
            # Force redraw of sum label by modifying its captured variable
            # (use a direct text object instead of always_redraw)
            new_sum_lbl = MathTex(
                r"\text{Sum} \approx " + f"{sum_val:.4f}",
                font_size=32, color=WHITE
            ).to_edge(DOWN).shift(UP * 0.3)
            self.play(FadeIn(partial_lbl), Transform(sum_label, new_sum_lbl),
                      run_time=0.6)
            self.wait(0.4)

            rectangles.add(rect)
            fraction_labels.add(frac_lbl)
            partial_sum_labels.add(partial_lbl)
            current_x += width

        # ── Phase 4: Convergence ──────────────────────────────────────────────
        conv_arrow = Arrow(
            start=[target_x - 0.3, BASE_Y + RECT_HEIGHT + 0.5, 0],
            end=[target_x, BASE_Y + RECT_HEIGHT + 0.05, 0],
            color=WHITE, stroke_width=2, tip_length=0.2
        )
        conv_text = MathTex(
            r"S = \frac{1}{1 - \frac{1}{2}} = 2",
            font_size=34, color=YELLOW
        ).next_to(conv_arrow.get_start(), UP, buff=0.15)

        self.play(Create(conv_arrow), Write(conv_text), run_time=2)
        self.wait(2)

        limit_eq = MathTex(
            r"\sum_{n=0}^{\infty} \frac{1}{2^n} = 2",
            font_size=36, color=WHITE
        ).to_corner(UR).shift(LEFT * 0.3 + DOWN * 0.5)
        self.play(Write(limit_eq), run_time=2)
        self.wait(2)

        # ── Phase 5: Summary ──────────────────────────────────────────────────
        condition = MathTex(
            r"\text{Converges when } |r| < 1",
            font_size=30, color=GREEN
        ).to_edge(DOWN).shift(UP * 0.8)
        self.play(Write(condition), run_time=1.5)
        self.wait(4)

        self.play(FadeOut(VGroup(
            title, formula, params, rectangles, fraction_labels,
            partial_sum_labels, target_line, target_label, sum_label,
            conv_arrow, conv_text, limit_eq, condition
        )))
        self.wait(0.5)

----- REFERENCE 2: Trigonometry & the Unit Circle -----
from manim import *
import numpy as np


class TrigUnitCircle(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        # ── Axes setup ────────────────────────────────────────────────────────
        circle_axes = Axes(
            x_range=[-1.5, 1.5, 0.5],
            y_range=[-1.5, 1.5, 0.5],
            x_length=5.5,
            y_length=5.5,
            axis_config={"color": GREY_B, "stroke_width": 1.5},
            tips=False,
        ).shift(LEFT * 2.8)

        wave_axes = Axes(
            x_range=[0, 2 * PI, PI / 2],
            y_range=[-1.5, 1.5, 0.5],
            x_length=5.5,
            y_length=5.5,
            axis_config={"color": GREY_B, "stroke_width": 1.5},
            tips=False,
        ).shift(RIGHT * 2.8)

        unit_circle = Circle(
            radius=circle_axes.c2p(1, 0)[0] - circle_axes.c2p(0, 0)[0],
            color=GREY_B, stroke_width=2
        ).move_to(circle_axes.c2p(0, 0))

        circle_label = Text("Unit Circle", font_size=20, color=GREY_A)
        circle_label.next_to(circle_axes, UP, buff=0.1)

        # Phase 1: Setup
        self.play(Create(circle_axes), Create(wave_axes), run_time=1.5)
        self.play(Create(unit_circle), Write(circle_label), run_time=1.5)
        self.wait(0.5)

        # Phase 2: Key angle labels
        key_angles = [
            (0, "0"), (PI/6, "pi/6"), (PI/4, "pi/4"),
            (PI/3, "pi/3"), (PI/2, "pi/2"), (PI, "pi"),
        ]
        angle_markers = VGroup()
        for angle, label_str in key_angles:
            x, y = np.cos(angle), np.sin(angle)
            dot = Dot(circle_axes.c2p(x, y), color=YELLOW, radius=0.07)
            lbl = Text(label_str, font_size=14, color=YELLOW).move_to(
                circle_axes.c2p(x * 1.3, y * 1.3)
            )
            angle_markers.add(dot, lbl)
        self.play(Write(angle_markers), run_time=2)
        self.wait(1)

        # Phase 3: Animate point around circle
        theta_tracker = ValueTracker(0.0)

        point = always_redraw(lambda: Dot(
            circle_axes.c2p(np.cos(theta_tracker.get_value()),
                            np.sin(theta_tracker.get_value())),
            color=WHITE, radius=0.1
        ))
        radius_line = always_redraw(lambda: Line(
            circle_axes.c2p(0, 0),
            circle_axes.c2p(np.cos(theta_tracker.get_value()),
                            np.sin(theta_tracker.get_value())),
            color=WHITE, stroke_width=2
        ))
        sin_line = always_redraw(lambda: Line(
            circle_axes.c2p(np.cos(theta_tracker.get_value()), 0),
            circle_axes.c2p(np.cos(theta_tracker.get_value()),
                            np.sin(theta_tracker.get_value())),
            color=RED, stroke_width=3
        ))
        cos_line = always_redraw(lambda: Line(
            circle_axes.c2p(0, 0),
            circle_axes.c2p(np.cos(theta_tracker.get_value()), 0),
            color=BLUE_B, stroke_width=3
        ))
        theta_label = always_redraw(lambda: Text(
            "theta = " + f"{theta_tracker.get_value():.2f}",
            font_size=24, color=YELLOW
        ).to_corner(DL).shift(UP * 0.3 + RIGHT * 0.3))

        self.add(point, radius_line, sin_line, cos_line, theta_label)
        self.play(theta_tracker.animate.set_value(2 * PI),
                  run_time=6, rate_func=linear)
        self.wait(0.5)

        # Phase 4: Show sin and cos waves
        sin_wave = wave_axes.plot(np.sin, x_range=[0, 2*PI], color=RED, stroke_width=3)
        cos_wave = wave_axes.plot(np.cos, x_range=[0, 2*PI], color=BLUE_B, stroke_width=3)

        sin_lbl = Text("sin(theta)", font_size=20, color=RED).next_to(
            wave_axes.c2p(PI/2, 1.2), UP, buff=0.1)
        cos_lbl = Text("cos(theta)", font_size=20, color=BLUE_B).next_to(
            wave_axes.c2p(0, 1.2), UP, buff=0.1)

        self.play(Create(sin_wave), Create(cos_wave), run_time=2)
        self.play(FadeIn(sin_lbl), FadeIn(cos_lbl), run_time=0.8)
        self.wait(1)

        # Phase 5: Summary
        identity = Text("sin(theta)^2 + cos(theta)^2 = 1",
                        font_size=28, color=WHITE)
        identity.to_edge(DOWN, buff=0.4)
        identity_box = SurroundingRectangle(identity, color=YELLOW, buff=0.15)
        self.play(Write(identity), Create(identity_box), run_time=2)
        self.wait(3)
        self.play(FadeOut(Group(*self.mobjects)), run_time=1.5)
        self.wait(0.5)

----- REFERENCE 3: Linear Functions: Slope & Y-Intercept -----
from manim import *


class LinearFunctions(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        # ── Setup ─────────────────────────────────────────────────────────────
        plane = NumberPlane(
            x_range=[-5, 5, 1],
            y_range=[-4, 4, 1],
            background_line_style={
                "stroke_color": GREY_D,
                "stroke_width": 1,
                "stroke_opacity": 0.5
            }
        )
        self.play(Create(plane), run_time=1.5)

        m_tracker = ValueTracker(1.0)
        b_tracker = ValueTracker(0.0)

        # Dynamic Line
        line = always_redraw(lambda: plane.get_graph(
            lambda x: m_tracker.get_value() * x + b_tracker.get_value(),
            color=YELLOW
        ))

        # Dynamic Equation Readout
        eq_label = always_redraw(lambda: MathTex(
            f"y = {m_tracker.get_value():.2f}x + {b_tracker.get_value():.2f}",
            color=WHITE, font_size=36
        ).to_corner(UL).shift(RIGHT * 0.2 + DOWN * 0.2))

        self.add(line, eq_label)
        self.wait(1)

        # ── Phase 2: Varying Slope ────────────────────────────────────────────
        # Slope triangle (rise/run)
        slope_tri = always_redraw(lambda: self.get_slope_triangle(plane, m_tracker.get_value(), b_tracker.get_value()))
        self.add(slope_tri)

        self.play(m_tracker.animate.set_value(2.0), run_time=3)
        self.play(m_tracker.animate.set_value(-2.0), run_time=4)
        self.play(m_tracker.animate.set_value(1.0), run_time=3)
        self.wait(1)

        # ── Phase 3: Varying Intercept ────────────────────────────────────────
        intercept_dot = always_redraw(lambda: Dot(
            plane.c2p(0, b_tracker.get_value()), color=RED, radius=0.1
        ))
        self.add(intercept_dot)

        self.play(b_tracker.animate.set_value(3.0), run_time=3)
        self.play(b_tracker.animate.set_value(-3.0), run_time=4)
        self.play(b_tracker.animate.set_value(0.0), run_time=3)
        self.wait(2)

        # ── Phase 4: Summary ──────────────────────────────────────────────────
        summary_text = MathTex("y = mx + b", color=YELLOW, font_size=48).to_edge(DOWN, buff=0.5)
        self.play(Write(summary_text), run_time=1.5)
        self.wait(3)

    def get_slope_triangle(self, plane, m, b):
        x1, y1 = 1, m * 1 + b
        x2, y2 = 2, m * 2 + b
        p1 = plane.c2p(x1, y1)
        p2 = plane.c2p(x2, y1)
        p3 = plane.c2p(x2, y2)

        run_line = Line(p1, p2, color=GREEN, stroke_width=4)
        rise_line = Line(p2, p3, color=GREEN_E, stroke_width=4)
        return VGroup(run_line, rise_line)

----- REFERENCE 4: Negative Numbers on the Number Line -----
from manim import *


class NegativeNumbers(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        # ── Setup ─────────────────────────────────────────────────────────────
        number_line = NumberLine(
            x_range=[-10, 10, 1],
            length=10,
            include_numbers=True,
            label_direction=DOWN,
            color=WHITE
        )
        self.play(Create(number_line), run_time=2)
        self.wait(1)

        # Highlight Zero
        zero_marker = Dot(number_line.n2p(0), color=YELLOW, radius=0.15)
        zero_label = Text("Zero", font_size=24, color=YELLOW).next_to(zero_marker, UP)
        self.play(FadeIn(zero_marker), Write(zero_label))
        self.wait(1)

        # ── Phase 3: Negative Side ────────────────────────────────────────────
        neg_region = Rectangle(
            width=5, height=0.5, fill_color=RED, fill_opacity=0.3, stroke_width=0
        ).move_to(number_line.n2p(-5)).shift(UP * 0.5)
        neg_text = Text("Negative Numbers", font_size=32, color=RED).next_to(neg_region, UP)
        self.play(FadeIn(neg_region), Write(neg_text))
        self.wait(2)

        # ── Phase 4: Operations ───────────────────────────────────────────────
        # Example: 2 + (-3) = -1
        eq = MathTex("2 + (-3) = -1", font_size=48).to_edge(UP, buff=1.5)
        self.play(Write(eq))

        dot = Dot(number_line.n2p(2), color=YELLOW)
        self.add(dot)

        hop = CurvedArrow(number_line.n2p(2), number_line.n2p(-1), angle=-TAU/4, color=YELLOW)
        self.play(Create(hop), dot.animate.move_to(number_line.n2p(-1)), run_time=2)
        self.wait(3)

        self.play(FadeOut(VGroup(neg_region, neg_text, eq, dot, hop, zero_marker, zero_label)))
        self.wait(1)

----- REFERENCE 5: Deriving the Quadratic Formula -----
from manim import *


class QuadraticDerivation(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        title = Text("Deriving the Quadratic Formula", font_size=40).to_edge(UP)
        self.play(Write(title))

        # Step 1
        eq1 = MathTex("ax^2 + bx + c = 0")
        self.play(Write(eq1))
        self.wait(1)

        # Step 2: divide by a
        eq2 = MathTex("x^2 + \\frac{b}{a}x + \\frac{c}{a} = 0")
        self.play(TransformMatchingTex(eq1, eq2))
        self.wait(1)

        # Step 3: move c/a
        eq3 = MathTex("x^2 + \\frac{b}{a}x = -\\frac{c}{a}")
        self.play(TransformMatchingTex(eq2, eq3))
        self.wait(1)

        # Step 4: complete the square
        eq4 = MathTex("x^2 + \\frac{b}{a}x + \\left(\\frac{b}{2a}\\right)^2 = -\\frac{c}{a} + \\left(\\frac{b}{2a}\\right)^2")
        self.play(TransformMatchingTex(eq3, eq4))
        self.wait(1)

        # Final Result (Skipping steps for brevity)
        final_eq = MathTex(
            "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}",
            font_size=60, color=YELLOW
        ).shift(DOWN * 0.5)
        box = SurroundingRectangle(final_eq, color=WHITE, buff=0.3)
        
        self.play(FadeOut(eq4), Write(final_eq), Create(box))
        self.wait(3)

----- REFERENCE 6: Vectors in 2D -----
from manim import *


class Vectors2D(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        plane = NumberPlane()
        self.add(plane)

        v = Vector([3, 2], color=YELLOW)
        v_label = MathTex("\\vec{v} = \\begin{bmatrix} 3 \\\\ 2 \\end{bmatrix}", color=YELLOW).next_to(v.get_end(), UR)

        self.play(Create(v), Write(v_label))
        self.wait(1)

        # Components
        x_line = DashedLine(plane.c2p(0, 0), plane.c2p(3, 0), color=BLUE)
        y_line = DashedLine(plane.c2p(3, 0), plane.c2p(3, 2), color=BLUE)
        self.play(Create(x_line), Create(y_line))
        self.wait(2)

        # Magnitude
        mag_eq = MathTex("||\\vec{v}|| = \\sqrt{3^2 + 2^2} \\approx 3.61", color=WHITE).to_corner(UL)
        self.play(Write(mag_eq))
        self.wait(3)

----- REFERENCE 7: Permutations vs Combinations -----
from manim import *


class PermutationsCombinations(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        title = Text("Permutations vs Combinations", font_size=36).to_edge(UP)
        self.add(title)

        items = Text("{A, B, C}", color=YELLOW).next_to(title, DOWN)
        self.play(Write(items))

        # Permutations
        perms = VGroup(
            Text("(A,B)"), Text("(B,A)"),
            Text("(A,C)"), Text("(C,A)"),
            Text("(B,C)"), Text("(C,B)")
        ).arrange_in_grid(rows=3, cols=2, buff=1).shift(LEFT * 3)
        
        perm_title = Text("Permutations", color=BLUE, font_size=24).next_to(perms, UP)
        self.play(Write(perm_title), Write(perms))
        self.wait(2)

        # Combinations
        combs = VGroup(
            Text("{A,B}"), Text("{A,C}"), Text("{B,C}")
        ).arrange(DOWN, buff=1.2).shift(RIGHT * 3)
        
        comb_title = Text("Combinations", color=GREEN, font_size=24).next_to(combs, UP)
        self.play(Write(comb_title))

        # Animation: Collapsing
        self.play(
            ReplacementTransform(VGroup(perms[0], perms[1]), combs[0]),
            ReplacementTransform(VGroup(perms[2], perms[3]), combs[1]),
            ReplacementTransform(VGroup(perms[4], perms[5]), combs[2]),
            run_time=3
        )
        self.wait(3)

----- REFERENCE 8: Percentages -----
from manim import *


class Percentages(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        grid = VGroup(*[Square(side_length=0.3) for _ in range(100)]).arrange_in_grid(rows=10, cols=10, buff=0.05).shift(LEFT * 3)
        self.play(Create(grid), run_time=2)

        # Shade 25%
        shaded = VGroup(*[grid[i].copy().set_fill(YELLOW, opacity=0.8) for i in range(25)])
        
        calc = MathTex("\\frac{25}{100} = 0.25 = 25\\%", font_size=48).shift(RIGHT * 3)
        
        self.play(FadeIn(shaded), Write(calc), run_time=2)
        self.wait(3)

----- REFERENCE 9: Logarithms: Inverse of Exponential -----
from manim import *
import numpy as np


class LogInverse(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        axes = Axes(x_range=[-2, 5], y_range=[-2, 5], axis_config={"include_tip": True})
        self.play(Create(axes))

        exp_curve = axes.plot(lambda x: 2**x, color=BLUE)
        exp_label = MathTex("y = 2^x", color=BLUE).next_to(exp_curve, UR, buff=0.1)

        self.play(Create(exp_curve), Write(exp_label))
        self.wait(1)

        sym_line = DashedLine(axes.c2p(-2, -2), axes.c2p(5, 5), color=WHITE)
        self.play(Create(sym_line))

        log_curve = axes.plot(lambda x: np.log2(x) if x > 0 else -10, x_range=[0.25, 5], color=RED)
        log_label = MathTex("y = \\log_2(x)", color=RED).next_to(log_curve, DR, buff=0.1)

        self.play(TransformFromCopy(exp_curve, log_curve), Write(log_label), run_time=2)
        self.wait(3)

----- REFERENCE 10: Eigenvalues & Eigenvectors -----
from manim import *


class Eigenvalues(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        matrix = [[2, 1], [1, 2]]
        
        grid = NumberPlane()
        self.add(grid)

        v = Vector([1, 1], color=YELLOW) # This is an eigenvector for this matrix
        self.play(Create(v))
        self.wait(1)

        self.play(
            grid.animate.apply_matrix(matrix),
            v.animate.apply_matrix(matrix),
            run_time=3
        )
        self.wait(2)
        
        eq = MathTex("A\\vec{v} = 3\\vec{v}", color=YELLOW).to_corner(UL)
        self.play(Write(eq))
        self.wait(3)

----- REFERENCE 11: Area of Triangle and Circle -----
from manim import *
import numpy as np


class AreaProof(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"

        # Triangle
        rect = Rectangle(width=4, height=3, color=GREY)
        diag = Line(rect.get_corner(DL), rect.get_corner(UR), color=WHITE)
        tri = Polygon(rect.get_corner(DL), rect.get_corner(DR), rect.get_corner(UR), fill_opacity=0.5, color=BLUE)
        
        self.play(Create(rect))
        self.play(Create(diag))
        self.play(FadeIn(tri))
        
        label = MathTex("A = \\frac{1}{2}bh").next_to(rect, DOWN)
        self.play(Write(label))
        self.wait(2)
        self.play(FadeOut(VGroup(rect, diag, tri, label)))

        # Circle (Conceptual)
        circle = Circle(radius=2, color=RED)
        self.play(Create(circle))
        self.wait(1)
        
        # Slices (simplification)
        slices = VGroup(*[AnnularSector(inner_radius=0, outer_radius=2, angle=TAU/8, start_angle=i*TAU/8, color=RED, fill_opacity=0.5) for i in range(8)])
        self.play(ReplacementTransform(circle, slices))
        self.wait(2)
'''


def _strip_code_fences(txt):
    """Gemini sometimes wraps code in ```python fences despite instructions — strip them."""
    t = (txt or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


_BANNED_IMPORT_ROOTS = {
    "os", "sys", "subprocess", "socket", "requests", "urllib", "http", "pathlib", "shutil",
    "tempfile", "importlib", "builtins", "inspect", "ctypes", "multiprocessing", "threading",
    "asyncio", "pickle", "marshal", "base64",
}
_BANNED_CALLS = {"eval", "exec", "compile", "open", "__import__", "input", "globals", "locals", "vars"}
_BANNED_NAMES = {"__builtins__", "__loader__", "__spec__", "__package__", "__file__", "__cached__"}
_BANNED_ASSET_MOBJECTS = {"ImageMobject", "SVGMobject", "VMobjectFromSVGPath"}


def validate_scene_code(code):
    """Static guardrail for model-authored Manim code before Manim executes it.

    This is defense-in-depth, not a full Python sandbox. The Manim subprocess also receives a
    scrubbed environment so even a missed trick cannot read Gemini/HF secrets from env vars.
    """
    errors = []
    try:
        tree = ast.parse(code or "")
    except SyntaxError as e:
        return ["Scene code does not parse: {}".format(e)]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            errors.append("Only `from manim import *` is allowed; plain import statements are blocked.")
            continue
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if node.module != "manim" or not any(alias.name == "*" for alias in node.names):
                errors.append("Blocked import from `{}`; only `from manim import *` is allowed.".format(node.module or ""))
            if mod in _BANNED_IMPORT_ROOTS:
                errors.append("Blocked dangerous import root `{}`.".format(mod))
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _BANNED_CALLS:
                errors.append("Blocked call to `{}`.".format(fn.id))
            elif isinstance(fn, ast.Name) and fn.id in _BANNED_ASSET_MOBJECTS:
                errors.append("External asset mobject `{}` is not available; redraw the idea with Manim primitives.".format(fn.id))
            elif isinstance(fn, ast.Attribute) and fn.attr in _BANNED_CALLS:
                errors.append("Blocked call to attribute `{}`.".format(fn.attr))
        if isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            errors.append("Blocked access to `{}`.".format(node.id))
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                errors.append("Blocked dunder attribute access `{}`.".format(node.attr))
            root = node.value
            if isinstance(root, ast.Name) and root.id in _BANNED_IMPORT_ROOTS:
                errors.append("Blocked access to dangerous module/object `{}`.".format(root.id))

    return sorted(set(errors))


SPEC_SYSTEM_PROMPT = r'''You are a pedagogical engineer planning a 3Blue1Brown-style Manim animation BEFORE any code is written. Design a clear, faithful Specification for an educational animation of: {topic} (subject: {subject}){question_line}.

Output the Specification as Markdown with EXACTLY these sections, in this order. No code, no preamble, no closing remarks.

**Description**
One short paragraph: what the animation shows and the intuition it builds.

**Phases**
A Markdown table with columns `| # | Phase Name | Duration | Description |`.
- 4 or 5 phases, in chronological order.
- Duration is whole seconds written like "8s"; the durations MUST sum to between 50 and 70 seconds.
- Each Description says what ANIMATES (continuous motion, not static holds) and what is spoken in that phase.

**Layout**
A small ASCII sketch splitting the screen into a TOP zone (title / active formula), a CENTER zone (the main animation), and a BOTTOM zone (captions), showing roughly where the key elements sit.

**Area Descriptions**
A Markdown table `| Area | Content | Notes |` — one row per screen region, naming the Manim mobjects that live there.

**Assets & Dependencies**
- Colors: choose from Manim core constants (BLUE, GREEN, RED, YELLOW, ORANGE, PURPLE, PINK, TEAL, MAROON, WHITE, GREY); for any custom colour give a hex string like "#FFD700". State each colour's role (e.g. CURVE = BLUE).
- Manim: ManimCE, 2D `Scene`.
- External assets: none. If the source notes describe an attached image or photo, convert only its educational content into simple Manim primitives; never require image files, SVGs, URLs, or `ImageMobject`.

**Notes**
3-6 concrete implementation hints: which Manim mobjects/animations to use, what to drive with a `ValueTracker`, what should keep moving continuously, and any alignment cautions.

Keep it tight and concrete — a coder will reproduce this Specification faithfully, so every phase needs a duration and every region needs named content.'''


def generate_spec(topic, subject, question=""):
    """First pass of the two-pass pipeline: Gemini DESIGNS the lesson as a Markdown Specification
    (description, a phased timeline with per-phase durations, layout, area table, assets, notes)
    before any code exists. The spec is then handed to generate_manim_code() to implement, which
    makes pacing deliberate and the structure consistent. Returns the spec text, or "" on failure
    (the code pass then runs spec-free)."""
    question_line = ""
    if (question or "").strip():
        question_line = ", focusing especially on answering: " + question.strip()
    prompt = (SPEC_SYSTEM_PROMPT
              .replace("{topic}", topic or "")
              .replace("{subject}", subject or "General")
              .replace("{question_line}", question_line))
    return (gemini(prompt, temperature=0.5) or "").strip()


def generate_manim_code(topic, subject, question="", broken=None, error=None, spec=None):
    """Second pass: one Gemini call -> a complete Manim script (class MainScene) that implements
    the approved `spec` (when provided). On a repair pass the previous (broken) script and the
    render-error tail are appended so Gemini fixes to the same rules and the same spec. Returns
    raw Python source with any markdown fences stripped."""
    question_line = ""
    if (question or "").strip():
        question_line = ", focusing especially on answering: " + question.strip()
    spec_block = ""
    if (spec or "").strip():
        spec_block = ("\n### APPROVED SPECIFICATION (implement this EXACTLY)\n"
                      "You already designed this lesson. Build the Manim scene that realises the "
                      "Specification below — honour its phase names, order and per-phase DURATION "
                      "budgets, its layout zones, and its colour/asset choices.\n\n"
                      + spec.strip() + "\n")
    prompt = (MANIM_SYSTEM_PROMPT
              .replace("{spec_block}", spec_block)
              .replace("{topic}", topic or "")
              .replace("{subject}", subject or "General")
              .replace("{question_line}", question_line))
    if broken is not None and error:
        prompt += ("\n\nThe PREVIOUS SCRIPT below failed to render. Return a corrected, "
                   "COMPLETE script that still follows every rule above, fixing the actual "
                   "cause (bad LaTeX, an undefined name, a Manim API misuse, or a bad value)."
                   "\n\nPREVIOUS SCRIPT:\n" + str(broken)
                   + "\n\nRENDER ERROR (tail):\n" + error[-1800:])
    return _strip_code_fences(gemini(prompt, temperature=0.4))


# Appended to every generated scene before render. Gemini still occasionally emits
# `self.play(None)` (a helper that forgot to return a mobject), which crashes the whole
# render with "Unexpected argument None passed to Scene.play()" and burns all 3 repair
# attempts. This monkeypatch makes Scene.play tolerate it: None args are dropped, and a
# play() left with no animations becomes a no-op (a skipped beat) instead of a hard crash.
# Self-contained and wrapped in try/except so the guard can never itself break a render.
_SCENE_GUARD = '''

# --- render-server safety guard (auto-appended) ---
try:
    from manim import Scene as _CP_Scene
    _cp_orig_play = _CP_Scene.play

    def _cp_safe_play(self, *args, **kwargs):
        args = tuple(a for a in args if a is not None)
        if not args:
            return
        return _cp_orig_play(self, *args, **kwargs)

    _CP_Scene.play = _cp_safe_play
except Exception:
    pass

# Gemini keeps reaching for easing rate functions that `from manim import *` does NOT expose as
# bare names in this ManimCE — e.g. `rate_func=ease_in_out_sine` (NameError) or `ease_in_out`
# (doesn't exist at all). Either crashes the render and burns every repair attempt. Define the
# whole Penner easing family (and the bare ease_* shorthands) as module attributes AND as bare
# globals the scene can reference: each maps to the real curve if this ManimCE has it, else to a
# safe fallback (`smooth`). globals().setdefault never clobbers a name the scene already imported.
try:
    from manim.utils import rate_functions as _cp_rf
    _cp_fallback = getattr(_cp_rf, "smooth", None)
    _cp_names = ["ease", "ease_in", "ease_out", "ease_in_out"]
    for _cp_base in ("sine", "quad", "cubic", "quart", "quint", "expo",
                     "circ", "back", "elastic", "bounce"):
        for _cp_pre in ("ease_in_", "ease_out_", "ease_in_out_"):
            _cp_names.append(_cp_pre + _cp_base)
    for _cp_n in _cp_names:
        _cp_fn = getattr(_cp_rf, _cp_n, None) or _cp_fallback
        if _cp_fn is not None:
            if not hasattr(_cp_rf, _cp_n):
                try:
                    setattr(_cp_rf, _cp_n, _cp_fn)
                except Exception:
                    pass
            globals().setdefault(_cp_n, _cp_fn)
except Exception:
    pass

# Gemini frequently calls graphing helpers with keyword arguments that don't exist in this
# ManimCE (e.g. axes.get_riemann_rectangles(sample_points_func=...) -> TypeError: unexpected
# keyword argument), which crashes the render and burns every repair attempt. Wrap the most-
# misused CoordinateSystem methods (Axes/NumberPlane inherit them) to silently DROP kwargs the
# real method doesn't declare, so a hallucinated argument degrades to default behaviour instead
# of crashing. Methods that already take **kwargs are left alone.
try:
    import inspect as _cp_inspect
    from manim import CoordinateSystem as _CP_CS

    def _cp_kwarg_filter(cls, name):
        orig = getattr(cls, name, None)
        if not callable(orig):
            return
        try:
            params = _cp_inspect.signature(orig).parameters
        except (TypeError, ValueError):
            return
        if any(p.kind == p.VAR_KEYWORD for p in params.values()):
            return  # already accepts arbitrary kwargs — nothing to guard
        allowed = set(params)

        def _wrap(self, *a, **kw):
            return orig(self, *a, **{k: v for k, v in kw.items() if k in allowed})
        _wrap.__name__ = getattr(orig, "__name__", name)
        setattr(cls, name, _wrap)

    for _cp_m in ("get_riemann_rectangles", "get_area", "get_secant_slope_group", "plot",
                  "plot_parametric_curve", "plot_polar_graph", "get_vertical_lines_to_graph",
                  "get_lines_to_point", "get_vertical_line", "get_horizontal_line",
                  "get_graph", "get_T_label"):
        try:
            _cp_kwarg_filter(_CP_CS, _cp_m)
        except Exception:
            pass
except Exception:
    pass

# A second common model slip: using familiar color names that this Manim build does not expose
# as bare constants. Give those names safe hex equivalents so a good scene does not fail only
# because it wrote CYAN or GOLD once.
try:
    _cp_color_aliases = {
        "CYAN": "#00FFFF",
        "MAGENTA": "#FF00FF",
        "GOLD": "#FFD700",
        "LIME": "#00FF66",
        "NAVY": "#1E3A8A",
    }
    for _cp_name, _cp_value in _cp_color_aliases.items():
        globals().setdefault(_cp_name, _cp_value)
except Exception:
    pass
'''


def _harden_scene(code):
    """Append the runtime guard so common model mistakes degrade gracefully instead of crashing
    the render: a stray `self.play(None)` becomes a skipped beat, invented rate functions
    (`ease_in_out` &c.) are aliased to real curves, and unknown kwargs on the most-misused graphing
    helpers (`get_riemann_rectangles(sample_points_func=...)` &c.) are dropped. Kept separate from
    the model's `code` so the repair loop still re-prompts on the model's original source."""
    return (code or "") + "\n" + _SCENE_GUARD


def _count_segments(code):
    """Estimate how many partial movie files Manim will emit for a scene — one per `self.play(`
    AND one per `self.wait(` — so render progress can be gauged from how many exist so far.
    Min 1 to avoid divide-by-zero."""
    code = code or ""
    return max(1, code.count("self.play(") + code.count("self.wait("))


def _faststart_copy(src, dst):
    """Stream-copy `src` to `dst` with the moov atom relocated to the front (`-movflags
    +faststart`). No re-encode, so it's fast and lossless. Returns True on success; on any
    failure the caller falls back to a plain byte copy. ffmpeg ships in the Docker image."""
    try:
        p = subprocess.run(["ffmpeg", "-y", "-i", src, "-c", "copy", "-movflags", "+faststart", dst],
                           capture_output=True, text=True, timeout=120)
        return p.returncode == 0 and os.path.isfile(dst) and os.path.getsize(dst) > 0
    except Exception as e:
        print("[publish] faststart remux failed ({!r}) — using a plain copy.".format(e), flush=True)
        return False


def render(scene_path, workdir, quality="-qh", on_progress=None, n_anim=1):
    """Render `MainScene` at 1080p / 30fps (30fps halves the frame count vs the -qh default of
    60 — visually identical for these animations, ~2x faster on the free CPU tier). While Manim
    runs, a watcher thread counts the partial movie files it emits (one per animation) and reports
    real fractional progress 0..1 via `on_progress`, so the site's bar advances during the render
    instead of sitting still then jumping. The generated script defines `class MainScene(Scene)`."""
    stop = threading.Event()

    def _watch():
        # Poll the partial_movie_files Manim writes per animation -> fraction of n_anim done.
        while not stop.wait(1.5):
            try:
                parts = glob.glob(os.path.join(workdir, "media", "videos", "**",
                                  "partial_movie_files", "**", "*.mp4"), recursive=True)
                on_progress(min(0.98, len(parts) / float(max(1, n_anim))))
            except Exception:
                pass

    watcher = None
    if on_progress:
        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()
    try:
        p = subprocess.run(["manim", quality, "--fps", "30", scene_path, "MainScene"],
                           cwd=workdir, capture_output=True, text=True,
                           timeout=RENDER_TIMEOUT, env=_render_env())
    except subprocess.TimeoutExpired as e:
        stop.set()
        log = ((e.stdout or "") if isinstance(e.stdout, str) else "") + "\n" + \
              ((e.stderr or "") if isinstance(e.stderr, str) else "")
        return False, "Render timed out after {} seconds.\n{}".format(RENDER_TIMEOUT, log), None
    finally:
        stop.set()
        if watcher:
            watcher.join(timeout=3)
    log = (p.stdout or "") + "\n" + (p.stderr or "")
    mp4s = glob.glob(os.path.join(workdir, "media", "videos", "**", "MainScene*.mp4"), recursive=True)
    return (p.returncode == 0 and bool(mp4s)), log, (sorted(mp4s)[-1] if mp4s else None)


# ------------------------------------------------------------------- narration
def narration_script(prompt, subject, content):
    ask = ("Write a narration script to be read aloud over an educational math/physics "
           "animation. Write 120-180 words of plain spoken English a teacher would say, in "
           "this order: a short introduction, building up the idea, the key concept, a worked "
           "example, and a one-sentence recap. Do NOT use markdown, headings, bullet points or "
           "LaTeX symbols - write maths as a narrator would speak it (say 'x squared', not "
           "'x^2'). Return only the narration text.\nTopic: " + prompt + "\nSubject: " + subject
           + "\nOn-screen content for reference: " + str(content)[:1500])
    return gemini(ask, temperature=0.5).strip()


# ----------------------------------------- scene subcaptions -> narration source
def _static_str(node):
    """Best-effort: resolve an AST string expression to its literal text, or None.
    Handles plain string constants, `+`-concatenated strings, and the literal portions
    of f-strings (dynamic `{...}` parts are dropped)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static_str(node.left), _static_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _clean_caption(txt):
    """Normalise a subcaption into a single clean line. Whitespace is collapsed and stray
    markdown emphasis (``*``/backticks — the browser TTS would otherwise read "asterisk" aloud)
    is dropped, but any inline LaTeX (e.g. ``\\( ... \\)``) is PRESERVED: the website typesets it
    for the on-screen caption and converts it to spoken words for the browser's text-to-speech."""
    t = (txt or "").replace("\n", " ").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", t).strip()


def extract_subcaptions(code):
    """Parse the ordered `self.add_subcaption("...")` strings out of a generated MainScene
    script. These are the exact per-beat spoken narrative the model authored, in source
    order (= animation order), so they drive BOTH the TTS audio and the VTT cues — which
    is what guarantees the subtitles match the spoken audio word-for-word.

    AST-based (robust to commas/escapes inside the string); falls back to a regex only if
    the source somehow doesn't parse. Returns a list of cleaned, non-empty captions."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        caps = re.findall(r"add_subcaption\(\s*[rRfFbB]*(['\"])(.*?)(?<!\\)\1", code or "", re.S)
        return [c for c in (_clean_caption(t) for _, t in caps) if c]

    found = []  # (lineno, col, text) so we can restore source order
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_subcaption"):
            arg = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg in ("content", "text")), None)
            text = _static_str(arg) if arg is not None else None
            if text:
                found.append((node.lineno, node.col_offset, text))
    found.sort(key=lambda x: (x[0], x[1]))
    return [c for c in (_clean_caption(t) for _, _, t in found) if c]


def _srt_ts_to_sec(ts):
    """'00:00:03,500' -> 3.5 seconds."""
    hh, mm, rest = ts.strip().split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def parse_srt(text):
    """Parse a SubRip (.srt) into ordered (start, end, text) cues in seconds. This is the
    subtitle timeline Manim writes during render from the scene's add_subcaption() calls,
    so each start is the exact animation time (frame marker) a caption appears on screen."""
    cues = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        timing = next((ln for ln in lines if "-->" in ln), None)
        if not timing:
            continue
        try:
            start_s, end_s = timing.split("-->")
            start, end = _srt_ts_to_sec(start_s), _srt_ts_to_sec(end_s)
        except Exception:
            continue
        body = " ".join(lines[lines.index(timing) + 1:]).strip()
        if body:
            cues.append((start, end, body))
    cues.sort(key=lambda c: c[0])
    return cues


def _find_srt(workdir):
    """Locate the MainScene .srt Manim emitted next to the rendered mp4 (if any)."""
    hits = glob.glob(os.path.join(workdir, "media", "videos", "**", "MainScene*.srt"),
                     recursive=True)
    return sorted(hits)[-1] if hits else None


def build_captions(workdir, content, prompt, subject):
    """Turn the scene's narration beats into a structured caption timeline for the browser.

    No audio is synthesised server-side — the rendered MP4 stays SILENT. The site speaks each
    beat with the browser's native window.speechSynthesis and renders the same text as closed
    captions, so the "voice" matches the Slide Deck generator exactly.

    Returns an ordered list of {"text": <plain spoken line>, "start": <seconds float | None>}.
    Caption sources, in priority order (we never regress to no captions):
      1. Manim's .srt timeline (frame-locked): `start` is the exact animation-time the caption
         appears on screen, so the site can fire each utterance as the video reaches it.
      2. The scene's add_subcaption() strings, when no .srt was emitted: `start` is None and the
         site speaks them in order (one after the previous finishes).
      3. A Gemini narration script split into sentences, when the scene had no subcaptions at
         all: `start` is None (sequential). `content` is the generated MainScene source.
    Every step is best-effort; on total failure we return [] (a silent, caption-less video)."""
    # 1. Frame-locked from Manim's own subtitle timeline.
    srt = _find_srt(workdir)
    if srt:
        try:
            timed = parse_srt(open(srt, encoding="utf-8").read())
        except Exception as e:
            print("[captions] could not read SRT ({!r}) — ignoring timeline.".format(e),
                  flush=True)
            timed = []
        caps = [{"text": _clean_caption(t), "start": max(0.0, s)} for (s, _e, t) in timed]
        caps = [c for c in caps if c["text"]]
        if caps:
            print("[captions] {} captions frame-locked to the manim SRT timeline.".format(
                len(caps)), flush=True)
            return caps

    # 2. The add_subcaption() strings parsed straight from the source (no timeline available).
    subs = extract_subcaptions(content or "")
    if subs:
        print("[captions] no SRT timeline — {} subcaptions returned for sequential playback."
              .format(len(subs)), flush=True)
        return [{"text": t, "start": None} for t in subs]

    # 3. Last resort: a generated narration script split into sentence cues.
    print("[captions] no subcaptions — falling back to a Gemini narration script.", flush=True)
    try:
        script = narration_script(prompt, subject, content)
    except Exception as e:
        print("[captions] script generation failed: " + repr(e), flush=True)
        traceback.print_exc()
        return []
    if not script:
        print("[captions] Gemini returned an empty script — no captions.", flush=True)
        return []
    sentences = [c for c in (_clean_caption(s) for s in
                 re.split(r"(?<=[.!?])\s+", script.strip())) if c] or [_clean_caption(script)]
    return [{"text": t, "start": None} for t in sentences if t]


def _clean_fallback_text(value, max_len=120):
    """Short plain text for the deterministic fallback scene."""
    text = str(value or "")
    text = re.sub(r"---\s*Source material brief\s*---", " ", text, flags=re.I)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"\\[()[\]]|\$+", " ", text)
    text = re.sub(r"[#*_`>|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].strip() + "..."
    return text or "STEM lesson"


def _fallback_points(prompt, question):
    """Extract a few safe teaching points from the prompt without asking Gemini again."""
    text = str(prompt or "")
    text = re.sub(r"---\s*Source material brief\s*---", ". ", text, flags=re.I)
    chunks = re.split(r"(?:\n+|[.;!?]\s+|-\s+|\u2022\s+)", text)
    points = []
    if (question or "").strip():
        points.append("Answer the focus question: " + _clean_fallback_text(question, 95))
    for chunk in chunks:
        t = _clean_fallback_text(chunk, 105)
        low = t.lower()
        if len(t) < 18:
            continue
        if "file:" in low or "source material" in low or "attached image" in low:
            continue
        if t not in points:
            points.append(t)
        if len(points) >= 5:
            break
    defaults = [
        "Identify the main quantities and how they relate.",
        "Represent the idea with simple shapes, arrows, and labels.",
        "Move from intuition to the key formula or rule.",
        "Apply the rule to the focus question step by step.",
        "End with the core takeaway in one sentence.",
    ]
    while len(points) < 5:
        points.append(defaults[len(points) % len(defaults)])
    return points[:5]


def fallback_scene_code(prompt, subject, question="", reason=""):
    """A deterministic, low-risk Manim lesson used only after generated scenes fail."""
    title = _clean_fallback_text(str(prompt or "").splitlines()[0], 54)
    subtitle = _clean_fallback_text(subject or "General", 42)
    points = _fallback_points(prompt, question)
    spoken_title = _clean_fallback_text(title, 90)
    return """
from manim import *


class MainScene(Scene):
    def construct(self):
        self.camera.background_color = "#111827"
        title = Text(%s, font="DejaVu Sans", font_size=40, color=WHITE).to_edge(UP, buff=0.55)
        subtitle = Text(%s, font="DejaVu Sans", font_size=24, color="#A7F3D0").next_to(title, DOWN, buff=0.18)

        self.add_subcaption(%s)
        self.play(Write(title), FadeIn(subtitle, shift=UP * 0.15), run_time=2.4)

        frame = RoundedRectangle(width=10.8, height=4.25, corner_radius=0.25, stroke_color="#38BDF8", stroke_width=2)
        left = Circle(radius=0.55, color="#60A5FA").shift(LEFT * 3.1 + UP * 0.45)
        mid = Circle(radius=0.55, color="#FBBF24").shift(UP * 0.45)
        right = Circle(radius=0.55, color="#34D399").shift(RIGHT * 3.1 + UP * 0.45)
        arrows = VGroup(
            Arrow(left.get_right(), mid.get_left(), buff=0.12, color=WHITE),
            Arrow(mid.get_right(), right.get_left(), buff=0.12, color=WHITE),
        )
        labels = VGroup(
            Text("Given", font="DejaVu Sans", font_size=25, color=WHITE).next_to(left, DOWN, buff=0.25),
            Text("Reason", font="DejaVu Sans", font_size=25, color=WHITE).next_to(mid, DOWN, buff=0.25),
            Text("Result", font="DejaVu Sans", font_size=25, color=WHITE).next_to(right, DOWN, buff=0.25),
        )
        diagram = VGroup(frame, left, mid, right, arrows, labels).move_to(ORIGIN)
        self.add_subcaption("First, organize the lesson into what is given, the reasoning step, and the result.")
        self.play(Create(frame), LaggedStart(FadeIn(left), FadeIn(mid), FadeIn(right), Create(arrows), FadeIn(labels), lag_ratio=0.18), run_time=4.2)

        points = %s
        rows = VGroup()
        for i, line in enumerate(points, start=1):
            badge = Circle(radius=0.22, color="#34D399", fill_opacity=0.22)
            num = Text(str(i), font="DejaVu Sans", font_size=18, color=WHITE).move_to(badge)
            body = Text(line, font="DejaVu Sans", font_size=24, color=WHITE)
            row = VGroup(VGroup(badge, num), body).arrange(RIGHT, buff=0.25, aligned_edge=UP)
            if row.width > 10.6:
                row.scale_to_fit_width(10.6)
            rows.add(row)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.27).move_to(ORIGIN).shift(DOWN * 0.15)

        self.add_subcaption("Now turn the source material into a clean sequence of ideas.")
        self.play(FadeOut(diagram), run_time=0.9)
        for i, row in enumerate(rows):
            self.add_subcaption("Point " + str(i + 1) + ": " + points[i])
            self.play(FadeIn(row, shift=RIGHT * 0.2), run_time=2.4)

        box = SurroundingRectangle(rows, color="#FBBF24", buff=0.22, stroke_width=2)
        takeaway = Text("Core takeaway", font="DejaVu Sans", font_size=30, color="#FBBF24").next_to(rows, DOWN, buff=0.35)
        if takeaway.get_bottom()[1] < -3.45:
            takeaway.to_edge(DOWN, buff=0.35)
        self.add_subcaption("The takeaway is to connect each known fact to the next step, then check that the result answers the question.")
        self.play(Create(box), FadeIn(takeaway, shift=UP * 0.15), run_time=2.8)
        self.play(Indicate(box, color="#FBBF24"), run_time=1.6)
        self.wait(0.5)
""" % (
        json.dumps(title),
        json.dumps(subtitle),
        json.dumps("Let's build a reliable visual summary for " + spoken_title + "."),
        json.dumps(points),
    )


# ------------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "model_candidates": _available_models()}


def _run_job(job_id, prompt, subject, question):
    """Background worker: the full render pipeline, writing live progress into jobs[job_id].
    Progress: created 5 -> plan 10 -> code 20 -> render started 30 -> render done 70 ->
    captions 85 -> published 95 -> done 100. Two-pass generation: first design a Specification
    (phased, with per-phase durations), then write the MainScene that implements it. The MP4 is
    silent — narration is spoken in the browser from the `captions` timeline. Failure -> error."""
    workdir = tempfile.mkdtemp(prefix="manim_")
    scene_path = os.path.join(workdir, "generated_scene.py")
    try:
        # Pass 1 — design the lesson Specification (best-effort: a failure here just drops us to
        # spec-free code generation rather than failing the whole job). Reused across repairs.
        spec = ""
        try:
            _set(job_id, status="planning", progress=10)
            spec = generate_spec(prompt, subject, question=question)
        except Exception as e:
            print("[spec] generation failed, continuing without a spec: " + repr(e), flush=True)
            spec = ""

        # Pass 2 — write the MainScene that implements the Specification.
        try:
            code = generate_manim_code(prompt, subject, question=question, spec=spec)
        except Exception as e:
            _set(job_id, status="error", error="Gemini call failed: {}".format(e))
            return
        _set(job_id, status="rendering", progress=20)  # code generated

        last_log = ""
        mp4 = None
        for attempt in range(MAX_REPAIRS + 1):  # 1 initial + up to 3 repairs
            validation_errors = validate_scene_code(code)
            if validation_errors:
                last_log = "Security validation blocked the generated scene:\n" + "\n".join(validation_errors[:12])
                print("[security] " + last_log.replace("\n", " | "), flush=True)
                if attempt == MAX_REPAIRS:
                    break
                try:
                    code = generate_manim_code(prompt, subject, question=question,
                                               broken=code, error=last_log, spec=spec)
                except Exception as e:
                    _set(job_id, status="error", error="Repair call failed: {}".format(e))
                    return
                continue
            with open(scene_path, "w", encoding="utf-8") as fh:
                fh.write(_harden_scene(code))
            _set(job_id, status="rendering", progress=30)  # render started
            # Real render progress: map Manim's partial-file fraction (0..1) onto the 30..70 band
            # so the bar climbs steadily through the long render instead of sitting at 30.
            ok, log, m = render(
                scene_path, workdir,
                on_progress=lambda f: _set(job_id, progress=int(30 + f * 40)),
                n_anim=_count_segments(code))
            last_log = log
            if ok:
                mp4 = m
                break
            if attempt == MAX_REPAIRS:
                break
            try:
                code = generate_manim_code(prompt, subject, question=question,
                                           broken=code, error=log, spec=spec)
            except Exception as e:
                _set(job_id, status="error", error="Repair call failed: {}".format(e))
                return

        if not mp4 and FALLBACK_RENDER_ON_FAILURE:
            print("[render] generated scene failed after repairs; trying deterministic fallback.",
                  flush=True)
            try:
                fallback_code = fallback_scene_code(prompt, subject, question=question,
                                                    reason=last_log[-800:])
                validation_errors = validate_scene_code(fallback_code)
                if validation_errors:
                    last_log += "\nFallback validation failed:\n" + "\n".join(validation_errors[:8])
                else:
                    code = fallback_code
                    with open(scene_path, "w", encoding="utf-8") as fh:
                        fh.write(_harden_scene(code))
                    _set(job_id, status="rendering", progress=45)
                    ok, log, m = render(
                        scene_path, workdir,
                        on_progress=lambda f: _set(job_id, progress=int(45 + f * 25)),
                        n_anim=_count_segments(code))
                    last_log = log
                    if ok:
                        mp4 = m
                        print("[render] deterministic fallback succeeded.", flush=True)
                    else:
                        print("[render] deterministic fallback failed.", flush=True)
            except Exception as e:
                last_log += "\nFallback render exception: {}".format(e)

        if not mp4:
            _set(job_id, status="error",
                 error="Render failed after {} repair attempts.\n{}".format(
                     MAX_REPAIRS, last_log[-400:]))
            return
        _set(job_id, progress=70)  # render complete

        # Build the structured caption timeline (text + frame-locked start times) from the
        # scene's own subcaptions. No audio is synthesised — the browser speaks each beat.
        # `code` is passed as the on-screen "content" reference for the no-SRT fallbacks.
        _set(job_id, status="captioning", progress=85)
        captions = build_captions(workdir, code, prompt, subject)

        # Publish the silent MP4 to the served VIDEO_DIR (it must outlive `workdir`, which is
        # deleted below) so the site can stream it from GET /video/{job_id}.mp4. Web-optimise it
        # first (+faststart) so the browser learns the duration up front and can seek anywhere
        # smoothly — without it, a streamed mp4 whose moov atom sits at the END often reports an
        # unknown/Infinity duration and the scrub bar only works at the very start and end.
        out_path = os.path.join(VIDEO_DIR, job_id + ".mp4")
        if not _faststart_copy(mp4, out_path):
            shutil.copyfile(mp4, out_path)
        _set(job_id, progress=95)  # video published

        _set(job_id, status="done", progress=100, result={
            "video_url": "/video/" + job_id + ".mp4",  # relative to the Space origin
            "captions": captions,
            "filename": "manim-lesson.mp4",
        })
    except Exception as e:
        _set(job_id, status="error", error=str(e))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@app.post("/generate")
def generate(req: GenReq):
    if not KEYS:
        return JSONResponse(status_code=500,
                            content={"error": "No Gemini API key is configured on the Space."})
    req.prompt = (req.prompt or "").strip()
    req.subject = (req.subject or "General").strip()[:MAX_SUBJECT_CHARS] or "General"
    req.question = (req.question or "").strip()
    if not req.prompt:
        return JSONResponse(status_code=400, content={"error": "A 'prompt' is required."})
    if len(req.prompt) > MAX_PROMPT_CHARS:
        return JSONResponse(status_code=413, content={"error": "Prompt is too large."})
    if len(req.question) > MAX_QUESTION_CHARS:
        return JSONResponse(status_code=413, content={"error": "Question/focus text is too large."})

    _cleanup_jobs()
    if _active_job_count() >= MAX_ACTIVE_JOBS:
        return JSONResponse(status_code=429,
                            content={"error": "Renderer is busy. Please wait for the current render to finish."})
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        jobs[job_id] = {"status": "pending", "progress": 5, "result": None,
                        "error": None, "created": time.time()}
    # Non-blocking: render on a background thread and return the id immediately so the
    # site can poll /status/{job_id} for live progress instead of holding the request open.
    threading.Thread(target=_run_job, args=(job_id, req.prompt, req.subject, req.question),
                     daemon=True).start()
    return JSONResponse(content={"job_id": job_id})


@app.get("/status/{job_id}")
def status(job_id: str):
    with _jobs_lock:
        j = jobs.get(job_id)
        if j is None:
            return JSONResponse(status_code=404, content={"error": "Unknown or expired job id."})
        # The result is now lightweight (a video_url + the captions array — the MP4 itself is
        # served separately by /video), so we keep it retrievable on repeat polls: a transient
        # blip while the site reads "done" no longer loses the payload. The job (and its served
        # MP4) are dropped together after an hour by _cleanup_jobs.
        return {"status": j["status"], "progress": j["progress"],
                "result": j["result"], "error": j["error"]}


@app.get("/video/{name}")
def video(name: str):
    """Serve a finished job's silent MP4 by "<job_id>.mp4". Streams with Range support so the
    site's <video> can seek. basename() guards against path traversal; only .mp4 is served."""
    safe = os.path.basename(name)
    path = os.path.join(VIDEO_DIR, safe)
    if not (safe.endswith(".mp4") and os.path.isfile(path)):
        return JSONResponse(status_code=404, content={"error": "Video not found or expired."})
    return FileResponse(path, media_type="video/mp4", filename="manim-lesson.mp4")
