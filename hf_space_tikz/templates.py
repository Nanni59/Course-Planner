r"""
Course Planner - TikZ template catalog (the single source of truth for the
constrained "AI fills values, code assembles the diagram" generation path).

WHY THIS FILE EXISTS
--------------------
The old backend defined every diagram three times, in three incompatible
formats: a regex-extraction template, a `.format()` param blueprint, and a
few-shot example block. They drifted constantly. This module replaces all
three with ONE declarative catalog entry per diagram. The generation pipeline
becomes linear: route -> fill params -> render/repair -> (reference fallback).

The AI is never asked to write TikZ on the primary path. It only returns a flat
JSON object of parameter values. Deterministic code substitutes those values
into a fixed skeleton, so structure is guaranteed correct and only the numbers,
labels, and a couple of constrained slots vary.

HOW TO ADD A TEMPLATE (the authoring contract)
----------------------------------------------
Append a dict to TEMPLATES with these keys:

  id        Unique short slug, e.g. "triangle_general".
  subject   Course name it belongs to, or "*" for general STEM. Used only as a
            mild routing tiebreak; triggers do the real work.
  triggers  List of lowercase substrings. If any appear in the request text,
            this template is a routing candidate; more hits = higher priority.
  caption   One short sentence describing the finished diagram.
  skeleton  Raw TikZ (a full tikzpicture environment). Insert a value slot as
            __NAME__ (double underscore, UPPERCASE). Literal LaTeX braces {..}
            stay literal - no brace-doubling, unlike the old .format() path.
  params    Dict mapping each __NAME__ slot to a spec:
              type      "label" | "number" | "tikz"
              default   String used when the AI omits the value or on fallback.
              desc      One line telling the AI what to put here.
              answer_safe (optional, default True) Set False for a slot that
                        holds the requested UNKNOWN on a worksheet; if the AI
                        fills it with a solved-looking value it is replaced by
                        `unknown` on worksheet targets.
              unknown   (optional, default "?") Replacement symbol above.

  reference (optional) A richer worked TikZ example of this diagram, shown to
            the AI verbatim only when this template is used as a few-shot
            reference for a bespoke (no-exact-template) request. Never compiled.

Param TYPES and their sanitizers:
  label  Math/text label. LaTeX backslashes preserved (\vec, \theta, \circ).
  number Pure number; anything non-numeric collapses to the default.
  tikz   Zero or more constrained TikZ lines (currently: angle pics only).

Run `python templates.py` to validate the catalog and see a routing/fill demo.
"""

import re


ALL_PARAM_TYPES = ("label", "number", "tikz")


# ---------------------------------------------------------------------------
# Value sanitizers (pure; ported faithfully from the old app.py so the new path
# is self-contained and unit-testable without importing the FastAPI service).
# ---------------------------------------------------------------------------

def repair_transport_escapes(text: str) -> str:
    r"""Repair LaTeX command names damaged by a layer interpreting \t, \f, etc."""
    text = str(text or "")
    text = re.sub(r"\t\s*riangle\b", r"\\triangle", text)
    text = re.sub(r"\t\s*ext\s*\{", r"\\text{", text)
    text = re.sub(r"\t\s*heta\b", r"\\theta", text)
    text = re.sub(r"\t\s*imes\b", r"\\times", text)
    text = re.sub(r"\t\s*an\b", r"\\tan", text)
    text = re.sub(r"\t\s*o\b", r"\\to", text)
    text = re.sub(r"\f\s*rac\b", r"\\frac", text)
    text = re.sub(r"\r\s*ight\b", r"\\right", text)
    text = re.sub(r"\n\s*abla\b", r"\\nabla", text)
    return text


