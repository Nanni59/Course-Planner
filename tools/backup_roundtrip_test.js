// Regression test for the JSON backup logic in index.html: the REAL exportData()
// and importData() are extracted by string markers (same approach as
// worksheet_text_harness.js) and run against a stubbed localStorage/DOM.
//
// Covers:
//   1. export -> import round trip preserves every key/value pair
//   2. unrelated (unknown-to-the-app) keys survive the round trip
//   3. malformed input is rejected BEFORE existing data is cleared
//   4. cancelling (never invoking) the confirmation leaves storage untouched
//   5. transactional import (the AUDIT P1-1 fix): a failure during the DEFERRED
//      restore — on the first write or after several writes — rolls back to the
//      exact previous store, surfaces an error, does not reload, and does not
//      escape as an uncaught exception
//   6. keys existing only in the failed backup are removed by the rollback
//   7. an initially empty store returns to empty after a failed import
//   8. if rollback itself also fails, BOTH errors are reported (alert + console)
//      and no false "data restored" claim is made
//   9. export's lesson_links compatibility injection is unchanged
//
// Fidelity note: in the real app, showAppConfirm() runs its callback on a later
// button click — OUTSIDE importData's try/catch and after importData has
// returned. The stub models exactly that: it only CAPTURES the callback;
// each test invokes it explicitly via h.confirm(), which also records whether
// an exception escaped the callback (an escaped exception here corresponds to
// an uncaught error in production). This cleanly separates:
//   - parse/validation failures BEFORE confirmation (alert fires inside
//     importData; no confirm dialog is ever shown), from
//   - restore failures LATER inside the confirmation callback.
//
// Run: node tools/backup_roundtrip_test.js   (exit 0 = pass)
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

// ---- extract the real code -------------------------------------------------
const src = slice('function exportData() {', '// Backup tab specific listeners');

// ---- stubs ------------------------------------------------------------------
function makeLocalStorage() {
    const order = []; // insertion order, backs key(i)/length like the real thing
    const map = new Map();
    return {
        get length() { return order.length; },
        key(i) { return i >= 0 && i < order.length ? order[i] : null; },
        getItem(k) { return map.has(String(k)) ? map.get(String(k)) : null; },
        setItem(k, v) {
            k = String(k);
            if (!map.has(k)) order.push(k);
            map.set(k, String(v)); // real localStorage coerces to string
        },
        removeItem(k) {
            k = String(k);
            if (map.delete(k)) order.splice(order.indexOf(k), 1);
        },
        clear() { map.clear(); order.length = 0; },
        // test helpers (not part of the real API; underscore-prefixed)
        _snapshot() { return order.map(k => [k, map.get(k)]); },
    };
}

function makeHarness(localStorage) {
    let exportedText = null;   // captured JSON written to the download Blob
    const alerts = [];
    let reloaded = false;
    let confirmMessage = null;
    let confirmCb = null;      // captured, NOT invoked — mirrors the real modal
    const consoleErrors = [];

    class Blob {
        constructor(parts) { this._text = parts.join(''); }
    }
    const URL = {
        createObjectURL(blob) { exportedText = blob._text; return 'blob:stub'; },
        revokeObjectURL() { },
    };
    const document = {
        body: { appendChild() { }, removeChild() { } },
        createElement() { return { click() { }, set href(v) { }, set download(v) { } }; },
    };
    class FileReader {
        readAsText(file) { this.onload({ target: { result: file._content } }); }
    }
    function showAppConfirm(message, onConfirm) { confirmMessage = message; confirmCb = onConfirm; }
    function alert(msg) { alerts.push(String(msg)); }
    const window = { location: { reload() { reloaded = true; } } };
    const consoleStub = {
        error(...args) { consoleErrors.push(args.map(String).join(' ')); },
        warn() { }, log() { },
    };
    const LS_LESSON_LINKS_KEY = 'lesson_links'; // matches index.html:5576

    const fns = new Function(
        'localStorage', 'Blob', 'URL', 'document', 'FileReader',
        'showAppConfirm', 'alert', 'window', 'console', 'LS_LESSON_LINKS_KEY',
        src + '\nreturn { exportData, importData };'
    )(localStorage, Blob, URL, document, FileReader, showAppConfirm, alert, window, consoleStub, LS_LESSON_LINKS_KEY);

    return {
        exportData: fns.exportData,
        importData: fns.importData,
        getExportedText: () => exportedText,
        alerts,
        consoleErrors,
        wasReloaded: () => reloaded,
        getConfirmMessage: () => confirmMessage,
        hasPendingConfirm: () => confirmCb !== null,
        // Invoke the captured confirmation callback the way a later user click
        // would. Returns the exception that ESCAPED the callback (uncaught in
        // production), or null if it completed/handled its own errors.
        confirm() {
            if (!confirmCb) throw new Error('no confirmation callback was captured');
            const cb = confirmCb; confirmCb = null;
            try { cb(); return null; } catch (e) { return e; }
        },
    };
}

function makeImportEvent(fileContent) {
    return { target: { files: [{ _content: fileContent }], value: 'stale' } };
}

