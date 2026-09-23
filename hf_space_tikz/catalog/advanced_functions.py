"""Course Planner TikZ catalog - Advanced Functions.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

templates = [
    {
        "id": 'poly_roots_end',
        "subject": 'Advanced Functions',
        "triggers": ['polynomial', 'roots', 'end behaviour', 'cubic'],
        "caption": 'Graph of a cubic polynomial highlighting its roots and end behaviour.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-4, xmax=4,
    ymin=-10, ymax=10,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-3,-2,-1,0,1,2,3}, ytick={-10,-5,0,5,10},
    tick label style={font=\scriptsize},
    domain=-3.5:3.5,
    samples=201,
]
    % cubic polynomial defined by its three roots
    \addplot[cp line] { (x - __ROOTA__)*(x - __ROOTB__)*(x - __ROOTC__) };
    % roots marked on the x–axis
    \addplot[only marks, cp point] coordinates {(__ROOTA__,0) (__ROOTB__,0) (__ROOTC__,0)};
    % labels for each root
    \node[cp label, anchor=north] at (axis cs:__ROOTA__,0) {__LABELA__};
    \node[cp label, anchor=north] at (axis cs:__ROOTB__,0) {__LABELB__};
    \node[cp label, anchor=north] at (axis cs:__ROOTC__,0) {__LABELC__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'ROOTA': {'type': 'number', 'default': -2, 'desc': 'leftmost root of the cubic'},
            'ROOTB': {'type': 'number', 'default': 0, 'desc': 'middle root of the cubic'},
            'ROOTC': {'type': 'number', 'default': 2, 'desc': 'rightmost root of the cubic'},
            'LABELA': {'type': 'label', 'default': '$-2$', 'desc': 'label for the first root'},
            'LABELB': {'type': 'label', 'default': '$0$', 'desc': 'label for the second root'},
            'LABELC': {'type': 'label', 'default': '$2$', 'desc': 'label for the third root'},
        },
    },
    {
        "id": 'rational_asymptotes',
        "subject": 'Advanced Functions',
        "triggers": ['rational', 'rational function', 'vertical asymptote', 'horizontal asymptote', 'asymptotes'],
        "caption": 'Rational function with a vertical and a horizontal asymptote.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=__XMIN__, xmax=__XMAX__,
    ymin=__YMIN__, ymax=__YMAX__,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    unbounded coords=jump,
    % Clip the curves only; the asymptote labels sit just outside the window.
    clip mode=individual,
]
    % rational function f(x) = A/(x - H) + K
    \addplot[cp line, samples=301, domain=__XMIN__:__XMAX__] { __A__/(x - __H__) + __K__ };
    % vertical asymptote x = H
    \addplot[cp dashed] coordinates {(__H__,__YMIN__) (__H__,__YMAX__)};
    % horizontal asymptote y = K
    \addplot[cp dashed] coordinates {(__XMIN__,__K__) (__XMAX__,__K__)};
    % labels for asymptotes
    \node[cp label, anchor=south west] at (axis cs:__H__,__YMAX__) {$x=__LABEL_H__$};
    \node[cp label, anchor=north east] at (axis cs:__XMIN__,__K__) {$y=__LABEL_K__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'XMIN': {'type': 'number', 'default': -5, 'desc': 'left axis bound far enough to show the left branch'},
            'XMAX': {'type': 'number', 'default': 5, 'desc': 'right axis bound far enough to show the right branch'},
            'YMIN': {'type': 'number', 'default': -5, 'desc': 'bottom axis bound'},
            'YMAX': {'type': 'number', 'default': 5, 'desc': 'top axis bound'},
            'A': {'type': 'number', 'default': 1, 'desc': 'numerator coefficient in the rational function'},
            'H': {'type': 'number', 'default': 1, 'desc': 'x-value of the vertical asymptote'},
            'K': {'type': 'number', 'default': 0, 'desc': 'y-value of the horizontal asymptote'},
            'LABEL_H': {'type': 'label', 'default': '?', 'desc': 'symbolic label for the vertical asymptote; do not reveal it when the worksheet asks the student to identify it', 'answer_safe': False},
            'LABEL_K': {'type': 'label', 'default': '?', 'desc': 'symbolic label for the horizontal asymptote; do not reveal it when the worksheet asks the student to identify it', 'answer_safe': False},
        },
    },
    {
        "id": 'exponential_asymptote',
        "subject": 'Advanced Functions',
        "triggers": ['exponential', 'growth', 'decay', '^x', 'horizontal asymptote'],
        "caption": 'Exponential growth or decay function with its horizontal asymptote.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-2, xmax=3,
    % The window follows the curve (capped at 8 units past the asymptote); the
    % old fixed 0..6 range cut off shifted graphs such as y = 2^(x - 1) + 3.
    ymin={max(min(0,__K__,__K__+__A__*pow(__B__,-2-(__H__)),__K__+__A__*pow(__B__,3-(__H__))),min(0,__K__)-8)-1},
    ymax={min(max(0,__K__,__K__+__A__*pow(__B__,-2-(__H__)),__K__+__A__*pow(__B__,3-(__H__))),max(0,__K__)+8)+1},
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-2,-1,0,1,2,3},
    % Clip the curve only; the asymptote label sits just left of the window.
    clip mode=individual,
]
    % exponential function f(x) = A*B^(x - H) + K
    \addplot[cp line, samples=201, domain=-2:3] { __A__*(pow(__B__, x - (__H__))) + __K__ };
    % horizontal asymptote y = K
    \addplot[cp dashed] coordinates {(-2,__K__) (3,__K__)};
    % label for asymptote
    \node[cp label, anchor=east] at (axis cs:-2,__K__) {$y=__LABEL_K__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'A': {'type': 'number', 'default': 1, 'desc': 'coefficient multiplying the power in y = A*B^(x - H) + K'},
            'B': {'type': 'number', 'default': 2, 'desc': 'positive base of the exponential function'},
            'H': {'type': 'number', 'default': 0, 'desc': 'horizontal shift H in y = A*B^(x - H) + K; y = 2^(x - 1) + 3 has H = 1'},
            'K': {'type': 'number', 'default': 0, 'desc': 'vertical shift (horizontal asymptote)'},
            'LABEL_K': {'type': 'label', 'default': '?', 'desc': 'symbolic label for the horizontal asymptote; do not reveal the value when it is requested', 'answer_safe': False},
        },
    },
    {
        "id": 'logarithmic_asymptote',
        "subject": 'Advanced Functions',
        "triggers": ['logarithmic', 'vertical asymptote', 'log'],
        "caption": 'Logarithmic function with its vertical asymptote.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-1, xmax=6,
    ymin=-2, ymax=4,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={0,1,2,3,4,5}, ytick={-2,-1,0,1,2,3,4},
    domain=0.1:6,
]
    % logarithmic function f(x) = A*log_B(x) + K
    \addplot[cp line, samples=201] { __A__*(ln(x)/ln(__B__)) + __K__ };
    % vertical asymptote at x = 0
    \addplot[cp dashed] coordinates {(0,-2) (0,4)};
    % label for asymptote
    \node[cp label, anchor=north west] at (axis cs:0,4) {$x=__LABEL_X__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'A': {'type': 'number', 'default': 1, 'desc': 'coefficient of the logarithmic function'},
            'B': {'type': 'number', 'default': 10, 'desc': 'base of the logarithm'},
            'K': {'type': 'number', 'default': 0, 'desc': 'vertical shift'},
            'LABEL_X': {'type': 'label', 'default': '0', 'desc': 'label for the vertical asymptote'},
        },
    },
    {
        "id": 'sinusoid_amplitude_period',
        "subject": 'Advanced Functions',
        "triggers": ['sinusoid', 'sinusoidal', 'amplitude', 'period', 'phase shift', 'midline', 'sine', 'tide'],
        "caption": 'Sinusoidal function marking its amplitude, period, and midline.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=0, xmax=6.2832,
    % The window always contains the full wave and the x-axis; the old fixed
    % -4..4 range cut off the trough of y = 3 sin x - 2.
    ymin={min(0,__MIDLINE_VALUE__-abs(__AMPLITUDE_VALUE__))-ifthenelse(__MIDLINE_VALUE__<0,1.8,0.8)},
    ymax={max(0,__MIDLINE_VALUE__+abs(__AMPLITUDE_VALUE__))+ifthenelse(__MIDLINE_VALUE__<0,0.8,1.8)},
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={0,1.5708,3.1416,4.7124,6.2832},
    xticklabels={$0$,$\frac{\pi}{2}$,$\pi$,$\frac{3\pi}{2}$,$2\pi$},
    % Clip the curve only; the midline label sits just right of the window.
    clip mode=individual,
]
    % sinusoidal function f(x) = A*sin(B*(x - C)) + D
    \addplot[cp line, samples=241, domain=0:6.2832] { __AMPLITUDE_VALUE__*sin(deg(__FREQUENCY_VALUE__*(x - (__PHASE_SHIFT_VALUE__)))) + __MIDLINE_VALUE__ };
    % midline
    \addplot[cp dashed] coordinates {(0,__MIDLINE_VALUE__) (6.2832,__MIDLINE_VALUE__)};
    \node[cp label, anchor=west] at (axis cs:6.2832,__MIDLINE_VALUE__) {__MIDLINE_LABEL__};
    % amplitude: midline to the extremum on the side away from the x-axis, so
    % the arrow never crosses the axis or its tick labels (x kept off the y-axis)
    \draw[cp axis,<->] (axis cs:{((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)-(6.2832/__FREQUENCY_VALUE__)*floor((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)/(6.2832/__FREQUENCY_VALUE__)))+ifthenelse(((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)-(6.2832/__FREQUENCY_VALUE__)*floor((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)/(6.2832/__FREQUENCY_VALUE__)))<0.3,(6.2832/__FREQUENCY_VALUE__),0)},__MIDLINE_VALUE__) -- (axis cs:{((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)-(6.2832/__FREQUENCY_VALUE__)*floor((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)/(6.2832/__FREQUENCY_VALUE__)))+ifthenelse(((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)-(6.2832/__FREQUENCY_VALUE__)*floor((__PHASE_SHIFT_VALUE__+(2-ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*ifthenelse(__AMPLITUDE_VALUE__>=0,1,-1))*1.5708/__FREQUENCY_VALUE__)/(6.2832/__FREQUENCY_VALUE__)))<0.3,(6.2832/__FREQUENCY_VALUE__),0)},{__MIDLINE_VALUE__+ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*abs(__AMPLITUDE_VALUE__)}) node[pos=1, anchor=west, xshift=2pt] {__AMPLITUDE_LABEL__};
    % period: one cycle long, drawn on the side of the wave away from the x-axis
    \draw[cp axis,<->] (axis cs:0,{__MIDLINE_VALUE__+ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*(abs(__AMPLITUDE_VALUE__)+1)}) -- (axis cs:{min(6.2832,6.2832/__FREQUENCY_VALUE__)},{__MIDLINE_VALUE__+ifthenelse(__MIDLINE_VALUE__>=0,1,-1)*(abs(__AMPLITUDE_VALUE__)+1)}) node[midway, yshift={ifthenelse(__MIDLINE_VALUE__>=0,7,-7)}] {__PERIOD_LABEL__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'AMPLITUDE_VALUE': {'type': 'number', 'default': 2, 'desc': 'A in y = A*sin(B*(x - C)) + D'},
            'FREQUENCY_VALUE': {'type': 'number', 'default': 1, 'desc': 'positive B in y = A*sin(B*(x - C)) + D; the period is 2*pi/B'},
            'PHASE_SHIFT_VALUE': {'type': 'number', 'default': 0, 'desc': 'C in radians; for a cosine y = A*cos(B*(x - C)) + D use C - 1.5708/B'},
            'MIDLINE_VALUE': {'type': 'number', 'default': 0, 'desc': 'D, the vertical midline of the sinusoid'},
            'AMPLITUDE_LABEL': {'type': 'label', 'default': '$A$', 'desc': 'symbolic label for the amplitude arrow; never the requested numeric answer', 'answer_safe': False, 'unknown': '$A$'},
            'MIDLINE_LABEL': {'type': 'label', 'default': 'midline', 'desc': 'symbolic midline label; never the requested equation', 'answer_safe': False, 'unknown': 'midline'},
            'PERIOD_LABEL': {'type': 'label', 'default': '$P$', 'desc': 'symbolic label for the period arrow; never the requested numeric answer', 'answer_safe': False, 'unknown': '$P$'},
        },
    },
    {
        "id": 'reciprocal_asymptotes',
        "subject": 'Advanced Functions',
        "triggers": ['reciprocal', 'hyperbola', 'y=1/x'],
        "caption": 'Reciprocal function y = k/x showing both vertical and horizontal asymptotes.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-5, xmax=5,
    ymin=-5, ymax=5,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-5,-4,-3,-2,-1,0,1,2,3,4,5}, ytick={-5,-4,-3,-2,-1,0,1,2,3,4,5},
    unbounded coords=jump,
]
    % reciprocal function f(x) = COEFF/x (split domain to skip the x=0 asymptote)
    \addplot[cp line, samples=100, domain=-4.8:-0.2] { __COEFF__/x };
    \addplot[cp line, samples=100, domain=0.2:4.8] { __COEFF__/x };
    % vertical asymptote x=0
    \addplot[cp dashed] coordinates {(0,-5) (0,5)};
    % horizontal asymptote y=0
    \addplot[cp dashed] coordinates {(-5,0) (5,0)};
    % labels for asymptotes
    \node[cp label, anchor=north west] at (axis cs:0,5) {$x=__LABEL_VA__$};
    \node[cp label, anchor=north east] at (axis cs:-5,0) {$y=__LABEL_HA__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'COEFF': {'type': 'number', 'default': 1, 'desc': 'numerator coefficient in the reciprocal function'},
            'LABEL_VA': {'type': 'label', 'default': '0', 'desc': 'label for the vertical asymptote (x=0)'},
            'LABEL_HA': {'type': 'label', 'default': '0', 'desc': 'label for the horizontal asymptote (y=0)'},
        },
    },
    {
        "id": 'projectile_parabola',
        "subject": 'Advanced Functions',
        "triggers": [
            'projectile', 'thrown upward', 'thrown into the air', 'height-time',
            'maximum height', 'ground intercepts', 'launched upward',
            'height of the ball', 'path of the ball',
        ],
        "caption": 'A downward height-time parabola with the vertex as maximum height and the launch/landing intercepts.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4.5cm,
    axis lines=left,
    axis line style=cp axis,
    xlabel={$t$}, ylabel={$h$},
    xmin=0, ymin=0,
    enlarge x limits={rel=0.12},
    enlarge y limits={upper, value=0.18},
    ytick=\empty,
]
    % downward height-time parabola; roots at t=0 (launch) and t=T_END (landing)
    \addplot[cp line, mark=none, samples=100, domain=0:__T_END__]
        { __H_MAX__ - (__H_MAX__/((__T_VERT__)*(__T_VERT__)))*(x - __T_VERT__)^2 };
    % maximum height (vertex)
    \addplot[only marks, cp point] coordinates {(__T_VERT__, __H_MAX__)};
    \node[cp label, anchor=south] at (axis cs:__T_VERT__, __H_MAX__) {__VERTEX_LABEL__};
    % ground intercepts (launch and landing)
    \addplot[only marks, cp point] coordinates {(0,0) (__T_END__,0)};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'T_VERT': {'type': 'number', 'default': '2', 'desc': 'time of maximum height (x-coordinate of the vertex)'},
            'T_END': {'type': 'number', 'default': '4', 'desc': 'time the object lands (right x-intercept); use about twice the vertex time for a level launch'},
            'H_MAX': {'type': 'number', 'default': '5', 'desc': 'maximum height reached (y-coordinate of the vertex)'},
            'VERTEX_LABEL': {'type': 'label', 'default': '\\text{max height}', 'desc': 'label at the vertex; keep it symbolic (e.g. "max height"), never the solved numeric height', 'answer_safe': False},
        },
    },
    {
        "id": 'parabola_transformation',
        "subject": 'Advanced Functions',
        "triggers": ['parent function', 'transformation', 'parabola', 'shift', 'stretch'],
        "caption": 'Parent quadratic function overlaid with a transformed parabola.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-3, xmax=5,
    ymin=-2, ymax=8,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-3,-2,-1,0,1,2,3,4,5}, ytick={-2,0,2,4,6,8},
]
    % parent function f(x) = x^2
    \addplot[cp dashed, samples=201, domain=-3:5] { x^2 };
    % transformed function g(x) = A*(x - H)^2 + K
    \addplot[cp line, samples=201, domain=-3:5] { __A__*((x - __H__)^2) + __K__ };
    % vertex of the transformed parabola
    \addplot[only marks, cp point] coordinates {(__H__, __K__)};
    \node[cp label, anchor=south west] at (axis cs:__H__, __K__) {__VERTEX_LABEL__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'A': {'type': 'number', 'default': 1, 'desc': 'vertical stretch/compression factor'},
            'H': {'type': 'number', 'default': 1, 'desc': 'horizontal shift of the parabola'},
            'K': {'type': 'number', 'default': 2, 'desc': 'vertical shift of the parabola'},
            'VERTEX_LABEL': {'type': 'label', 'default': '$(1,2)$', 'desc': 'label for the vertex of the transformed parabola'},
        },
    },
    {
        "id": 'unit_circle_reference_angle',
        "subject": 'Advanced Functions',
        "triggers": ['unit circle', 'terminal arm', 'reference angle'],
        "caption": 'Unit circle showing a terminal arm, its angle, and the corresponding reference angle.',
        "skeleton": r"""\begin{tikzpicture}
    \begin{scope}[scale=2]
    % define key points
    \coordinate (O) at (0,0);
    \coordinate (Xaxis) at (1,0);
    \coordinate (B) at ({cos(__THETA__)},{sin(__THETA__)});
    % draw the unit circle and axes
    \draw[cp line] (O) circle (1);
    \draw[cp axis] (-1.2,0) -- (1.2,0) node[cp label, anchor=west] {$x$};
    \draw[cp axis] (0,-1.2) -- (0,1.2) node[cp label, anchor=south] {$y$};
    % terminal arm
    \draw[cp line] (O) -- (B);
    % central angle \theta
    \pic[draw, cp axis, ->, angle radius=0.3cm] {angle=Xaxis--O--B};
    \node[cp label, anchor=west] at (0.18,0.38) {__THETA_LABEL__};
    % foot of the projection to create reference angle
    \coordinate (C) at ({cos(__THETA__)},0);
    % reference angle (between B, C, and Xaxis)
    \pic[draw, cp axis, ->, angle radius=0.2cm] {angle=B--C--Xaxis};
    \node[cp label, anchor=north east] at ({cos(__THETA__)+0.12},-0.18) {__REF_LABEL__};
    \end{scope}
