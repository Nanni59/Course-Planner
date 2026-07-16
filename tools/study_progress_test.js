// Regression test for createJobRegistry() in index.html — the state machine behind
// the Study Tools background-progress badge, the tab title, and the "generation
// finished" notification. Extracted by string markers (see tools/README-style
// harnesses: renaming the function means updating this file in the same commit).
//
// Why this is worth pinning: the registry is the ONLY thing that knows a
// generation is still alive once the user navigates away from Study Tools. If its
// aggregation or acknowledgement logic drifts, the failure is silent — the badge
// simply lies, and you only notice by watching a Manim render for five minutes.
//
// Covers:
//   - idle when empty; a started job reports running at 0%
//   - percentages are clamped and rounded (garbage in never escapes 0..100)
//   - update() on an unknown, settled or dropped job is a no-op
//   - concurrent jobs aggregate to the mean, and RUNNING outranks settled —
//     a finished worksheet must never mask an in-flight video
//   - a failure outranks a success when several jobs have settled
//   - ack() clears settled jobs but leaves running ones alone
//   - drop() (explicit cancel) leaves nothing behind to acknowledge
//   - subscribers fire on real changes and stay silent on no-ops
//   - get() hands back a copy, so callers can't mutate registry state
//
// Run: node tools/study_progress_test.js   (exit 0 = pass)
'use strict';
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

function slice(startMarker, endMarker) {
    const a = html.indexOf(startMarker);
    const b = html.indexOf(endMarker, a);
    if (a < 0 || b < 0) throw new Error('marker not found: ' + startMarker + ' / ' + endMarker);
    return html.slice(a, b);
}

// The registry is deliberately DOM-free, so it loads into Node exactly as it runs
// in the browser — this pins the LIVE code, not a copy that can drift.
const createJobRegistry = new Function(
    slice('function createJobRegistry() {', 'const stJobs = createJobRegistry();') +
    '\nreturn createJobRegistry;'
)();

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}

// == empty / single job ==========================================================
{
    const r = createJobRegistry();
    check('empty registry is idle', r.summary().status === 'idle', JSON.stringify(r.summary()));
    check('empty registry reports 0%', r.summary().pct === 0);

    const id = r.start('worksheet', 'Worksheet');
    const s = r.summary();
    check('started job is running', s.status === 'running', s.status);
    check('started job begins at 0%', s.pct === 0, String(s.pct));
    check('single running job shows its own label', s.label === 'Worksheet', s.label);
    check('single job detail carries the percentage', s.detail === 'Worksheet 0%', s.detail);

    r.update(id, 62.4);
    check('percentage is rounded', r.summary().pct === 62, String(r.summary().pct));
}

// == clamping ====================================================================
{
    const r = createJobRegistry();
    const id = r.start('video', 'Video lesson');

    r.update(id, -20);
    check('negative percentage clamps to 0', r.summary().pct === 0, String(r.summary().pct));

    r.update(id, 400);
    check('over-100 percentage clamps to 100', r.summary().pct === 100, String(r.summary().pct));

    r.update(id, NaN);
    check('NaN percentage falls back to 0', r.summary().pct === 0, String(r.summary().pct));

    r.update(id, undefined);
    check('undefined percentage falls back to 0', r.summary().pct === 0, String(r.summary().pct));
}

// == no-op updates ===============================================================
{
    const r = createJobRegistry();
    const id = r.start('guide', 'Study guide');
    r.update(9999, 50);
    check('update on an unknown id is ignored', r.summary().pct === 0, String(r.summary().pct));

    r.finish(id, true);
    r.update(id, 25);
    check('update on a settled job is ignored', r.summary().pct === 100, String(r.summary().pct));

    r.finish(id, false);
    check('finish on an already-settled job does not flip it to error',
        r.summary().status === 'done', r.summary().status);
}

