'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
function code(a,b) { const start=html.indexOf(a), end=html.indexOf(b,start); assert(start>=0 && end>start); return html.slice(start,end); }
const helpers = code('const deBold', '/* ---------- Subjects from');
const {normalizeGeneratedContent, escMath} = new Function(helpers+';return {normalizeGeneratedContent,escMath};')();
const rows = String.raw`\[\begin{aligned}x &= 3 \\ y &= 4\end{aligned}\]`;
const data = {questions:[{type:'work',q:'Find x.',answer:'3',solutionSteps:[String.raw`\(x+2=5\)`,rows,'<img src=x onerror=alert(1)>',null,7,'  ']}]};
normalizeGeneratedContent(data);
assert.equal(data.questions[0].solutionSteps.length,3);
assert(data.questions[0].solutionSteps[1].includes(String.raw`\\ y`));
assert(escMath(data.questions[0].solutionSteps[1]).includes(String.raw`\\ y`));
assert.deepEqual(normalizeGeneratedContent(JSON.parse(JSON.stringify(data))),data,'Repeated normalization must be stable');
assert.deepEqual(normalizeGeneratedContent({solutionSteps:'bad'}).solutionSteps,[]);
const render = new Function('escMath','escMathFlow','worksheetStudentText','worksheetTikzHTML','WS_SPACE','WS_LINES','WS_DIAGRAMS',
    code('function questionHTML','function sheetHTML')+';return questionHTML;')(escMath,escMath,q=>q.q,()=>'',false,false,false);
const key = render(data.questions[0],0,true);
assert(key.includes('<ol class="st-solution-steps">'));
assert.equal((key.match(/<li>/g)||[]).length,3);
assert(key.includes('&lt;img'));
assert(!key.includes('<img'));
assert(!render(data.questions[0],0,false).includes('st-solution-steps'));
assert(!render({q:'Legacy',answer:'Legacy full solution',type:'work'},0,true).includes('<ol'));
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/worksheet_reliability.json'),'utf8'));
for (const q of fixture) {
    const legacy = {answer:q.answer};
    const normalized = normalizeGeneratedContent(legacy);
    assert(!normalized.solutionSteps,'Never invent steps from concatenated legacy answers');
    assert.deepEqual(normalizeGeneratedContent(JSON.parse(JSON.stringify(normalized))),normalized);
}
const bundle = new Function('worksheetNeedsVisual','TIKZ_SPACE_URL',code('function buildWorksheetFeedback','function exportWorksheetFeedback')+';return buildWorksheetFeedback;')(()=>false,'');
assert.deepEqual(bundle(data).worksheet.questions[0].solutionSteps,data.questions[0].solutionSteps);
assert.deepEqual(JSON.parse(JSON.stringify(data)),data,'Storage/backup JSON round-trip preserves optional steps');
assert.equal((html.match(/For worked solutions provide "solutionSteps"/g)||[]).length,2,'Standalone and All-in-One share instructions');
console.log('PASS structured solution rows, idempotence, escaping, legacy data, feedback and prompt parity');
