// Regression test for worksheetNeedsVisual (index.html): which worksheet questions
// get a backend diagram. Guards against the "irrelevant/repeated visual" bug — abstract
// vector/algebra/notation questions must be excluded, geometric/graphable ones kept.
// Run:  node tools/worksheet_visual_gate_test.js   (exits 1 on regression)
const fs = require('fs');
const html = fs.readFileSync(require('path').join(__dirname, '..', 'index.html'), 'utf8');
// extract worksheetNeedsVisual + its dep sdCleanTikz (stub)
const i = html.indexOf('function worksheetNeedsVisual');
const j = html.indexOf('async function renderTikzWorksheet');
const body = html.slice(i, j);
const fn = new Function('sdCleanTikz', body + '\nreturn worksheetNeedsVisual;')(() => '');

const cases = [
  // [expected, label, question]
  [false, 'V-Q1 state associative property', 'Given vectors a, b, and c, state the associative property of vector addition in mathematical notation.'],
  [false, 'V-Q2 simplify 3D path AB+BC', 'In a 3D coordinate system, consider points A(1, 2, 3), B(4, -1, 5), and C(-2, 3, 0). Simplify the vector path represented by AB + BC. Express the result as a single vector.'],
  [false, 'V-Q3 state distributive property', 'State the distributive property of scalar multiplication over vector addition in mathematical notation, given a scalar k and vectors a and b.'],
  [false, 'V-Q4 prove vector identity', 'Prove the vector identity: a + (b - c) = (a + b) - c. Assume a, b, and c are vectors in 3D space.'],
  [false, 'V-Q5 calculate 3(u-v)', 'Let u = (2, -1, 4) and v = (-3, 5, 1). Calculate 3(u - v) and verify that it is equal to 3u - 3v.'],
  // concrete vector-QUANTITY questions SHOULD get a visual when TikZ is enabled — the
  // backend matches the diagram (single vector + components for magnitude/component form,
  // perpendicular arrows for orthogonal). These are NOT the abstract state/prove cases above.
  [true, 'V-Q6 magnitude of 3D vector', 'Find the magnitude of the algebraic vector u = 4i - 2j + 4k in R^3. Show your steps.'],
  [true, 'V-Q7 component form linear combo', 'Given points A(3, -5) and B(-2, 7) in R^2, write the vector AB in component form and then as a linear combination of the standard unit vectors i and j.'],
  [true, 'V-Q8 component form of c=3a-2b', 'If a = (3, -1) and b = (-2, 5), determine the component form of the vector c = 3a - 2b.'],
  [true, 'V-Q9 position vector of midpoint', 'Find the position vector of the midpoint M of the line segment AB, and verify that OM = OA + (1/2)AB, where O is the origin.'],
  [true, 'V-Q10 orthogonal vectors', 'Determine if the algebraic vectors u = (2, -3, 4) and v = (5, 2, -1) are orthogonal.'],
  [true, 'V-Q11 unit vector opposite', 'Find a unit vector in the opposite direction of v = (-3, 0, 4).'],
  // Symbolic vector operations (a+b, p-q, 2u-3v) are diagram-worthy and must be treated
  // the SAME whether or not the worked answer happens to say "component-wise" (decided on
  // the question). Real worksheet output writes vectors as \vec{...}.
  [true, 'V-Q12 subtraction p-q', 'Given \\vec{p} = (5, -1, 2) and \\vec{q} = (2, 3, -4), calculate \\vec{p} - \\vec{q}.'],
  [true, 'V-Q13 linear combination 2u-3v', 'Given \\vec{u} = (-1, 0, 4) and \\vec{v} = (3, -5, 2), calculate 2\\vec{u} - 3\\vec{v}.'],
  [true, 'V-Q14 sum a+b', 'Given \\vec{a} = (3, -2) and \\vec{b} = (1, 5), find the resultant vector \\vec{c} = \\vec{a} + \\vec{b} and its magnitude.'],
  // quadratic: a parabola genuinely helps -> should be TRUE (Gemini draws it; no wrong triangle now)
  [true, 'Quad-Q1 vertex', 'What is the vertex of the quadratic function f(x) = 2x^2 - 8x + 5?'],
  [true, 'Quad-Q3 axis of symmetry parabola', 'What is the axis of symmetry for the parabola defined by y = -x^2 + 6x - 9?'],
  [false, 'Quad-Q2 find roots quadratic formula', 'Find the roots of the quadratic equation 3x^2 + 5x - 2 = 0 using the quadratic formula. Show all steps.'],
  // things that SHOULD still get visuals (regression guard)
  [true, 'sine law triangle', 'In triangle ABC, angle A = 40 degrees, angle B = 60 degrees, and side a = 10cm. Find side b using the sine law.'],
  [true, 'resultant of two vectors', 'Find the resultant of vector u and vector v where the angle between them is 60 degrees.'],
  [true, 'bearing navigation', 'A boat sails 10km on a bearing of 040 degrees then 15km on a bearing of 110 degrees. How far from port?'],
  [true, 'histogram data', 'Draw a histogram for the following frequency distribution of test scores.'],
  [true, 'box plot', 'Construct a box-and-whisker plot given the five-number summary.'],
  [true, 'skewness distribution', 'A dataset has a mean of 5%, median of 4%, and mode of 3%. Describe the skewness of this distribution.'],
  [true, 'angle of elevation', 'A surveyor measures the angle of elevation to the top of a tree as 30 degrees.'],
  // river-crossing / boat-in-current / plane-in-wind resultant problems are vector
  // problems even when the word "vector" never appears (the Q8 regression).
  [true, 'river current resultant', 'A boat heads directly across a river at 4 m/s while the current flows downstream at 3 m/s. Find the resultant velocity and the angle of the path.'],
  [true, 'swimmer upstream', 'A swimmer can swim at 1.5 m/s in still water and tries to cross a river with a current of 0.8 m/s. Determine the resultant speed.'],
  [true, 'airplane wind', 'An airplane flies at 300 km/h on a heading of north while a wind blows from the west at 50 km/h. Find the ground speed.'],
  [true, 'two-rope tension', 'A 100kg mass is suspended by two ropes. The first rope makes an angle of 60 degrees with the horizontal, and the second rope makes an angle of 45 degrees with the horizontal. Find the tension in each rope.'],
  [false, 'define equilibrant force', 'Define the term equilibrant force and explain its relationship to the resultant force of a system.'],
  [true, 'inclined crate constant velocity', 'A crate of mass 40 kg is being pulled up a 20 degree incline by a rope that is parallel to the incline. If the crate is moving at a constant velocity, find the force of friction.'],
  [true, 'two wires support mass', 'A mass of 50 kg is supported by two wires. One wire is at an angle of 30 degrees to the horizontal and the other is at an angle of 45 degrees to the horizontal. Determine the tensions.'],
  [true, 'angle bracket linear combination', 'Given \\vec{u} = \\left< 2, 1 \\right> and \\vec{v} = \\left< 1, -1 \\right>, express \\vec{w} = \\left< 5, 4 \\right> as a linear combination of \\vec{u} and \\vec{v}.'],
  [true, 'arc length sector', 'Find the arc length of a sector with a radius of 8.5cm and a central angle of 2.4 radians.'],
  [true, 'circle chord arc difference', 'A chord of a circle of radius 12cm subtends an angle of 110 degrees at the center. Calculate the difference between the length of the arc and the length of the chord.'],
  [true, 'probability tree defective', 'A factory has two machines, A and B. Machine A produces 60% of items and Machine B produces 40%. Use a probability tree approach to find the probability an item came from Machine A given that it is defective.'],
  [true, 'scatter correlation data', 'A study collects data on hours of study (x) and test scores (y) for five students. Calculate the Pearson correlation coefficient and interpret its meaning.'],
  [true, 'complete graph edges', 'A complete graph K_n is a graph where every pair of distinct vertices is connected by a unique edge. How many edges are there in K_7?'],
  [true, 'network depot route', 'A delivery driver needs to visit each location exactly once, starting and ending at a central depot. Explain what kind of graph theory problem this is.'],
  [true, 'rational asymptotes', 'Identify the vertical and horizontal asymptotes of the rational function f(x) = (3x - 6)/(x + 4).'],
  [true, 'sinusoidal amplitude period', 'Determine the amplitude, period, and phase shift of the sinusoidal function y = -5 sin(2x + pi) - 3.'],
  // "current"/"plane" in a non-motion context must NOT trigger a diagram
  [false, 'current price', 'The current price of a stock is $52. If it rises 8%, what is the new price?'],
  // things that should NOT get visuals
  [false, 'solve linear', 'Solve the equation 2x + 3 = 7 for x.'],
  [false, 'factor polynomial', 'Factor the expression x^2 - 5x + 6.'],
  [false, 'matrix determinant', 'Calculate the determinant of the matrix A = [[4, -2], [3, 5]].'],
  [false, 'matrix Gaussian elimination', 'Solve the system of linear equations using matrix methods such as Gaussian elimination.'],
  [true, 'linear transformation unit square', 'Describe the geometric transformation applied to the unit square in the coordinate plane by the matrix M.'],
  // conceptual "explain the method/law" question (no object to draw) -> no diagram
  [false, 'explain cosine vs sine law', 'Explain the necessary information (known sides and angles) required to solve a triangle using the Cosine Law instead of the Sine Law.'],
  [false, 'when to use cosine law', 'When should you use the Cosine Law rather than the Sine Law?'],
  // a three-point angle name (∠ACB) is a triangle even without the word "triangle" (surveyor SAS)
  [true, 'surveyor SAS three-point angle', 'A surveyor stands at point C and measures the distance to point A as 250m and the distance to point B as 310m. If the angle ∠ACB = 52 degrees, calculate the distance from point A to point B.'],
  [true, 'surveyor SAS latex angle', 'A surveyor at point C measures CA = 250m and CB = 310m with \\angle ACB = 52^\\circ. Find the distance from A to B.'],
  // guard: "angle sum" / "interior angles" must NOT trip the 3-letter-angle rule
  [false, 'polygon interior angle sum', 'What is the sum of the interior angles of a regular hexagon?'],
  // related-rates ladder is a classic right-triangle diagram question (2026-07-07:
  // the gate silently skipped it, so the backend right_triangle template never ran)
  [true, 'ladder related rates', 'A 10 ft ladder is leaning against a wall. If the bottom of the ladder is pulled away from the wall at a rate of 2 ft/s, how fast is the top sliding down when the bottom is 6 ft from the wall?'],
  // critical numbers -> curve with marked extrema (backend curve_extrema_inflection)
  [true, 'critical numbers quartic', 'Find the critical numbers of the function g(x) = x^4 - 4x^3.'],
  // Lines in R^2 (2026-07-09 worksheet): 7 of 10 line-equation questions were never
  // sent — every one of these is a drawable coordinate-plane picture.
  [true, 'line through point + direction vector', 'Find the vector and parametric equations of the line passing through point \\( A(4, -7) \\) with direction vector \\( \\vec{d} = (3, 2) \\).'],
  [true, 'line through two points', 'Determine the vector equation of the line passing through the points \\( P(-1, 5) \\) and \\( Q(3, -2) \\).'],
  [true, 'convert vector eq to Cartesian', 'A line has the vector equation \\( \\vec{r} = (2, 3) + t(5, -4) \\). Convert this into Cartesian (scalar) form \\( Ax + By + C = 0 \\).'],
  [true, 'convert Cartesian to vector eq', 'Convert the Cartesian equation \\( 5x - 2y + 10 = 0 \\) into a vector equation.'],
  [true, 'parallel line through point', 'Find the Cartesian equation of the line that is parallel to the line \\( 3x + 4y - 12 = 0 \\) and passes through the point \\( (5, -2) \\).'],
  [true, 'intersection between two lines', 'Determine the point of intersection between the lines \\( L_1: \\vec{r} = (1, 4) + s(1, -2) \\) and \\( L_2: \\vec{r} = (4, -5) + t(-1, 3) \\).'],
  [true, 'point lies on parametric line', 'Determine if the point \\( P(11, -2) \\) lies on the line with parametric equations \\( x = 1 + 2t \\) and \\( y = 3 - t \\).'],
];
let fails = 0;
for (const [exp, label, q] of cases) {
  const got = fn({ q, answer: '' });
  const ok = (!!got === exp);
  if (!ok) fails++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${String(got).padEnd(5)} (want ${String(exp).padEnd(5)})  ${label}`);
}
console.log(fails ? `\n${fails} FAILURES` : '\nALL GATE CASES PASS');
process.exit(fails ? 1 : 0);
