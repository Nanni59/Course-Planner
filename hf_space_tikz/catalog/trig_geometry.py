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
        # The shape follows the interior angles at A and B (C gets the rest): a
        # fixed shape drew 42 degrees as 60 and an 8 cm side longer than 11 cm.
        # The backend solves the triangle from the question's givens when it can
        # (SSS, SAS, SSA, two angles) and puts the largest angle at C, so AB, the
        # longest side, is the base; otherwise the model supplies the angles.
        "skeleton": r"""\begin{tikzpicture}[scale=.9]
  \pgfmathsetmacro\cpa{min(170,max(4,__DEG_A__))}
  \pgfmathsetmacro\cpb{min(176-\cpa,max(4,__DEG_B__))}
  \pgfmathsetmacro\cpc{180-\cpa-\cpb}
  \pgfmathsetmacro\cpl{4.2*sin(\cpb)/sin(\cpa+\cpb)}
  \pgfmathsetmacro\cpr{4.2*sin(\cpa)/sin(\cpa+\cpb)}
  % angle marks shrink with the shortest side and the height (in a flat
  % triangle the label of the wide angle sat on the base)
  \pgfmathsetmacro\cpm{min(0.55,0.3*min(\cpl,\cpr),0.35*\cpl*sin(\cpa))}
  \coordinate (A) at (0,0); \coordinate (B) at (4.2,0); \coordinate (C) at (\cpa:\cpl);
  \coordinate (G) at ($1/3*(A)+1/3*(B)+1/3*(C)$);
  \draw[cp line] (A)--(B)--(C)--cycle;
  % vertex names straight out from the centroid
  \node[cp label] at ($(A)!-0.32cm!(G)$) {$__A__$};
  \node[cp label] at ($(B)!-0.32cm!(G)$) {$__B__$};
  \node[cp label] at ($(C)!-0.32cm!(G)$) {$__C__$};
  \cpsidelabel{A}{B}{C}{0.5}{$__AB__$}
  \cpsidelabel{A}{C}{B}{0.5}{$__AC__$}
  \cpsidelabel{B}{C}{A}{0.5}{$__BC__$}
  % an arc only where the angle is labelled; the label on its bisector, past
  % its mark and clear of both sides
  \draw[draw opacity=__SHOW_A__] ($(A)+(0:\cpm)$) arc[start angle=0,end angle=\cpa,radius=\cpm];
  \draw[draw opacity=__SHOW_B__] ($(B)+({180-\cpb}:\cpm)$) arc[start angle={180-\cpb},end angle=180,radius=\cpm];
  \draw[draw opacity=__SHOW_C__] ($(C)+({\cpa-180}:\cpm)$) arc[start angle={\cpa-180},end angle={-\cpb},radius=\cpm];
  \cpanglelabel{A}{\cpa/2}{\cpm}{\cpa/2}{$__ANG_A__$}
  \cpanglelabel{B}{180-\cpb/2}{\cpm}{\cpb/2}{$__ANG_B__$}
  \cpanglelabel{C}{(\cpa-180-\cpb)/2}{\cpm}{\cpc/2}{$__ANG_C__$}
\end{tikzpicture}""",
        "params": {
            "A": {"type": "label", "default": "A", "desc": "vertex label at one end of the base"},
            "B": {"type": "label", "default": "B", "desc": "vertex label at the other end of the base"},
            "C": {"type": "label", "default": "C", "desc": "top vertex label"},
            "DEG_A": {"type": "number", "default": "60", "desc": "the true interior angle at vertex A in degrees (the given value, else found from the givens), so the drawing has the right shape"},
            "DEG_B": {"type": "number", "default": "50", "desc": "the true interior angle at vertex B in degrees"},
            # Empty defaults: an empty value falls back to the default, and a
            # stray side letter reads as another quantity to find.
            "AB": {"type": "label", "default": "", "desc": "label on side A-B: its given length with unit, a symbol like x or ? if it is the unknown, or empty"},
            "AC": {"type": "label", "default": "", "desc": "label on side A-C: given length, symbol if unknown, or empty"},
            "BC": {"type": "label", "default": "", "desc": "label on side B-C: given length, symbol if unknown, or empty"},
            # An angle is marked only when labelled: a given value, ? for the unknown.
            "ANG_A": {"type": "label", "default": "", "desc": "label for the angle at vertex A: a given value like 40^\\circ, ? if this angle is the unknown, or empty for no mark"},
            "ANG_B": {"type": "label", "default": "", "desc": "label for the angle at vertex B: given value like 60^\\circ, ?, or empty for no mark"},
            "ANG_C": {"type": "label", "default": "", "desc": "label for the angle at vertex C: given value, ?, or empty for no mark"},
            "SHOW_A": {"type": "number", "default": "0", "flag_of": "ANG_A"},
            "SHOW_B": {"type": "number", "default": "0", "flag_of": "ANG_B"},
            "SHOW_C": {"type": "number", "default": "0", "flag_of": "ANG_C"},
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
  % Legs in proportion to their distances (fixed lengths could draw a 10 km
  % leg longer than a 50 km one), the shorter at least 0.45 of the longer (at
  % 0.3 the first leg was shorter than its bearing label).
  \pgfmathsetmacro\cpda{max(0.45,min(1,(__LEN1__)/max(__LEN2__,0.001)))}
  \pgfmathsetmacro\cpdb{max(0.45,min(1,(__LEN2__)/max(__LEN1__,0.001)))}
  \coordinate (P) at ({90-(__B1__)}:{2.6*\cpda});
  \coordinate (Q) at ($(P)+({90-(__B2__)}:{2.6*\cpdb})$);
  % label placement from the renderer: R1 / R2 (the other leg's far end or its
  % mirror image), the fraction l along each leg, and the E label's side
  \coordinate (Qr) at ($($(O)!(Q)!(P)$)!-1!(Q)$);
  \coordinate (Or) at ($($(P)!(O)!(Q)$)!-1!(O)$);
  @@ALT@@
  \draw[cp axis,-Stealth] (O)--(0,2.4) node[above] {$N$};
  % a short east reference: at 2.3 the second leg often crossed its E
  \draw[cp axis,-Stealth] (O)--(1.5,0) node[cp east] {$E$};
  \draw[cp line,-Stealth] (O)--(P);
  \draw[cp line,-Stealth] (P)--(Q);
  \draw[cp dashed] (O)--(Q);
  % Distance labels beside their own legs by their measured size (midway above
  % right ran each leg through its label), on the side away from R1 / R2.
  \cpsidelabel[0.1]{O}{P}{R1}{\cpfl}{\ensuremath{__L1__}}
  \cpsidelabel[0.1]{P}{Q}{R2}{\cpfl}{\ensuremath{__L2__}}
  \cpsidelabel{O}{Q}{P}{0.65}{$d$}  % past the E label when d runs near due east
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
            "LEN1": {"type": "number", "default": "1", "desc": "the first leg's distance as a plain number, for the drawn proportions"},
            "LEN2": {"type": "number", "default": "1", "desc": "the second leg's distance as a plain number, in the same unit as LEN1"},
            "L1": {"type": "label", "default": "", "desc": "given distance of the first leg with unit, e.g. 12\\,\\mathrm{km}; empty when none is given (the bearing is already marked on its arc)"},
            "L2": {"type": "label", "default": "", "desc": "given distance of the second leg with unit; empty when none is given"},
        },
        # the E label beside or below its arrow (a displacement near due east ran
        # along it) x the distance labels' sides and fraction
        "layout_alternatives": [rf'\tikzset{{cp east/.style={{{e}}}}}\coordinate (R1) at ({r1});\coordinate (R2) at ({r2});\pgfmathsetmacro\cpfl{{{l}}}'
                                for e in ('anchor=west', 'anchor=north west')
                                for l in ('0.5', '0.35', '0.65')
                                for r1, r2 in (('Q', 'O'), ('Qr', 'O'), ('Q', 'Or'), ('Qr', 'Or'))],
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
  % Directions and label angles derive from the bearings, as above; the legs
  % are in proportion to the distances (fixed lengths drew a 12 km leg longer
  % than an 18 km one), the shorter at least 0.3 of the longer.
  \pgfmathsetmacro\cpda{max(0.3,min(1,(__LEN1__)/max(__LEN2__,0.001)))}
  \pgfmathsetmacro\cpdb{max(0.3,min(1,(__LEN2__)/max(__LEN1__,0.001)))}
  \coordinate (P) at ({90-(__B1__)}:{3.2*\cpda});
  \coordinate (Q) at ({90-(__B2__)}:{3.2*\cpdb});
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
  \cpsidelabel[0.1]{O}{P}{R1}{\cpfl}{\ensuremath{__L1__}}
  \cpsidelabel[0.1]{O}{Q}{R2}{\cpfl}{\ensuremath{__L2__}}
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
                                for l in ('0.78', '0.55', '0.9', '0.35')
                                for r1, r2 in (('Q', 'P'), ('Q', 'Pr'), ('Qr', 'P'), ('Qr', 'Pr'))
                                for f in ('0.5', '0.3', '0.7')],
        "params": {
            "B1": {"type": "number", "default": "20", "desc": "first bearing value in degrees, clockwise from north"},
            "B2": {"type": "number", "default": "110", "desc": "second bearing value in degrees, clockwise from north"},
            "LEN1": {"type": "number", "default": "1", "desc": "the first object's distance travelled as a plain number (speed times time when only those are given), for the drawn proportions"},
            "LEN2": {"type": "number", "default": "1", "desc": "the second object's distance travelled as a plain number, in the same unit as LEN1"},
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
        # The base angle is drawn at its size (a fixed 33 degree shape was
        # labelled 72 for a ladder); the hypotenuse keeps one length.
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \pgfmathsetmacro\cpt{min(82,max(8,__ANGLE_DEG__))}
  \coordinate (A) at (0,0);
  \coordinate (B) at ({4.4*cos(\cpt)},0);
  \coordinate (C) at ({4.4*cos(\cpt)},{4.4*sin(\cpt)});
  \draw[cp line] (A) -- (B) -- (C) -- cycle;
  \pic [draw=black, angle radius={min(0.45,0.3*4.4*min(cos(\cpt),sin(\cpt)))*1cm}] {right angle=C--B--A};
  % Each angle label first, then its arc just inside it: in a narrow angle
  % the label sits far out, and a small arc left it floating mid-side.
  \pgfmathsetmacro\cpm{min(0.55,0.4*4.4*cos(\cpt))}
  \cpanglelabel{A}{\cpt/2}{\cpm}{\cpt/2}{$__ANGLAB__$}
  \pgfmathsetmacro\cpm{max(\cpm,min(\cplabelin-0.1,0.6*4.4*cos(\cpt)))}
  \draw[draw opacity=__SHOWBASE__] ($(A)+(0:\cpm)$) arc[start angle=0,end angle=\cpt,radius=\cpm];
  % the angle at the top (with a wall or the vertical), marked only when labelled
  \pgfmathsetmacro\cpn{min(0.55,0.4*4.4*sin(\cpt))}
  \cpanglelabel{C}{(\cpt-270)/2}{\cpn}{(90-\cpt)/2}{$__TOPANGLAB__$}
  \pgfmathsetmacro\cpn{max(\cpn,min(\cplabelin-0.1,0.6*4.4*sin(\cpt)))}
  \draw[draw opacity=__SHOWTOP__] ($(C)+(-90:\cpn)$) arc[start angle=-90,end angle={\cpt-180},radius=\cpn];
  \cpsidelabel[0.12]{A}{B}{C}{0.5}{$__BASELAB__$}
  \cpsidelabel[0.12]{B}{C}{A}{0.5}{$__HEIGHTLAB__$}
  \cpsidelabel[0.12]{A}{C}{B}{0.5}{$__HYPLAB__$}
\end{tikzpicture}""",
        "params": {
            "ANGLE_DEG": {"type": "number", "default": "34", "desc": "the true size of the base angle in degrees: the given angle, else found from the given sides, so the triangle has the right shape"},
            "ANGLAB": {"type": "label", "default": "", "desc": "angle label at the base vertex: a given value like 32^\\circ, \\theta / ? if it is the unknown, or empty when the angle given is at the top"},
            "SHOWBASE": {"type": "number", "default": "0", "flag_of": "ANGLAB"},
            "BASELAB": {"type": "label", "default": "", "desc": "label on the horizontal leg (given distance with unit, a symbol if it is the unknown, or empty)"},
            "HEIGHTLAB": {"type": "label", "default": "", "desc": "label on the vertical leg (given height with unit, a symbol like h if it is the unknown, or empty)", "answer_safe": False},
            "HYPLAB": {"type": "label", "default": "", "desc": "label on the hypotenuse / line of sight (e.g. the ladder length, or empty)"},
            "TOPANGLAB": {"type": "label", "default": "", "desc": "label for the angle at the top vertex, between the hypotenuse and the vertical side (an angle with a wall or the vertical), or empty"},
            "SHOWTOP": {"type": "number", "default": "0", "flag_of": "TOPANGLAB"},
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
