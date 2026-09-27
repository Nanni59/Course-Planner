"""Course Planner TikZ catalog - Vectors / Linear Algebra.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

# View choice for the cross-product parallelogram. One fixed oblique view sees
# some planes edge-on (a = (2,-1,3), b = (1,4,-2) drew a sliver), and a view
# looking straight at the face would shrink a x b to a stub. Each candidate
# (azimuth, elevation), all in the textbook arrangement (z up, x toward the
# viewer on the lower left, y to the right), is scored by c*sqrt(1-c^2), c = |n.d| for the unit
# normal n and view direction d: best when the face is seen at 45 degrees. The
# first (the old view) gets a bonus, so it stays unless the face is nearly
# edge-on in it (without, a face seen from 25 degrees up lost to 40).
_CROSS_VIEWS = [(35, 25)] + [(az, el) for az in (20, 45, 70) for el in (12, 25, 40)]


def _cross_view_head() -> str:
    # TeX macro names take letters only: view i is \cpc<a..j> / \cps<a..j>
    tag = "abcdefghij"
    lines = [r"  \pgfmathsetmacro\cpnl{max(0.0001,veclen(veclen(\cpnx,\cpny),\cpnz))}"]
    for i, (az, el) in enumerate(_CROSS_VIEWS):
        t = tag[i]
        lines.append(rf"  \pgfmathsetmacro\cpc{t}{{abs((\cpnx*cos({az})*cos({el})+\cpny*sin({az})*cos({el})+\cpnz*sin({el}))/\cpnl)}}")
        bonus = "+0.15" if i == 0 else ""
        lines.append(rf"  \pgfmathsetmacro\cps{t}{{\cpc{t}*sqrt(max(0,1-\cpc{t}*\cpc{t})){bonus}}}")
    names = ",".join(rf"\cps{tag[i]}" for i in range(len(_CROSS_VIEWS)))
    lines.append(rf"  \pgfmathsetmacro\cpbest{{max({names})}}")
    for key, pick in (("cpaz", 0), ("cpel", 1)):
        expr = str(_CROSS_VIEWS[-1][pick])
        for i in range(len(_CROSS_VIEWS) - 2, -1, -1):
            expr = rf"ifthenelse(\cps{tag[i]}>=\cpbest,{_CROSS_VIEWS[i][pick]},{expr})"
        lines.append(rf"  \pgfmathsetmacro\{key}{{{expr}}}")
    return "\n".join(lines) + "\n"


_CROSS_VIEW_HEAD = _cross_view_head()

templates = [
    {
        "id": 'airplane_wind_ground_velocity',
        "subject": 'Vectors / Linear Algebra',
        "triggers": [
            'airspeed', 'air speed', 'ground velocity', 'ground speed',
            'wind is blowing', 'wind from the west', 'airplane', 'aircraft',
        ],
        "caption": 'Airplane airspeed and wind vectors with the ground-velocity resultant.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0);
  \coordinate (A) at (__AIRANG__:3.0);
  \coordinate (G) at ($(A)+(__WINDANG__:1.45)$);
  \draw[cp axis,-Stealth] (O)--(0,3.4) node[cp label,above] {$N$};
  \draw[cp axis,-Stealth] (O)--(4.2,0) node[cp label,right] {$E$};
  \draw[cp line,-Stealth] (O)--(A);
  \draw[cp line,-Stealth] (A)--(G);
  \draw[cp dashed,-Stealth] (O)--(G);
  % Placement: the wind and ground labels at fraction f along their arrows,
  % the ground label on side g and the air-speed label on side a (1: outside
  % the triangle O-A-G, whose orientation is the sign of sin(wind - air);
  % -1: inside it, where there is room when the bearing label needs the wedge).
  @@ALT@@
  % Speed labels clear of their lines by their own measured size. The air and
  % ground speeds are written along their arrows: a wide label such as 500 km/h
  % cannot fit beside a steep arrow, least of all in the bearing wedge. The air
  % speed sits out along its arrow (fraction af), past the bearing label; inside
  % a tall triangle at its middle (out there it reached the wind arrow).
  \pgfmathsetmacro\cpo{ifthenelse(sin(__WINDANG__-(__AIRANG__))<0,90,-90)}
  \node[cp label,overlay,opacity=0] (cpmA) at (0,0) {$__AIRLAB__$};
  \path let \p1=($(A)-(O)$), \n1={atan2(\y1,\x1)}, \p2=($(cpmA.north east)-(cpmA.south west)$) in
    node[cp label,rotate={\n1-180*round(\n1/180)}] at ($(O)!\cpaf!(A)+({\n1+\cpa*\cpo}:{0.5*\y2+2pt})$) {$__AIRLAB__$};
  \node[cp label,overlay,opacity=0] (cpmW) at (0,0) {$__WINDLAB__$};
  \path let \p1=($(G)-(A)$), \n1={atan2(\y1,\x1)+\cpo}, \p2=($(cpmW.north east)-(cpmW.south west)$) in
    node[cp label] at ($(A)!\cpf!(G)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__WINDLAB__$};
  \node[cp label,overlay,opacity=0] (cpmG) at (0,0) {$__GROUNDLAB__$};
  \path let \p1=($(G)-(O)$), \n1={atan2(\y1,\x1)}, \p2=($(cpmG.north east)-(cpmG.south west)$) in
    node[cp label,rotate={\n1-180*round(\n1/180)}] at ($(O)!\cpf!(G)+({\n1-\cpg*\cpo}:{0.5*\y2+2pt})$) {$__GROUNDLAB__$};
  \draw[cp dashed] (90:0.62) arc[start angle=90,end angle=__AIRANG__,radius=0.62];
  % Bearing label inside its wedge, from l to h (it used to jump across the
  % north axis, where it read as the wrong angle): in the wider part the ground
  % vector (at angle n) leaves when it runs through the wedge, out past the arc
  % by its own size. Only a part too narrow for it (half under 7 degrees) sends
  % it beside the arc: across the north axis (x), unless the ground vector runs
  % there, then just beyond the heading (s: the side the wedge opens to).
  \pgfmathsetmacro\cpl{min(__AIRANG__,90)}
  \pgfmathsetmacro\cph{max(__AIRANG__,90)}
  \pgfmathsetmacro\cpn{atan2(3*sin(__AIRANG__)+1.45*sin(__WINDANG__),3*cos(__AIRANG__)+1.45*cos(__WINDANG__))}
  \pgfmathsetmacro\cpin{ifthenelse(\cpn>\cpl+0.5&&\cpn<\cph-0.5,1,0)}
  \pgfmathsetmacro\cpgl{ifthenelse(\cpin>0,\cpn-\cpl,\cph-\cpl)}
  \pgfmathsetmacro\cpgh{ifthenelse(\cpin>0,\cph-\cpn,0)}
  \pgfmathsetmacro\cpbm{ifthenelse(\cpgl>=\cpgh,\cpl+\cpgl/2,\cph-\cpgh/2)}
  \pgfmathsetmacro\cpbh{max(\cpgl,\cpgh)/2}
  \pgfmathsetmacro\cps{ifthenelse(__AIRANG__<90,1,-1)}
  \pgfmathsetmacro\cpx{ifthenelse(abs(\cpn-(90+28*\cps))<22,__AIRANG__-28*\cps,90+28*\cps)}
  \cpanglelabel{O}{ifthenelse(\cpbh>=7,\cpbm,\cpx)}{0.62}{ifthenelse(\cpbh>=7,\cpbh,90)}{$__BEARINGLAB__$}
\end{tikzpicture}""",
        "layout_alternatives": [rf'\pgfmathsetmacro\cpf{{{f}}}\pgfmathsetmacro\cpg{{{g}}}\pgfmathsetmacro\cpa{{{a}}}\pgfmathsetmacro\cpaf{{{af}}}'
                                for a, g, af in (('1', '1', '0.78'), ('1', '-1', '0.78'), ('-1', '1', '0.78'),
                                                 ('-1', '-1', '0.78'), ('-1', '1', '0.5'), ('-1', '-1', '0.5'))
                                for f in ('0.5', '0.35', '0.65', '0.2', '0.8')],
        "params": {
            'AIRANG': {'type': 'number', 'default': '60', 'desc': 'airplane direction in standard math degrees; N30E is 60'},
            'WINDANG': {'type': 'number', 'default': '0', 'desc': 'wind vector direction in standard math degrees; from West means east, 0 degrees'},
            'AIRLAB': {'type': 'label', 'default': '500\\,\\mathrm{km/h}', 'desc': 'airspeed label'},
            'WINDLAB': {'type': 'label', 'default': '80\\,\\mathrm{km/h}', 'desc': 'wind speed label'},
            'GROUNDLAB': {'type': 'label', 'default': '\\vec{v}_g', 'desc': 'symbolic ground velocity resultant label; do not include solved magnitude'},
            'BEARINGLAB': {'type': 'label', 'default': '30^\\circ', 'desc': 'bearing angle east of north'},
        },
    },
    {
        "id": 'vector_resultant_from_angle',
        "subject": 'Vectors / Linear Algebra',
        "triggers": [
            'resultant vector', 'resultant force', 'magnitude of the resultant',
            'resultant r', 'p + q', 'u + v', 'angle between their tails',
            'angle between the two force vectors', 'resultant of two forces',
            'two forces', 'resultant ground speed',
        ],
        "caption": 'Two vectors from a common tail with their resultant and included angle.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \draw[cp axis] (-0.5,0) -- (4.8,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,3.6) node[cp label,anchor=south] {$y$};
  \coordinate (O) at (0,0);
  \coordinate (A) at (3.2,0);
  \coordinate (B) at (__ANG__:3.0);
  \coordinate (R) at ($(A)+(B)$);
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=north] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__BLAB__$};
  \draw[cp dashed] (A) -- (R);
  \draw[cp dashed] (B) -- (R);
  \draw[cp line,->] (O) -- (R) node[cp label,anchor=south] {$__RLAB__$};
  \pic [draw=black, angle radius=0.58cm] {angle=A--O--B};
  % The resultant, and the y-axis when the angle passes 90 degrees, run through
  % the angle; its label goes in the widest gap they leave, out far enough to fit.
  \cpanglelabel{O}{ifthenelse((atan2(3*sin(__ANG__),3.2+3*cos(__ANG__)))-(0)>=max((min(__ANG__,90))-(atan2(3*sin(__ANG__),3.2+3*cos(__ANG__))),((__ANG__))-(min(__ANG__,90))),((0)+(atan2(3*sin(__ANG__),3.2+3*cos(__ANG__))))/2,ifthenelse((min(__ANG__,90))-(atan2(3*sin(__ANG__),3.2+3*cos(__ANG__)))>=((__ANG__))-(min(__ANG__,90)),((atan2(3*sin(__ANG__),3.2+3*cos(__ANG__)))+(min(__ANG__,90)))/2,((min(__ANG__,90))+((__ANG__)))/2))}{0.58}{(max((atan2(3*sin(__ANG__),3.2+3*cos(__ANG__)))-(0),max((min(__ANG__,90))-(atan2(3*sin(__ANG__),3.2+3*cos(__ANG__))),((__ANG__))-(min(__ANG__,90)))))/2}{$__ANGLAB__$}
