"""Course Planner TikZ catalog - Data Management.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

EVENT_DESC = 'short outcome name from the question (plain words; maths in $...$)'
PROB_DESC = 'probability exactly as the question states it: a decimal such as 0.4, or a fraction written \\frac{4}{10} (no $ signs); ? when the student has to work it out,'

templates = [
    {
        "id": 'histogram',
        "subject": 'Data Management',
        "triggers": ['histogram', 'frequency', 'class interval', 'bars'],
        "caption": 'Histogram displaying frequencies across five class intervals.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=4cm,
    ybar,
    ymin=0,
    ymax=__YMAX__,
    xmin=0.2,
    xmax=5.8,
    xtick={1,2,3,4,5},
    xticklabels={__L1__,__L2__,__L3__,__L4__,__L5__},
    xlabel={Class Interval},
    ylabel={Frequency},
    % Class intervals are continuous, so each bar spans a full unit and touches.
    bar width=1,
    bar shift=0pt,
    ymajorgrids,
    axis lines=left,
]
\addplot+[cp fill, cp line] coordinates {
    (1, __F1__)
    (2, __F2__)
    (3, __F3__)
    (4, __F4__)
    (5, __F5__)
};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'YMAX': {'type': 'number', 'default': '10', 'desc': 'top frequency-axis bound above the tallest bar'},
            'L1': {'type': 'label', 'default': '1', 'desc': 'first class-interval label'},
            'L2': {'type': 'label', 'default': '2', 'desc': 'second class-interval label'},
            'L3': {'type': 'label', 'default': '3', 'desc': 'third class-interval label'},
            'L4': {'type': 'label', 'default': '4', 'desc': 'fourth class-interval label'},
            'L5': {'type': 'label', 'default': '5', 'desc': 'fifth class-interval label'},
            'F1': {'type': 'number', 'default': '2', 'desc': 'Height of the first bar (frequency)'},
            'F2': {'type': 'number', 'default': '5', 'desc': 'Height of the second bar (frequency)'},
            'F3': {'type': 'number', 'default': '3', 'desc': 'Height of the third bar (frequency)'},
            'F4': {'type': 'number', 'default': '4', 'desc': 'Height of the fourth bar (frequency)'},
            'F5': {'type': 'number', 'default': '1', 'desc': 'Height of the fifth bar (frequency)'},
        },
    },
    {
        "id": 'boxplot',
        "subject": 'Data Management',
        "triggers": ['box plot', 'box-and-whisker', 'five-number', 'quartile'],
        "caption": 'Box-and-whisker plot showing a five-number summary.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=3cm,
    boxplot/draw direction = x,
    xmin=__XMIN__,
    xmax=__XMAX__,
    xlabel={Value},
    ylabel={},
    ytick=\empty,
]
\addplot+[cp fill, cp line, boxplot prepared={
    lower whisker=__MIN__,
    lower quartile=__Q1__,
    median=__MED__,
    upper quartile=__Q3__,
    upper whisker=__MAX__
}] coordinates {};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'XMIN': {'type': 'number', 'default': '0', 'desc': 'axis minimum below the lower whisker'},
            'XMAX': {'type': 'number', 'default': '14', 'desc': 'axis maximum above the upper whisker'},
            'MIN': {'type': 'number', 'default': '4', 'desc': 'Minimum value'},
            'Q1': {'type': 'number', 'default': '6', 'desc': 'First quartile (lower quartile)'},
            'MED': {'type': 'number', 'default': '8', 'desc': 'Median value'},
            'Q3': {'type': 'number', 'default': '10', 'desc': 'Third quartile (upper quartile)'},
            'MAX': {'type': 'number', 'default': '12', 'desc': 'Maximum value'},
        },
    },
    {
        "id": 'normal_curve',
        "subject": 'Data Management',
        # Bare 'normal' hijacked calculus "normal line to the curve" questions
        # into a bell curve — require the statistics phrasing instead.
        "triggers": ['normal distribution', 'normally distributed', 'normal curve',
                     'normal model', 'bell curve', 'gaussian', 'standard deviation', 'sigma'],
        "caption": 'Normal distribution curve with a shaded region and sigma tick marks.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    % A wider axis over 3.5 sigma each side leaves about 1.2 cm per sigma, so
    % symbolic tick labels such as mu - 2 sigma no longer run together.
    width=8.5cm,
    height=4cm,
    domain=__MU__-3.5*__SIGMA__ : __MU__+3.5*__SIGMA__,
    xticklabel style={font=\scriptsize},
    samples=150,
    xlabel={$x$},
    ylabel={},
    axis lines=left,
    ytick=\empty,
    scaled y ticks=false,
    xtick={__MU__-2*__SIGMA__, __MU__-__SIGMA__, __MU__, __MU__+__SIGMA__, __MU__+2*__SIGMA__},
    xticklabels={__T1__,__T2__,__T3__,__T4__,__T5__},
    declare function={gauss(\x)=1/(sqrt(2*pi*(__SIGMA__)^2)) * exp(-((\x-(__MU__))^2)/(2*(__SIGMA__)^2));},
]
% shaded region first, so the fill cannot paint over the curve's stroke
\addplot[cp fill, draw=none, mark=none, domain=__SHADE_L__:__SHADE_R__] {gauss(x)} \closedcycle;
% density curve (no plot-cycle marks; a smooth line, not a band of dots)
\addplot[cp line, mark=none, smooth] {gauss(x)};
% vertical line at the mean
\draw[cp dashed] (axis cs:__MU__,0) -- (axis cs:__MU__,{gauss(__MU__)});
\end{axis}
\end{tikzpicture}""",
        "params": {
            'MU': {'type': 'number', 'default': '0', 'desc': 'Mean of the normal distribution'},
            'SIGMA': {'type': 'number', 'default': '1', 'desc': 'Standard deviation of the normal distribution'},
            'SHADE_L': {'type': 'number', 'default': '-0.5', 'desc': 'Left boundary of the shaded region'},
            'SHADE_R': {'type': 'number', 'default': '0.5', 'desc': 'Right boundary of the shaded region'},
            'T1': {'type': 'label', 'default': '$\\mu-2\\sigma$', 'desc': 'label at mean minus two standard deviations; T1-T5 share one style: all numbers when the question gives numeric values, otherwise all symbols'},
            'T2': {'type': 'label', 'default': '$\\mu-\\sigma$', 'desc': 'label at mean minus one standard deviation'},
            'T3': {'type': 'label', 'default': '$\\mu$', 'desc': 'label at the mean'},
            'T4': {'type': 'label', 'default': '$\\mu+\\sigma$', 'desc': 'label at mean plus one standard deviation'},
            'T5': {'type': 'label', 'default': '$\\mu+2\\sigma$', 'desc': 'label at mean plus two standard deviations'},
        },
    },
    {
        "id": 'probability_tree',
        "subject": 'Data Management',
        "triggers": ['probability tree', 'tree diagram', 'two-stage', 'defective', 'without replacement', 'first branch'],
        "caption": 'Two-stage probability tree with each branch labelled with its outcome and probability.',
        "skeleton": r"""\begin{tikzpicture}
\coordinate (O) at (0,0);
\coordinate (A) at (2,1);
\coordinate (B) at (2,-1);
\coordinate (A1) at (4,1.5);
\coordinate (A2) at (4,0.5);
\coordinate (B1) at (4,-0.5);
\coordinate (B2) at (4,-1.5);
\draw[cp line] (O) -- (A) node[midway, above left=2pt]{$__P1__$};
\draw[cp line] (O) -- (B) node[midway, below left=2pt]{$__P2__$};
\draw[cp line] (A) -- (A1) node[midway, above left=2pt]{$__P3__$};
\draw[cp line] (A) -- (A2) node[midway, below left=2pt]{$__P4__$};
\draw[cp line] (B) -- (B1) node[midway, above left=2pt]{$__P5__$};
\draw[cp line] (B) -- (B2) node[midway, below left=2pt]{$__P6__$};
\node[cp point] at (O) {};
% each branch's event where it ends (the leaves had fixed placeholder names
% whatever the question): first stage above/below its node, clear of the branches
\node[cp point, label=above:{__E1__}] at (A) {};
\node[cp point, label=below:{__E2__}] at (B) {};
\node[cp point, label=right:{__L1__}] at (A1) {};
\node[cp point, label=right:{__L2__}] at (A2) {};
\node[cp point, label=right:{__L3__}] at (B1) {};
\node[cp point, label=right:{__L4__}] at (B2) {};
\end{tikzpicture}""",
        "params": {
            # Labels, not numbers: a number field kept only the first number of
            # "4/10" (a without-replacement tree printed 4, 3, 6 ...). A branch
            # shows only a probability the question states (3/9 on the second
            # draw is the student's step); others show ?.
            'P1': {'type': 'label', 'default': '0.5', 'desc': PROB_DESC + ' on the first branch from the root', 'stated_only': True},
            'P2': {'type': 'label', 'default': '0.5', 'desc': PROB_DESC + ' on the second branch from the root', 'stated_only': True},
            'P3': {'type': 'label', 'default': '0.6', 'desc': PROB_DESC + ' on the first sub-branch of branch 1', 'stated_only': True},
            'P4': {'type': 'label', 'default': '0.4', 'desc': PROB_DESC + ' on the second sub-branch of branch 1', 'stated_only': True},
            'P5': {'type': 'label', 'default': '0.7', 'desc': PROB_DESC + ' on the first sub-branch of branch 2', 'stated_only': True},
            'P6': {'type': 'label', 'default': '0.3', 'desc': PROB_DESC + ' on the second sub-branch of branch 2', 'stated_only': True},
            'E1': {'type': 'label', 'default': 'A', 'desc': EVENT_DESC + ' of the first branch from the root, e.g. Red'},
            'E2': {'type': 'label', 'default': 'B', 'desc': EVENT_DESC + ' of the second branch from the root, e.g. Blue'},
            'L1': {'type': 'label', 'default': 'A', 'desc': EVENT_DESC + ' of the first sub-branch of branch 1 (the second-stage outcome), e.g. Red'},
            'L2': {'type': 'label', 'default': 'B', 'desc': EVENT_DESC + ' of the second sub-branch of branch 1, e.g. Blue'},
            'L3': {'type': 'label', 'default': 'A', 'desc': EVENT_DESC + ' of the first sub-branch of branch 2, e.g. Red'},
            'L4': {'type': 'label', 'default': 'B', 'desc': EVENT_DESC + ' of the second sub-branch of branch 2, e.g. Blue'},
        },
    },
    {
        "id": 'venn_two',
        "subject": 'Data Management',
        "triggers": ['two-set venn', 'venn diagram', 'overlap'],
        "caption": 'Two-set Venn diagram inside a universal rectangle with region values, including the region outside both sets.',
        "skeleton": r"""\begin{tikzpicture}
\coordinate (L) at (0,0);
\coordinate (R) at (2,0);
% the universal set: its rectangle, name, and the value outside both circles
% (it had none, so "how many play neither" had no region to mark)
\draw[cp line] (-2.3,-2.1) rectangle (4.3,2.3);
\node[cp label,anchor=north west] at (-2.3,2.3) {__LU__};
\node[cp label] at (3.6,-1.65) {__VN__};
\draw[cp line] (L) circle (1.5cm);
\draw[cp line] (R) circle (1.5cm);
% set names above their circles, which leaves each about 2 cm (in a corner a
% long name ran past the rectangle)
\node[cp label,anchor=south] at (0,1.6) {__LA__};
\node[cp label,anchor=south] at (2,1.6) {__LB__};
\node[cp label] at (-0.8,0) {__VA__};
\node[cp label] at (1,0) {__VAB__};
\node[cp label] at (2.8,0) {__VB__};
\end{tikzpicture}""",
        "params": {
            'LA': {'type': 'label', 'default': '$A$', 'desc': 'Label of the left set'},
            'LB': {'type': 'label', 'default': '$B$', 'desc': 'Label of the right set'},
            # a region shows only a count the question states (13 from 18 - 5 was
            # the answer to "how many play only soccer"); others show ?
            'VA': {'type': 'label', 'default': '$x$', 'desc': 'Value in the left-only region: the count the question states, else ?', 'stated_only': True},
            'VAB': {'type': 'label', 'default': '$y$', 'desc': 'Value in the intersection region: the count the question states, else ?', 'stated_only': True},
            'VB': {'type': 'label', 'default': '$z$', 'desc': 'Value in the right-only region: the count the question states, else ?', 'stated_only': True},
            'LU': {'type': 'label', 'default': '$U$', 'desc': 'Label of the universal set (the rectangle), e.g. $U$ or $S$'},
            # answer-guarded without keep_if_given: "neither" is usually the value
            # asked for, and it can equal a stated number (30 students, 18, 12 and
            # 5 in both leave 5 in neither)
            'VN': {'type': 'label', 'default': '', 'desc': 'Value outside both circles (in neither set): the number if given, ? if the question asks for it, otherwise empty', 'answer_safe': False},
        },
    },
    {
        "id": 'venn_three',
        "subject": 'Data Management',
        "triggers": ['three-set venn', 'venn diagram', 'triple overlap'],
        "caption": 'Three-set Venn diagram inside a universal rectangle with labelled regions.',
        "skeleton": r"""\begin{tikzpicture}
\coordinate (A) at (-1,0.6);
\coordinate (B) at (1,0.6);
\coordinate (C) at (0,-0.8);
% the universal set: its rectangle, name, and the value outside all circles
\draw[cp line] (-4,-2.9) rectangle (4,2.7);
\node[cp label,anchor=north west] at (-4,2.7) {__LU__};
\node[cp label] at (-3.3,-2.45) {__V8__};
\draw[cp line] (A) circle (1.6cm);
\draw[cp line] (B) circle (1.6cm);
\draw[cp line] (C) circle (1.6cm);
% set names just outside their circles, growing away from them
\node[cp label,anchor=south east] at (-2.25,1.7) {__LA__};
\node[cp label,anchor=south west] at (2.25,1.7) {__LB__};
\node[cp label,anchor=north west] at (1.2,-2.2) {__LC__};
\node[cp label] at (-2.2,0.6) {__V1__};
\node[cp label] at (2.2,0.6) {__V2__};
\node[cp label] at (0,-2.0) {__V3__};
\node[cp label] at (0,1.2) {__V4__};
\node[cp label] at (-0.9,-0.2) {__V5__};
\node[cp label] at (0.9,-0.2) {__V6__};
\node[cp label] at (0,0) {__V7__};
\end{tikzpicture}""",
        "params": {
            'LA': {'type': 'label', 'default': '$A$', 'desc': 'Label of the first set'},
            'LB': {'type': 'label', 'default': '$B$', 'desc': 'Label of the second set'},
            'LC': {'type': 'label', 'default': '$C$', 'desc': 'Label of the third set'},
            'V1': {'type': 'label', 'default': '?', 'desc': 'Value in the region only in set A', 'answer_safe': False, 'keep_if_given': True},
            'V2': {'type': 'label', 'default': '?', 'desc': 'Value in the region only in set B', 'answer_safe': False, 'keep_if_given': True},
            'V3': {'type': 'label', 'default': '?', 'desc': 'Value in the region only in set C', 'answer_safe': False, 'keep_if_given': True},
            'V4': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to A and B only', 'answer_safe': False, 'keep_if_given': True},
            'V5': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to A and C only', 'answer_safe': False, 'keep_if_given': True},
            'V6': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to B and C only', 'answer_safe': False, 'keep_if_given': True},
            'V7': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to all three sets', 'answer_safe': False, 'keep_if_given': True},
            'LU': {'type': 'label', 'default': '$U$', 'desc': 'Label of the universal set (the rectangle), e.g. $U$ or $S$'},
            'V8': {'type': 'label', 'default': '', 'desc': 'Value outside all three circles: the number if given, ? if the question asks for it, otherwise empty', 'answer_safe': False},
        },
    },
    {
        "id": 'scatter_fit',
        "subject": 'Data Management',
        "triggers": ['scatter plot', 'line of best fit', 'trend line', 'correlation coefficient', 'pearson correlation', 'correlation'],
        "caption": 'Scatter plot with a line of best fit drawn through the data points.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=4cm,
    xmin=__XMIN__,
    xmax=__XMAX__,
    ymin=__YMIN__,
    ymax=__YMAX__,
    xlabel={__XLABEL__},
    ylabel={__YLABEL__},
    xmajorgrids,
    ymajorgrids,
    axis lines=left,
]
% scatter points
\addplot[only marks, mark=*, cp line] coordinates {
    (__X1__, __Y1__)
    (__X2__, __Y2__)
    (__X3__, __Y3__)
    (__X4__, __Y4__)
    (__X5__, __Y5__)
};
% line of best fit
\addplot[cp line, domain=__XMIN__:__XMAX__] {__M__ * x + __B__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'XMIN': {'type': 'number', 'default': '0', 'desc': 'left axis bound'},
            'XMAX': {'type': 'number', 'default': '6', 'desc': 'right axis bound'},
            'YMIN': {'type': 'number', 'default': '0', 'desc': 'bottom axis bound'},
            'YMAX': {'type': 'number', 'default': '10', 'desc': 'top axis bound'},
            'XLABEL': {'type': 'label', 'default': '$x$', 'desc': 'short horizontal-axis label from the problem'},
            'YLABEL': {'type': 'label', 'default': '$y$', 'desc': 'short vertical-axis label from the problem'},
            'X1': {'type': 'number', 'default': '1', 'desc': 'x-coordinate of the first data point'},
            'Y1': {'type': 'number', 'default': '2', 'desc': 'y-coordinate of the first data point'},
            'X2': {'type': 'number', 'default': '2', 'desc': 'x-coordinate of the second data point'},
            'Y2': {'type': 'number', 'default': '4', 'desc': 'y-coordinate of the second data point'},
            'X3': {'type': 'number', 'default': '3', 'desc': 'x-coordinate of the third data point'},
            'Y3': {'type': 'number', 'default': '6', 'desc': 'y-coordinate of the third data point'},
            'X4': {'type': 'number', 'default': '4', 'desc': 'x-coordinate of the fourth data point'},
            'Y4': {'type': 'number', 'default': '8', 'desc': 'y-coordinate of the fourth data point'},
            'X5': {'type': 'number', 'default': '5', 'desc': 'x-coordinate of the fifth data point'},
            'Y5': {'type': 'number', 'default': '9', 'desc': 'y-coordinate of the fifth data point'},
            'M': {'type': 'number', 'default': '1.5', 'desc': 'Slope of the best-fit line'},
            'B': {'type': 'number', 'default': '0.5', 'desc': 'Intercept of the best-fit line'},
        },
    },
    {
        "id": 'complete_graph_sketch',
        "subject": 'Data Management',
        "triggers": ['complete graph', 'k_n', 'k_7', 'maximum number of edges', 'every pair of distinct vertices'],
        "caption": 'Complete graph sketch showing every pair of vertices connected.',
        "skeleton": r"""\begin{tikzpicture}[scale=0.9]
\foreach \name/\ang in {A/90,B/18,C/-54,D/-126,E/162} {
  \coordinate (\name) at (\ang:1.75);
  \node[cp point,label=\ang:{$\name$}] at (\name) {};
}
\foreach \u/\v in {A/B,A/C,A/D,A/E,B/C,B/D,B/E,C/D,C/E,D/E} {
  \draw[cp line] (\u) -- (\v);
}
\node[cp label] at (0,-2.35) {$__LABEL__$};
\end{tikzpicture}""",
        "params": {
            'LABEL': {'type': 'label', 'default': 'K_n\\text{: every pair connected}', 'desc': 'short math label such as K_5; wrap any words in \\text{...} (the label is typeset in math mode, which drops plain spaces)'},
        },
    },
    {
        "id": 'network_graph',
        "subject": 'Data Management',
        "triggers": [
            'weighted graph', 'vertices', 'edges', 'degree of vertex', 'network',
            'minimum spanning tree', 'minimum total cost', 'traveling salesman',
            'travelling salesman', 'visit each location exactly once', 'starting and ending',
            'central depot', 'depot', 'hamiltonian', 'euler circuit',
        ],
        "caption": 'Network graph with labelled vertices and weighted edges AB, AC, BC, BD, CE, DE, and AE when given.',
        "skeleton": r"""\begin{tikzpicture}[scale=0.9]
  \coordinate (A) at (0,1.5);
  \coordinate (B) at (2.2,2.1);
  \coordinate (C) at (4.2,1.3);
  \coordinate (D) at (3.1,-0.8);
  \coordinate (E) at (0.9,-0.7);
  % Each vertex label points where no edge leaves that vertex (above D and E
  % the edges ran through them).
  \foreach \p/\q in {A/above left,B/above,C/right,D/below right,E/below left} {\node[cp point,label=\q:{$\p$}] at (\p) {};}
  \draw[cp line] (A)--(B) node[midway,above] {$__WAB__$};
  \draw[cp line] (A)--(C) node[pos=.3,below] {$__WAC__$};
  \draw[cp line] (B)--(C) node[midway,above] {$__WBC__$};
  % AC crosses BD a quarter of the way down BD and CE crosses it at 0.58, so
  % each weight sits where its edge is clear of every crossing (AC at 0.3).
  \draw[cp line] (B)--(D) node[pos=.8,right] {$__WBD__$};
  \draw[cp line] (C)--(E) node[pos=.25,above] {$__WCE__$};
  \draw[cp line] (D)--(E) node[midway,below] {$__WDE__$};
  % AE only when the question has it: an empty weight is an empty list, so
  % nothing is drawn
  \foreach \w in {__WAE__} {\draw[cp line] (A)--(E) node[midway,left] {$\w$};}
\end{tikzpicture}""",
        "params": {
            'WAB': {'type': 'label', 'default': '4', 'desc': 'weight label for edge AB, if given'},
            'WAC': {'type': 'label', 'default': '2', 'desc': 'weight label for edge AC, if given'},
            'WBC': {'type': 'label', 'default': '1', 'desc': 'weight label for edge BC, if given'},
            'WBD': {'type': 'label', 'default': '5', 'desc': 'weight label for edge BD, if given'},
            'WCE': {'type': 'label', 'default': '10', 'desc': 'weight label for edge CE, if given'},
            'WDE': {'type': 'label', 'default': '2', 'desc': 'weight label for edge DE, if given'},
            'WAE': {'type': 'label', 'default': '', 'desc': 'weight label for edge AE; leave empty unless the question has an edge AE (an empty value draws no edge)'},
        },
    },
    {
        "id": 'ogive',
        "subject": 'Data Management',
        "triggers": ['ogive', 'cumulative frequency', 's-curve'],
        "caption": 'Cumulative-frequency ogive plotted through ordered points.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=4cm,
    xmin=__XMIN__,
    xmax=__XMAX__,
    ymin=0,
    ymax=__YMAX__,
    xlabel={$x$},
    ylabel={Cumulative Frequency},
    xmajorgrids,
    ymajorgrids,
    axis lines=left,
]
\addplot[cp line, smooth] coordinates {
    (__X1__, __C1__)
    (__X2__, __C2__)
    (__X3__, __C3__)
    (__X4__, __C4__)
    (__X5__, __C5__)
};
\addplot[only marks, mark=*, cp line] coordinates {
    (__X1__, __C1__)
    (__X2__, __C2__)
    (__X3__, __C3__)
    (__X4__, __C4__)
    (__X5__, __C5__)
};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'XMIN': {'type': 'number', 'default': '0', 'desc': 'left axis bound at or below the first upper-class boundary'},
            'XMAX': {'type': 'number', 'default': '6', 'desc': 'right axis bound above the last upper-class boundary'},
            'YMAX': {'type': 'number', 'default': '10', 'desc': 'top cumulative-frequency bound above C5'},
            'X1': {'type': 'number', 'default': '1', 'desc': 'first upper-class boundary'},
            'C1': {'type': 'number', 'default': '2', 'desc': 'Cumulative frequency at the first point'},
            'X2': {'type': 'number', 'default': '2', 'desc': 'second upper-class boundary'},
            'C2': {'type': 'number', 'default': '5', 'desc': 'Cumulative frequency at the second point'},
            'X3': {'type': 'number', 'default': '3', 'desc': 'third upper-class boundary'},
            'C3': {'type': 'number', 'default': '7', 'desc': 'Cumulative frequency at the third point'},
            'X4': {'type': 'number', 'default': '4', 'desc': 'fourth upper-class boundary'},
            'C4': {'type': 'number', 'default': '9', 'desc': 'Cumulative frequency at the fourth point'},
            'X5': {'type': 'number', 'default': '5', 'desc': 'fifth upper-class boundary'},
            'C5': {'type': 'number', 'default': '10', 'desc': 'Cumulative frequency at the fifth point'},
        },
    },
    {
        "id": 'bar_chart',
        "subject": 'Data Management',
        "triggers": ['bar chart', 'categorical', 'counts'],
        "caption": 'Simple bar chart representing categorical counts.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=4cm,
    ybar,
    ymin=0,
    % the scale follows the counts (a fixed 10 cut off any taller bar), and the
    % categories are the question's (placeholder names were shown)
    ymax={1.15*max(__D1__,__D2__,__D3__,__D4__,1)},
    xmin=0.5,
    xmax=4.5,
    xtick={1,2,3,4},
    xticklabels={{__C1__},{__C2__},{__C3__},{__C4__}},
    xlabel={__XLABEL__},
    ylabel={__YLABEL__},
    bar width=0.6cm,
    ymajorgrids,
    axis lines=left,
    enlarge x limits=0.15,
]
\addplot+[cp fill, cp line] coordinates {
    (1, __D1__)
    (2, __D2__)
    (3, __D3__)
    (4, __D4__)
};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'D1': {'type': 'number', 'default': '3', 'desc': 'Count for category 1'},
            'D2': {'type': 'number', 'default': '5', 'desc': 'Count for category 2'},
            'D3': {'type': 'number', 'default': '2', 'desc': 'Count for category 3'},
            'D4': {'type': 'number', 'default': '7', 'desc': 'Count for category 4'},
            'C1': {'type': 'label', 'default': 'A', 'desc': 'name of category 1 from the question, e.g. Apples'},
            'C2': {'type': 'label', 'default': 'B', 'desc': 'name of category 2 from the question'},
            'C3': {'type': 'label', 'default': 'C', 'desc': 'name of category 3 from the question'},
            'C4': {'type': 'label', 'default': 'D', 'desc': 'name of category 4 from the question'},
            'XLABEL': {'type': 'label', 'default': 'Category', 'desc': 'short horizontal-axis title from the question, e.g. Fruit'},
            'YLABEL': {'type': 'label', 'default': 'Count', 'desc': 'short vertical-axis title, e.g. Number of students'},
        },
    },
]
