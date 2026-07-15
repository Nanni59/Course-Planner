"""Course Planner TikZ catalog - Calculus.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

templates = [
    {
        "id": 'function_tangent',
        "subject": 'Calculus',
        # 'normal line' lives here so it cannot leak to the Data Management
        # bell curve; the schematic (curve + marked point + line) fits both.
        "triggers": ['tangent line', 'tangent at', 'tangent to', 'derivative', 'function curve',
                     'normal line', 'normal to the curve'],
        "caption": 'A function curve with a tangent line at a marked point.',
        # Curve and axis window are fillable: the old fixed x^2 / [-2,3] frame
        # could not show e.g. the normal to sqrt(x) at (4,2) - the marked point
        # landed outside the plot. The fill prompt shows the model this skeleton,
        # so it can frame the window around the actual point of tangency.
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=__XMIN__, xmax=__XMAX__, ymin=__YMIN__, ymax=__YMAX__,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=100, domain=__XMIN__:__XMAX__]{__CURVE__};
  \addplot[only marks, cp point] coordinates {(__POINT_X__, __POINT_Y__)};
  \node[cp label, above right] at (axis cs:__POINT_X__,__POINT_Y__) {$(__POINT_X__,__POINT_Y__)$};
  \addplot[cp dashed, domain=__XMIN__:__XMAX__]{__SLOPE__*x + __INTERCEPT__};
  \node[cp label, above right] at (axis cs:__LABEL_X__, {__SLOPE__*(__LABEL_X__) + __INTERCEPT__}) {__LINE_LABEL__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'CURVE': {'type': 'label', 'default': 'x^2', 'desc': "pgfplots expression for the question's curve in terms of x, e.g. x^2, sqrt(x), x^3 - 6*x^2 + 5*x - 1 (write * for every product; keep it defined over the whole axis window)"},
            'XMIN': {'type': 'number', 'default': '-2', 'desc': 'left edge of the axis window; choose bounds so the marked point sits comfortably inside'},
            'XMAX': {'type': 'number', 'default': '3', 'desc': 'right edge of the axis window'},
            'YMIN': {'type': 'number', 'default': '-1', 'desc': 'bottom edge of the axis window'},
            'YMAX': {'type': 'number', 'default': '5', 'desc': 'top edge of the axis window'},
            'POINT_X': {'type': 'number', 'default': '1', 'desc': 'x-coordinate of the point of tangency'},
            'POINT_Y': {'type': 'number', 'default': '1', 'desc': 'y-coordinate of the point of tangency'},
            'SLOPE': {'type': 'number', 'default': '2', 'desc': 'slope of the drawn line at the point'},
            'INTERCEPT': {'type': 'number', 'default': '-1', 'desc': 'y-intercept of the drawn line'},
            'LABEL_X': {'type': 'number', 'default': '-1.5', 'desc': 'x-position for the line label, inside the window and away from the marked point'},
            'LINE_LABEL': {'type': 'label', 'default': 'tangent', 'desc': "name of the drawn line: 'tangent' for tangent-line questions, 'normal' for normal-line questions"},
        },
    },
    {
        "id": 'secant_and_tangent',
        "subject": 'Calculus',
        "triggers": ['secant', 'secant line', 'average rate', 'instantaneous rate'],
        "caption": 'A function curve with a secant line between two points and a tangent line at one of them.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=-1, xmax=3.5, ymin=-1, ymax=6,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=100, domain=-1:3.5]{x^2};
  \addplot[only marks, cp point] coordinates {(__X1__, __Y1__) (__X2__, __Y2__)};
  \draw[cp line] (axis cs:__X1__,__Y1__) -- (axis cs:__X2__,__Y2__);
  \node[cp label, above right] at (axis cs:__X1__,__Y1__) {secant};
  \addplot[cp dashed, domain=-1:3.5]{__TAN_SLOPE__*x + __TAN_INTERCEPT__};
  \node[cp label, anchor=west] at (axis cs:-0.5, {__TAN_SLOPE__*(-0.5)+__TAN_INTERCEPT__}) {tangent};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'X1': {'type': 'number', 'default': '1', 'desc': 'x-coordinate of the first point on the curve'},
            'Y1': {'type': 'number', 'default': '1', 'desc': 'y-coordinate of the first point on the curve'},
            'X2': {'type': 'number', 'default': '2', 'desc': 'x-coordinate of the second point on the curve'},
            'Y2': {'type': 'number', 'default': '4', 'desc': 'y-coordinate of the second point on the curve'},
            'TAN_SLOPE': {'type': 'number', 'default': '2', 'desc': 'slope of the tangent line at the first point'},
            'TAN_INTERCEPT': {'type': 'number', 'default': '-1', 'desc': 'y-intercept of the tangent line at the first point'},
        },
    },
    {
        "id": 'definite_integral_shaded',
        "subject": 'Calculus',
        "triggers": [
            'definite integral', 'shaded area', 'shade the area', 'area under',
            'area under curve', 'area from', 'area between', 'rate curve',
            'net area', 'bounded by', 'bounded region', 'x-axis',
            'accumulated', 'total distance travelled',
        ],
        "caption": 'Definite integral represented as shaded area under a curve between $x=a$ and $x=b$.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=-1, xmax=4, ymin=0, ymax=5,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=100, domain=-1:4]{x^2};
  \addplot[cp fill, draw=none, samples=100, domain=__A__:__B__] {x^2} \closedcycle;
  \node[cp label, above] at (axis cs:__AREA_LABEL_X__, __AREA_LABEL_Y__) {area};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'A': {'type': 'number', 'default': '0.5', 'desc': 'lower limit of integration'},
            'B': {'type': 'number', 'default': '2', 'desc': 'upper limit of integration'},
            'AREA_LABEL_X': {'type': 'number', 'default': '1.3', 'desc': 'x-coordinate for the area label'},
            'AREA_LABEL_Y': {'type': 'number', 'default': '2', 'desc': 'y-coordinate for the area label'},
        },
    },
    {
        "id": 'riemann_sum_rectangles',
        "subject": 'Calculus',
        "triggers": ['Riemann sum', 'rectangles', 'left endpoint'],
        "caption": 'Riemann sum approximation using left-endpoint rectangles under a curve.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=0, xmax=1.6, ymin=0, ymax=2.5,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=100, domain=0:1.5]{x^2};
  \path[cp fill] (axis cs:__X0__,0) -- (axis cs:__X1__,0) -- (axis cs:__X1__, __H1__) -- (axis cs:__X0__, __H1__) -- cycle;
  \path[cp fill] (axis cs:__X1__,0) -- (axis cs:__X2__,0) -- (axis cs:__X2__, __H2__) -- (axis cs:__X1__, __H2__) -- cycle;
  \path[cp fill] (axis cs:__X2__,0) -- (axis cs:__X3__,0) -- (axis cs:__X3__, __H3__) -- (axis cs:__X2__, __H3__) -- cycle;
\end{axis}
\end{tikzpicture}""",
        "params": {
            'X0': {'type': 'number', 'default': '0', 'desc': 'left endpoint of the first rectangle'},
            'X1': {'type': 'number', 'default': '0.5', 'desc': 'right endpoint of the first rectangle and left endpoint of the second'},
            'X2': {'type': 'number', 'default': '1', 'desc': 'right endpoint of the second rectangle and left endpoint of the third'},
            'X3': {'type': 'number', 'default': '1.5', 'desc': 'right endpoint of the third rectangle'},
            'H1': {'type': 'number', 'default': '0', 'desc': 'height of the first rectangle'},
            'H2': {'type': 'number', 'default': '0.25', 'desc': 'height of the second rectangle'},
            'H3': {'type': 'number', 'default': '1', 'desc': 'height of the third rectangle'},
        },
    },
    {
        "id": 'removable_discontinuity',
        "subject": 'Calculus',
        "triggers": ['removable discontinuity', 'removable discontinuities', 'limit at a point', 'hole in graph', 'holes'],
        "caption": 'A graph illustrating a removable discontinuity with an open hole and a defined value.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=0, xmax=3, ymin=0, ymax=4,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=100, domain=0:3]{x+1};
  \draw[cp line, fill=white] (axis cs:__X0__, __HOLE_Y__) circle[radius=2pt];
  \addplot[only marks, cp point] coordinates {(__X0__, __FILLED_Y__)};
  \node[cp label, above right] at (axis cs:__X0__, __HOLE_Y__) {hole};
  \node[cp label, right] at (axis cs:__X0__, __FILLED_Y__) {defined};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'X0': {'type': 'number', 'default': '1', 'desc': 'x-coordinate of the discontinuity'},
            'HOLE_Y': {'type': 'number', 'default': '2', 'desc': 'y-value of the function approaching the discontinuity'},
            'FILLED_Y': {'type': 'number', 'default': '1', 'desc': 'defined y-value at the discontinuity'},
        },
    },
    {
        "id": 'asymptotes_graph',
        "subject": 'Calculus',
        "triggers": ['vertical asymptote', 'horizontal asymptote'],
        "caption": 'A graph of a rational function showing both a vertical and a horizontal asymptote.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=-2, xmax=5, ymin=-1, ymax=5,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=100, domain=-2:__C__-0.2]{1/(x-__C__) + __K__};
  \addplot[cp line, samples=100, domain=__C__+0.2:5]{1/(x-__C__) + __K__};
  \draw[cp dashed] (axis cs:__C__,-1) -- (axis cs:__C__,5);
  \draw[cp dashed] (axis cs:-2,__K__) -- (axis cs:5,__K__);
  \node[cp label, anchor=west] at (axis cs:__C__+0.05,4.5) {vertical asymptote};
  \node[cp label, anchor=south] at (axis cs:-1.5,__K__+0.05) {horizontal asymptote};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'C': {'type': 'number', 'default': '1', 'desc': 'x-coordinate of the vertical asymptote'},
            'K': {'type': 'number', 'default': '2', 'desc': 'y-coordinate of the horizontal asymptote'},
        },
    },
    {
        "id": 'curve_extrema_inflection',
        "subject": 'Calculus',
        "triggers": ['local maxima', 'local minima', 'inflection point', 'curve sketch',
                     'critical number', 'critical point', 'local maximum', 'local minimum',
                     'local extrema'],
        "caption": 'A curve with marked local maximum, local minimum and an inflection point.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[width=7cm,height=4.5cm, axis lines=center, xlabel={$x$}, ylabel={$y$},
  xmin=-2, xmax=2, ymin=-3, ymax=3,
  grid=both, grid style={cp dashed},
  every axis line/.style={cp axis},
  every tick/.style={cp label}]
  \addplot[cp line, samples=200, domain=-2:2]{x^3 - 3*x};
  \addplot[only marks, cp point] coordinates {(__MAX_X__, __MAX_Y__) (__MIN_X__, __MIN_Y__) (__INFLEX_X__, __INFLEX_Y__)};
  \node[cp label, above left] at (axis cs:__MAX_X__, __MAX_Y__) {max};
  \node[cp label, below right] at (axis cs:__MIN_X__, __MIN_Y__) {min};
  \node[cp label, above right] at (axis cs:__INFLEX_X__, __INFLEX_Y__) {inflection};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'MAX_X': {'type': 'number', 'default': '-1', 'desc': 'x-coordinate of the local maximum'},
            'MAX_Y': {'type': 'number', 'default': '2', 'desc': 'y-coordinate of the local maximum'},
            'MIN_X': {'type': 'number', 'default': '1', 'desc': 'x-coordinate of the local minimum'},
            'MIN_Y': {'type': 'number', 'default': '-2', 'desc': 'y-coordinate of the local minimum'},
            'INFLEX_X': {'type': 'number', 'default': '0', 'desc': 'x-coordinate of the inflection point'},
            'INFLEX_Y': {'type': 'number', 'default': '0', 'desc': 'y-coordinate of the inflection point'},
        },
    },
    {
        "id": 'optimization_rectangle',
        "subject": 'Calculus',
        "triggers": ['optimization', 'rectangle', 'constraint', 'fencing', 'enclose'],
        "caption": 'A rectangle with labelled dimensions and a perimeter constraint for optimization problems.',
        "skeleton": r"""\begin{tikzpicture}
\draw[cp line] (0,0) rectangle (4,2);
\draw[cp dashed,<->] (0,-0.4) -- (4,-0.4) node[midway,below] {$__WIDTH_LABEL__$};
\draw[cp dashed,<->] (-0.4,0) -- (-0.4,2) node[midway,left] {$__HEIGHT_LABEL__$};
\node[cp label] at (2,2.5) {$2\times __WIDTH_LABEL__ + 2\times __HEIGHT_LABEL__ = __P__$};
\end{tikzpicture}""",
        "params": {
            'WIDTH_LABEL': {'type': 'label', 'default': 'x', 'desc': "symbol for the rectangle's width"},
            'HEIGHT_LABEL': {'type': 'label', 'default': 'y', 'desc': "symbol for the rectangle's height"},
            'P': {'type': 'label', 'default': 'P', 'desc': 'perimeter constant in the constraint'},
        },
    },
    {
        # Three-sided fencing variant: one side borders a river/barn/wall, so
        # the constraint is 2x + y = P, NOT the closed perimeter 2x + 2y = P
        # that optimization_rectangle shows. Multi-word triggers outrank that
        # template's bare 'fencing'/'optimization' hits. Bare 'river' is NOT a
        # trigger (vector river-crossing questions would collide).
        "id": 'optimization_river_rectangle',
        "subject": 'Calculus',
        # NOTE: no wall triggers like 'against a wall' — ladder problems say
        # "leaning against a wall" and must keep routing to right_triangle.
        "triggers": [
            'along a river', 'along the river', 'along a straight river',
            'borders a river', 'bank of a river', 'no fence', 'no fencing',
            'three sides', 'against a barn', 'side of a barn',
            'side of a house', 'existing wall',
        ],
        "caption": 'A rectangular field fenced on three sides with one side open along a river.',
        "skeleton": r"""\begin{tikzpicture}
\draw[cp line] (0,0) -- (0,2) -- (4,2) -- (4,0);
\draw[cp dashed] (0,0) -- (4,0);
\draw[cp axis, line width=1.6pt] (-0.35,-0.45) -- (4.35,-0.45);
\node[cp label, below] at (2,-0.55) {__OPEN_SIDE_LABEL__};
\draw[cp dashed,<->] (-0.45,0) -- (-0.45,2) node[midway,left] {$__SIDE_LABEL__$};
\draw[cp dashed,<->] (4.45,0) -- (4.45,2) node[midway,right] {$__SIDE_LABEL__$};
\draw[cp dashed,<->] (0,2.4) -- (4,2.4) node[midway,above] {$__TOP_LABEL__$};
\node[cp label] at (2,3.05) {$2\times __SIDE_LABEL__ + __TOP_LABEL__ = __P__$};
\end{tikzpicture}""",
        "params": {
            'SIDE_LABEL': {'type': 'label', 'default': 'x', 'desc': 'symbol for each of the two fenced sides perpendicular to the open side'},
            'TOP_LABEL': {'type': 'label', 'default': 'y', 'desc': 'symbol for the fenced side parallel to the open side'},
            'P': {'type': 'label', 'default': 'P', 'desc': 'total length of fencing available (given constant)'},
            'OPEN_SIDE_LABEL': {'type': 'label', 'default': 'river', 'desc': 'what the unfenced side borders: river, barn, wall or house'},
        },
    },
    {
        "id": 'related_rates_circle',
        "subject": 'Calculus',
        "triggers": [
            'related rates', 'expanding circle', 'growing circle',
            'rate of change of the radius', 'ripple', 'radius is increasing',
            'radius increasing', 'circle is expanding',
            # "The radius of a circle is increasing at a rate of..." — the noun
            # phrase between "radius" and "is increasing" broke the contiguous
            # match, so the question fell through to the legacy generic circle.
            'circle is increasing', 'circle is decreasing', 'circle is growing',
            'circle is shrinking', 'radius of a circle is', 'radius of the circle is',
            'area of the circle increasing', 'area of a circle increasing',
        ],
        "caption": 'An expanding circle with a radius and its rate of change indicated.',
        # Geometry is FIXED (drawing radius 2): Gemini once filled RADIUS with the
        # question's real radius (5 cm) and drew a page-filling circle. Only the
        # two text labels are fillable; the dashed outer ring shows the growth.
        "skeleton": r"""\begin{tikzpicture}
\coordinate (O) at (0,0);
\draw[cp line] (O) circle [radius=2];
\draw[cp dashed] (O) circle [radius=2.5];
\fill (O) circle (1.4pt);
\draw[cp axis,-Stealth] (O) -- (2,0);
\node[cp label, above] at (1,0.06) {__R_LABEL__};
\draw[cp axis,-Stealth] (2.04,0) -- (2.5,0);
\node[cp label, above right] at (2.3,0.28) {__DR_LABEL__};
\end{tikzpicture}""",
        "params": {
            'R_LABEL': {'type': 'label', 'default': 'r', 'desc': "radius label using the question's given value, e.g. r=5 cm"},
            'DR_LABEL': {'type': 'label', 'default': '$\\frac{dr}{dt}$', 'desc': "rate-of-change label using the question's given rate, e.g. $\\frac{dr}{dt}=2$"},
        },
    },
]
