"""Regression test for the TikZ backend's deterministic template routing.

Guards the topic-relevance behavior of hf_space_tikz/app.py: the right topics get the
right deterministic diagram, non-visual/foreign topics get none (blank > wrong), and the
fixed worksheet-brief boilerplate no longer leaks shape keywords into routing.

Run: python tools/worksheet_visual_route_test.py   (exit 0 = pass)

Pure-regex functions only; heavy imports (fastapi/pydantic/requests) are stubbed so the
module loads without its web deps or a LaTeX toolchain.
"""
import os
import sys
import types
from types import SimpleNamespace


def _stub(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


fa = _stub("fastapi")


class _FastAPI:
    def __init__(self, *a, **k):
        pass

    def add_middleware(self, *a, **k):
        pass

    def get(self, *a, **k):
        return lambda f: f

    def post(self, *a, **k):
        return lambda f: f


fa.FastAPI = _FastAPI
_stub("fastapi.middleware")
_cors = _stub("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_resp = _stub("fastapi.responses")
_resp.JSONResponse = type("JSONResponse", (), {"__init__": lambda self, *a, **k: None})
_req = _stub("requests")
_req.exceptions = SimpleNamespace(RequestException=type("RequestException", (Exception,), {}))
_req.get = lambda *a, **k: None
_req.post = lambda *a, **k: None
_pyd = _stub("pydantic")
_pyd.BaseModel = type("BaseModel", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
_pyd.Field = lambda *a, **k: (a[0] if a and a[0] is not ... else "")

# Suppress only the LaTeX cache warm-up thread that app.py starts at import time, then
# restore Thread.start so this module can't disable threading elsewhere (e.g. if it is
# ever collected in a shared pytest session — the *_test.py name matches discovery).
import threading  # noqa: E402
_orig_thread_start = threading.Thread.start
threading.Thread.start = lambda self: None

APP = os.path.join(os.path.dirname(__file__), "..", "hf_space_tikz", "app.py")
ns = {}
try:
    with open(APP, encoding="utf-8") as fh:
        exec(compile(fh.read(), APP, "exec"), ns)  # noqa: S102
finally:
    threading.Thread.start = _orig_thread_start

_deterministic_template = ns["_deterministic_template"]
_semantic_visual_issue = ns["_semantic_visual_issue"]
_worksheet_answer_safe_tikz = ns["_worksheet_answer_safe_tikz"]
_local_reject_critic_correction = ns["_local_reject_critic_correction"]

# The exact fixed instruction the worksheet frontend prepends to every brief. It must stay
# free of shape words; this test fails if a future edit reintroduces polluting keywords.
INSTR = (
    "Create a compact, landscape textbook diagram that helps a student answer this worksheet "
    "question. Use clean black or gray lines with short labels. If this question has no safe, "
    "directly relevant diagram, return an empty tikz string rather than a generic or decorative "
    "picture."
)


def req(question, subject="General", answer=""):
    brief = INSTR + "\nQuestion: " + question + (("\nAnswer/key idea: " + answer) if answer else "")
    return SimpleNamespace(brief=brief, subject=subject, title=question,
                           equation="", format="svg", theme="mono", target="worksheet")


failures = []


def check(name, question, *, subject="General", answer="", expect_template, expect_caption=None, expect_renders=True):
    """expect_template True -> a deterministic template must fire; False -> none may fire.
    expect_caption: substring the caption must contain. expect_renders: audit must not reject.
    answer: worked-solution prose included in the brief — routing must NOT depend on it."""
    hit = _deterministic_template(req(question, subject, answer))
    if not expect_template:
        if hit is not None:
            failures.append(f"{name}: expected NO template, got {hit[1]!r}")
        return
    if hit is None:
        failures.append(f"{name}: expected a template, got none")
        return
    tikz, caption = hit
    if expect_caption and expect_caption.lower() not in caption.lower():
        failures.append(f"{name}: caption {caption!r} lacks {expect_caption!r}")
    if expect_renders and _semantic_visual_issue(req(question, subject, answer), tikz):
        failures.append(f"{name}: relevant template was flagged by the semantic audit")
    # Nothing should ever route to a bearing diagram unless the text is truly about bearings.
    if "bearing" in caption.lower() and "bearing" not in (question + " " + subject).lower():
        failures.append(f"{name}: unexpected bearing diagram")


# --- topic-correct routing ---
check("trig law of sines", "In triangle ABC, side a = 15 cm, angle A = 40 degrees, angle B = 65 degrees; find side b using the law of sines.",
      subject="Trigonometry", expect_template=True, expect_caption="Triangle")
check("trig median (not stats)", "Find the length of the median of triangle ABC from vertex A to the midpoint of BC.",
      subject="Trigonometry", expect_template=True, expect_caption="Triangle")
check("vectors resultant", "Two forces of magnitude 10 N and 15 N act at an angle of 120 degrees; find the resultant.",
      subject="Vectors", expect_template=True, expect_caption="Vector")
# Algebraic vector-quantity questions must each get a RELEVANT deterministic diagram
# (matches the question), not a blank and not the generic angle-between picture.
check("vectors magnitude", "Find the magnitude of the algebraic vector u = 4i - 2j + 4k in R^3.",
      subject="Vectors", expect_template=True, expect_caption="components")
check("vectors component form", "Given points A(3,-5) and B(-2,7), write the vector AB in component form.",
      subject="Vectors", expect_template=True, expect_caption="components")
check("vectors orthogonal", "Determine if the algebraic vectors u = (2,-3,4) and v = (5,2,-1) are orthogonal.",
      subject="Vectors", expect_template=True, expect_caption="orthogonal")
check("vectors collinear", "Determine the values of m and n so that the vectors u = (3,m,-2) and v = (9,12,n) are collinear.",
      subject="Vectors", expect_template=True, expect_caption="Collinear")
# Vector arithmetic: a subtraction and a linear combination must get the SAME difference
# diagram (not a single-vector picture for one and a blank for the other), and a sum gets
# the resultant. Routed on the question, so the answer's "component-wise"/"sum" can't flip it.
check("vectors subtraction", r"Given \vec{p}=(5,-1,2) and \vec{q}=(2,3,-4), calculate \vec{p}-\vec{q}.",
      subject="Vectors", answer="The subtraction is performed component-wise.",
      expect_template=True, expect_caption="subtraction")
check("vectors linear combination", r"Given \vec{u}=(-1,0,4) and \vec{v}=(3,-5,2), calculate 2\vec{u}-3\vec{v}.",
      subject="Vectors", answer="First, perform the scalar multiplication, then subtract the resulting vectors.",
      expect_template=True, expect_caption="subtraction")
check("vectors sum resultant", r"Given \vec{a}=(3,-2) and \vec{b}=(1,5), find the resultant vector \vec{c}=\vec{a}+\vec{b} and its magnitude.",
      subject="Vectors", expect_template=True, expect_caption="resultant")
check("vectors magnitude of a sum", r"Given \vec{m}=(6,-8) and \vec{n}=(-2,3), find the magnitude of the vector 2\vec{m}+5\vec{n}.",
      subject="Vectors", answer="find the sum of these vectors then its magnitude", expect_template=True, expect_caption="resultant")
# A triangle/trig question that merely says "magnitude" must NOT be stolen by the vector
# template — it still routes to the triangle diagram.
check("trig magnitude not vector", "In triangle ABC, find the magnitude of angle B given side a = 10 cm and angle A = 40 degrees.",
      subject="Trigonometry", expect_template=True, expect_caption="Triangle")
check("stats histogram", "Draw a histogram for the frequency distribution of the data.",
      subject="Statistics", expect_template=True, expect_caption="Histogram")
check("stats box plot", "Construct a box-and-whisker plot; find the quartiles and interquartile range.",
      subject="Statistics", expect_template=True, expect_caption="Box")
check("stats normal", "For a normal distribution, apply the 68-95-99.7 empirical rule.",
      subject="Statistics", expect_template=True, expect_caption="Normal")
check("geometry rectangle", "Find the area of a rectangle with length 8 cm and width 5 cm.",
      subject="Geometry", expect_template=True, expect_caption="Rectangle")
check("geometry circle", "Find the circumference of a circle with radius 7 cm.",
      subject="Geometry", expect_template=True, expect_caption="Circle")

# --- worksheet diagrams must not reveal the answer ---
guard_req = req("Express the position vector v corresponding to point P(-4,7) in standard unit vectors i and j.",
                subject="Vectors")
guarded = _worksheet_answer_safe_tikz(guard_req, r"""
\begin{tikzpicture}
  \node {$\vec{v}=(-4,7)$};
  \node {$-4\vec{i}+7\vec{j}$};
  \node {$|\vec{v}|=\sqrt{65}$};
  \node {$P(-4,7)$};
\end{tikzpicture}
""")
for bad in (r"\vec{v}=(-4,7)", r"-4\vec{i}+7\vec{j}", r"|\vec{v}|=\sqrt{65}"):
    if bad in guarded:
        failures.append(f"answer guard: leaked solved label {bad!r}")
if "P(-4,7)" not in guarded:
    failures.append("answer guard: removed the given point label")

cp_style_reject = _local_reject_critic_correction(
    req("Find the magnitude of vector v = (2,-3,5).", subject="Vectors"),
    r"\begin{tikzpicture}\draw[cp axis,-Stealth] (0,0)--(1,0);\draw[cp line,-Stealth] (0,0)--(1,1);\end{tikzpicture}",
    r"\begin{tikzpicture}\draw[-Stealth] (0,0)--(1,0);\draw[-Stealth] (0,0)--(1,1);\end{tikzpicture}",
    "The proposed TikZ has undefined styles cp axis and cp line.",
)
if not cp_style_reject:
    failures.append("critic guard: accepted a false undefined-cp-style correction")

# --- foreign / non-visual topics must NOT get a deterministic diagram (blank > wrong) ---
check("geometry vague area (no drawable shape)", "Calculate the area enclosed by the given region.",
      subject="Geometry", expect_template=False)
check("LA gaussian elimination", "Solve the system of linear equations using Gaussian elimination: 2x - y + 3z = 9.",
      subject="Linear Algebra", expect_template=False)
check("LA determinant", "Calculate the determinant of the matrix A = [[4,-2],[3,5]].",
      subject="Linear Algebra", expect_template=False)
check("LA unit-square area", "Describe the transformation applied to the unit square by M; what is the area of the transformed shape?",
      subject="Linear Algebra", expect_template=False)
check("LA transform to parallelogram", "A linear transformation maps the unit square to a parallelogram; determine the 2x2 transformation matrix T.",
      subject="Linear Algebra", expect_template=False)
check("calculus tangent", "Sketch the tangent line to f(x) = x^2 at x = 1 and a secant over [1, 3].",
      subject="Calculus", expect_template=False)

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("ALL ROUTE CASES PASS")