// ---- assertions --------------------------------------------------------------
let failures = 0;
function check(name, cond, detail) {
    if (cond) { console.log('PASS  ' + name); }
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}
function snapshotsEqual(a, b) {
    if (a.length !== b.length) return false;
    const bm = new Map(b);
    return a.every(([k, v]) => bm.get(k) === v);
}

// ---- seed data resembling real app state ------------------------------------
function seed(ls) {
    ls.setItem('tracker_lessons', JSON.stringify([{ id: 'l1', course: 'Calculus & Vectors', name: 'Unit 3 Lesson 2', status: 'Finished' }]));
    ls.setItem('tracker_assignments', JSON.stringify([{ id: 'a1', course: 'English', name: 'Essay Draft', status: 'Not Started' }]));
    ls.setItem('split_assignments', JSON.stringify({ 'English||Essay Draft': { totalDays: 3, completedDays: 1 } }));
    ls.setItem('cp_theme', 'dark');                       // plain string, not JSON
    ls.setItem('selectedDay', 'dayB');                    // plain string
    ls.setItem('cp_calendar_items_v1', JSON.stringify([{ id: 'cal_x', title: 'Quiz', startDate: '2026-07-14', type: 'task' }]));
    ls.setItem('someFutureFeatureKey', JSON.stringify({ nested: { deep: [1, 2, 3] } })); // unrelated/unknown key
    // exportData() deliberately injects lesson_links:{} when absent (index.html
    // "Ensure lesson_links is included in export"), so seed it for identity checks;
    // the injection itself is asserted in its own case below.
    ls.setItem('lesson_links', JSON.stringify({}));
}

// == 1 & 2: export -> import round trip (incl. unrelated key) ==================
{
    const ls = makeLocalStorage();
    seed(ls);
    const original = ls._snapshot();

    const h1 = makeHarness(ls);
    h1.exportData();
    const backup = h1.getExportedText();
    check('export produced JSON', typeof backup === 'string' && backup.length > 0);
    check('export parses as an object', (() => { try { const o = JSON.parse(backup); return o && typeof o === 'object'; } catch (e) { return false; } })());

    // simulate a different browser profile: unrelated residue that import must wipe
    ls.clear();
    ls.setItem('residueKey', 'stale-value');
    ls.setItem('cp_theme', 'light');

    const h2 = makeHarness(ls);
    h2.importData(makeImportEvent(backup));
    check('import asked for confirmation', h2.getConfirmMessage() !== null);
    check('storage untouched until the user confirms', ls.getItem('residueKey') === 'stale-value' && !h2.wasReloaded());
    const escaped = h2.confirm(); // the later user click
    check('confirmation callback completed without uncaught error', escaped === null, escaped && escaped.message);
    check('import reloads on success', h2.wasReloaded());
    const restored = ls._snapshot();
    check('round trip preserves every key/value pair', snapshotsEqual(original, restored),
        JSON.stringify({ original, restored }).slice(0, 300));
    check('unrelated key survives the round trip', ls.getItem('someFutureFeatureKey') === JSON.stringify({ nested: { deep: [1, 2, 3] } }));
    check('pre-import residue is fully replaced', ls.getItem('residueKey') === null);
}

// == export injects lesson_links when absent (intentional app behavior) ========
{
    const ls = makeLocalStorage();
    ls.setItem('cp_theme', 'dark'); // no lesson_links seeded
    const h = makeHarness(ls);
    h.exportData();
    const backup = JSON.parse(h.getExportedText());
    check('export injects empty lesson_links when absent', JSON.stringify(backup.lesson_links) === '{}');
}

// == 3a: malformed JSON rejected before data is cleared ========================
{
    const ls = makeLocalStorage();
    seed(ls);
    const before = ls._snapshot();
    const h = makeHarness(ls);
    h.importData(makeImportEvent('this is { not valid json'));
    check('malformed JSON: existing data untouched', snapshotsEqual(before, ls._snapshot()));
    check('malformed JSON: user sees an error, no confirm dialog', h.alerts.length === 1 && h.getConfirmMessage() === null);
    check('malformed JSON: no reload', !h.wasReloaded());
}

// == 3b: valid JSON but not an object rejected before clear ====================
{
    const ls = makeLocalStorage();
    seed(ls);
    const before = ls._snapshot();
    const h = makeHarness(ls);
    h.importData(makeImportEvent('42'));
    check('non-object backup: existing data untouched', snapshotsEqual(before, ls._snapshot()));
    check('non-object backup: rejected with error', h.alerts.length === 1);
}

// == 4: cancelled confirmation leaves storage untouched =========================
{
    const ls = makeLocalStorage();
    seed(ls);
    const before = ls._snapshot();
    const hExp = makeHarness(ls);
    hExp.exportData();
    const h = makeHarness(ls);
    h.importData(makeImportEvent(hExp.getExportedText()));
    check('cancel: confirmation was offered', h.hasPendingConfirm());
    // the user presses Cancel / closes the modal: the callback is never invoked
    check('cancel: storage untouched', snapshotsEqual(before, ls._snapshot()));
    check('cancel: no reload', !h.wasReloaded());
}

