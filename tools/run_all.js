// Runs every regression suite (existing + new) and exits non-zero if any
// suite fails — a non-zero exit here always means a real regression.
//
// Run: node tools/run_all.js
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');

const ROOT = path.join(__dirname, '..');

const SUITES = [
    { cmd: 'node', args: ['tools/worksheet_text_harness.js'] },
    { cmd: 'node', args: ['tools/worksheet_visual_gate_test.js'] },
    { cmd: 'node', args: ['tools/worksheet_visual_render_all_test.js'] },
    { cmd: 'node', args: ['tools/backup_roundtrip_test.js'] },
    { cmd: 'node', args: ['tools/saved_video_backup_test.js'] },
    { cmd: 'node', args: ['tools/svg_sanitization_test.js'] },
    { cmd: 'node', args: ['tools/calendar_recurrence_test.js'] },
    { cmd: 'node', args: ['tools/tracker_day_sync_test.js'] },
    { cmd: 'node', args: ['tools/question_ocr_test.js'] },
    { cmd: 'node', args: ['tools/study_progress_test.js'] },
    { cmd: 'python', args: ['tools/worksheet_visual_route_test.py'], fallbackCmd: 'python3' },
];

function runSuite(s) {
    let r = spawnSync(s.cmd, s.args, { cwd: ROOT, encoding: 'utf8', shell: false });
    if (r.error && r.error.code === 'ENOENT' && s.fallbackCmd) {
        r = spawnSync(s.fallbackCmd, s.args, { cwd: ROOT, encoding: 'utf8', shell: false });
    }
    return r;
}

let failed = 0;
const results = [];
for (const s of SUITES) {
    const label = s.args[s.args.length - 1];
    const r = runSuite(s);
    const ok = !r.error && r.status === 0;
    if (!ok) failed++;
    results.push({ label, ok });
    console.log('===== ' + label + ' =====');
    if (r.error) {
        console.log('COULD NOT RUN: ' + r.error.message);
    } else {
        // print each suite's own tail so xfail/summary lines stay visible
        const out = ((r.stdout || '') + (r.stderr || '')).trim().split('\n');
        console.log(out.slice(-4).join('\n'));
    }
    console.log('');
}

console.log('================ SUMMARY ================');
for (const x of results) console.log((x.ok ? 'PASS ' : 'FAIL ') + ' ' + x.label);
console.log('==========================================');
if (failed) {
    console.log(failed + ' suite(s) failed.');
    process.exit(1);
}
console.log('All ' + results.length + ' suites passed.');
