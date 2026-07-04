"""Course Planner TikZ catalog - Vectors / Linear Algebra.

One dict per diagram. Authoring contract lives in ../templates.py.
Slots are __UPPER__; skeletons are raw strings; every slot has a params entry.
"""

templates = [
    {
        "id": '2d_vector_components',
        "subject": 'Vectors / Linear Algebra',
        "triggers": ['components', '2d vector', 'right triangle'],
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
        "triggers": ['vector addition', 'parallelogram', 'resultant', 'sum of two vectors'],
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
        "triggers": ['vector addition', 'head to tail', 'triangle method'],
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
        "triggers": ['vector subtraction', 'difference', 'head to tail'],
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
        "triggers": ['angle between', 'angle between vectors', 'angle between two vectors'],
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
  \draw[cp line,->] (O) -- (F) node[cp label,anchor=west] {$__PROJLAB__$};
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
        "triggers": ['3d vector', 'components', 'xyz'],
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
  \node[cp label] at ($(Px)!0.5!(O)$) {$__XVALLABEL__$};
  \node[cp label] at ($(Py)!0.5!(O)$) {$__YVALLABEL__$};
  \node[cp label] at ($(Pz)!0.5!(O)$) {$__ZVALLABEL__$};
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
        "triggers": ['cross product', 'parallelogram', 'area'],
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
        "triggers": ['parallelepiped', 'volume', 'scalar triple product'],
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
        "triggers": ['line', 'plane', 'intersection'],
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
        "triggers": ['collinear', 'parallel', 'scalar multiple'],
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
        "triggers": ['orthogonal', 'right angle', 'perpendicular'],
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
