"""Course Planner TikZ catalog - Data Management.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

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
    ymax=10,
    xmin=0.5,
    xmax=5.5,
    xtick={1,2,3,4,5},
    xticklabels={1,2,3,4,5},
    xlabel={Class Interval},
    ylabel={Frequency},
    bar width=0.6cm,
    ymajorgrids,
    axis lines=left,
    enlarge x limits=0.15,
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
    xmin=0,
    xmax=14,
    xlabel={Value},
    ylabel={},
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
        "triggers": ['normal', 'bell curve', 'gaussian', 'sigma'],
        "caption": 'Normal distribution curve with a shaded region and sigma tick marks.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=4cm,
    domain=__MU__-4*__SIGMA__ : __MU__+4*__SIGMA__,
    samples=150,
    xlabel={$x$},
    ylabel={},
    axis lines=left,
    yticklabels={\,},
    xtick={__MU__-2*__SIGMA__, __MU__-__SIGMA__, __MU__, __MU__+__SIGMA__, __MU__+2*__SIGMA__},
    xticklabels={$\mu-2\sigma$, $\mu-\sigma$, $\mu$, $\mu+\sigma$, $\mu+2\sigma$},
    declare function={gauss(\x)=1/(sqrt(2*pi*(__SIGMA__)^2)) * exp(-((\x-(__MU__))^2)/(2*(__SIGMA__)^2));},
]
% density curve
\addplot+[cp line] {gauss(x)};
% shaded region under the curve
\addplot+[cp fill, draw=none, domain=__SHADE_L__:__SHADE_R__] {gauss(x)} \closedcycle;
% vertical line at the mean
\draw[cp dashed] (axis cs:__MU__,0) -- (axis cs:__MU__,{gauss(__MU__)});
\end{axis}
\end{tikzpicture}""",
        "params": {
            'MU': {'type': 'number', 'default': '0', 'desc': 'Mean of the normal distribution'},
            'SIGMA': {'type': 'number', 'default': '1', 'desc': 'Standard deviation of the normal distribution'},
            'SHADE_L': {'type': 'number', 'default': '-0.5', 'desc': 'Left boundary of the shaded region'},
            'SHADE_R': {'type': 'number', 'default': '0.5', 'desc': 'Right boundary of the shaded region'},
        },
    },
    {
        "id": 'probability_tree',
        "subject": 'Data Management',
        "triggers": ['probability tree', 'tree diagram', 'two-stage'],
        "caption": 'Two-stage probability tree with branch probabilities labelled.',
        "skeleton": r"""\begin{tikzpicture}
\coordinate (O) at (0,0);
\coordinate (A) at (2,1);
\coordinate (B) at (2,-1);
\coordinate (A1) at (4,1.5);
\coordinate (A2) at (4,0.5);
\coordinate (B1) at (4,-0.5);
\coordinate (B2) at (4,-1.5);
\draw[cp line] (O) -- (A) node[midway, above left=2pt]{__P1__};
\draw[cp line] (O) -- (B) node[midway, below left=2pt]{__P2__};
\draw[cp line] (A) -- (A1) node[midway, above left=2pt]{__P3__};
\draw[cp line] (A) -- (A2) node[midway, below left=2pt]{__P4__};
\draw[cp line] (B) -- (B1) node[midway, above left=2pt]{__P5__};
\draw[cp line] (B) -- (B2) node[midway, below left=2pt]{__P6__};
\node[cp point] at (O) {};
\node[cp point, label=right:{Outcome 1}] at (A1) {};
\node[cp point, label=right:{Outcome 2}] at (A2) {};
\node[cp point, label=right:{Outcome 3}] at (B1) {};
\node[cp point, label=right:{Outcome 4}] at (B2) {};
\end{tikzpicture}""",
        "params": {
            'P1': {'type': 'number', 'default': '0.5', 'desc': 'Probability on the first branch from the root'},
            'P2': {'type': 'number', 'default': '0.5', 'desc': 'Probability on the second branch from the root'},
            'P3': {'type': 'number', 'default': '0.6', 'desc': 'Probability on the first sub-branch of branch 1'},
            'P4': {'type': 'number', 'default': '0.4', 'desc': 'Probability on the second sub-branch of branch 1'},
            'P5': {'type': 'number', 'default': '0.7', 'desc': 'Probability on the first sub-branch of branch 2'},
            'P6': {'type': 'number', 'default': '0.3', 'desc': 'Probability on the second sub-branch of branch 2'},
        },
    },
    {
        "id": 'venn_two',
        "subject": 'Data Management',
        "triggers": ['two-set venn', 'venn diagram', 'overlap'],
        "caption": 'Two-set Venn diagram with region values.',
        "skeleton": r"""\begin{tikzpicture}
\coordinate (L) at (0,0);
\coordinate (R) at (2,0);
\draw[cp line] (L) circle (1.5cm);
\draw[cp line] (R) circle (1.5cm);
\node[cp label] at (-1.6,1.6) {__LA__};
\node[cp label] at (3.6,1.6) {__LB__};
\node[cp label] at (-0.8,0) {__VA__};
\node[cp label] at (1,0) {__VAB__};
\node[cp label] at (2.8,0) {__VB__};
\end{tikzpicture}""",
        "params": {
            'LA': {'type': 'label', 'default': '$A$', 'desc': 'Label of the left set'},
            'LB': {'type': 'label', 'default': '$B$', 'desc': 'Label of the right set'},
            'VA': {'type': 'label', 'default': '$x$', 'desc': 'Value in the left-only region'},
            'VAB': {'type': 'label', 'default': '$y$', 'desc': 'Value in the intersection region'},
            'VB': {'type': 'label', 'default': '$z$', 'desc': 'Value in the right-only region'},
        },
    },
    {
        "id": 'venn_three',
        "subject": 'Data Management',
        "triggers": ['three-set venn', 'venn diagram', 'triple overlap'],
        "caption": 'Three-set Venn diagram with labelled regions.',
        "skeleton": r"""\begin{tikzpicture}
\coordinate (A) at (-1,0.6);
\coordinate (B) at (1,0.6);
\coordinate (C) at (0,-0.8);
\draw[cp line] (A) circle (1.6cm);
\draw[cp line] (B) circle (1.6cm);
\draw[cp line] (C) circle (1.6cm);
\node[cp label] at (-3.0,1.6) {__LA__};
\node[cp label] at (3.0,1.6) {__LB__};
\node[cp label] at (0,-2.4) {__LC__};
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
            'V1': {'type': 'label', 'default': '?', 'desc': 'Value in the region only in set A', 'answer_safe': False},
            'V2': {'type': 'label', 'default': '?', 'desc': 'Value in the region only in set B', 'answer_safe': False},
            'V3': {'type': 'label', 'default': '?', 'desc': 'Value in the region only in set C', 'answer_safe': False},
            'V4': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to A and B only', 'answer_safe': False},
            'V5': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to A and C only', 'answer_safe': False},
            'V6': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to B and C only', 'answer_safe': False},
            'V7': {'type': 'label', 'default': '?', 'desc': 'Value in the region common to all three sets', 'answer_safe': False},
        },
    },
    {
        "id": 'scatter_fit',
        "subject": 'Data Management',
        "triggers": ['scatter plot', 'line of best fit', 'trend line'],
        "caption": 'Scatter plot with a line of best fit drawn through the data points.',
        "skeleton": r"""\begin{tikzpicture}
\begin{axis}[
    width=7cm,
    height=4cm,
    xmin=0,
    xmax=5,
    ymin=0,
    ymax=10,
    xlabel={$x$},
    ylabel={$y$},
    xmajorgrids,
    ymajorgrids,
    axis lines=left,
]
% scatter points
\addplot[only marks, mark=*, cp line] coordinates {
    (1, __Y1__)
    (2, __Y2__)
    (3, __Y3__)
    (4, __Y4__)
};
% line of best fit
\addplot[cp line, domain=0:5] {__M__ * x + __B__};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'Y1': {'type': 'number', 'default': '2', 'desc': 'y-coordinate of the first data point'},
            'Y2': {'type': 'number', 'default': '4', 'desc': 'y-coordinate of the second data point'},
            'Y3': {'type': 'number', 'default': '6', 'desc': 'y-coordinate of the third data point'},
            'Y4': {'type': 'number', 'default': '8', 'desc': 'y-coordinate of the fourth data point'},
            'M': {'type': 'number', 'default': '1.5', 'desc': 'Slope of the best-fit line'},
            'B': {'type': 'number', 'default': '0.5', 'desc': 'Intercept of the best-fit line'},
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
    xmin=0,
    xmax=6,
    ymin=0,
    ymax=10,
    xlabel={$x$},
    ylabel={Cumulative Frequency},
    xmajorgrids,
    ymajorgrids,
    axis lines=left,
]
\addplot[cp line, smooth] coordinates {
    (1, __C1__)
    (2, __C2__)
    (3, __C3__)
    (4, __C4__)
    (5, __C5__)
};
\addplot[only marks, mark=*, cp line] coordinates {
    (1, __C1__)
    (2, __C2__)
    (3, __C3__)
    (4, __C4__)
    (5, __C5__)
};
\end{axis}
\end{tikzpicture}""",
        "params": {
            'C1': {'type': 'number', 'default': '2', 'desc': 'Cumulative frequency at the first point'},
            'C2': {'type': 'number', 'default': '5', 'desc': 'Cumulative frequency at the second point'},
            'C3': {'type': 'number', 'default': '7', 'desc': 'Cumulative frequency at the third point'},
            'C4': {'type': 'number', 'default': '9', 'desc': 'Cumulative frequency at the fourth point'},
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
    ymax=10,
    xmin=0.5,
    xmax=4.5,
    xtick={1,2,3,4},
    xticklabels={{Cat 1},{Cat 2},{Cat 3},{Cat 4}},
    xlabel={Category},
    ylabel={Count},
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
        },
    },
]