// == concurrency: running outranks settled =======================================
// The real scenario: kick off a worksheet, go back to the hub, start a video, then
// leave Study Tools. The worksheet lands first — the badge must keep showing the
// video's progress rather than declaring everything ready.
{
    const r = createJobRegistry();
    const ws = r.start('worksheet', 'Worksheet');
    const vid = r.start('video', 'Video lesson');

    r.update(ws, 40);
    r.update(vid, 80);
    const s = r.summary();
    check('two running jobs average their progress', s.pct === 60, String(s.pct));
    check('two running jobs report the count', s.label === '2 generations running', s.label);
    check('two running jobs list both in the detail',
        s.detail === 'Worksheet 40% · Video lesson 80%', s.detail);

    r.finish(ws, true);
    const s2 = r.summary();
    check('a finished job never masks one still running', s2.status === 'running', s2.status);
    check('the still-running job owns the badge', s2.label === 'Video lesson', s2.label);
    check('progress drops the finished job from the average', s2.pct === 80, String(s2.pct));
}

// == settled precedence ==========================================================
{
    const r = createJobRegistry();
    const a = r.start('worksheet', 'Worksheet');

    r.finish(a, true);
    check('one finished job reads as ready', r.summary().status === 'done', r.summary().status);
    check('one finished job names itself', r.summary().label === 'Worksheet is ready', r.summary().label);

    // Settle a second one as a failure. Both are now settled, so precedence applies.
    r.finish(r.start('video', 'Video lesson'), false);
    const s = r.summary();
    check('a failure outranks a success', s.status === 'error', s.status);
    check('the failure names the failed job', s.label === 'Video lesson couldn’t finish', s.label);
    check('a settled badge sits at 100%', s.pct === 100, String(s.pct));
}
{
    const r = createJobRegistry();
    r.finish(r.start('worksheet', 'Worksheet'), true);
    r.finish(r.start('guide', 'Study guide'), true);
    const s = r.summary();
    check('two successes are counted together', s.label === '2 generations are ready', s.label);

    const r2 = createJobRegistry();
    r2.finish(r2.start('worksheet', 'Worksheet'), false);
    r2.finish(r2.start('guide', 'Study guide'), false);
    check('two failures are counted together',
        r2.summary().label === '2 generations failed', r2.summary().label);
}

// == ack ==========================================================================
{
    const r = createJobRegistry();
    const done = r.start('worksheet', 'Worksheet');
    const live = r.start('video', 'Video lesson');
    r.update(live, 30);
    r.finish(done, true);

    r.ack();
    const s = r.summary();
    check('ack clears the settled job', s.status === 'running', s.status);
    check('ack leaves the running job untouched', s.label === 'Video lesson' && s.pct === 30,
        s.label + ' / ' + s.pct);

    r.finish(live, true);
    r.ack();
    check('ack with nothing running returns to idle', r.summary().status === 'idle', r.summary().status);
}

// == drop (explicit cancel) =======================================================
{
    const r = createJobRegistry();
    const id = r.start('video', 'Video lesson');
    r.update(id, 55);
    r.drop(id);
    check('a dropped job leaves the registry idle', r.summary().status === 'idle', r.summary().status);

    r.drop(id);       // second cancel must not throw or resurrect anything
    check('dropping twice is harmless', r.summary().status === 'idle', r.summary().status);

    const other = r.start('worksheet', 'Worksheet');
    r.drop(9999);
    check('dropping an unknown id leaves others alone',
        r.summary().status === 'running' && r.summary().label === 'Worksheet', r.summary().label);
    r.finish(other, true);
    check('a dropped job is not counted among the finished',
        r.summary().label === 'Worksheet is ready', r.summary().label);
}