// helper for the failure cases: seed a store, export a backup, start an import,
// then invoke the deferred confirmation with setItem rigged to throw on the
// given write numbers (counted across restore AND rollback writes).
function runFailedImport(opts) {
    opts = opts || {};
    const ls = makeLocalStorage();
    if (opts.seedStore !== false) seed(ls);
    const before = ls._snapshot();

    const hExp = makeHarness(ls);
    hExp.exportData();
    let backup = opts.backup || hExp.getExportedText();
    if (opts.extraBackupKey) {
        // inject a key that exists ONLY in the backup, first in restore order
        backup = JSON.stringify(Object.assign({ [opts.extraBackupKey]: 'backup-only' }, JSON.parse(backup)));
    }

    const h = makeHarness(ls);
    h.importData(makeImportEvent(backup)); // returns with the callback still pending
    const setupOk = h.hasPendingConfirm() && snapshotsEqual(before, ls._snapshot());

    const failOn = new Set(opts.failOnWrites);
    let writes = 0;
    const realSet = ls.setItem.bind(ls);
    ls.setItem = (k, v) => {
        writes++;
        if (failOn.has(writes)) { const e = new Error('QuotaExceededError (simulated)'); e.name = 'QuotaExceededError'; throw e; }
        realSet(k, v);
    };
    const escaped = h.confirm();
    ls.setItem = realSet;
    return { ls, before, h, escaped, setupOk };
}

// == 5a: failure on the FIRST imported write rolls back losslessly =============
{
    const r = runFailedImport({ failOnWrites: [1] });
    check('first-write failure: setup sane (deferred, untouched)', r.setupOk);
    check('first-write failure: previous data fully restored', snapshotsEqual(r.before, r.ls._snapshot()),
        'storage has ' + r.ls.length + ' of ' + r.before.length + ' keys');
    check('first-write failure: user told import failed and data restored',
        r.h.alerts.length === 1 && /import failed/i.test(r.h.alerts[0]) && /previous data has been restored/i.test(r.h.alerts[0]));
    check('first-write failure: handled, not uncaught', r.escaped === null, r.escaped && r.escaped.message);
    check('first-write failure: no reload', !r.h.wasReloaded());
}

// == 5b: failure after several imported writes rolls back losslessly ===========
{
    const r = runFailedImport({ failOnWrites: [4] });
    check('mid-restore failure: previous data fully restored', snapshotsEqual(r.before, r.ls._snapshot()),
        'storage has ' + r.ls.length + ' of ' + r.before.length + ' keys');
    check('mid-restore failure: user told import failed and data restored',
        r.h.alerts.length === 1 && /import failed/i.test(r.h.alerts[0]) && /previous data has been restored/i.test(r.h.alerts[0]));
    check('mid-restore failure: handled, not uncaught', r.escaped === null, r.escaped && r.escaped.message);
    check('mid-restore failure: no reload', !r.h.wasReloaded());
}

// == 6: keys existing only in the failed backup are removed by rollback ========
{
    // 'onlyInBackupKey' is written FIRST during restore (write 1 succeeds),
    // then write 3 fails — rollback must remove it again.
    const r = runFailedImport({ extraBackupKey: 'onlyInBackupKey', failOnWrites: [3] });
    check('rollback removes keys that exist only in the failed backup',
        r.ls.getItem('onlyInBackupKey') === null);
    check('rollback after partial import restores the exact previous store',
        snapshotsEqual(r.before, r.ls._snapshot()));
}

// == 7: initially empty store returns to empty after a failed import ===========
{
    const seeded = makeLocalStorage();
    seed(seeded);
    const hSeed = makeHarness(seeded);
    hSeed.exportData();
    const r = runFailedImport({ seedStore: false, backup: hSeed.getExportedText(), failOnWrites: [2] });
    check('empty store: rollback returns to empty', r.ls.length === 0);
    check('empty store: failure surfaced, handled, no reload',
        r.h.alerts.length === 1 && r.escaped === null && !r.h.wasReloaded());
}

// == 8: rollback itself fails -> both errors reported, no false recovery claim ==
{
    // write 3 kills the restore; rollback replays the 8-key snapshot and its
    // 2nd replay write (overall write 5) fails too.
    const r = runFailedImport({ failOnWrites: [3, 5] });
    check('double failure: single combined alert', r.h.alerts.length === 1);
    check('double failure: alert reports the import failure', /import failed/i.test(r.h.alerts[0] || ''));
    check('double failure: alert reports that recovery ALSO failed', /automatic recovery also failed/i.test(r.h.alerts[0] || ''));
    check('double failure: no false "data restored" claim', !/previous data has been restored/i.test(r.h.alerts[0] || ''));
    check('double failure: both errors logged to console', r.h.consoleErrors.length === 2 &&
        /import failed/i.test(r.h.consoleErrors[0]) && /rollback also failed/i.test(r.h.consoleErrors[1]));
    check('double failure: handled, not uncaught', r.escaped === null, r.escaped && r.escaped.message);
    check('double failure: no reload', !r.h.wasReloaded());
}

// ---- summary -----------------------------------------------------------------
console.log('');
if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
console.log('ALL BACKUP CASES PASS');