def sanitize_label(value, default: str = "") -> str:
    """A math/text label. Keeps LaTeX backslashes and common math punctuation;
    strips newlines, separators, and anything that could break out of a node."""
    value = repair_transport_escapes(str(value if value is not None else default))
    value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    value = re.sub(r"[;&]", " ", value)
    # Allow % so an escaped \% (e.g. "68\%") survives; a bare % would only
    # comment out the label and fail the compile, which the repair loop catches.
    value = re.sub(r"[^A-Za-z0-9_+\-*/=.,:(){}\\^\s/|%°]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or default


def sanitize_number(value, default: str = "0") -> str:
    value = str(value if value is not None else default).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return match.group(0) if match else default


_TIKZ_LINE_BLOCKLIST = re.compile(
    r"\\(?:write18|input|include|openin|openout|read|write|def|let|newcommand|"
    r"renewcommand|usepackage|documentclass|catcode|csname|immediate|special|"
    r"includegraphics|externalize)\b",
    re.IGNORECASE,
)


def sanitize_tikz_lines(value, default: str = "") -> str:
    """Constrained TikZ passthrough. Today this only permits angle/right-angle
    pics (the one slot where free-form TikZ is genuinely needed - variable count
    of angle marks). Any dangerous macro voids the whole value to its default."""
    value = repair_transport_escapes(str(value if value is not None else default))
    if _TIKZ_LINE_BLOCKLIST.search(value):
        return default
    lines = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        if "\\pic" in line and ("angle=" in line or "right angle=" in line):
            lines.append(line)
    return "\n  ".join(lines) or default


_SANITIZERS = {
    "label": sanitize_label,
    "number": sanitize_number,
    "tikz": sanitize_tikz_lines,
}


# ---------------------------------------------------------------------------
# The catalog. Seed set spans every param type and three subjects so the schema
# is proven before the remaining diagrams are migrated. Faithful to the old
# blueprints, with the vector-angle label bug fixed (old blueprint emitted
# "$..^\circ" with no closing $).
# ---------------------------------------------------------------------------

TEMPLATES: list[dict] = [
    {
        "id": "triangle_general",
        "subject": "Calculus & Vectors",
        "triggers": [
            "triangle", "law of sines", "law of cosines", "sine law", "cosine law",
            "sas", "sss", "asa", "included angle", "angle of elevation",
            "angle of depression", "line of sight",
        ],
        "caption": "Triangle with interior angle and side labels.",
        "skeleton": r"""\begin{tikzpicture}[scale=.9]
  \coordinate (A) at (0,0); \coordinate (B) at (4.2,0); \coordinate (C) at (1.35,2.35);
  \draw[cp line] (A)--(B)--(C)--cycle;
  \node[below left] at (A) {$__A__$};
  \node[below right] at (B) {$__B__$};
  \node[above] at (C) {$__C__$};
  \node[below] at ($(A)!0.5!(B)$) {$__AB__$};
  \node[left] at ($(A)!0.5!(C)$) {$__AC__$};
  \node[right] at ($(B)!0.5!(C)$) {$__BC__$};
  __ANGLE_LINES__
\end{tikzpicture}""",
        "params": {
            "A": {"type": "label", "default": "A", "desc": "bottom-left vertex label"},
            "B": {"type": "label", "default": "B", "desc": "bottom-right vertex label"},
            "C": {"type": "label", "default": "C", "desc": "top vertex label"},
            "AB": {"type": "label", "default": "c", "desc": "label on side A-B (given value or symbol)"},
            "AC": {"type": "label", "default": "b", "desc": "label on side A-C (given value or symbol)"},
            "BC": {"type": "label", "default": "a", "desc": "label on side B-C (given value or symbol)"},
            "ANGLE_LINES": {
                "type": "tikz", "default": "",
                "desc": (
                    "Zero or more interior angle pics, one per line. Vertex is the "
                    "MIDDLE coordinate. At A use {angle=B--A--C}; at B use "
                    "{angle=C--B--A}; at C use {angle=A--C--B}. Example: "
                    "\\pic[draw=black,angle radius=5mm,\"$45^\\circ$\",angle "
                    "eccentricity=1.35] {angle=B--A--C};"
                ),
            },
        },
    },
    {
        "id": "bearing_two_leg",
        "subject": "Calculus & Vectors",
        "triggers": ["bearing", "navigation", "heading", "compass", "due north", "due east"],
        "caption": "Bearing diagram with north reference rays and travel vectors.",
        "skeleton": r"""\begin{tikzpicture}[scale=.85]
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
\end{tikzpicture}""",
        "params": {
            "A1": {"type": "number", "default": "45", "desc": "first leg direction in standard math degrees = 90 - bearing1"},
            "A2": {"type": "number", "default": "-25", "desc": "second leg direction = 90 - bearing2"},
            "M1": {"type": "number", "default": "67.5", "desc": "midpoint angle for first bearing arc label = (90 + A1)/2"},
            "M2": {"type": "number", "default": "32.5", "desc": "midpoint angle for second bearing arc label = (90 + A2)/2"},
            "B1": {"type": "number", "default": "45", "desc": "first bearing value in degrees, as measured clockwise from north"},
            "B2": {"type": "number", "default": "115", "desc": "second bearing value in degrees"},
            "L1": {"type": "label", "default": "45^\\circ", "desc": "label on first leg (given distance with unit, else the bearing)"},
            "L2": {"type": "label", "default": "115^\\circ", "desc": "label on second leg"},
        },
    },
    {
        "id": "vector_resultant",
        "subject": "Calculus & Vectors",
        "triggers": ["resultant", "parallelogram", "sum of two vectors", "add the vectors", "vector addition"],
        "caption": "Vector resultant shown with a parallelogram construction.",
        "skeleton": r"""\begin{tikzpicture}[scale=.82]
  \coordinate (O) at (0,0); \coordinate (A) at (3.2,0); \coordinate (B) at (__ANGLE__:2.2); \coordinate (C) at ($(A)+(B)$);
  \draw[cp dashed] (A)--(C)--(B);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below] {$__U__$};
  \draw[cp line,-Stealth] (O)--(B) node[midway,left] {$__V__$};
  \draw[cp line,-Stealth] (O)--(C) node[pos=.58,above] {$__R__$};
  \pic[draw=black,angle radius=5mm,"$__ANGLE__^\circ$",angle eccentricity=1.35] {angle=A--O--B};
  \fill (O) circle (1.3pt);
\end{tikzpicture}""",
        "params": {
            "ANGLE": {"type": "number", "default": "55", "desc": "angle between the two vectors in degrees"},
            "U": {"type": "label", "default": "\\vec{u}", "desc": "first vector label (optionally with given magnitude)"},
            "V": {"type": "label", "default": "\\vec{v}", "desc": "second vector label"},
            "R": {"type": "label", "default": "\\vec{u}+\\vec{v}", "answer_safe": False,
                  "desc": "resultant label - use \\vec{R} or u+v symbolically, never a solved magnitude"},
        },
    },
    {
        "id": "vector_difference",
        "subject": "Calculus & Vectors",
        "triggers": ["difference of two vectors", "subtract the vectors", "vector subtraction", "u-v", "p-q"],
        "caption": "Vector subtraction shown head-to-tail as the difference of the two vectors.",
        "skeleton": r"""\begin{tikzpicture}[scale=.9]
  \coordinate (O) at (0,0); \coordinate (A) at (3.3,0.5); \coordinate (B) at (1.1,2.2);
  \draw[cp line,-Stealth] (O)--(A) node[midway,below right] {$__U__$};
  \draw[cp line,-Stealth] (O)--(B) node[midway,above left] {$__V__$};
  \draw[cp dashed,-Stealth] (B)--(A) node[midway,above] {$__D__$};
  \fill (O) circle (1.3pt) node[below left] {$O$};
\end{tikzpicture}""",
        "params": {
            "U": {"type": "label", "default": "\\vec{u}", "desc": "first vector label"},
            "V": {"type": "label", "default": "\\vec{v}", "desc": "second vector label"},
            "D": {"type": "label", "default": "\\vec{u}-\\vec{v}", "answer_safe": False,
                  "desc": "difference label - symbolic (u-v), never a solved vector"},
        },
    },
    {
        "id": "normal_distribution",
        "subject": "Data Management",
        "triggers": [
            "normal distribution", "normally distributed", "bell curve",
            "standard deviation", "z-score", "empirical rule", "gaussian",
        ],
        "caption": "Normal distribution curve with the central one-standard-deviation region shaded.",
        "skeleton": r"""\begin{tikzpicture}[declare function={gauss(\x,\m,\s)=1/(\s*sqrt(2*pi))*exp(-((\x-\m)^2)/(2*\s^2));}]
\begin{axis}[width=6.4cm,height=3.5cm,axis lines=middle,xlabel={$x$},ylabel={density},xmin=-3.6,xmax=3.6,ymin=0,ymax=0.45,samples=120,ytick=\empty,xtick={-2,-1,0,1,2},xticklabels={$-2\sigma$,$-\sigma$,$__CENTER_LABEL__$,$\sigma$,$2\sigma$}]
  \addplot[cp fill,draw=none,domain=-1:1] {gauss(x,0,1)} \closedcycle;
  \addplot[cp line,domain=-3.5:3.5] {gauss(x,0,1)};
  \node at (axis cs:0,0.13) {\small $__SHADE_LABEL__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            "CENTER_LABEL": {"type": "label", "default": "\\mu", "desc": "label under the centre tick (usually \\mu or the given mean)"},
            "SHADE_LABEL": {"type": "label", "default": "68\\%", "desc": "label inside the shaded central region"},
        },
    },
    {
        "id": "boxplot",
        "subject": "Data Management",
        "triggers": [
            "box plot", "boxplot", "box-and-whisker", "box and whisker", "quartile",
            "interquartile", "iqr", "five-number", "median and quartiles",
        ],
        "caption": "Box-and-whisker plot with quartiles and median marked.",
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=6.4cm,height=2.8cm,boxplot/draw direction=x,xmin=0,xmax=100,ytick={1},yticklabels={data},xlabel={Value}]
  \addplot[boxplot prepared={median=__MEDIAN__,lower quartile=__Q1__,upper quartile=__Q3__,lower whisker=__MIN__,upper whisker=__MAX__},draw=black,fill=gray!20] coordinates {};
\end{axis}
\end{tikzpicture}""",
        "params": {
            "MIN": {"type": "number", "default": "15", "desc": "minimum / lower whisker value"},
            "Q1": {"type": "number", "default": "35", "desc": "first quartile"},
            "MEDIAN": {"type": "number", "default": "55", "desc": "median"},
            "Q3": {"type": "number", "default": "75", "desc": "third quartile"},
            "MAX": {"type": "number", "default": "95", "desc": "maximum / upper whisker value"},
        },
    },
]


_TEMPLATES_BY_ID = {t["id"]: t for t in TEMPLATES}
_SLOT_RE = re.compile(r"__([A-Z0-9_]+)__")


# ---------------------------------------------------------------------------
# Engine: validation, routing, fill, and the AI parameter spec.
# ---------------------------------------------------------------------------

def catalog_errors() -> list[str]:
    """Return a list of authoring mistakes in TEMPLATES (empty == healthy).

    Catches the common ways a hand-added entry goes wrong: duplicate id, a
    __SLOT__ with no param spec, a param with no matching slot, a bad type, or a
    default that fails its own sanitizer. Run in the self-test and at import in
    debug so a malformed template surfaces immediately instead of at render time.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()
    for t in TEMPLATES:
        tid = t.get("id", "<missing id>")
        if tid in seen_ids:
            errors.append(f"{tid}: duplicate id")
        seen_ids.add(tid)
        for key in ("id", "subject", "triggers", "caption", "skeleton", "params"):
            if key not in t:
                errors.append(f"{tid}: missing required key '{key}'")
        skeleton = t.get("skeleton", "")
        params = t.get("params", {})
        slots = set(_SLOT_RE.findall(skeleton))
        for slot in slots:
            if slot not in params:
                errors.append(f"{tid}: skeleton slot __{slot}__ has no params entry")
        for name, spec in params.items():
            if name not in slots:
                errors.append(f"{tid}: param '{name}' has no __{name}__ slot in skeleton")
            ptype = spec.get("type")
            if ptype not in ALL_PARAM_TYPES:
                errors.append(f"{tid}.{name}: invalid type {ptype!r} (allowed: {ALL_PARAM_TYPES})")
                continue
            if "default" not in spec:
                errors.append(f"{tid}.{name}: missing 'default'")
        if not t.get("triggers"):
            errors.append(f"{tid}: empty triggers list (unroutable by keyword)")
    return errors


def route(text: str, subject: str = "") -> dict | None:
    """Keyword routing. Returns the best-matching template or None.

    Score = number of distinct triggers present in the text, +0.5 if the
    request subject matches the template's subject. None means "no keyword hit"
    - the caller then decides whether to invoke the AI-classifier fallback.
    """
    low = " ".join([str(subject or ""), str(text or "")]).lower()
    subject_low = str(subject or "").lower()
    best: dict | None = None
    best_score = 0.0
    for t in TEMPLATES:
        hits = sum(1 for kw in t["triggers"] if kw in low)
        if not hits:
            continue
        score = hits + (0.5 if t.get("subject", "*").lower() in subject_low and subject_low else 0.0)
        if score > best_score:
            best_score = score
            best = t
    return best


def get(template_id: str) -> dict | None:
    return _TEMPLATES_BY_ID.get(template_id)


def fill(template: dict, ai_params: dict | None = None, target: str = "generic") -> str:
    """Substitute AI-supplied values into a template skeleton, deterministically.

    Every slot is sanitized by its declared type. Missing values fall back to
    the param default. On a worksheet target, a slot marked answer_safe=False
    whose value looks like a solved result is replaced by its unknown symbol.
    """
    ai_params = ai_params or {}
    out = template["skeleton"]
    for name, spec in template["params"].items():
        ptype = spec.get("type", "label")
        default = str(spec.get("default", ""))
        raw = ai_params.get(name, default)
        value = _SANITIZERS[ptype](raw, default)
        if target == "worksheet" and not spec.get("answer_safe", True):
            if _looks_like_answer(value):
                value = str(spec.get("unknown", "?"))
        out = out.replace("__" + name + "__", value)
    return out


def _looks_like_answer(value: str) -> bool:
    """Heuristic: a symbolic label (u+v, \\vec{R}, ?) is fine; a solved coordinate
    tuple, a \\sqrt/\\frac result, or a bare number reads as a leaked answer."""
    v = str(value or "").strip()
    if not v or v == "?":
        return False
    if re.search(r"\(\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d", v):  # (3,-2) style tuple
        return True
    if re.search(r"\\(?:sqrt|frac)\b", v):
        return True
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", v):  # a bare solved number
        return True
    return False


def ai_spec(template: dict) -> dict:
    """The constrained instruction the AI receives: fill THESE keys, nothing else.

    Returns a plain dict (the caller serializes it into the model prompt). The
    AI must never emit TikZ - only a flat {slot: value} object.
    """
    return {
        "template_id": template["id"],
        "keys": list(template["params"].keys()),
        "defaults": {k: v.get("default", "") for k, v in template["params"].items()},
        "fields": {
            k: {"type": v.get("type", "label"), "desc": v.get("desc", "")}
            for k, v in template["params"].items()
        },
    }


if __name__ == "__main__":
    import json

    print("=== catalog validation ===")
    errs = catalog_errors()
    if errs:
        for e in errs:
            print("  ERROR:", e)
        raise SystemExit(f"{len(errs)} catalog error(s)")
    print(f"  OK - {len(TEMPLATES)} templates, all slots/params consistent.\n")

    demos = [
        ("Calculus & Vectors", "In triangle PQR, angle P = 40 degrees and side q = 12 cm. Find angle R."),
        ("Calculus & Vectors", "A ship sails on a bearing of 040 then 110. Find its distance from start."),
        ("Calculus & Vectors", "Find the resultant of two forces with an angle of 60 between them."),
        ("Data Management", "The marks are normally distributed. Shade within one standard deviation."),
        ("Data Management", "Draw a box-and-whisker plot for the five-number summary."),
        ("Advanced Functions", "Sketch y = log(x) and its asymptote."),  # expect no route
    ]
    for subject, text in demos:
        t = route(text, subject)
        print(f"[{subject}] {text[:60]!r}")
        if not t:
            print("  -> no template (would use AI-classifier / reference fallback)\n")
            continue
        print(f"  -> {t['id']}")
        print("  ai_spec keys:", ai_spec(t)["keys"])
        print("  filled (defaults):")
        print("    " + fill(t, {}, target="worksheet").replace("\n", "\n    "))
        print()
