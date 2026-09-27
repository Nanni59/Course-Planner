// Regression test for renderTikzWorksheet (index.html): visual-enabled worksheets
// should attempt every question, not just the first few candidates.
// Run: node tools/worksheet_visual_render_all_test.js
const fs = require('fs');
const html = fs.readFileSync(require('path').join(__dirname, '..', 'index.html'), 'utf8');

function slice(startMarker, endMarker) {
  const a = html.indexOf(startMarker);
  const b = html.indexOf(endMarker, a);
  if (a < 0 || b < 0) throw new Error('marker not found: ' + startMarker + ' / ' + endMarker);
  return html.slice(a, b);
}

const src = slice('async function renderTikzWorksheet', "document.getElementById('wsGen')");
const renderTikzWorksheet = new Function(
  'tikzReady',
  'worksheetNeedsVisual',
  'generateTikzVisual',
  'renderTikzCode',
  'sdCleanTikz',
  'noteVisualFailures',
  src + '\nreturn renderTikzWorksheet;'
)(
  () => true,
  () => true,
  async payload => ({
    ok: true,
    tikz: '% rendered ' + payload.title,
    svg: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
  }),
  async () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
  value => String(value || '').trim(),
  () => {}
);

(async () => {
  const data = {
    subject: 'Statistics',
    questions: Array.from({ length: 12 }, (_, i) => ({
      q: 'Histogram question ' + (i + 1),
      answer: ''
    }))
  };
  await renderTikzWorksheet(data, null);
  const rendered = data.questions.filter(q => q.tikzSvg).length;
  if (rendered !== 12) {
    console.error(`FAIL rendered ${rendered} of 12 questions`);
    process.exit(1);
  }
  console.log('PASS rendered all 12 worksheet questions');
})().catch(err => {
  console.error(err);
  process.exit(1);
});