\end{tikzpicture}""",
        "params": {
            'ANG': {'type': 'number', 'default': '60', 'desc': 'included angle between the vectors in degrees'},
            'ALAB': {'type': 'label', 'default': '\\vec{u}=5', 'desc': 'label for first vector, including magnitude if given'},
            'BLAB': {'type': 'label', 'default': '\\vec{v}=8', 'desc': 'label for second vector, including magnitude if given'},
            'RLAB': {'type': 'label', 'default': '\\vec{r}=\\vec{u}+\\vec{v}', 'desc': 'symbolic label for resultant; do not include a solved magnitude'},
            'ANGLAB': {'type': 'label', 'default': '60^\\circ', 'desc': 'included angle label'},
        },
    },
    {
        "id": 'vector_difference_from_angle',
        "subject": 'Vectors / Linear Algebra',
        "triggers": [
            'difference vector', 'magnitude of the difference', 'a - b',
            'p - q', 'u - v', 'find the magnitude of the difference',
        ],
        "caption": 'Two vectors from a common tail with the difference vector drawn head-to-head.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \draw[cp axis] (-0.5,0) -- (4.8,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,3.6) node[cp label,anchor=south] {$y$};
  \coordinate (O) at (0,0);
  \coordinate (A) at (3.4,0);
  \coordinate (B) at (__ANG__:2.65);
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=north] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__BLAB__$};
  \draw[cp line,->] (B) -- (A);
  % Labels clear of their lines: the difference label outside the triangle by
  % its own measured size, the angle label outside its arc, not inside it (the
  % default, where it touched both vectors), further out for a narrow angle.
  \node[cp label,overlay,opacity=0] (cpmD) at (0,0) {$__DIFFLAB__$};
  \path let \p1=($(A)-(B)$), \p3=($(O)-(B)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmD.north east)-(cpmD.south west)$) in
    node[cp label] at ($(B)!0.5!(A)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__DIFFLAB__$};
  % the angle mark shrinks with the difference arrow's distance from O (a wide
  % angle's arrow passes close, leaving no room for the label past a fixed mark)
  \pgfmathsetmacro\cpmk{min(0.58,0.3*3.4*2.65*sin(__ANG__)/veclen(3.4-2.65*cos(__ANG__),2.65*sin(__ANG__)))}
  \pic [draw=black, angle radius=\cpmk cm] {angle=A--O--B};
  % the widest gap the y-axis leaves, from s to e; the label at fraction f of it
  % (the difference arrow crosses a wide angle close to its bisector)
  \pgfmathsetmacro\cpgs{ifthenelse(min(__ANG__,90)>=(__ANG__)-min(__ANG__,90),0,min(__ANG__,90))}
  \pgfmathsetmacro\cpge{ifthenelse(min(__ANG__,90)>=(__ANG__)-min(__ANG__,90),min(__ANG__,90),__ANG__)}
  @@ALT@@
  \cpanglelabel{O}{\cpgs+\cpf*(\cpge-\cpgs)}{\cpmk}{min(\cpf,1-\cpf)*(\cpge-\cpgs)}{$__ANGLAB__$}
\end{tikzpicture}""",
        "layout_alternatives": [rf'\pgfmathsetmacro\cpf{{{f}}}' for f in ('0.5', '0.3', '0.7', '0.2')],
        "params": {
            'ANG': {'type': 'number', 'default': '45', 'desc': 'included angle between the original vectors in degrees'},
            'ALAB': {'type': 'label', 'default': '\\vec{a}=10', 'desc': 'label for minuend vector, including magnitude if given'},
            'BLAB': {'type': 'label', 'default': '\\vec{b}=7', 'desc': 'label for subtrahend vector, including magnitude if given'},
            'DIFFLAB': {'type': 'label', 'default': '\\vec{a}-\\vec{b}', 'desc': 'symbolic label for the difference; do not include solved magnitude'},
            'ANGLAB': {'type': 'label', 'default': '45^\\circ', 'desc': 'included angle label'},
        },
    },
    {
        "id": 'vector_subtraction_as_addition',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['expressed as an addition', 'addition problem', 'p - q', 'subtract q', 'add negative q'],
        "caption": 'Vector subtraction rewritten as addition of the opposite vector.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \draw[cp axis] (-0.5,0) -- (4.9,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-1.7) -- (0,2.6) node[cp label,anchor=south] {$y$};
  \coordinate (O) at (0,0);
  \coordinate (P) at (2.5,1.1);
  \coordinate (D) at (3.6,-0.8);
  \draw[cp line,->] (O) -- (P) node[cp label,midway,anchor=south east] {$__PLAB__$};
  \draw[cp line,->] (P) -- (D);
  % -q label above the x-axis (at mid-arrow the axis ran through it), outside
  % the triangle
  \node[cp label,overlay,opacity=0] (cpmQ) at (0,0) {$__NQLAB__$};
  \path let \p1=($(D)-(P)$), \p3=($(O)-(P)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmQ.north east)-(cpmQ.south west)$) in
    node[cp label] at ($(P)!0.3!(D)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__NQLAB__$};
  \draw[cp line,->] (O) -- (D) node[cp label,midway,anchor=north] {$__DLAB__$};
  \node[cp label,anchor=west] at (4.0,0.75) {$__REL__$};
