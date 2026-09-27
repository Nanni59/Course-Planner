"""Course Planner TikZ catalog - Trigonometry & geometry.

Preserved from the proven backend blueprints: triangle (law of sines/cosines,
elevation/depression) and two-leg bearing. These fill a gap the sourced subject
files don't cover, and the triangle exercises the `tikz`-type ANGLE_LINES slot
(a variable number of interior angle pics). Authoring contract: ../templates.py.
"""

templates = [
    {
        "id": "triangle_general",
        "subject": "Trigonometry / Geometry",
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
        "subject": "Trigonometry / Geometry",
        "triggers": ["bearing", "bearing of", "true bearing", "navigation", "heading", "compass", "due north", "due east"],
        "caption": "Bearing diagram with north reference rays and travel vectors.",
        "skeleton": r"""\begin{tikzpicture}[scale=.85]
  \coordinate (O) at (0,0);
  % Directions and label angles derive from the bearings (standard angle =
  % 90 - bearing; the arc label sits at 90 - bearing/2) instead of asking the
  % model to do that arithmetic.
  \coordinate (P) at ({90-(__B1__)}:2.45);
  \coordinate (Q) at ($(P)+({90-(__B2__)}:2.1)$);
  \draw[cp axis,-Stealth] (O)--(0,2.4) node[above] {$N$};
  \draw[cp axis,-Stealth] (O)--(2.3,0) node[right] {$E$};
  \draw[cp line,-Stealth] (O)--(P) node[midway,above right] {\ensuremath{__L1__}};
  \draw[cp line,-Stealth] (P)--(Q) node[midway,above] {\ensuremath{__L2__}};
  \draw[cp dashed] (O)--(Q) node[midway,below] {$d$};
  \draw[cp dashed] (90:.62) arc[start angle=90,end angle={90-(__B1__)},radius=.62];
  % bearing labels past their arcs by their own size (at a fixed .88 and .84
  % the arc ran through a wide label such as 115)
  \cpanglelabel{O}{90-(__B1__)/2}{0.62}{abs(__B1__)/2}{$__B1__^\circ$}
  \draw[cp axis,-Stealth] (P)--($(P)+(0,1.15)$) node[above] {$N$};
  \draw[cp dashed] ($(P)+(0,.58)$) arc[start angle=90,end angle={90-(__B2__)},radius=.58];
  \cpanglelabel{P}{90-(__B2__)/2}{0.58}{abs(__B2__)/2}{$__B2__^\circ$}
\end{tikzpicture}""",
        "params": {
            "B1": {"type": "number", "default": "45", "desc": "first bearing value in degrees, clockwise from north"},
            "B2": {"type": "number", "default": "115", "desc": "second bearing value in degrees, clockwise from north"},
            "L1": {"type": "label", "default": "", "desc": "given distance of the first leg with unit, e.g. 12\\,\\mathrm{km}; empty when none is given (the bearing is already marked on its arc)"},
            "L2": {"type": "label", "default": "", "desc": "given distance of the second leg with unit; empty when none is given"},
        },
    },
    {
        "id": "bearing_two_objects",
        "subject": "Trigonometry / Geometry",
        "triggers": [
            "same point", "from the same point", "same starting point",
            "two drones", "two ships", "two planes", "two boats", "two aircraft",
            "two cars", "two hikers", "distance between the two", "distance apart",
            "how far apart", "apart after",
        ],
        "caption": "Two objects leaving a common point along two bearings, with the distance between them.",
        "skeleton": r"""\begin{tikzpicture}[scale=0.9]
  \coordinate (O) at (0,0);
  % Directions and label angles derive from the bearings, as above.
  \coordinate (P) at ({90-(__B1__)}:2.7);
  \coordinate (Q) at ({90-(__B2__)}:2.3);
  \draw[cp axis,-Stealth] (O)--(0,3.0) node[above] {$N$};
  \draw[cp axis,-Stealth] (O)--(3.0,0) node[right] {$E$};
  % Distance labels beside their own segments by their measured size (fixed
  % sides fitted only the default bearings): d1 and d2 out past the bearing
  % labels and arcs, on the side away from reference point R1 / R2 (the other
  % leg's end, or its mirror image to put the label inside the triangle when an
  % axis crowds the outside), at fraction l along their legs, and d at fraction
  % f of P to Q; placement from the renderer.
  \draw[cp line,-Stealth] (O)--(P);
  \draw[cp line,-Stealth] (O)--(Q);
  \draw[cp dashed] (P)--(Q);
  \coordinate (Qr) at ($($(O)!(Q)!(P)$)!-1!(Q)$);
  \coordinate (Pr) at ($($(O)!(P)!(Q)$)!-1!(P)$);
  @@ALT@@
  \cpsidelabel{O}{P}{R1}{\cpfl}{\ensuremath{__L1__}}
  \cpsidelabel{O}{Q}{R2}{\cpfl}{\ensuremath{__L2__}}
  \cpsidelabel{P}{Q}{O}{\cpfd}{$__DLAB__$}
  % Separate radii keep the two bearing arcs apart. Each label goes in its own
  % part of its wedge, out past its arc by its own size: the first between N
  % and P, the second between P and Q (the part the first does not cover), each
  % in the wider side of the E axis when that axis runs through it (a bearing
  % over 90 put the 140 label on it).
  \draw[cp dashed] (90:0.5) arc[start angle=90,end angle={90-(__B1__)},radius=0.5];
  \pgfmathsetmacro\cpal{90-(__B1__)}
  \pgfmathsetmacro\cpbl{90-(__B2__)}
  \pgfmathsetmacro\cpsa{ifthenelse(\cpal<0,ifthenelse(-\cpal>=90,\cpal/2,45),(\cpal+90)/2)}
  \pgfmathsetmacro\cpha{ifthenelse(\cpal<0,max(-\cpal,90)/2,(90-\cpal)/2)}
  \cpanglelabel{O}{\cpsa}{0.5}{\cpha}{$__B1__^\circ$}
  \pgfmathsetmacro\cpia{\cplabelin}\pgfmathsetmacro\cpoa{\cplabelout}
  \pgfmathsetmacro\cpsb{ifthenelse(\cpbl<0&&\cpal>0,ifthenelse(-\cpbl>=\cpal,\cpbl/2,\cpal/2),(\cpbl+\cpal)/2)}
  \pgfmathsetmacro\cphb{ifthenelse(\cpbl<0&&\cpal>0,max(-\cpbl,\cpal)/2,(\cpal-\cpbl)/2)}
  \cpanglelabel{O}{\cpsb}{0}{\cphb}{$__B2__^\circ$}
  \pgfmathsetmacro\cpib{\cplabelin}\pgfmathsetmacro\cpob{\cplabelout}
  % The second arc sweeps past both labels: it passes outside each one whose
  % inner edge is within reach, inside one that sits far out (a narrow wedge).
  \pgfmathsetmacro\cprr{max(1.2,ifthenelse(\cpia<1.35,\cpoa+0.12,0),ifthenelse(\cpib<1.35,\cpob+0.12,0))}
  \draw[cp dashed] (90:\cprr) arc[start angle=90,end angle={90-(__B2__)},radius=\cprr];
\end{tikzpicture}""",
        "layout_alternatives": [rf'\coordinate (R1) at ({r1});\coordinate (R2) at ({r2});\pgfmathsetmacro\cpfd{{{f}}}\pgfmathsetmacro\cpfl{{{l}}}'
                                for l in ('0.78', '0.55')
                                for r1, r2 in (('Q', 'P'), ('Q', 'Pr'), ('Qr', 'P'), ('Qr', 'Pr'))
                                for f in ('0.5', '0.3', '0.7')],
        "params": {
            "B1": {"type": "number", "default": "20", "desc": "first bearing value in degrees, clockwise from north"},
            "B2": {"type": "number", "default": "110", "desc": "second bearing value in degrees, clockwise from north"},
            "L1": {"type": "label", "default": "d_1", "desc": "label on the first object's path (its distance travelled with unit, e.g. 45\\,\\mathrm{km})"},
            "L2": {"type": "label", "default": "d_2", "desc": "label on the second object's path (its distance travelled with unit)"},
            "DLAB": {"type": "label", "default": "d", "desc": "label for the distance between the two objects (the unknown); keep it symbolic like d", "answer_safe": False},
        },
    },
    {
        "id": "right_triangle",
        "subject": "Trigonometry / Geometry",
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
  % Angle label on the bisector, outside its mark, out far enough to fit between
  % the sides (the angle at A is atan(2.5/3.8) = 33.3 degrees). A computed angle
  % eccentricity is not usable: the angles library splices it into a polar
  % radius, where only a plain number behaves.
  \pic [draw=black, angle radius=0.55cm] {angle=B--A--C};
  \node[cp label] at ($(A)+(16.65:{max(0.85,0.3/sin(16.65))})$) {$__ANGLAB__$};
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
        "subject": "Trigonometry / Geometry",
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
  % angle label on the bisector, outside its mark (inside it, the default, it met
  % both radii), out far enough to fit between them
  \pic [draw=black, angle radius=0.8cm] {angle=A--O--B};
  \node[cp label] at ({(__ANGLE__)/2}:{max(1.1,0.3/sin(max(4,abs(__ANGLE__)/2)))}) {$__ANGLELAB__$};
\end{tikzpicture}""",
        "params": {
            "ANGLE": {"type": "number", "default": "60", "desc": "central angle of the sector in degrees (use the given value; keep it 20-160 for a readable wedge)"},
            "RLABEL": {"type": "label", "default": "r", "desc": "radius label: the given length with unit like 10\\,\\mathrm{cm}, or the symbol r"},
            "ANGLELAB": {"type": "label", "default": "60^\\circ", "desc": "central angle label, e.g. 60^\\circ or \\theta"},
        },
    },
    {
        "id": "circle_chord_arc",
        "subject": "Trigonometry / Geometry",
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
  % Chord label clear of the chord by its measured size: on the centre's side
  % for a short chord (outside, it crowded the arc label s), outside for a long
  % one, whose midpoint is on the bisector with the angle label inside.
  \draw[cp line] (A) -- (B);
  \node[cp label,overlay,opacity=0] (cpmC) at (0,0) {$__CHORDLAB__$};
  \path let \p1=($(B)-(A)$), \p3=($(__ARCMID__:2.35)-(A)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)*ifthenelse(__ANGLE__<80,1,-1)},
    \p2=($(cpmC.north east)-(cpmC.south west)$) in
    node[cp label] at ($(A)!0.5!(B)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__CHORDLAB__$};
  \draw[cp line] (A) arc[start angle=0,end angle=__ANGLE__,radius=2.35];
  \node[cp label] at (__ARCMID__:2.65) {$__ARCLAB__$};
  % Angle label between its mark and the chord, which crosses the angle
  % d = 2.35 cos(half-angle) from O. The mark shrinks with d (a wide angle's
  % chord left no room past a fixed mark), and the label sits in direction q
  % (the bisector by default; the renderer tries directions nearer either
  % radius) as far out as the band allows for its measured extent e along q
  % (in picture units: the label's pt over one unit's length on the canvas, so
  % the worksheet scale-up counts; scalar() drops the pt a let value carries).
  \pgfmathsetmacro\cpd{2.35*cos(abs(__ANGLE__)/2)}
  \pgfmathsetmacro\cpm{min(0.5,0.22*\cpd)}
  \pgfmathsetmacro\cpq{(__ANGLE__)*(@@ALT@@)}
  \draw (\cpm,0) arc[start angle=0,end angle=__ANGLE__,radius=\cpm];
  \node[cp label,overlay,opacity=0] (cpmT) at (0,0) {$__ANGLELAB__$};
  \path let \p2=($(cpmT.north east)-(cpmT.south west)$), \p9=($(1,0)-(0,0)$),
    \n1={(0.5*scalar(\x2)*abs(cos(\cpq))+0.5*scalar(\y2)*abs(sin(\cpq)))/scalar(\x9)},
    \n2={\cpd/cos(\cpq-(__ANGLE__)/2)} in
    node[cp label] at (\cpq:{min(\n2-\n1-0.04,max(\cpm+\n1+0.04,(\cpm+\n2)/2))}) {$__ANGLELAB__$};
  \node[cp label,below left] at (O) {$O$};
\end{tikzpicture}""",
        "layout_alternatives": ["0.5", "0.2", "0.8"],
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