// == subscribe ====================================================================
{
    const r = createJobRegistry();
    let calls = 0, last = null;
    r.subscribe(s => { calls++; last = s; });

    const id = r.start('worksheet', 'Worksheet');
    check('subscriber fires on start', calls === 1, String(calls));

    r.update(id, 50);
    check('subscriber fires on a real change', calls === 2 && last.pct === 50, calls + ' / ' + last.pct);

    r.update(id, 50);
    check('subscriber stays silent when nothing changed', calls === 2, String(calls));

    r.update(id, 50.2);
    check('subscriber stays silent when the rounded value is unchanged', calls === 2, String(calls));

    r.finish(id, true);
    check('subscriber fires on finish', calls === 3 && last.status === 'done', calls + ' / ' + last.status);

    r.ack();
    check('subscriber fires on a clearing ack', calls === 4 && last.status === 'idle',
        calls + ' / ' + last.status);

    r.ack();
    check('subscriber stays silent on a redundant ack', calls === 4, String(calls));
}

// == get() is a copy ==============================================================
{
    const r = createJobRegistry();
    const id = r.start('video', 'Video lesson');
    const job = r.get(id);
    check('get returns the job', job && job.tool === 'video' && job.status === 'running');

    job.pct = 99;
    job.status = 'done';
    check('mutating the returned copy does not touch the registry',
        r.summary().pct === 0 && r.summary().status === 'running',
        r.summary().pct + ' / ' + r.summary().status);

    check('get on an unknown id returns null', r.get(9999) === null);
    r.drop(id);
    check('get on a dropped id returns null', r.get(id) === null);
}

// == the video path must not hand the Space's job id to the registry =============
// Static check, because this one cannot be caught dynamically without a live Manim
// render — and it shipped once already. vidGenerateManim binds the registry id at
// FUNCTION scope, but further down, INSIDE the try block that wraps the whole poll
// loop, the Space's own render-job id is bound as `const jobId`. Anything inside
// that block calling stJobs.*/stJobFinish(jobId) therefore silently gets a job-id
// STRING instead of the registry's number: stJobs.get() returns null, stJobFinish
// early-returns, and the badge sticks at 100% with no tick and no notification while
// progress keeps working (setPct closes over the outer binding). Hence the distinct
// name — this asserts nobody renames it back.
{
    const vid = slice('async function vidGenerateManim(opts) {', '/* ---------- video: generate ---------- */');

    check('video path binds its registry id as stJobId',
        /const stJobId\s*=\s*stJobs\.start\(/.test(vid));
    check('the Space render-job id is still bound as jobId (shadowing premise holds)',
        /const jobId\s*=\s*job\.job_id\s*;/.test(vid),
        'if this moved/renamed, revisit why stJobId exists');
    check('registry calls never take the Space job id',
        !/stJobs\.(update|finish|drop|get)\(\s*jobId\b/.test(vid) && !/stJobFinish\(\s*jobId\b/.test(vid),
        'stJobs.*/stJobFinish must be passed stJobId, never jobId');
    check('the completion path settles the registry job',
        /stJobFinish\(\s*stJobId\s*,\s*true\s*\)/.test(vid));
    check('the failure path settles the registry job',
        /stJobFinish\(\s*stJobId\s*,\s*false\s*\)/.test(vid));

    // A cosmetic wait() between real completion and stJobFinish is throttled to
    // ~1/min by a hidden tab, stalling the badge and delaying the notification past
    // the point of use. It must stay gated on someone actually watching.
    check('the 100% settle pause is skipped while the user is away',
        /if\s*\(\s*!stAway\(\)\s*\)\s*await wait\(/.test(vid),
        'a cosmetic delay must not gate a background job finishing');
}

// runTool's ordering is the counterpart: it must settle the job BEFORE its own
// cosmetic wait, for the same reason.
{
    const rt = slice('async function runTool(name, steps, task) {', 'WORKSHEET');
    const finishAt = rt.indexOf('stJobFinish(jobId, true)');
    const waitAt = rt.indexOf('await wait(');
    check('runTool settles the job before its cosmetic wait',
        finishAt > 0 && waitAt > 0 && finishAt < waitAt,
        'stJobFinish must precede await wait() so a hidden tab cannot stall it');
}

console.log('');
if (failures) {
    console.log(failures + ' STUDY PROGRESS CASE(S) FAIL');
    process.exit(1);
}
console.log('ALL STUDY PROGRESS CASES PASS');
