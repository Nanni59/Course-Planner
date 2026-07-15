"""Course Planner TikZ catalog - Vectors / Linear Algebra.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

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
  \draw[cp line,-Stealth] (O)--(A) node[cp label,midway,anchor=east] {$__AIRLAB__$};
  \draw[cp line,-Stealth] (A)--(G) node[cp label,midway,anchor=south] {$__WINDLAB__$};
  \draw[cp dashed,-Stealth] (O)--(G) node[cp label,midway,anchor=north west] {$__GROUNDLAB__$};
  \draw[cp dashed] (90:0.62) arc[start angle=90,end angle=__AIRANG__,radius=0.62];
  \node[cp label] at (__BEARING_MID__:0.9) {$__BEARINGLAB__$};
\end{tikzpicture}""",
        "params": {
            'AIRANG': {'type': 'number', 'default': '60', 'desc': 'airplane direction in standard math degrees; N30E is 60'},
            'WINDANG': {'type': 'number', 'default': '0', 'desc': 'wind vector direction in standard math degrees; from West means east, 0 degrees'},
            'BEARING_MID': {'type': 'number', 'default': '75', 'desc': 'midpoint angle for bearing label'},
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
  \pic [draw=black, angle radius=0.58cm, "$__ANGLAB__$"] {angle=A--O--B};
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
  \draw[cp line,->] (B) -- (A) node[cp label,midway,anchor=south] {$__DIFFLAB__$};
  \pic [draw=black, angle radius=0.58cm, "$__ANGLAB__$"] {angle=A--O--B};
\end{tikzpicture}""",
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
  \draw[cp line,->] (P) -- (D) node[cp label,midway,anchor=west] {$__NQLAB__$};
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
  \pic [draw=black, angle radius=0.45cm, "$__ANGLAB__$"] {angle=U--O--V};
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=north] {$__ULAB__$};
  \draw[cp line,->] (A) -- (B) node[cp label,anchor=west] {$__VLAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south east] {$__RLAB__$};
\end{tikzpicture}""",
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
  \draw[cp line,->] (B) -- (C) node[cp label,midway,right] {$\overrightarrow{BC}$};
  \draw[cp line,->] (C) -- (A) node[cp label,midway,left] {$\overrightarrow{CA}$};
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
  \node[cp label,anchor=west] at (M) {$M$};
  \draw[cp line,->] (A) -- (B) node[cp label,midway,below] {$\overrightarrow{AB}$};
  \draw[cp line,->] (A) -- (C) node[cp label,midway,left] {$\overrightarrow{AC}$};
  \draw[cp dashed,->] (A) -- (M) node[cp label,midway,anchor=south west] {$\overrightarrow{AM}$};
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

  % vector u
  \draw[cp line,->] (O) -- (U) node[cp label,anchor=south east] {$__ULAB__$};
  % vector v placed at head of u
  \draw[cp line,->] (U) -- (Vend) node[cp label,anchor=south east] {$__VLAB__$};
  % resultant vector
  \draw[cp line,->] (O) -- (Vend) node[cp label,anchor=south] {$__SUM__$};
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

  % vectors u and v
  \draw[cp line,->] (O) -- (U) node[cp label,anchor=south east] {$__ULAB__$};
  \draw[cp line,->] (O) -- (V) node[cp label,anchor=south west] {$__VLAB__$};
  % difference vector (u - v)
  \draw[cp line,->] (V) -- (U) node[cp label,anchor=south] {$__DIFF__$};
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
        "triggers": ['angle between vectors', 'angle between two vectors', 'angle between force vectors'],
        "caption": 'Two vectors with the marked angle between them.',
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  \draw[cp axis] (-0.5,0) -- (4.5,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,4.0) node[cp label,anchor=south] {$y$};
  \coordinate (O) at (0,0);
  % fixed geometry: first vector on the x-axis, second at the given angle
  \coordinate (A) at (3.4,0);
  \coordinate (B) at (__ANG__:3.2);
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=north] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__BLAB__$};
  \pic [draw=black, angle radius=0.7cm, "$__ANGLAB__$"] {angle=A--O--B};
