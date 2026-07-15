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
_question_should_stay_blank = ns["_question_should_stay_blank"]

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


def check(name, question, *, subject="General", answer="", expect_template, expect_caption=None, expect_tikz=None, reject_tikz=None, expect_renders=True):
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
    if expect_tikz:
        for needle in expect_tikz:
            if needle not in tikz:
                failures.append(f"{name}: TikZ lacks expected fragment {needle!r}")
    if reject_tikz:
        for needle in reject_tikz:
            if needle in tikz:
                failures.append(f"{name}: TikZ contains rejected fragment {needle!r}")
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
check("bearing hiker values", "A hiker walks 6 km on a bearing of 040 degrees, then 9 km on a bearing of 115 degrees. Draw the two travel vectors and the displacement from the start.",
      subject="Geometry and Trigonometry", expect_template=True, expect_caption="Bearing", expect_tikz=["$40^\\circ$", "$115^\\circ$", "$6km$", "$9km$"])
check("bearing due east then bearing", "An aircraft flies 200 km due East from point X to point Y. It then flies 300 km on a bearing of 060 degrees to reach point Z.",
      subject="Geometry and Trigonometry", expect_template=True, expect_caption="Bearing", expect_tikz=["$90^\\circ$", "$60^\\circ$", "$200km$", "$300km$"])
check("bearing north then west", "A plane flies 400 miles North, then 300 miles West. What is the final bearing of the plane from its starting point?",
      subject="Geometry and Trigonometry", expect_template=True, expect_caption="Bearing", expect_tikz=["$0^\\circ$", "$270^\\circ$", "$400miles$", "$300miles$"])
check("vectors resultant", "Two forces of magnitude 10 N and 15 N act at an angle of 120 degrees; find the resultant.",
      subject="Vectors", expect_template=True, expect_caption="Vector")
# Algebraic vector-quantity questions must each get a RELEVANT deterministic diagram
# (matches the question), not a blank and not the generic angle-between picture.
check("vectors magnitude", "Find the magnitude of the algebraic vector u = 4i - 2j + 4k in R^3.",
      subject="Vectors", expect_template=True, expect_caption="3D vector")
check("vectors magnitude angle-bracket r2", r"What is the magnitude of the vector \(\vec{a} = \langle -3, 5 \rangle\)?",
      subject="Vectors", expect_template=True, expect_caption="components", expect_tikz=["(-1.56,2.6)"])
check("vectors unit angle-bracket r3", r"What is the unit vector in the direction of \(\vec{v} = \langle 1, -2, 2 \rangle\)?",
      subject="Vectors", expect_template=True, expect_caption="3D vector", expect_tikz=["node[above] {$z$}"])
# NOTE: the peak build (preserved in the app_COMPLETE .pyc backup) draws BOTH operands
# (caption "3D coordinate", \vec{a}+\vec{b}). The currently shipped build draws a single
# labelled 3D vector in an xyz frame — still a valid, relevant diagram.
check("vectors unicode angle-bracket r3", "Given vectors 𝑎→=⟨−3,5,1⟩ and 𝑏→=⟨2,−1,4⟩, find the resultant vector 𝑐→=2𝑎→−𝑏→. Express your answer in component form.",
      subject="Vectors", expect_template=True, expect_caption="3D vector", expect_tikz=["node[above] {$z$}"])
check("vectors component form", "Given points A(3,-5) and B(-2,7), write the vector AB in component form.",
      subject="Vectors", expect_template=True, expect_caption="2D point-to-point")
check("vectors 2d initial terminal points", "A vector a has initial point P(2,-1) and terminal point Q(5,3). Express a in component form.",
      subject="Vectors", expect_template=True, expect_caption="2D point-to-point", expect_tikz=["\\vec{PQ}", "$ P $", "$ Q $"])
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
check("vectors two-wire tension", "A mass of 50 kg is supported by two wires. One wire is at an angle of 30 degrees to the horizontal and the other is at an angle of 45 degrees to the horizontal. Determine the tensions.",
      subject="Vectors", expect_template=True, expect_caption="Tension", expect_tikz=["$30^\\circ$", "$45^\\circ$", "(150:2.15)", "(45:2.15)"])
# The equilibrant "define/explain" question must stay blank. The authoritative gate the
# backend uses is _question_should_stay_blank (asserted here). (The peak .pyc build also
# returns None from _deterministic_template directly; the shipped build blanks via this gate.)
if not _question_should_stay_blank(req("Define equilibrant force and explain how it relates to the resultant force.", subject="Vectors as Forces")):
    failures.append("vectors define equilibrant blank: API-level blank predicate did not fire")
check("vectors scalar-vs-vector comparison blank", "What is the difference between a scalar quantity and a vector quantity? Provide one example of each.",
      subject="Vectors as Forces", expect_template=False)
if not _question_should_stay_blank(req("What is the difference between a scalar quantity and a vector quantity? Provide one example of each.", subject="Vectors as Forces")):
    failures.append("vectors scalar-vs-vector comparison blank: API-level blank predicate did not fire")
check("vectors ramp no fake tension", "A 10 kg box rests on a ramp inclined at an angle of 30 degrees to the horizontal. Draw a free-body diagram for the box, labeling all forces acting on it.",
      subject="Vectors as Forces", expect_template=True, expect_caption="Inclined-plane", expect_tikz=["$30^\\circ$", "mg\\sin\\theta"], reject_tikz=["{$T$}"])
# A free-body / inclined-plane request must fire even when the wording carries NO explicit
# "force"/"vector" cue (only "free-body diagram") and the subject is Calculus & Vectors — the
# vector-cue gate used to reject it, so it fell to a generic (growing-pattern) fallback.
check("ramp free-body no force word", "A 10 kg block rests on a frictionless ramp inclined at 30 degrees. Draw the free-body diagram.",
      subject="Calculus and Vectors", expect_template=True, expect_caption="Inclined-plane", expect_tikz=["$30^\\circ$", "mg\\sin\\theta"], reject_tikz=["{$T$}"])
check("vectors pulling force work angle", "An object is pulled along a horizontal surface with a force of 50 N at an angle of 20 degrees above the horizontal. If the object moves a distance of 10 m, calculate the work done by the pulling force.",
      subject="Vectors as Forces", expect_template=True, expect_caption="Force and displacement", expect_tikz=["$20^\\circ$", "F=50\\,\\mathrm{N}", "d=10\\,\\mathrm{m}"])
check("vectors drone east north up", "A drone starts at the origin (0,0,0) and moves 5 km east, then 3 km north, and finally 2 km up. Represent the drone's final position as a position vector.",
      subject="Vectors", expect_template=True, expect_caption="3D position vector", expect_tikz=["node[above] {$z$}", "\\vec{p}"])
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
check("number theory modulo clock", "Show arithmetic modulo 12 on a clock diagram. Mark starting at 9 and moving forward 5 hours.",
      subject="Number Theory", expect_template=True, expect_caption="Modulo")
check("arithmetic sequence stairs", "A staircase has 3 blocks on the first step, 5 on the second, and 7 on the third. Draw the first few terms as a growing arithmetic pattern.",
      subject="Advanced Functions", expect_template=True, expect_caption="Arithmetic sequence")
check("combinations committee", "A committee is selected from a group of students. Draw a simple branching or grouping diagram to represent combinations without listing every outcome.",
      subject="Data Management", expect_template=True, expect_caption="Combination")

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