\end{tikzpicture}""",
        "params": {
            'THETA': {'type': 'number', 'default': 135, 'desc': 'terminal angle in degrees'},
            'THETA_LABEL': {'type': 'label', 'default': '$135^{\\circ}$', 'desc': 'label for the terminal angle'},
            'REF_LABEL': {'type': 'label', 'default': '$45^{\\circ}$', 'desc': 'label for the reference angle'},
        },
    },
    {
        "id": 'piecewise_linear',
        "subject": 'Advanced Functions',
        "triggers": ['piecewise', 'piecewise linear', 'open and closed circles', 'open point', 'closed point', 'linear pieces', 'break point'],
        "caption": 'Piecewise linear function with distinct behaviour on either side of a break point.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-5, xmax=5,
    % The window contains both pieces end to end; a fixed -2..8 cut off steep
    % or negative pieces.
    ymin={min(0,__M1__*(-5)+__B1__,__M1__*(__C__)+__B1__,__M2__*(__C__)+__B2__,__M2__*5+__B2__)-1},
    ymax={max(0,__M1__*(-5)+__B1__,__M1__*(__C__)+__B1__,__M2__*(__C__)+__B2__,__M2__*5+__B2__)+1},
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-5,-4,-3,-2,-1,0,1,2,3,4,5},
    % Clip the pieces only; the break label sits just above the window.
    clip mode=individual,
]
    % first piece for x < C
    \addplot[cp line, domain=-5:__C__, samples=2] { __M1__*x + __B1__ };
    % open circle at the break point for the first piece
    \draw[cp line, fill=white] (axis cs:__C__, __M1__*__C__ + __B1__) circle[radius=1.5pt];
    % second piece for x >= C
    \addplot[cp line, domain=__C__:5, samples=2] { __M2__*x + __B2__ };
    % closed circle at the break point for the second piece
    \addplot[only marks, cp point] coordinates {(__C__, __M2__*__C__ + __B2__)};
    % label for the break point, above the window so it never overlaps the
    % x-axis tick labels or either piece
    \node[cp label, anchor=south] at (rel axis cs:{(__C__+5)/10},1) {__LABEL_BREAK__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'M1': {'type': 'number', 'default': 1, 'desc': 'slope of the first linear segment'},
            'B1': {'type': 'number', 'default': 2, 'desc': 'y-intercept of the first segment'},
            'M2': {'type': 'number', 'default': -1, 'desc': 'slope of the second linear segment'},
            'B2': {'type': 'number', 'default': 2, 'desc': 'y-intercept of the second segment'},
            'C': {'type': 'number', 'default': 1, 'desc': 'x-value at which the definition changes'},
            'LABEL_BREAK': {'type': 'label', 'default': '$x=1$', 'desc': 'label indicating the break point'},
        },
    },
    {
        "id": 'function_inverse_reflection',
        "subject": 'Advanced Functions',
        "triggers": ['inverse', 'reflection', 'exponential', 'logarithm', 'y=x'],
        "caption": 'A function and its inverse reflected across the line y = x.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-2, xmax=4,
    ymin=-2, ymax=4,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-2,-1,0,1,2,3,4}, ytick={-2,-1,0,1,2,3,4},
    samples=201,
    % Clip the curves but not the labels.
    clip mode=individual,
]
    % line y = x as the mirror, under both curves
    \addplot[cp dashed, domain=-2:4] { x };
    % exponential function f(x) = BASE^x
    \addplot[cp line, domain=-2:4] { pow(__BASE__, x) };
    % its inverse g(x) = log_BASE(x)
    \addplot[cp line, domain=0.01:4] { ln(x)/ln(__BASE__) };
    % Labels sit on each curve near the top/right edge for any base (fixed
    % coordinates floated off the curve when the base changed).
    \node[cp label, anchor=west, xshift=3pt] at (axis cs:{max(-1.9,min(3.9,ln(3.6)/ln(__BASE__)))},{pow(__BASE__,max(-1.9,min(3.9,ln(3.6)/ln(__BASE__))))}) {__F_LABEL__};
    \node[cp label, anchor=north] at (axis cs:3.6,{ln(3.6)/ln(__BASE__)}) {__INV_LABEL__};
    % A point and its mirror image: (0,1) on f and (1,0) on the inverse. The old
    % marked "intersection" (1,1) lies on neither curve.
    \draw[cp dashed, densely dotted] (axis cs:0,1) -- (axis cs:1,0);
    \addplot[only marks, cp point] coordinates {(0,1) (1,0)};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'BASE': {'type': 'number', 'default': 2, 'desc': 'base of the exponential function (and logarithm)'},
            'F_LABEL': {'type': 'label', 'default': '$f$', 'desc': 'symbolic label for the function'},
            'INV_LABEL': {'type': 'label', 'default': '$f^{-1}$', 'desc': 'symbolic label for the inverse function'},
        },
    },
    {
        "id": 'function_intersection_two_curves',
        "subject": 'Advanced Functions',
        "triggers": ['points of intersection', 'point of intersection', 'intersection for the functions', 'intersections of functions', 'two functions intersect'],
        "caption": 'Two function graphs with their intersection point indicated symbolically.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-1, xmax=3,
    ymin=0, ymax=9,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-1,0,1,2,3}, ytick={0,2,4,6,8},
    samples=100,
]
    \addplot[cp line, domain=-1:3] {2^(x+1)};
    \addplot[cp dashed, domain=-1:3] {4^x};
    \addplot[only marks, cp point] coordinates {(1,4)};
    \node[cp label, anchor=south west] at (axis cs:1,4) {$P$};
    \node[cp label, anchor=south east] at (axis cs:2.7,7.2) {$f(x)$};
    \node[cp label, anchor=north west] at (axis cs:1.55,6.2) {$g(x)$};
\end{axis}
\end{tikzpicture}""",
        "params": {},
    },
]
