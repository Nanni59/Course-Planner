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
  [true, 'angle of elevation', 'A surveyor measures the angle of elevation to the top of a tree as 30 degrees.'],
  // things that should NOT get visuals
  [false, 'solve linear', 'Solve the equation 2x + 3 = 7 for x.'],
  [false, 'factor polynomial', 'Factor the expression x^2 - 5x + 6.'],
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