\end{tikzpicture}""",
        "params": {
            'PLAB': {'type': 'label', 'default': '\\vec{p}', 'desc': 'first vector label'},
            'NQLAB': {'type': 'label', 'default': '-\\vec{q}', 'desc': 'opposite of the subtracted vector'},
            'DLAB': {'type': 'label', 'default': '\\vec{d}', 'desc': 'difference vector label'},
            'REL': {'type': 'label', 'default': '\\vec{d}=\\vec{p}+(-\\vec{q})', 'desc': 'subtraction-as-addition relationship'},
        },
    },
    {
        "id": 'vector_linear_combination',
        "subject": 'Vectors / Linear Algebra',
        "triggers": [
            'unit vectors', 'linear combination', '2u - 3v', '2\\vec{u}-3\\vec{v}',
            'p - 2q', 'p-2q', 'resultant vector \\vec{p} - 2\\vec{q}', 'exact magnitude',
        ],
        "caption": 'A vector linear combination built from scaled copies of two unit vectors.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0);
  \coordinate (U) at (1.2,0);
  \coordinate (V) at (__ANG__:1.2);
  \coordinate (A) at (2.7,0);
  \coordinate (B) at ($(A)+(__NEGANG__:2.25)$);
  \draw[cp axis,-Stealth] (-0.3,0) -- (4.2,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis,-Stealth] (0,-2.4) -- (0,2.5) node[cp label,anchor=south] {$y$};
  \draw[cp dashed,->] (O) -- (U) node[cp label,anchor=north] {$\vec{u}$};
  \draw[cp dashed,->] (O) -- (V) node[cp label,anchor=south west] {$\vec{v}$};
  \pic [draw=black, angle radius=0.45cm] {angle=U--O--V};
  % angle label outside its arc, in the widest gap the y-axis leaves
  \cpanglelabel{O}{ifthenelse((min(__ANG__,90))-(0)>=((__ANG__))-(min(__ANG__,90)),((0)+(min(__ANG__,90)))/2,((min(__ANG__,90))+((__ANG__)))/2)}{0.45}{(max((min(__ANG__,90))-(0),((__ANG__))-(min(__ANG__,90))))/2}{$__ANGLAB__$}
  \draw[cp line,->] (O) -- (A);
  \draw[cp line,->] (A) -- (B);
  % 2u above its arrow near the tip and -3v beside its own arrow, both outside
  % the triangle: at the tips the arrowheads ran through them
  \node[cp label,overlay,opacity=0] (cpmU) at (0,0) {$__ULAB__$};
  \path let \p1=($(A)-(O)$), \p3=($(B)-(O)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmU.north east)-(cpmU.south west)$) in
    node[cp label] at ($(O)!0.8!(A)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__ULAB__$};
  \node[cp label,overlay,opacity=0] (cpmV) at (0,0) {$__VLAB__$};
  \path let \p1=($(B)-(A)$), \p3=($(O)-(A)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmV.north east)-(cpmV.south west)$) in
    node[cp label] at ($(A)!0.5!(B)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__VLAB__$};
  \draw[cp line,->] (O) -- (B);
  % result label written along its own arrow, outside the triangle: beside it,
  % a wide label reached the y-axis whenever the arrow was steep (at the tip it
  % sat on the arrow). The side away from A is from the sign of OB x OA.
  \node[cp label,overlay,opacity=0] (cpmL) at (0,0) {$__RLAB__$};
  \path let \p1=($(B)-(O)$), \p3=($(A)-(O)$), \n1={atan2(\y1,\x1)},
    \n3={ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)}, \p2=($(cpmL.north east)-(cpmL.south west)$) in
    node[cp label,rotate={\n1-180*round(\n1/180)}] at ($(O)!@@ALT@@!(B)+({\n1+\n3}:{0.5*\y2+2pt})$) {$__RLAB__$};
\end{tikzpicture}""",
        # result label slides along its arrow when the y-axis runs through it
        "layout_alternatives": [
            '0.6',
            '0.75',
            '0.85',
            '0.45',
        ],
        "params": {
            'ANG': {'type': 'number', 'default': '60', 'desc': 'angle from u to v in degrees'},
            'NEGANG': {'type': 'number', 'default': '240', 'desc': 'direction for the negative scaled v vector, usually ANG + 180'},
            'ANGLAB': {'type': 'label', 'default': '60^\\circ', 'desc': 'angle label between unit vectors u and v'},
            'ULAB': {'type': 'label', 'default': '2\\vec{u}', 'desc': 'label for scaled u vector'},
            'VLAB': {'type': 'label', 'default': '-3\\vec{v}', 'desc': 'label for negative scaled v vector'},
            'RLAB': {'type': 'label', 'default': '2\\vec{u}-3\\vec{v}', 'desc': 'symbolic resultant label; do not include solved magnitude'},
        },
    },
    {
        "id": 'vector_zero_sum_opposites',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['a + b = 0', 'sum of two non-zero vectors', 'zero vector', 'opposite directions', 'same magnitude'],
        "caption": 'Two equal-length vectors in opposite directions whose sum is zero.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0);
  \coordinate (A) at (2.3,0);
  \coordinate (B) at (-2.3,0);
  \draw[cp axis] (-2.8,0) -- (2.8,0) node[cp label,anchor=west] {$x$};
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=north] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=north] {$__BLAB__$};
  \node[cp label,anchor=south] at (0,0.45) {$__SUM_LAB__$};
\end{tikzpicture}""",
        "params": {
            'ALAB': {'type': 'label', 'default': '\\vec{a}', 'desc': 'label for first vector'},
            'BLAB': {'type': 'label', 'default': '\\vec{b}=-\\vec{a}', 'desc': 'label for opposite vector'},
            'SUM_LAB': {'type': 'label', 'default': '\\vec{a}+\\vec{b}=\\vec{0}', 'desc': 'given zero-sum relationship'},
        },
    },
    {
        "id": 'vector_closed_triangle_sum',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['ab + bc + ca', '\\overrightarrow{ab}', 'closed triangle', 'geometric interpretation'],
        "caption": 'Three directed sides of a triangle forming a closed vector loop.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (A) at (0,0);
  \coordinate (B) at (3.2,0.35);
  \coordinate (C) at (1.0,2.35);
  \draw[cp line,->] (A) -- (B) node[cp label,midway,below] {$\overrightarrow{AB}$};
  \draw[cp line,->] (B) -- (C);
  \draw[cp line,->] (C) -- (A);
  % side labels outside the triangle, clear of their slanted sides
  \node[cp label,overlay,opacity=0] (cpmBC) at (0,0) {$\overrightarrow{BC}$};
  \path let \p1=($(C)-(B)$), \p3=($(A)-(B)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmBC.north east)-(cpmBC.south west)$) in
    node[cp label] at ($(B)!0.5!(C)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$\overrightarrow{BC}$};
  \node[cp label,overlay,opacity=0] (cpmCA) at (0,0) {$\overrightarrow{CA}$};
  \path let \p1=($(A)-(C)$), \p3=($(B)-(C)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmCA.north east)-(cpmCA.south west)$) in
    node[cp label] at ($(C)!0.5!(A)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$\overrightarrow{CA}$};
  \node[cp label,below left] at (A) {$A$};
  \node[cp label,below right] at (B) {$B$};
  \node[cp label,above] at (C) {$C$};
  \node[cp label,anchor=west] at (3.55,1.1) {$__SUM_LAB__$};
\end{tikzpicture}""",
        "params": {
            'SUM_LAB': {'type': 'label', 'default': '\\overrightarrow{AB}+\\overrightarrow{BC}+\\overrightarrow{CA}=\\vec{0}', 'desc': 'closed-loop vector sum'},
        },
    },
    {
        "id": 'triangle_midpoint_vector_sum',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['midpoint of side bc', 'midpoint bc', '2am', 'ab + ac = 2am', 'median from a'],
        "caption": 'Triangle ABC with M as the midpoint of BC and vectors from A.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \coordinate (A) at (0,0);
  \coordinate (B) at (3.8,0.25);
  \coordinate (C) at (1.1,2.65);
  \coordinate (M) at ($(B)!0.5!(C)$);
  \draw[cp line] (A) -- (B) -- (C) -- cycle;
  \node[cp label,below left] at (A) {$A$};
  \node[cp label,below right] at (B) {$B$};
  \node[cp label,above] at (C) {$C$};
  \node[cp point] at (M) {};
  % M just outside BC, clear of its point (to the right of M, BC ran through it)
  \cpsidelabel[0.12]{B}{C}{A}{0.5}{$M$}
  \draw[cp line,->] (A) -- (B) node[cp label,midway,below] {$\overrightarrow{AB}$};
  \draw[cp line,->] (A) -- (C) node[cp label,midway,left] {$\overrightarrow{AC}$};
  \draw[cp dashed,->] (A) -- (M);
  % median label on the C side of its line (it straddled the line)
  \node[cp label,overlay,opacity=0] (cpmM) at (0,0) {$\overrightarrow{AM}$};
  \path let \p1=($(M)-(A)$), \p3=($(B)-(A)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmM.north east)-(cpmM.south west)$) in
    node[cp label] at ($(A)!0.5!(M)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$\overrightarrow{AM}$};
  \draw[cp dashed] ($(B)!0.5!(M)$) -- ++(0,-0.12);
  \draw[cp dashed] ($(M)!0.5!(C)$) -- ++(0.10,0.10);
