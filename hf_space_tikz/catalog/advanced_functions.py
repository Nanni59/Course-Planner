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
        "triggers": ['rational', 'rational function', 'vertical asymptote', 'horizontal asymptote'],
        "caption": 'Rational function with a vertical and a horizontal asymptote.',
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
    % rational function f(x) = A/(x - H) + K
    \addplot[cp line, samples=201, domain=-4.8:4.8] { __A__/(x - __H__) + __K__ };
    % vertical asymptote x = H
    \addplot[cp dashed] coordinates {(__H__,-5) (__H__,5)};
    % horizontal asymptote y = K
    \addplot[cp dashed] coordinates {(-5,__K__) (5,__K__)};
    % labels for asymptotes
    \node[cp label, anchor=south west] at (axis cs:__H__,5) {$x=__LABEL_H__$};
    \node[cp label, anchor=north east] at (axis cs:-5,__K__) {$y=__LABEL_K__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'A': {'type': 'number', 'default': 1, 'desc': 'numerator coefficient in the rational function'},
            'H': {'type': 'number', 'default': 1, 'desc': 'x-value of the vertical asymptote'},
            'K': {'type': 'number', 'default': 0, 'desc': 'y-value of the horizontal asymptote'},
            'LABEL_H': {'type': 'label', 'default': '1', 'desc': 'label for the vertical asymptote'},
            'LABEL_K': {'type': 'label', 'default': '0', 'desc': 'label for the horizontal asymptote'},
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
    ymin=-1, ymax=6,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-2,-1,0,1,2,3}, ytick={0,1,2,3,4,5},
]
    % exponential function f(x) = A*B^x + K
    \addplot[cp line, samples=201, domain=-2:3] { __A__*(pow(__B__, x)) + __K__ };
    % horizontal asymptote y = K
    \addplot[cp dashed] coordinates {(-2,__K__) (3,__K__)};
    % label for asymptote
    \node[cp label, anchor=south east] at (axis cs:-2,__K__) {$y=__LABEL_K__$};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'A': {'type': 'number', 'default': 1, 'desc': 'leading coefficient of the exponential function'},
            'B': {'type': 'number', 'default': 2, 'desc': 'base of the exponential function'},
            'K': {'type': 'number', 'default': 0, 'desc': 'vertical shift (horizontal asymptote)'},
            'LABEL_K': {'type': 'label', 'default': '0', 'desc': 'label for the horizontal asymptote'},
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
        "triggers": ['sinusoid', 'amplitude', 'period', 'midline', 'sine'],
        "caption": 'Sinusoidal function marking its amplitude, period, and midline.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=0, xmax=6.28,
    ymin=-4, ymax=4,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={0,1.57,3.14,4.71,6.28},
    xticklabels={$0$,$\frac{\pi}{2}$,$\pi$,$\frac{3\pi}{2}$,$2\pi$},
    ytick={-4,-2,0,2,4}, yticklabels={-4,-2,0,2,4},
]
    % sinusoidal function f(x) = A*sin(x) + M
    \addplot[cp line, samples=201, domain=0:6.28] { __AMPLITUDE_VALUE__*sin(deg(x)) + __MIDLINE_VALUE__ };
    % midline
    \addplot[cp dashed] coordinates {(0,__MIDLINE_VALUE__) (6.28,__MIDLINE_VALUE__)};
    \node[cp label, anchor=south east] at (axis cs:0,__MIDLINE_VALUE__) {__MIDLINE_LABEL__};
    % amplitude arrow
    \draw[cp axis,<->] (axis cs:6.28,__MIDLINE_VALUE__) -- (axis cs:6.28,__MIDLINE_VALUE__ + __AMPLITUDE_VALUE__) node[midway, anchor=west] {__AMPLITUDE_LABEL__};
    % period arrow from 0 to 2*pi
    \draw[cp axis,<->] (axis cs:0, __MIDLINE_VALUE__ - __AMPLITUDE_VALUE__/2) -- (axis cs:6.28, __MIDLINE_VALUE__ - __AMPLITUDE_VALUE__/2) node[midway, anchor=south] {__PERIOD_LABEL__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'AMPLITUDE_VALUE': {'type': 'number', 'default': 2, 'desc': 'amplitude of the sinusoid'},
            'MIDLINE_VALUE': {'type': 'number', 'default': 0, 'desc': 'vertical midline of the sinusoid'},
            'AMPLITUDE_LABEL': {'type': 'label', 'default': '$A$', 'desc': 'label for the amplitude arrow'},
            'MIDLINE_LABEL': {'type': 'label', 'default': 'midline', 'desc': 'label for the midline'},
            'PERIOD_LABEL': {'type': 'label', 'default': '$2\\pi$', 'desc': 'label for the period arrow'},
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
    % reciprocal function f(x) = COEFF/x
    \addplot[cp line, samples=201, domain=-4.8:4.8] { __COEFF__/x };
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
    \node[cp label, anchor=north east] at (0.3,0.15) {__THETA_LABEL__};
    % foot of the projection to create reference angle
    \coordinate (C) at ({cos(__THETA__)},0);
    % reference angle (between B, C, and Xaxis)
    \pic[draw, cp axis, ->, angle radius=0.2cm] {angle=B--C--Xaxis};
    \node[cp label, anchor=south west] at ({cos(__THETA__)/2},0) {__REF_LABEL__};
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
        "triggers": ['piecewise', 'function', 'linear', 'open and closed circles'],
        "caption": 'Piecewise linear function with distinct behaviour on either side of a break point.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm, height=4cm,
    xmin=-5, xmax=5,
    ymin=-2, ymax=8,
    axis lines=middle,
    axis line style=cp axis,
    xlabel={$x$}, ylabel={$y$},
    xtick={-5,-4,-3,-2,-1,0,1,2,3,4,5}, ytick={-2,0,2,4,6,8},
]
    % first piece for x < C
    \addplot[cp line, domain=-5:__C__, samples=2] { __M1__*x + __B1__ };
    % open circle at the break point for the first piece
    \draw[cp line, fill=white] (axis cs:__C__, __M1__*__C__ + __B1__) circle[radius=1.5pt];
    % second piece for x >= C
    \addplot[cp line, domain=__C__:5, samples=2] { __M2__*x + __B2__ };
    % closed circle at the break point for the second piece
    \addplot[only marks, cp point] coordinates {(__C__, __M2__*__C__ + __B2__)};
    % label for the break point on the x-axis
    \node[cp label, anchor=south] at (axis cs:__C__, -2) {__LABEL_BREAK__};
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
]
    % exponential function f(x) = BASE^x
    \addplot[cp line, domain=-2:3] { pow(__BASE__, x) };
    % its inverse g(x) = log_BASE(x)
    \addplot[cp line, domain=0.1:4] { ln(x)/ln(__BASE__) };
    % line y = x as the mirror
    \addplot[cp dashed, domain=-2:4] { x };
    % intersection point (1,1)
    \addplot[only marks, cp point] coordinates {(1,1)};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'BASE': {'type': 'number', 'default': 2, 'desc': 'base of the exponential function (and logarithm)'},
        },
    },
]
