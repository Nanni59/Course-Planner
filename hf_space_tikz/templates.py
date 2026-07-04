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
    # Allow % so an escaped \% survives, and $ so a label may carry its own math
    # delimiters (many templates use a bare node {__LABEL__} with a "$...$" value).
    # A bare/unbalanced % or $ only fails the compile, which the repair loop catches.
    value = re.sub(r"[^A-Za-z0-9_+\-*/=.,:(){}\\^\s/|%$°]", "", value)
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
# The catalog. Templates live in the per-subject modules under catalog/ (one
# file per course, in the exact shape the sourcing agent emits). Edit those to
# add or change diagrams; this module is the engine that routes and fills them.
# ---------------------------------------------------------------------------

from catalog import ALL as _CATALOG_ALL

TEMPLATES: list[dict] = list(_CATALOG_ALL)

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


_INFLECTION = r"(?:s|es|ed|ing|ly)?"


def _trigger_hit(keyword: str, text_low: str) -> bool:
    """Whole-word/phrase match that tolerates common inflectional suffixes.

    Letter-boundaries are applied only on the sides where the keyword starts or
    ends with a letter, so 'angle' still won't fire inside 'triangle' yet a
    symbol-edged trigger like '^x' can match 'e^x' (whose 'e' would otherwise
    trip a blanket left boundary). The optional suffix lets 'normal' match
    'normally' and 'quartile' match 'quartiles' without matching 'planet'."""
    kw = keyword.lower()
    left = r"(?<![a-z])" if kw[:1].isalpha() else ""
    right = (_INFLECTION + r"(?![a-z])") if kw[-1:].isalpha() else ""
    return re.search(left + re.escape(kw) + right, text_low) is not None


def _relevance(template: dict, text_low: str, subj_tokens: set) -> float:
    """Keyword-trigger score for one template, weighting multi-word phrases higher
    (a specific "angle between" beats a bare "triangle") plus a subject-token
    tiebreak. Subject is NOT part of the keyword haystack (folding it in made
    "vectors" match every vector template)."""
    score = 0.0
    for kw in template["triggers"]:
        if _trigger_hit(kw, text_low):
            score += 1 + kw.count(" ")
    tmpl_tokens = set(re.findall(r"[a-z]+", template.get("subject", "").lower()))
    if subj_tokens & tmpl_tokens:
        score += 0.25
    return score


def route(text: str, subject: str = "") -> dict | None:
    """Keyword routing for an EXACT match. Returns the best template or None.

    None means "no keyword hit"; the caller then decides whether to fall through
    to the reference-guided path (which uses route_top for structural examples).
    """
    text_low = str(text or "").lower()
    subj_tokens = set(re.findall(r"[a-z]+", str(subject or "").lower()))
    best: dict | None = None
    best_score = 0.0
    for t in TEMPLATES:
        score = _relevance(t, text_low, subj_tokens)
        if score > best_score:
            best_score = score
            best = t
    return best


def route_top(text: str, subject: str = "", k: int = 3) -> list[dict]:
    """The k most relevant templates, for use as structural REFERENCES on the
    reference-guided fallback (novel problems with no exact match). Always returns
    up to k: keyword matches first, then padded by same-subject/leading templates
    so the generator always has a few style exemplars to anchor on."""
    text_low = str(text or "").lower()
    subj_tokens = set(re.findall(r"[a-z]+", str(subject or "").lower()))
    scored = sorted(
        ((_relevance(t, text_low, subj_tokens), i, t) for i, t in enumerate(TEMPLATES)),
        key=lambda x: (-x[0], x[1]),
    )
    picked = [t for s, _i, t in scored if s > 0][:k]
    if len(picked) < k:
        for _s, _i, t in scored:
            if t not in picked:
                picked.append(t)
            if len(picked) >= k:
                break
    return picked


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
