"""Course Planner TikZ catalog - Trigonometry & geometry (Calculus & Vectors).

Preserved from the proven backend blueprints: triangle (law of sines/cosines,
elevation/depression) and two-leg bearing. These fill a gap the sourced subject
files don't cover, and the triangle exercises the `tikz`-type ANGLE_LINES slot
(a variable number of interior angle pics). Authoring contract: ../templates.py.
"""

templates = [
    {
        "id": "triangle_general",
        "subject": "Calculus / Vectors",
        "triggers": [
            "triangle", "law of sines", "law of cosines", "sine law", "cosine law",
            "sas", "sss", "asa", "included angle", "oblique triangle",
            "triangular plot", "three sides", "third side", "interior angle",
            "largest interior angle", "two sides of a triangle",
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
  \pic[draw=black,angle radius=6mm,"$__ANG_A__$",angle eccentricity=1.4]{angle=B--A--C};
  \pic[draw=black,angle radius=6mm,"$__ANG_B__$",angle eccentricity=1.4]{angle=C--B--A};
  \pic[draw=black,angle radius=6mm,"$__ANG_C__$",angle eccentricity=1.4]{angle=A--C--B};
\end{tikzpicture}""",
        "params": {
            "A": {"type": "label", "default": "A", "desc": "bottom-left vertex label"},
            "B": {"type": "label", "default": "B", "desc": "bottom-right vertex label"},
            "C": {"type": "label", "default": "C", "desc": "top vertex label"},
            "AB": {"type": "label", "default": "c", "desc": "label on side A-B (given value or symbol)"},
            "AC": {"type": "label", "default": "b", "desc": "label on side A-C (given value or symbol)"},
            "BC": {"type": "label", "default": "a", "desc": "label on side B-C (given value or symbol)"},
            # All three angle arcs are always drawn; the ANG_* value only sets the
            # arc's label. Empty => an unlabeled arc at that vertex (not a hidden one).
            "ANG_A": {"type": "label", "default": "", "desc": "label for the angle arc at vertex A: a given value like 40^\\circ, ? if this angle is the unknown, or empty for an unlabeled arc"},
            "ANG_B": {"type": "label", "default": "", "desc": "label for the angle arc at vertex B: given value like 60^\\circ, ?, or empty for an unlabeled arc"},
            "ANG_C": {"type": "label", "default": "", "desc": "label for the angle arc at vertex C: given value, ?, or empty for an unlabeled arc"},
        },
    },
    {
        "id": "bearing_two_leg",
        "subject": "Calculus / Vectors",
        "triggers": ["bearing", "bearing of", "true bearing", "navigation", "heading", "compass", "due north", "due east"],
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
  \draw[cp axis,-Stealth] (P)--($(P)+(0,1.15)$) node[above] {$N$};
  \draw[cp dashed] ($(P)+(0,.58)$) arc[start angle=90,end angle=__A2__,radius=.58];
  \node at ($(P)+(__M2__:.84)$) {$__B2__^\circ$};
\end{tikzpicture}""",
        "params": {
            "A1": {"type": "number", "default": "45", "desc": "first leg direction in standard math degrees = 90 - bearing1"},
            "A2": {"type": "number", "default": "-25", "desc": "second leg direction = 90 - bearing2"},
            "M1": {"type": "number", "default": "67.5", "desc": "midpoint angle for first bearing arc label = (90 + A1)/2"},
            "M2": {"type": "number", "default": "32.5", "desc": "midpoint angle for second bearing arc label = (90 + A2)/2"},
            "B1": {"type": "number", "default": "45", "desc": "first bearing value in degrees, clockwise from north"},
            "B2": {"type": "number", "default": "115", "desc": "second bearing value in degrees"},
            "L1": {"type": "label", "default": "45^\\circ", "desc": "label on first leg (given distance with unit, else the bearing)"},
            "L2": {"type": "label", "default": "115^\\circ", "desc": "label on second leg"},
        },
    },
    {
        "id": "bearing_two_objects",
        "subject": "Calculus / Vectors",
        "triggers": [
            "same point", "from the same point", "same starting point",
            "two drones", "two ships", "two planes", "two boats", "two aircraft",
            "two cars", "two hikers", "distance between the two", "distance apart",
            "how far apart", "apart after",
        ],
        "caption": "Two objects leaving a common point along two bearings, with the distance between them.",
        "skeleton": r"""\begin{tikzpicture}[scale=0.9]
  \coordinate (O) at (0,0);
  \coordinate (P) at (__A1__:2.7);
  \coordinate (Q) at (__A2__:2.3);
  \draw[cp axis,-Stealth] (O)--(0,3.0) node[above] {$N$};
  \draw[cp axis,-Stealth] (O)--(3.0,0) node[right] {$E$};
  \draw[cp line,-Stealth] (O)--(P) node[midway,above left] {$__L1__$};
  \draw[cp line,-Stealth] (O)--(Q) node[midway,below right] {$__L2__$};
  \draw[cp dashed] (P)--(Q) node[midway,above right] {$__DLAB__$};
  \draw[cp dashed] (90:0.62) arc[start angle=90,end angle=__A1__,radius=0.62];
  \node at (__M1__:0.92) {$__B1__^\circ$};
  \draw[cp dashed] (90:0.42) arc[start angle=90,end angle=__A2__,radius=0.42];
  \node at (__M2__:0.7) {$__B2__^\circ$};
\end{tikzpicture}""",
        "params": {
            "A1": {"type": "number", "default": "70", "desc": "first object's direction in standard math degrees = 90 - bearing1 (e.g. bearing 020 -> 70)"},
            "A2": {"type": "number", "default": "-20", "desc": "second object's direction in standard math degrees = 90 - bearing2 (e.g. bearing 110 -> -20)"},
            "M1": {"type": "number", "default": "80", "desc": "midpoint angle for the first bearing arc label = (90 + A1)/2"},
            "M2": {"type": "number", "default": "35", "desc": "midpoint angle for the second bearing arc label = (90 + A2)/2"},
            "B1": {"type": "number", "default": "20", "desc": "first bearing value in degrees, clockwise from north"},
            "B2": {"type": "number", "default": "110", "desc": "second bearing value in degrees, clockwise from north"},
            "L1": {"type": "label", "default": "d_1", "desc": "label on the first object's path (its distance travelled with unit, e.g. 45\\,\\mathrm{km})"},
            "L2": {"type": "label", "default": "d_2", "desc": "label on the second object's path (its distance travelled with unit)"},
            "DLAB": {"type": "label", "default": "d", "desc": "label for the distance between the two objects (the unknown); keep it symbolic like d", "answer_safe": False},
        },
    },
    {
        "id": "right_triangle",
        "subject": "Calculus / Vectors",
        "triggers": [
            "right triangle", "angle of elevation", "angle of depression",
            "line of sight", "ladder", "leans against", "foot of the",
            "slides away", "height of the", "elevation of",
        ],
        "caption": "Right triangle with a horizontal base, vertical height, hypotenuse, and the angle at the base.",
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (A) at (0,0);
  \coordinate (B) at (3.8,0);
  \coordinate (C) at (3.8,2.5);
  \draw[cp line] (A) -- (B) -- (C) -- cycle;
  \pic [draw=black, angle radius=0.45cm] {right angle=C--B--A};
  \pic [draw=black, angle radius=0.55cm, "$__ANGLAB__$"] {angle=B--A--C};
  \node[cp label, below] at ($(A)!0.5!(B)$) {$__BASELAB__$};
  \node[cp label, right] at ($(B)!0.5!(C)$) {$__HEIGHTLAB__$};
  \node[cp label, above left] at ($(A)!0.5!(C)$) {$__HYPLAB__$};
\end{tikzpicture}""",
        "params": {
            "ANGLAB": {"type": "label", "default": "\\theta", "desc": "angle label at the base vertex: a given value like 32^\\circ, or \\theta / ? if it is the unknown"},
            "BASELAB": {"type": "label", "default": "x", "desc": "label on the horizontal leg (given distance with unit, or a symbol)"},
            "HEIGHTLAB": {"type": "label", "default": "h", "desc": "label on the vertical leg (given height with unit, or a symbol like h)", "answer_safe": False},
            "HYPLAB": {"type": "label", "default": "", "desc": "label on the hypotenuse / line of sight (e.g. the ladder length, or empty)"},
        },
    },
    {
        "id": "circle_sector",
        "subject": "Calculus / Vectors",
        "triggers": [
            "sector", "central angle", "arc length", "subtends", "subtended",
            "pizza slice", "slice of", "pie slice", "wedge", "radians",
        ],
        "caption": "A circular sector with its radius and central angle labelled.",
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0);
  \coordinate (A) at (0:2.7);
  \coordinate (B) at (__ANGLE__:2.7);
  \draw[cp fill] (O) -- (A) arc[start angle=0, end angle=__ANGLE__, radius=2.7] -- cycle;
  \draw[cp line] (O) -- (A);
  \draw[cp line] (O) -- (B);
  \draw[cp line] (A) arc[start angle=0, end angle=__ANGLE__, radius=2.7];
  \node[cp label, below] at (0:1.4) {$__RLABEL__$};
  \pic [draw=black, angle radius=0.8cm, "$__ANGLELAB__$"] {angle=A--O--B};
\end{tikzpicture}""",
        "params": {
            "ANGLE": {"type": "number", "default": "60", "desc": "central angle of the sector in degrees (use the given value; keep it 20-160 for a readable wedge)"},
            "RLABEL": {"type": "label", "default": "r", "desc": "radius label: the given length with unit like 10\\,\\mathrm{cm}, or the symbol r"},
            "ANGLELAB": {"type": "label", "default": "60^\\circ", "desc": "central angle label, e.g. 60^\\circ or \\theta"},
        },
    },
    {
        "id": "circle_chord_arc",
        "subject": "Calculus / Vectors",
        "triggers": [
            "chord", "circular segment", "length of the chord", "arc and chord",
            "arc length and chord", "area of a circular segment",
        ],
        "caption": "Circle with a chord, the intercepted arc, and the central angle.",
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0);
  \coordinate (A) at (0:2.35);
  \coordinate (B) at (__ANGLE__:2.35);
  \draw[cp line] (O) circle (2.35);
  \draw[cp line] (O) -- (A) node[cp label,midway,below] {$__RLABEL__$};
  \draw[cp line] (O) -- (B);
  \draw[cp line] (A) -- (B) node[cp label,midway,anchor=south west] {$__CHORDLAB__$};
  \draw[cp line] (A) arc[start angle=0,end angle=__ANGLE__,radius=2.35];
  \node[cp label] at (__ARCMID__:2.65) {$__ARCLAB__$};
  \pic [draw=black, angle radius=0.7cm, "$__ANGLELAB__$"] {angle=A--O--B};
  \node[cp label,below left] at (O) {$O$};
\end{tikzpicture}""",
        "params": {
            "ANGLE": {"type": "number", "default": "110", "desc": "central angle in degrees"},
            "ARCMID": {"type": "number", "default": "55", "desc": "half the central angle, for placing the arc label"},
            "RLABEL": {"type": "label", "default": "r", "desc": "radius label with unit if given"},
            "CHORDLAB": {"type": "label", "default": "c", "desc": "chord label"},
            "ARCLAB": {"type": "label", "default": "s", "desc": "arc length label"},
            "ANGLELAB": {"type": "label", "default": "110^\\circ", "desc": "central angle label"},
        },
    },
]