\end{tikzpicture}""",
        "params": {},
    },
    {
        "id": '2d_vector_components',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['components', '2d vector', 'component form'],
        "caption": 'A 2D vector with its horizontal and vertical components.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (4.5,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,3.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  \coordinate (P) at (__XVAL__,__YVAL__);
  \coordinate (X) at (__XVAL__,0);
  \coordinate (Y) at (0,__YVAL__);

  % the vector
  \draw[cp line,->] (O) -- (P) node[cp label,anchor=south east] {$__LAB__$};

  % projection legs
  \draw[cp dashed] (P) -- (X);
  \draw[cp dashed] (P) -- (Y);

  % component labels positioned at midpoints
  \node[cp label, below] at ($(O)!0.5!(X)$) {$__XLABEL__$};
  \node[cp label, left] at ($(O)!0.5!(Y)$) {$__YLABEL__$};

  % origin label
  \node[cp label,below left] at (O) {$O$};
\end{tikzpicture}""",
        "params": {
            'XVAL': {'type': 'number', 'default': '3', 'desc': "x-coordinate of the vector's tip"},
            'YVAL': {'type': 'number', 'default': '2', 'desc': "y-coordinate of the vector's tip"},
            'LAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for the vector'},
            'XLABEL': {'type': 'label', 'default': '3', 'desc': 'label for the horizontal component'},
            'YLABEL': {'type': 'label', 'default': '2', 'desc': 'label for the vertical component'},
        },
    },
    {
        "id": 'vector_add_parallelogram',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['vector addition', 'parallelogram', 'parallelogram law', 'parallelogram law of addition', 'resultant', 'sum of two vectors'],
        "caption": 'Parallelogram construction for vector addition.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (5,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,4.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  \coordinate (U) at (__U1__,__U2__);
  \coordinate (V) at (__V1__,__V2__);
  \coordinate (S) at ($(U)+(V)$);

  % original vectors
  \draw[cp line,->] (O) -- (U) node[cp label,anchor=south east] {$__ULAB__$};
  \draw[cp line,->] (O) -- (V) node[cp label,anchor=south west] {$__VLAB__$};

  % resultant vector
  \draw[cp line,->] (O) -- (S) node[cp label,anchor=south] {$__SUM__$};

  % edges of the parallelogram
  \draw[cp dashed] (U) -- (S);
  \draw[cp dashed] (V) -- (S);
\end{tikzpicture}""",
        "params": {
            'U1': {'type': 'number', 'default': '2', 'desc': 'x-component of vector u'},
            'U2': {'type': 'number', 'default': '1', 'desc': 'y-component of vector u'},
            'V1': {'type': 'number', 'default': '1.5', 'desc': 'x-component of vector v'},
            'V2': {'type': 'number', 'default': '2', 'desc': 'y-component of vector v'},
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for vector u'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for vector v'},
            'SUM': {'type': 'label', 'default': '\\vec{u}+\\vec{v}', 'desc': 'label for the sum vector'},
        },
    },
    {
        "id": 'vector_add_head_to_tail',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['vector addition', 'head to tail', 'triangle method', 'triangle law', 'triangle law of addition'],
        "caption": 'Head-to-tail (triangle) method for vector addition.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (5,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,4.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  \coordinate (U) at (__U1__,__U2__);
  \coordinate (Vend) at ($(U)+(__V1__,__V2__)$);

  % Each label sits at the middle of its own arrow, outside the triangle
  % (labels at the arrow tips piled up where v and u+v end), out by its own
  % size (anchored at its border, a wide u+v's corner crossed the arrow).
  \draw[cp line,->] (O) -- (U);
  \draw[cp line,->] (U) -- (Vend);
  \draw[cp line,->] (O) -- (Vend);
  \cpsidelabel{O}{U}{Vend}{0.5}{$__ULAB__$}
  \cpsidelabel{U}{Vend}{O}{0.5}{$__VLAB__$}
  \cpsidelabel{O}{Vend}{U}{0.5}{$__SUM__$}
\end{tikzpicture}""",
        "params": {
            'U1': {'type': 'number', 'default': '2', 'desc': 'x-component of vector u'},
            'U2': {'type': 'number', 'default': '1', 'desc': 'y-component of vector u'},
            'V1': {'type': 'number', 'default': '1.5', 'desc': 'x-component of vector v'},
            'V2': {'type': 'number', 'default': '2', 'desc': 'y-component of vector v'},
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for vector u'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for vector v'},
            'SUM': {'type': 'label', 'default': '\\vec{u}+\\vec{v}', 'desc': 'label for the sum vector'},
        },
    },
    {
        "id": 'vector_subtraction_head_to_tail',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['vector subtraction', 'difference vector', 'head to tail', 'subtract vectors'],
        "caption": 'Head-to-tail depiction of vector subtraction (u minus v).',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (5,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,4.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  \coordinate (U) at (__U1__,__U2__);
  \coordinate (V) at (__V1__,__V2__);

  % Each label sits at the middle of its own arrow, outside the triangle
  % (labels at the arrow tips piled up where u and u-v end). The outward
  % side flips with the triangle's orientation, the sign of u x v.
  \draw[cp line,->] (O) -- (U);
  \draw[cp line,->] (O) -- (V);
  \draw[cp line,->] (V) -- (U);
  \node[cp label,anchor={atan2(__U2__,__U1__)+ifthenelse((__U1__)*(__V2__)-(__U2__)*(__V1__)>=0,90,-90)}] at ($(O)!0.5!(U)$) {$__ULAB__$};
  \node[cp label,anchor={atan2(__V2__,__V1__)+ifthenelse((__U1__)*(__V2__)-(__U2__)*(__V1__)>=0,-90,90)}] at ($(O)!0.5!(V)$) {$__VLAB__$};
  \node[cp label,anchor={atan2((__U2__)-(__V2__),(__U1__)-(__V1__))+ifthenelse((__U1__)*(__V2__)-(__U2__)*(__V1__)>=0,-90,90)}] at ($(V)!0.5!(U)$) {$__DIFF__$};
\end{tikzpicture}""",
        "params": {
            'U1': {'type': 'number', 'default': '3', 'desc': 'x-component of vector u'},
            'U2': {'type': 'number', 'default': '2', 'desc': 'y-component of vector u'},
            'V1': {'type': 'number', 'default': '1', 'desc': 'x-component of vector v'},
            'V2': {'type': 'number', 'default': '1.5', 'desc': 'y-component of vector v'},
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for vector u'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for vector v'},
            'DIFF': {'type': 'label', 'default': '\\vec{u}-\\vec{v}', 'desc': 'label for the difference vector'},
        },
    },
    {
        "id": 'angle_between_vectors',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['angle between vectors', 'angle between two vectors', 'angle between force vectors',
                     'angle between the vectors', 'angle between the two vectors'],
        "caption": 'Two vectors with the marked angle between them.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % Directions: the given components when both vectors have them, so the
  % marked angle is the true included angle (the model used to give the second
  % vector's direction as the angle); otherwise the first vector along the
  % x-axis and the second at ANG. Components also set the lengths: the longer
  % vector 3.4, the shorter in proportion but at least 1.5.
  \pgfmathsetmacro\cpuse{ifthenelse(veclen(__AX__,__AY__)>0 && veclen(__BX__,__BY__)>0,1,0)}
  \pgfmathsetmacro\cpta{atan2(\cpuse*(__AY__),\cpuse*(__AX__)+1-\cpuse)}
  \pgfmathsetmacro\cptb{\cpuse*atan2(\cpuse*(__BY__),\cpuse*(__BX__)+1-\cpuse)+(1-\cpuse)*(__ANG__)}
  \pgfmathsetmacro\cpma{veclen(__AX__,__AY__)}
  \pgfmathsetmacro\cpmb{veclen(__BX__,__BY__)}
  \pgfmathsetmacro\cpla{ifthenelse(\cpuse>0,max(1.5,3.4*\cpma/max(\cpma,\cpmb,0.001)),3.4)}
  \pgfmathsetmacro\cplb{ifthenelse(\cpuse>0,max(1.5,3.4*\cpmb/max(\cpma,\cpmb,0.001)),3.2)}
  % d: counterclockwise turn from the first vector to the second. The arc runs
  % from the clockwise-most vector (P) through the smaller angle to Q, and each
  % vector's label sits on its outer side (s = 1 when the first vector is P).
  \pgfmathsetmacro\cpd{mod(\cptb-\cpta+720,360)}
  \pgfmathsetmacro\cps{ifthenelse(\cpd<=180,1,-1)}
  \pgfmathsetmacro\cpp{ifthenelse(\cpd<=180,\cpta,\cptb)}
  \pgfmathsetmacro\cpq{\cpp+min(\cpd,360-\cpd)}
  \coordinate (O) at (0,0);
  \coordinate (A) at (\cpta:\cpla);
  \coordinate (B) at (\cptb:\cplb);
  \coordinate (P) at (\cpp:1);
  \coordinate (Q) at (\cpq:1);
  \draw[cp axis] ({min(-0.5,\cpla*cos(\cpta)-0.6,\cplb*cos(\cptb)-0.6)},0) -- ({max(1,\cpla*cos(\cpta),\cplb*cos(\cptb))+1.1},0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,{min(-0.5,\cpla*sin(\cpta)-0.6,\cplb*sin(\cptb)-0.6)}) -- (0,{max(1,\cpla*sin(\cpta),\cplb*sin(\cptb))+0.8}) node[cp label,anchor=south] {$y$};
  % tip labels just beyond each tip on its outer side (beside it, the
  % arrowhead's barb reached the label)
  \draw[cp line,->] (O) -- (A) node[cp label,anchor={\cpta+135*\cps}] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor={\cptb-135*\cps}] {$__BLAB__$};
  \pic [draw=black, angle radius=0.7cm] {angle=P--O--Q};
  % Angle label in the widest gap the axes leave inside the angle (at most two
  % axis directions, c1 and c2, fall inside it), on that gap's bisector and far
  % enough out for its measured size to clear both sides (the pic's own label
  % sat on the y-axis at 150 degrees and on the vectors at 25).
  \pgfmathsetmacro\cpca{90*(floor(\cpp/90)+1)}
  \pgfmathsetmacro\cpcb{min(\cpca+90,\cpq)}
  \pgfmathsetmacro\cpca{min(\cpca,\cpq)}
  \pgfmathsetmacro\cpg{max(\cpca-\cpp,\cpcb-\cpca,\cpq-\cpcb)}
  \pgfmathsetmacro\cpm{ifthenelse(\cpca-\cpp>=\cpg,(\cpp+\cpca)/2,ifthenelse(\cpcb-\cpca>=\cpg,(\cpca+\cpcb)/2,(\cpcb+\cpq)/2))}
  \cpanglelabel{O}{\cpm}{0.7}{\cpg/2}{$__ANGLAB__$}
\end{tikzpicture}""",
        "params": {
            'ANG': {'type': 'number', 'default': '55', 'desc': 'angle between the vectors in degrees, used only when the question gives the angle rather than components. Use the given angle, or ~55 if the angle is the unknown being solved'},
            'AX': {'type': 'number', 'default': '0', 'desc': 'x-component of the first vector when the question gives 2D components, else 0'},
            'AY': {'type': 'number', 'default': '0', 'desc': 'y-component of the first vector when the question gives 2D components, else 0'},
            'BX': {'type': 'number', 'default': '0', 'desc': 'x-component of the second vector when the question gives 2D components, else 0'},
            'BY': {'type': 'number', 'default': '0', 'desc': 'y-component of the second vector when the question gives 2D components, else 0'},
            'ALAB': {'type': 'label', 'default': '\\vec{a}', 'desc': 'first vector label; include its given magnitude if provided, e.g. \\vec{u}=5'},
            'BLAB': {'type': 'label', 'default': '\\vec{b}', 'desc': 'second vector label; include its given magnitude if provided, e.g. \\vec{v}=3'},
            'ANGLAB': {'type': 'label', 'default': '\\theta', 'desc': 'label for the angle: a given value like 60^\\circ, or \\theta / ? if the angle is the unknown'},
        },
    },
    {
        "id": 'boat_current_resultant',
        "subject": 'Vectors / Linear Algebra',
        "triggers": [
            'boat', 'river current', 'river flows', 'still water', 'downstream',
            'cross a river', 'across the river', 'ferry', 'canoe', 'kayak',
        ],
        "caption": 'Boat velocity across a river, current downstream, and resultant path.',
        "skeleton": r"""\begin{tikzpicture}[scale=0.95]
  \coordinate (O) at (0,0);
  \coordinate (A) at (0,2.8);
  \coordinate (C) at (1.45,0);
  \coordinate (R) at ($(A)+(C)$);
  \draw[cp dashed] (-0.45,0) -- (3.0,0);
  \draw[cp dashed] (-0.45,2.8) -- (3.0,2.8);
  % boat speed written along its arrow, outside the rectangle: inside, the
  % resultant crossed it; beside it, a wide label reached the width dimension
  \draw[cp line,-Stealth] (O) -- (A);
  \node[cp label,overlay,opacity=0] (cpmS) at (0,0) {$__BOATLAB__$};
  \path let \p1=($(A)-(O)$), \n1={atan2(\y1,\x1)}, \p2=($(cpmS.north east)-(cpmS.south west)$) in
    node[cp label,rotate={\n1-180*round(\n1/180)}] at ($(O)!0.5!(A)+({\n1+(90)}:{0.5*\y2+2pt})$) {$__BOATLAB__$};
  \draw[cp line,-Stealth] (O) -- (C) node[cp label,midway,below] {$__CURRENTLAB__$};
  \draw[cp dashed] (A) -- (R);
  \draw[cp dashed] (C) -- (R);
  \draw[cp line,-Stealth] (O) -- (R);
  % resultant label beside its arrow, in the free triangle O-A-R
  \node[cp label,overlay,opacity=0] (cpmR) at (0,0) {$__RESULTLAB__$};
  \path let \p1=($(R)-(O)$), \n1={atan2(\y1,\x1)+(90)}, \p2=($(cpmR.north east)-(cpmR.south west)$) in
    node[cp label] at ($(O)!0.62!(R)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__RESULTLAB__$};
  \draw[cp dashed,<->] (-1.1,0) -- (-1.1,2.8) node[midway,left] {$__WIDTHLAB__$};
\end{tikzpicture}""",
        "params": {
            'BOATLAB': {'type': 'label', 'default': '10\\,\\mathrm{km/h}', 'desc': 'boat speed directly across the river'},
            'CURRENTLAB': {'type': 'label', 'default': '3\\,\\mathrm{km/h}', 'desc': 'current speed downstream'},
            'RESULTLAB': {'type': 'label', 'default': '\\vec{v}_g', 'desc': 'resultant ground velocity or path'},
            'WIDTHLAB': {'type': 'label', 'default': '0.5\\,\\mathrm{km}', 'desc': 'river width, if given'},
        },
    },
    {
        "id": 'force_equilibrium_closed_polygon',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['forces in equilibrium', 'in equilibrium', 'equilibrium under', 'three forces', 'two ropes', 'tension in each rope'],
        "caption": 'Forces arranged head-to-tail to show the zero resultant condition for equilibrium.',
        "skeleton": r"""\begin{tikzpicture}[scale=0.95]
  \coordinate (O) at (0,0);
  \coordinate (A) at (2.45,0.65);
  \coordinate (B) at (1.35,2.45);
  \draw[cp line,-Stealth] (O) -- (A) node[cp label,midway,below right] {$__F1LAB__$};
  \draw[cp line,-Stealth] (A) -- (B) node[cp label,midway,right] {$__F2LAB__$};
  \draw[cp line,-Stealth] (B) -- (O) node[cp label,midway,left] {$__F3LAB__$};
  \node[cp label,anchor=west] at (2.8,1.35) {$__SUM_LAB__$};
\end{tikzpicture}""",
        "params": {
            'F1LAB': {'type': 'label', 'default': '\\vec{F}_1', 'desc': 'first force label'},
            'F2LAB': {'type': 'label', 'default': '\\vec{F}_2', 'desc': 'second force label'},
            'F3LAB': {'type': 'label', 'default': '\\vec{F}_3', 'desc': 'third force or unknown tension label'},
            'SUM_LAB': {'type': 'label', 'default': '\\vec{F}_1+\\vec{F}_2+\\vec{F}_3=\\vec{0}', 'desc': 'equilibrium zero-sum relationship'},
        },
    },
    {
        "id": 'vector_projection',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['projection', 'scalar projection', 'foot of perpendicular'],
        "caption": 'Projection of one vector onto another with the foot of the perpendicular.',
        # The old skeleton drew fixed example vectors whatever the question gave
        # (v = (5, 0) came out tilted). Now the vectors come from their
        # components, the foot is the true projection t*v with t = u.v/|v|^2,
        # and the line of v runs through the foot when t < 0 or t > 1.
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \pgfmathsetmacro\cpt{((__UX__)*(__VX__)+(__UY__)*(__VY__))/max(0.0001,(__VX__)*(__VX__)+(__VY__)*(__VY__))}
  \pgfmathsetmacro\cpk{3.4/max(0.0001,veclen(__UX__,__UY__),veclen(__VX__,__VY__),abs(\cpt)*veclen(__VX__,__VY__))}
  % s = 1 when u lies counterclockwise of v: u's label goes on its outer
  % (counterclockwise) side, v's and the projection's on the clockwise side
  \pgfmathsetmacro\cps{ifthenelse((__VX__)*(__UY__)-(__VY__)*(__UX__)>=0,1,-1)}
  \pgfmathsetmacro\cpau{atan2(__UY__,__UX__)}
  \pgfmathsetmacro\cpav{atan2(__VY__,__VX__)}
  \coordinate (O) at (0,0);
  \coordinate (U) at ({\cpk*(__UX__)},{\cpk*(__UY__)});
  \coordinate (V) at ({\cpk*(__VX__)},{\cpk*(__VY__)});
  \coordinate (F) at ({\cpk*\cpt*(__VX__)},{\cpk*\cpt*(__VY__)});
  \coordinate (D) at ($(F)+(\cpav:1)$);
  \draw[cp axis] ({min(-0.5,\cpk*(__UX__)-0.6,\cpk*(__VX__)-0.6,\cpk*\cpt*(__VX__)-0.6)},0) -- ({max(1,\cpk*(__UX__),\cpk*(__VX__),\cpk*\cpt*(__VX__))+1.1},0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,{min(-0.5,\cpk*(__UY__)-0.6,\cpk*(__VY__)-0.6,\cpk*\cpt*(__VY__)-0.6)}) -- (0,{max(1,\cpk*(__UY__),\cpk*(__VY__),\cpk*\cpt*(__VY__))+0.8}) node[cp label,anchor=south] {$y$};
  % the line of v, through the foot when it falls outside O to V
  \draw[gray,thin] ($(O)!{min(0,\cpt)-0.08}!(V)$) -- ($(O)!{max(1,\cpt)}!(V)$);
  \draw[cp dashed] (U) -- (F);
  \pic [cp dashed, angle radius=0.3cm] {right angle=U--F--D};
  \draw[cp line,->] (O) -- (V) node[cp label,anchor={\cpav+135*\cps}] {$__VLAB__$};
  \draw[cp line,->] (O) -- (U) node[cp label,anchor={\cpau-135*\cps}] {$__ULAB__$};
  \draw[cp line,->,very thick] (O) -- (F);
  % projection label beside O to F (at fraction p, on side q: 1 away from u,
  % -1 toward it), out by its own measured size
  @@ALT@@
  \node[cp label,overlay,opacity=0] (cpmP) at (0,0) {$__PROJLAB__$};
  \path let \p2=($(cpmP.north east)-(cpmP.south west)$), \n1={\cpav-90*\cps*\cpq} in
    node[cp label] at ($(O)!\cpp!(F)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+3pt})$) {$__PROJLAB__$};
