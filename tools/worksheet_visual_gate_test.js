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
  // "current"/"plane" in a non-motion context must NOT trigger a diagram
  [false, 'current price', 'The current price of a stock is $52. If it rises 8%, what is the new price?'],
  // things that should NOT get visuals
  [false, 'solve linear', 'Solve the equation 2x + 3 = 7 for x.'],
  [false, 'factor polynomial', 'Factor the expression x^2 - 5x + 6.'],
  [false, 'matrix determinant', 'Calculate the determinant of the matrix A = [[4, -2], [3, 5]].'],
  [false, 'matrix Gaussian elimination', 'Solve the system of linear equations using matrix methods such as Gaussian elimination.'],
  [true, 'linear transformation unit square', 'Describe the geometric transformation applied to the unit square in the coordinate plane by the matrix M.'],
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
