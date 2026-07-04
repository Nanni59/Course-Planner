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
]