\end{tikzpicture}""",
        # where the projection label goes when an axis runs through it
        "layout_alternatives": [
            r'\pgfmathsetmacro\cpp{0.5}\pgfmathsetmacro\cpq{1}',
            r'\pgfmathsetmacro\cpp{0.5}\pgfmathsetmacro\cpq{-1}',
            r'\pgfmathsetmacro\cpp{0.7}\pgfmathsetmacro\cpq{1}',
            r'\pgfmathsetmacro\cpp{0.7}\pgfmathsetmacro\cpq{-1}',
            r'\pgfmathsetmacro\cpp{0.3}\pgfmathsetmacro\cpq{1}',
            r'\pgfmathsetmacro\cpp{0.3}\pgfmathsetmacro\cpq{-1}',
        ],
        "params": {
            'UX': {'type': 'number', 'default': '2', 'desc': 'x-component of the vector being projected (u)'},
            'UY': {'type': 'number', 'default': '1.5', 'desc': 'y-component of the vector being projected (u)'},
            'VX': {'type': 'number', 'default': '3', 'desc': 'x-component of the vector projected onto (v)'},
            'VY': {'type': 'number', 'default': '0.5', 'desc': 'y-component of the vector projected onto (v)'},
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for the projected vector'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for the vector being projected onto'},
            'PROJLAB': {'type': 'label', 'default': '\\mathrm{proj}_{\\vec{v}}\\vec{u}', 'desc': 'label for the projection of u onto v'},
        },
    },
    {
        "id": '3d_vector_components',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['3d vector', 'components', 'z-component', 'three-dimensional vector',
                     'in three dimensions', 'x, y, and z axes', 'component guides'],
        "caption": 'A 3D vector with dashed component drops to the coordinate axes.',
        # Any fixed oblique view sends one direction to the origin; with the old
        # single view (2, 1.5, 1) drew as a stub. The x-axis foreshortening is
        # picked per vector: whichever of two views projects it longer.
        "skeleton": r"""\begin{tikzpicture}[scale=.8,
  x={({ifthenelse((-0.55*(__XVAL__)+(__YVAL__))^2+(-0.4*(__XVAL__)+(__ZVAL__))^2>=(-0.3*(__XVAL__)+(__YVAL__))^2+(-0.75*(__XVAL__)+(__ZVAL__))^2,-0.55,-0.3)*1cm},{ifthenelse((-0.55*(__XVAL__)+(__YVAL__))^2+(-0.4*(__XVAL__)+(__ZVAL__))^2>=(-0.3*(__XVAL__)+(__YVAL__))^2+(-0.75*(__XVAL__)+(__ZVAL__))^2,-0.4,-0.75)*1cm})},
  y={(1cm,0cm)}, z={(0cm,1cm)}]
  % three-dimensional axes, long enough (either way) to hold the vector
  \draw[cp axis] ({min(__XVAL__-0.5,0)},0,0) -- ({max(__XVAL__+1,3)},0,0) node[cp label,anchor=north east] {$x$};
  \draw[cp axis] (0,{min(__YVAL__-0.5,0)},0) -- (0,{max(__YVAL__+1,3)},0) node[cp label,anchor=west] {$y$};
  \draw[cp axis] (0,0,{min(__ZVAL__-0.5,0)}) -- (0,0,{max(__ZVAL__+1,3)}) node[cp label,anchor=south] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (P) at (__XVAL__,__YVAL__,__ZVAL__);
  \coordinate (Q) at (__XVAL__,__YVAL__,0);
  \coordinate (Px) at (__XVAL__,0,0);
  \coordinate (Py) at (0,__YVAL__,0);
  \coordinate (Pz) at (0,0,__ZVAL__);

  % component box: floor projection, then up to the tip
  \draw[cp dashed] (Px) -- (Q) -- (Py);
  \draw[cp dashed] (Q) -- (P) -- (Pz);

  % the vector
  \draw[cp line,->] (O) -- (P) node[cp label,anchor=south west] {$__LAB__$};

  % component labels where each component ends on its axis, on the side
  % away from the dashed box edge that leaves that point
  \node[cp label,anchor={ifthenelse(__YVAL__<0,180,0)}] at (Px) {$__XVALLABEL__$};
  \node[cp label,anchor={ifthenelse(__XVAL__<0,90,270)}] at (Py) {$__YVALLABEL__$};
  \node[cp label,anchor={ifthenelse(-0.4*(__XVAL__)+(__YVAL__)<0,180,0)}] at (Pz) {$__ZVALLABEL__$};
