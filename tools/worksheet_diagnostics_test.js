'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
function code(a,b) { const start=html.indexOf(a), end=html.indexOf(b,start); assert(start>=0 && end>start, 'Missing extraction marker: '+a+' / '+b); return html.slice(start,end); }
const student = new Function(code('function worksheetStudentText','function questionHTML')+'; return worksheetStudentText;')();
assert.equal(student({q:'Find BC. Diagram: Draw a triangle.'}), 'Find BC.');
assert.equal(student({q:'Use the diagram to find BC.'}), 'Use the diagram to find BC.');
assert.equal(student({q:'Diagram: What does this represent?'}), 'Diagram: What does this represent?');
const bundle = new Function('worksheetNeedsVisual','TIKZ_SPACE_URL',code('function buildWorksheetFeedback','function exportWorksheetFeedback')+'; return buildWorksheetFeedback;')(()=>true,'https://example.invalid');
const diag = {status:'failed',stage:'backend',jobId:'job-1',error:'Compile failed',events:[{stage:'render-error'}]};
const exported = bundle({questions:[{q:'Find x.',answer:'secret answer',visualDescription:'Draw a triangle.',visualDiagnostic:diag}]});
assert.deepEqual(exported.worksheet.questions[0].visualDiagnostic,diag);
assert.equal(exported.worksheet.questions[0].visualDescription,'Draw a triangle.');

(async()=>{
  let calls=0;
  const generate = new Function('tikzFetch','TIKZ_SPACE_URL','wait',code('async function generateTikzVisual','function noteVisualFailures')+'; return generateTikzVisual;')(
    async()=>({ok:true,json:async()=>++calls===1 ? {job_id:'job-1'} : {status:'failed',error:'Compile failed',diagnostics:[{stage:'render-error'}]}}),
    'https://example.invalid',async()=>{});
  await assert.rejects(generate({}),e=>e.visualDiagnostic.jobId==='job-1' && e.visualDiagnostic.events[0].stage==='render-error');
  let sent, failures;
  const render = new Function('tikzReady','worksheetNeedsVisual','generateTikzVisual','renderTikzCode','sdCleanTikz','noteVisualFailures',code('async function renderTikzWorksheet',"document.getElementById('wsGen')")+'; return renderTikzWorksheet;')(
    ()=>true,()=>true,async p=>{sent=p;return {base64:'valid-png',job_id:'png-job'};},()=>{},()=>'',n=>{failures=n;});
  const data={questions:[{q:'Find x.',visualDescription:'Draw a triangle.',answer:'secret answer'}]};
  await render(data);
  assert(sent.title.includes('Draw a triangle.'));
  assert(!JSON.stringify(sent).includes('secret answer'));
  assert.equal(failures,0);
  assert.equal(data.questions[0].visualDiagnostic.jobId,'png-job');
  const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
  for (const [,script] of scripts) if(script.trim()) new Function(script);
  console.log('PASS feedback, authoring text separation, failure propagation, PNG success, and inline script syntax');
})().catch(e=>{console.error(e);process.exit(1);});