\end{tikzpicture}""",
        "params": {
            'ANG': {'type': 'number', 'default': '55', 'desc': 'angle between the vectors in degrees; drives the drawing. Use the given angle, or ~55 if the angle is the unknown being solved'},
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
  \draw[cp line,-Stealth] (O) -- (A) node[cp label,midway,anchor=west,xshift=3pt] {$__BOATLAB__$};
  \draw[cp line,-Stealth] (O) -- (C) node[cp label,midway,below] {$__CURRENTLAB__$};
  \draw[cp dashed] (A) -- (R);
  \draw[cp dashed] (C) -- (R);
  \draw[cp line,-Stealth] (O) -- (R) node[cp label,pos=0.72,anchor=west,xshift=4pt] {$__RESULTLAB__$};
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
        "skeleton": r"""\begin{tikzpicture}[scale=1]
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (4.5,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,3.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  % fixed example vectors
  \coordinate (U) at (2,1.5);
  \coordinate (V) at (3,0.5);
  % approximate foot of projection of U onto V
  \coordinate (F) at (2.2,0.36);

  % vectors and projection
  \draw[cp line,->] (O) -- (U) node[cp label,anchor=south east] {$__ULAB__$};
  \draw[cp line,->] (O) -- (V) node[cp label,anchor=south west] {$__VLAB__$};
  \draw[cp line,->] (O) -- (F) node[cp label,midway,below,yshift=-2pt] {$__PROJLAB__$};
  % perpendicular drop
  \draw[cp dashed] (U) -- (F);
  % right angle marker at foot
  \pic [cp dashed, angle radius=0.3cm] {right angle=U--F--O};
\end{tikzpicture}""",
        "params": {
            'ULAB': {'type': 'label', 'default': '\\vec{u}', 'desc': 'label for the projected vector'},
            'VLAB': {'type': 'label', 'default': '\\vec{v}', 'desc': 'label for the vector being projected onto'},
            'PROJLAB': {'type': 'label', 'default': '\\mathrm{proj}_{\\vec{v}}\\vec{u}', 'desc': 'label for the projection of u onto v'},
        },
    },
    {
        "id": '3d_vector_components',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['3d vector', 'components', 'z-component', 'three-dimensional vector'],
        "caption": 'A 3D vector with dashed component drops to the coordinate axes.',
        "skeleton": r"""\begin{tikzpicture}[scale=1, x={(-0.5cm,-0.3cm)}, y={(0.7cm,-0.3cm)}, z={(0cm,0.8cm)}]
  % three-dimensional axes
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (P) at (__XVAL__,__YVAL__,__ZVAL__);
  \coordinate (Px) at (__XVAL__,0,0);
  \coordinate (Py) at (0,__YVAL__,0);
  \coordinate (Pz) at (0,0,__ZVAL__);

  % the vector
  \draw[cp line,->] (O) -- (P) node[cp label,anchor=west] {$__LAB__$};

  % dashed drops to axes
  \draw[cp dashed] (P) -- (Px);
  \draw[cp dashed] (P) -- (Py);
  \draw[cp dashed] (P) -- (Pz);

  % component labels
  \node[cp label,anchor=north east] at ($(Px)!0.55!(O)+(-0.12,0,0)$) {$__XVALLABEL__$};
  \node[cp label,anchor=north west] at ($(Py)!0.55!(O)+(0,0.16,0)$) {$__YVALLABEL__$};
  \node[cp label,anchor=west] at ($(Pz)!0.55!(O)+(0,0,0.16)$) {$__ZVALLABEL__$};
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
        "skeleton": r"""\begin{tikzpicture}[scale=1, x={(-0.5cm,-0.3cm)}, y={(0.7cm,-0.3cm)}, z={(0cm,0.8cm)}]
  % axes
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (A) at (3,1,0);
  \coordinate (B) at (1,2,0);
  \coordinate (C) at ($(A)+(B)$);
  \coordinate (N) at (0,0,2.5);

  % vectors a and b
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=south east] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__BLAB__$};

  % parallelogram face
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;

  % cross product vector
  \draw[cp line,->] (O) -- (N) node[cp label,anchor=west] {$__CROSSLAB__$};
\end{tikzpicture}""",
        "params": {
            'ALAB': {'type': 'label', 'default': '\\vec{a}', 'desc': 'label for the first vector'},
            'BLAB': {'type': 'label', 'default': '\\vec{b}', 'desc': 'label for the second vector'},
            'CROSSLAB': {'type': 'label', 'default': '\\vec{a}\\times\\vec{b}', 'desc': 'label for the cross product vector'},
        },
    },
    {
        "id": 'parallelepiped_volume',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['parallelepiped', 'volume of parallelepiped', 'scalar triple product'],
        "caption": 'A parallelepiped spanned by three vectors showing hidden and visible edges.',
        "skeleton": r"""\begin{tikzpicture}[scale=0.9, x={(-0.5cm,-0.3cm)}, y={(0.8cm,-0.3cm)}, z={(0cm,0.8cm)}]
  % axes
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=west] {$x$};
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
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=south east] {$__V1LAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__V2LAB__$};
  \draw[cp line,->] (O) -- (V) node[cp label,anchor=west] {$__V3LAB__$};
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
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (A) at (3,0.5,0);
  \coordinate (B) at (0.5,2,1);
  \coordinate (C) at ($(A)+(B)$);

  % plane drawn as a parallelogram
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;

  % plane label at an interior point
  \node[cp label] at ($(A)!0.5!(B)$) {$__PLANELAB__$};

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
  \draw[cp axis] (0,0,0) -- (4,0,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,0,0) -- (0,3,0) node[cp label,anchor=south] {$y$};
  \draw[cp axis] (0,0,0) -- (0,0,3) node[cp label,anchor=west] {$z$};

  \coordinate (O) at (0,0,0);
  \coordinate (A) at (3,0.5,0);
  \coordinate (B) at (0.5,2,1);
  \coordinate (C) at ($(A)+(B)$);

  % plane
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;
  \node[cp label] at ($(A)!0.5!(B)$) {$__PLANELAB__$};

  % line defined by two endpoints
  \coordinate (I) at (1,0.7,0.3);
  \coordinate (Lstart) at (-0.5,-1,1.5);
  \coordinate (Lend) at (2,3,-0.5);
  \draw[cp line,->] (Lstart) -- (Lend) node[cp label,anchor=west] {$__LINELAB__$};

  % intersection point
  \node[cp point] at (I) {};
  \node[cp label,anchor=south] at (I) {$__PNTLAB__$};
\end{tikzpicture}""",
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
  % coordinate axes
  \draw[cp axis] (-0.5,0) -- (4,0) node[cp label,anchor=west] {$x$};
  \draw[cp axis] (0,-0.5) -- (0,3.5) node[cp label,anchor=south] {$y$};

  \coordinate (O) at (0,0);
  % unit square vertices
  \coordinate (U1) at (1,0);
  \coordinate (U2) at (1,1);
  \coordinate (U3) at (0,1);
  % draw unit square (dashed)
  \draw[cp dashed] (O) -- (U1) -- (U2) -- (U3) -- cycle;
  \node[cp label] at (0.5,0.5) {unit square};

  % images of basis vectors under the transformation
  \coordinate (A) at (__AVAL__,__BVAL__);
  \coordinate (B) at (__CVAL__,__DVAL__);
  \coordinate (C) at ($(A)+(B)$);

  % draw transformed region
  \draw[cp fill] (O) -- (A) -- (C) -- (B) -- cycle;
  \node[cp label] at ($(A)!0.5!(B)$) {image};

  % arrows showing the images of the standard basis
  \draw[cp line,->] (O) -- (A) node[cp label,anchor=south east] {$__ALAB__$};
  \draw[cp line,->] (O) -- (B) node[cp label,anchor=south west] {$__BLAB__$};
\end{tikzpicture}""",
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

  % ratio label on the shorter vector
  \node[cp label] at ($(O)!0.5!(V)$) {$__KLAB__ = __KVAL__$};
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