\end{tikzpicture}""",
        "params": {
            'XVAL': {'type': 'number', 'default': '2', 'desc': 'x-component of the vector'},
            'YVAL': {'type': 'number', 'default': '1.5', 'desc': 'y-component of the vector'},
            'ZVAL': {'type': 'number', 'default': '1', 'desc': 'z-component of the vector'},
            'LAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for the vector'},
            'XVALLABEL': {'type': 'label', 'default': '2', 'desc': 'label for the x-component'},
            'YVALLABEL': {'type': 'label', 'default': '1.5', 'desc': 'label for the y-component'},
            'ZVALLABEL': {'type': 'label', 'default': '1', 'desc': 'label for the z-component'},
        },
    },
    {
        "id": 'cross_product_parallelogram',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['cross product', 'vector product', 'area of the parallelogram'],
        "caption": 'Two vectors spanning a parallelogram and their cross product vector.',
        # The old skeleton drew fixed vectors with a×b straight up whatever the
        # question gave, and both labels inside the face. Now a and b come from
        # their components (the longer drawn 3 long) and a×b points along the
        # true cross product, drawn 2.5 long.
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \pgfmathsetmacro\cpk{3/max(0.0001,veclen(veclen(__AX__,__AY__),__AZ__),veclen(veclen(__BX__,__BY__),__BZ__))}
  \pgfmathsetmacro\cpnx{(__AY__)*(__BZ__)-(__AZ__)*(__BY__)}
  \pgfmathsetmacro\cpny{(__AZ__)*(__BX__)-(__AX__)*(__BZ__)}
  \pgfmathsetmacro\cpnz{(__AX__)*(__BY__)-(__AY__)*(__BX__)}
""" + _CROSS_VIEW_HEAD + r"""  \begin{scope}[x={({-sin(\cpaz)*0.9cm},{-cos(\cpaz)*sin(\cpel)*0.9cm})},
    y={({cos(\cpaz)*0.9cm},{-sin(\cpaz)*sin(\cpel)*0.9cm})}, z={(0cm,{cos(\cpel)*0.9cm})}]
  \pgfmathsetmacro\cpnk{2.5/max(0.0001,veclen(veclen(\cpnx,\cpny),\cpnz))}
  \coordinate (O) at (0,0,0);
  \coordinate (A) at ({\cpk*(__AX__)},{\cpk*(__AY__)},{\cpk*(__AZ__)});
  \coordinate (B) at ({\cpk*(__BX__)},{\cpk*(__BY__)},{\cpk*(__BZ__)});
  \coordinate (C) at ($(A)+(B)$);
  \coordinate (N) at ({\cpnk*\cpnx},{\cpnk*\cpny},{\cpnk*\cpnz});
  % axes long enough, either way, for the vectors, the face and a×b
  \draw[cp axis] ({min(0,\cpk*(__AX__),\cpk*(__BX__),\cpk*((__AX__)+(__BX__)),\cpnk*\cpnx)-0.3},0,0) -- ({max(3,\cpk*(__AX__),\cpk*(__BX__),\cpk*((__AX__)+(__BX__)),\cpnk*\cpnx)+0.8},0,0) node[cp label,anchor=north east] {$x$};
  \draw[cp axis] (0,{min(0,\cpk*(__AY__),\cpk*(__BY__),\cpk*((__AY__)+(__BY__)),\cpnk*\cpny)-0.3},0) -- (0,{max(3,\cpk*(__AY__),\cpk*(__BY__),\cpk*((__AY__)+(__BY__)),\cpnk*\cpny)+0.8},0) node[cp label,anchor=west] {$y$};
  \draw[cp axis] (0,0,{min(0,\cpk*(__AZ__),\cpk*(__BZ__),\cpk*((__AZ__)+(__BZ__)),\cpnk*\cpnz)-0.3}) -- (0,0,{max(3,\cpk*(__AZ__),\cpk*(__BZ__),\cpk*((__AZ__)+(__BZ__)),\cpnk*\cpnz)+0.8}) node[cp label,anchor=south] {$z$};

  % the face first, so the vectors and labels drawn after it stay visible, and
  % see-through, so the axes behind it do too
  \draw[cp fill, fill opacity=0.6] (O) -- (A) -- (C) -- (B) -- cycle;
  \draw[cp line,->] (O) -- (A);
  \draw[cp line,->] (O) -- (B);
  % each vector label beside its vector (at fractions fa, fb) on the side away
  % from the other one, outside the face (it sat inside it)
  @@ALT@@
  \node[cp label,overlay,opacity=0] (cpmA) at (0,0) {$__ALAB__$};
  \path let \p1=($(A)-(O)$), \p3=($(B)-(O)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmA.north east)-(cpmA.south west)$) in
    node[cp label] at ($(O)!\cpfa!(A)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__ALAB__$};
  \node[cp label,overlay,opacity=0] (cpmB) at (0,0) {$__BLAB__$};
  \path let \p1=($(B)-(O)$), \p3=($(A)-(O)$), \n1={atan2(\y1,\x1)+ifthenelse(\x1*\y3-\y1*\x3>0,-90,90)},
    \p2=($(cpmB.north east)-(cpmB.south west)$) in
    node[cp label] at ($(O)!\cpfb!(B)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__BLAB__$};

  % cross product vector, its label beside the tip, a turn of g from its drawn
  % direction (90: right of an upward arrow)
  \path let \p4=($(N)-(O)$) in
    [draw, cp line, ->] (O) -- (N) node[cp label,anchor={atan2(\y4,\x4)+\cpg}] {$__CROSSLAB__$};
  \end{scope}
\end{tikzpicture}""",
        # each vector label slides along its own vector (fa, fb) and the a x b
        # label turns about its tip (g) when a line runs through one: vectors in
        # the xy-plane need one label near the tip and the other mid-way, which
        # a shared position (the last fallback put both near the origin) cannot give
        "layout_alternatives": [rf'\pgfmathsetmacro\cpfa{{{fa}}}\pgfmathsetmacro\cpfb{{{fb}}}\pgfmathsetmacro\cpg{{{g}}}'
                                for g in ('90', '-90', '180') for fa in ('0.6', '1.0', '0.4') for fb in ('0.6', '1.0', '0.4')],
        "params": {
            'AX': {'type': 'number', 'default': '3', 'desc': 'x-component of the first vector a'},
            'AY': {'type': 'number', 'default': '1', 'desc': 'y-component of the first vector a'},
            'AZ': {'type': 'number', 'default': '0', 'desc': 'z-component of the first vector a'},
            'BX': {'type': 'number', 'default': '1', 'desc': 'x-component of the second vector b'},
            'BY': {'type': 'number', 'default': '2', 'desc': 'y-component of the second vector b'},
            'BZ': {'type': 'number', 'default': '0', 'desc': 'z-component of the second vector b'},
            'ALAB': {'type': 'label', 'default': '\\vec{a}', 'desc': 'label for the first vector'},
            'BLAB': {'type': 'label', 'default': '\\vec{b}', 'desc': 'label for the second vector'},
            'CROSSLAB': {'type': 'label', 'default': '\\vec{a}\\times\\vec{b}', 'desc': 'label for the cross product vector (a x b, in that order)'},
        },
    },
    {
        "id": 'parallelepiped_volume',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['parallelepiped', 'volume of parallelepiped', 'scalar triple product'],
        "caption": 'A parallelepiped spanned by three vectors showing hidden and visible edges.',
        "skeleton": r"""\begin{tikzpicture}[scale=0.9, x={(-0.5cm,-0.3cm)}, y={(0.8cm,-0.3cm)}, z={(0cm,0.8cm)}]
  % axes
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=north east] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (A) at (2,0.6,0);
  \coordinate (B) at (0,2,0.5);
  \coordinate (V) at (0,0.8,2);
  \coordinate (C) at ($(A)+(B)$);
  \coordinate (E) at ($(A)+(V)$);
  \coordinate (F) at ($(B)+(V)$);
  \coordinate (G) at ($(C)+(V)$);

  % draw base face (filled)
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;

  % front vertical faces
  \draw[cp line] (O) -- (B) -- (F) -- (V) -- cycle;
  \draw[cp line] (O) -- (A) -- (E) -- (V) -- cycle;

  % top face and remaining edges
  \draw[cp line] (A) -- (C);
  \draw[cp line] (B) -- (C);
  \draw[cp line] (A) -- (E);
  \draw[cp line] (E) -- (G);
  \draw[cp line] (C) -- (G);
  \draw[cp line] (B) -- (F);
  \draw[cp line] (F) -- (G);
  \draw[cp line] (V) -- (G);

  % hidden edges indicated with dashed style
  \draw[cp dashed] (C) -- (F);
  \draw[cp dashed] (B) -- (G);

  % vectors from origin labelled
  \draw[cp line,->] (O) -- (A);
  \draw[cp line,->] (O) -- (B);
  \draw[cp line,->] (O) -- (V);
  % each edge vector labelled just past its tip, straight out from the box's
  % centre (G/2), so no edge of the box runs through it
  \node[cp label,overlay,opacity=0] (cpmV1) at (0,0) {$__V1LAB__$};
  \path let \p1=($(A)-0.5*(G)$), \n1={atan2(\y1,\x1)}, \p2=($(cpmV1.north east)-(cpmV1.south west)$) in
    node[cp label] at ($(A)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__V1LAB__$};
  \node[cp label,overlay,opacity=0] (cpmV2) at (0,0) {$__V2LAB__$};
  \path let \p1=($(B)-0.5*(G)$), \n1={atan2(\y1,\x1)}, \p2=($(cpmV2.north east)-(cpmV2.south west)$) in
    node[cp label] at ($(B)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__V2LAB__$};
  \node[cp label,overlay,opacity=0] (cpmV3) at (0,0) {$__V3LAB__$};
  \path let \p1=($(V)-0.5*(G)$), \n1={atan2(\y1,\x1)}, \p2=($(cpmV3.north east)-(cpmV3.south west)$) in
    node[cp label] at ($(V)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__V3LAB__$};
\end{tikzpicture}""",
        "params": {
            'V1LAB': {'type': 'label', 'default': '\\vec{v}_1', 'desc': 'label for the first spanning vector'},
            'V2LAB': {'type': 'label', 'default': '\\vec{v}_2', 'desc': 'label for the second spanning vector'},
            'V3LAB': {'type': 'label', 'default': '\\vec{v}_3', 'desc': 'label for the third spanning vector'},
        },
    },
    {
        "id": 'plane_with_normal',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['plane', 'normal vector', '3d'],
        "caption": 'A plane in three dimensions together with its normal vector.',
        "skeleton": r"""\begin{tikzpicture}[scale=1, x={(-0.5cm,-0.3cm)}, y={(0.7cm,-0.3cm)}, z={(0cm,0.8cm)}]
  % axes
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=north east] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (A) at (3,0.5,0);
  \coordinate (B) at (0.5,2,1);
  \coordinate (C) at ($(A)+(B)$);

  % plane drawn as a parallelogram
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;

  % plane label in the plane's far corner: at the centre it sat under the normal
  \node[cp label] at ($0.85*(A)+0.15*(B)$) {$__PLANELAB__$};

  % midpoint of diagonal for positioning normal vector
  \coordinate (M) at ($(O)!0.5!(C)$);
  \coordinate (N) at ($(M)+(0,0,2)$);
  \draw[cp line,->] (M) -- (N) node[cp label,anchor=west] {$__NORMALAB__$};
\end{tikzpicture}""",
        "params": {
            'PLANELAB': {'type': 'label', 'default': '\\pi', 'desc': 'label for the plane'},
            'NORMALAB': {'type': 'label', 'default': '\\vec{n}', 'desc': 'label for the normal vector'},
        },
    },
    {
        "id": 'line_plane_intersection',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['line-plane intersection', 'line and plane', 'line intersects plane', 'line intersects the plane', 'plane intersection'],
        "caption": 'A line intersecting a plane in three-dimensional space.',
        "skeleton": r"""\begin{tikzpicture}[scale=1, x={(-0.5cm,-0.3cm)}, y={(0.7cm,-0.3cm)}, z={(0cm,0.8cm)}]
  % axes
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=north east] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (A) at (3,0.5,0);
  \coordinate (B) at (0.5,2,1);
  \coordinate (C) at ($(A)+(B)$);

  % plane
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;
  % plane label in the plane's far corner, away from the point and the line
  \node[cp label] at ($0.85*(A)+0.15*(B)$) {$__PLANELAB__$};

  % The line is built through the intersection point (the old endpoints missed
  % it), and the point sits near the plane's centre (0.35A + 0.35B), clear of
  % its edges and of the z- and y-axes on every side.
  \coordinate (I) at ($0.35*(A)+0.35*(B)$);
  \coordinate (Lstart) at ($(I)+(-1.2,-1.5,1.3)$);
  \coordinate (Lend) at ($(I)+(1.2,1.5,-1.3)$);
  \draw[cp line,->] (Lstart) -- (Lend) node[cp label,anchor=west] {$__LINELAB__$};

  % intersection point
  \node[cp point] at (I) {};
  % above right: the free quadrant between the line and the y-axis (to the
  % right, the y-axis ran behind the label); the plane's far edge can graze it
  % there, so the renderer tries the other free sides
  \node[cp label,@@ALT@@] at (I) {$__PNTLAB__$};
\end{tikzpicture}""",
        "layout_alternatives": ['above right', 'right=4pt', 'below right', 'above left', 'below left'],
        "params": {
            'PLANELAB': {'type': 'label', 'default': '\\pi', 'desc': 'label for the plane'},
            'LINELAB': {'type': 'label', 'default': '\\ell', 'desc': 'label for the line'},
            'PNTLAB': {'type': 'label', 'default': 'P', 'desc': 'label for the intersection point'},
        },
    },
    {
        "id": 'linear_transformation_unit_square',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['linear transformation', 'unit square', 'parallelogram'],
        "caption": 'Mapping of the unit square to a parallelogram under a linear transformation.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes, long enough for the square and its image either way (the
  % fixed -0.5 to 4 lost a negative or large image)
  \draw[cp axis] ({min(-0.5,__AVAL__,__CVAL__,(__AVAL__)+(__CVAL__))-0.4},0) -- ({max(1.5,__AVAL__,__CVAL__,(__AVAL__)+(__CVAL__))+0.7},0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,{min(-0.5,__BVAL__,__DVAL__,(__BVAL__)+(__DVAL__))-0.4}) -- (0,{max(1.5,__BVAL__,__DVAL__,(__BVAL__)+(__DVAL__))+0.6}) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  % unit square vertices
  \coordinate (U1) at (1,0);
  \coordinate (U2) at (1,1);
  \coordinate (U3) at (0,1);
  % images of basis vectors under the transformation
  \coordinate (A) at (__AVAL__,__BVAL__);
  \coordinate (B) at (__CVAL__,__DVAL__);
  \coordinate (C) at ($(A)+(B)$);

  % Transformed region first: drawn after the unit square, its fill hid the
  % square and its label.
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;
  \node[cp label] at ($(O)!0.68!(C)$) {image};

  % Unit square (dashed) on top of the fill. Its label sits outside the square
  % (inside it, a shear image crossed it): below the x-axis by default, else
  % left of the y-axis or above the square (an image reaching below the x-axis
  % covered the first spot); placement u.
  @@ALT@@
  \draw[cp dashed] (O) -- (U1) -- (U2) -- (U3) -- cycle;
  \node[cp label,font=\scriptsize,align=left,cp unit] at (\cpux,\cpuy) {unit\\square};

  % Images of the standard basis, each labelled just beyond its tip on the
  % parallelogram's outer side, turned k from the arrow (s = 1 when T(0,1) is
  % counterclockwise of T(1,0)); a fixed above-left of T(0,1) ran across the
  % y-axis when T(0,1) = (1, 1).
  \pgfmathsetmacro\cps{ifthenelse((__AVAL__)*(__DVAL__)-(__BVAL__)*(__CVAL__)>=0,1,-1)}
  \draw[cp line,->] (O) -- (A) node[cp label,anchor={atan2(__BVAL__,__AVAL__)+\cpk*\cps}] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor={atan2(__DVAL__,__CVAL__)-\cpk*\cps}] {$__BLAB__$};
