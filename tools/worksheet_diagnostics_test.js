'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
assert(html.includes('The user may give only a broad topic and is not expected to request individual diagrams'));
assert(html.includes('For named angles XYZ, Y is the vertex'));
assert(html.includes('visualDescription must never contain any value the student works out, including intermediate steps'));
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
  const urls=[];
  const generate = new Function('tikzFetch','TIKZ_SPACE_URL','wait','tikzBase',code('async function generateTikzVisual','function noteVisualFailures')+'; return generateTikzVisual;')(
    async url=>{urls.push(url);return {ok:true,json:async()=>++calls===1 ? {job_id:'job-1'} : {status:'failed',error:'Compile failed',diagnostics:[{stage:'render-error'}]}};},
    'https://example.invalid',async()=>{},async()=>'http://localhost:7860');
  await assert.rejects(generate({}),e=>e.visualDiagnostic.jobId==='job-1' && e.visualDiagnostic.events[0].stage==='render-error' && e.visualDiagnostic.backend==='local');
  // the job is polled on the renderer that started it
  assert(urls.length===2 && urls.every(u=>u.startsWith('http://localhost:7860/')), urls);
  let sent, failures, prepared=0;
  const render = new Function('tikzReady','worksheetNeedsVisual','generateTikzVisual','renderTikzCode','sdCleanTikz','noteVisualFailures','tikzPrepareLocal',code('async function renderTikzWorksheet',"document.getElementById('wsGen')")+'; return renderTikzWorksheet;')(
    ()=>true,()=>true,async p=>{sent=p;return {base64:'valid-png',job_id:'png-job',backend:'space'};},()=>{},()=>'',n=>{failures=n;},async()=>{prepared++;});
  const data={questions:[{q:'Find x.',visualDescription:'Draw a triangle.',answer:'secret answer'}]};
  await render(data);
  assert(sent.title.includes('Draw a triangle.'));
  assert(!JSON.stringify(sent).includes('secret answer'));
  assert.equal(failures,0);
  assert.equal(data.questions[0].visualDiagnostic.jobId,'png-job');
  assert.equal(data.questions[0].visualDiagnostic.backend,'space');
  assert.equal(prepared,1);  // the local-service check runs once, before the visuals
  // Local diagram service: chosen per device, used only while it answers, else the Space.
  const store={}, toasts=[], clicks=[];
  let healthy=false, answer=false;
  const ls={getItem:k=>k in store?store[k]:null,setItem:(k,v)=>{store[k]=String(v);},removeItem:k=>{delete store[k];}};
  const doc={createElement:()=>({click(){clicks.push(this.href);},remove(){}}),body:{appendChild(){}}};
  const win={cpConfirm:(msg,ok,opts)=>answer?ok():opts.onCancel()};
  const local = new Function('localStorage','TIKZ_DEVICE_UI_KEY','TIKZ_DEVICE_KEY','TIKZ_LOCAL_URL','TIKZ_SPACE_URL','TIKZ_LAUNCHER','tikzFetch','toast','wait','window','document',
    code('const tikzLocalShown','const hfReady')+'; return {tikzBase,tikzPrepareLocal,tikzLocalUp,tikzFollowLauncher};')(
    ls,'cp_tikz_local_ui','cp_tikz_backend','http://localhost:7860','https://space.invalid','courseplanner-tikz-',
    async url=>{ if(!healthy) throw new Error('refused'); return {ok:true,json:async()=>({status:'ok'})}; },
    msg=>toasts.push(msg),async()=>{ healthy=clicks.includes('courseplanner-tikz-start:'); },win,doc);
  assert.equal(await local.tikzBase(),'https://space.invalid');  // other visitors: never local
  store.cp_tikz_local_ui='1'; store.cp_tikz_backend='local';
  assert.equal(await local.tikzBase(),'https://space.invalid');  // chosen but not running
  assert.equal(toasts.length,1);
  assert.equal(await local.tikzBase(),'https://space.invalid');
  assert.equal(toasts.length,1);  // noted once per page
  await local.tikzPrepareLocal(null);  // "Use online": no launcher
  assert.deepEqual(clicks,[]);
  answer=true;
  await local.tikzPrepareLocal(null);  // "Start it": launcher, then wait for /health
  assert.deepEqual(clicks,['courseplanner-tikz-start:']);
  assert.equal(await local.tikzLocalUp(0),true);
  assert.equal(await local.tikzBase(),'http://localhost:7860');
  // Stop progress: steps finish in order once the service and the bridge stop answering.
  clicks.length=0; const seen=[];
  const stopped = await local.tikzFollowLauncher('stop',(steps)=>{ seen.push(steps.map(s=>s.state).join(',')); healthy=false; },60000);
  assert(stopped && seen[0]==='active,pending,pending' && seen[seen.length-1]==='done,done,done', seen);
  // A start that never comes up fails on the step it is waiting for.
  let last;
  assert.equal(await local.tikzFollowLauncher('start',steps=>{ last=steps.map(s=>s.state).join(','); },-1), false);
  assert.equal(last,'failed,pending,pending');
  delete store.cp_tikz_local_ui;  // ?tikz=space hides and turns it off
  assert.equal(await local.tikzBase(),'https://space.invalid');

  const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
  for (const [,script] of scripts) if(script.trim()) new Function(script);
  console.log('PASS feedback, authoring text separation, failure propagation, PNG success, and inline script syntax');
})().catch(e=>{console.error(e);process.exit(1);});