\end{tikzpicture}""",
        # (a named anchor, not an angle: on the wide two-line label an angle of
        # 135 is a point on its top edge, not its corner)
        "layout_alternatives": [rf'\pgfmathsetmacro\cpk{{{k}}}\pgfmathsetmacro\cpux{{{x}}}\pgfmathsetmacro\cpuy{{{y}}}\tikzset{{cp unit/.style={{anchor={a}}}}}'
                                for x, y, a in (('0.05', '-0.05', 'north west'), ('-0.08', '0.5', 'east'), ('0.5', '1.06', 'south'))
                                for k in ('135', '100', '165', '70')],
        "params": {
            'AVAL': {'type': 'number', 'default': '2', 'desc': 'x-image of the vector (1,0)'},
            'BVAL': {'type': 'number', 'default': '1', 'desc': 'y-image of the vector (1,0)'},
            'CVAL': {'type': 'number', 'default': '-0.5', 'desc': 'x-image of the vector (0,1)'},
            'DVAL': {'type': 'number', 'default': '1.5', 'desc': 'y-image of the vector (0,1)'},
            'ALAB': {'type': 'label', 'default': 'T(1,0)', 'desc': 'label for the image of (1,0)'},
            'BLAB': {'type': 'label', 'default': 'T(0,1)', 'desc': 'label for the image of (0,1)'},
        },
    },
    {
        "id": 'collinear_vectors',
        "subject": 'Vectors / Linear Algebra',
        # No bare 'parallel': "parallel to the line 3x+4y-12=0" is a line-equation
        # question that deserves a drawn line, not two generic parallel arrows.
        "triggers": ['collinear', 'parallel vectors', 'vectors are parallel', 'scalar multiple'],
        "caption": 'Two collinear vectors depicted as scalar multiples of each other.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (4,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,2.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  \coordinate (U) at (3,1);
  \coordinate (V) at (1.5,0.5);

  % vectors
  \draw[cp line,->] (O) -- (U) node[cp label,anchor=south east] {$__ULAB__$};
  \draw[cp line,->] (O) -- (V) node[cp label,anchor=south east] {$__VLAB__$};

  % ratio label below the longer vector, clear of the line and of the v label
  \node[cp label,overlay,opacity=0] (cpmK) at (0,0) {$__KLAB__ = __KVAL__$};
  \path let \p1=($(U)-(O)$), \n1={atan2(\y1,\x1)+(-90)}, \p2=($(cpmK.north east)-(cpmK.south west)$) in
    node[cp label] at ($(O)!0.72!(U)+(\n1:{0.5*\x2*abs(cos(\n1))+0.5*\y2*abs(sin(\n1))+2pt})$) {$__KLAB__ = __KVAL__$};
\end{tikzpicture}""",
        "params": {
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for the longer vector'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for the scaled vector'},
            'KLAB': {'type': 'label', 'default': 'k', 'desc': 'symbol denoting the scalar multiple'},
            'KVAL': {'type': 'number', 'default': '?', 'desc': 'scalar such that v = k u', 'answer_safe': False},
        },
    },
    {
        "id": 'orthogonal_vectors',
        "subject": 'Vectors / Linear Algebra',
        # No bare 'perpendicular'/'right angle': "perpendicular to the vector n"
        # in a Cartesian-line question drew two generic axis-aligned arrows with
        # no line, no point, no real direction; right-angle wording belongs to
        # right_triangle. Vector-PAIR phrasing only.
        "triggers": ['orthogonal', 'perpendicular vectors', 'vectors are perpendicular', 'dot product is zero'],
        "caption": 'Two perpendicular vectors with a right angle marker.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (4,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,3) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  \coordinate (A) at (3,0);
  \coordinate (B) at (0,2);

  % vectors
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=south east] {$__ULAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__VLAB__$};

  % right angle marker at the origin
  \pic [cp dashed, angle radius=0.4cm] {right angle=A--O--B};
\end{tikzpicture}""",
        "params": {
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for the first vector'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for the second vector'},
        },
    },
]
