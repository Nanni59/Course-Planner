// Regression test for the saved-video backup honesty behavior (AUDIT P1-4,
// honesty fix): saved videos are metadata in localStorage (cp_study_videos)
// plus an MP4 blob in IndexedDB (cp_study_media); JSON backups carry ONLY the
// metadata. The real exportData()/importData()/countSavedVideoEntries() and
// the real markVideoRowMissing()/annotateMissingVideos() are extracted from
// index.html by string markers and run against stubs.
//
// Covers:
//   - no warning when no saved videos exist / empty array / malformed value /
//     entries without ids
//   - warning fires when >=1 valid saved-video metadata entry exists
//   - exported JSON still contains the metadata, and no MP4/base64 payload
//   - import containing video metadata reports the limitation in ONE combined
//     success alert and still reloads; without video metadata the original
//     message is unchanged
//   - a failed (rolled-back) import shows the failure alert, not the video note
//   - missing IndexedDB blob => row marked unavailable (no broken player path);
//     existing blob => row untouched
//   - malformed cp_study_videos does not crash annotation
//   - deleting a video entry whose blob is absent still removes the metadata
//
// Run: node tools/saved_video_backup_test.js   (exit 0 = pass)
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

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}

// =============================================================================
// Part A — export/import notices (main planner scope)
// =============================================================================
const backupSrc = slice('function exportData() {', '// Backup tab specific listeners');

function makeLocalStorage() {
    const order = [], map = new Map();
    return {
        get length() { return order.length; },
        key(i) { return i >= 0 && i < order.length ? order[i] : null; },
        getItem(k) { return map.has(String(k)) ? map.get(String(k)) : null; },
        setItem(k, v) { k = String(k); if (!map.has(k)) order.push(k); map.set(k, String(v)); },
        removeItem(k) { k = String(k); if (map.delete(k)) order.splice(order.indexOf(k), 1); },
        clear() { map.clear(); order.length = 0; },
    };
}

function makeHarness(localStorage) {
    let exportedText = null, reloaded = false, confirmCb = null;
    const alerts = [];
    class Blob { constructor(parts) { this._text = parts.join(''); } }
    const URL = { createObjectURL(b) { exportedText = b._text; return 'blob:stub'; }, revokeObjectURL() { } };
    const document = {
        body: { appendChild() { }, removeChild() { } },
        createElement() { return { click() { }, set href(v) { }, set download(v) { } }; },
    };
    class FileReader { readAsText(f) { this.onload({ target: { result: f._content } }); } }
    function showAppConfirm(m, cb) { confirmCb = cb; }
    function alert(m) { alerts.push(String(m)); }
    const window = { location: { reload() { reloaded = true; } } };
    const consoleStub = { error() { }, warn() { }, log() { } };
    const fns = new Function(
        'localStorage', 'Blob', 'URL', 'document', 'FileReader',
        'showAppConfirm', 'alert', 'window', 'console', 'LS_LESSON_LINKS_KEY',
        backupSrc + '\nreturn { exportData, importData, countSavedVideoEntries };'
    )(localStorage, Blob, URL, document, FileReader, showAppConfirm, alert, window, consoleStub, 'lesson_links');
    return {
        ...fns, alerts,
        getExportedText: () => exportedText,
        wasReloaded: () => reloaded,
        confirm() { const cb = confirmCb; confirmCb = null; try { cb(); return null; } catch (e) { return e; } },
    };
}
const importEvent = c => ({ target: { files: [{ _content: c }], value: '' } });
const VID_META = [{ id: 'v1712', topic: "Newton's Second Law", captions: [{ text: 'F = ma', start: 0 }], createdAt: 1720000000000 }];

// -- export: cases that must NOT warn -----------------------------------------
for (const [label, value] of [
    ['no cp_study_videos key', undefined],
    ['empty saved-video array', '[]'],
    ['malformed cp_study_videos value', '{definitely not json'],
    ['array with no valid entries', JSON.stringify([null, 'x', { topic: 'no id' }])],
]) {
    const ls = makeLocalStorage();
    ls.setItem('cp_theme', 'dark');
    if (value !== undefined) ls.setItem('cp_study_videos', value);
    const h = makeHarness(ls);
    let crashed = false;
    try { h.exportData(); } catch (e) { crashed = true; }
    check('export (' + label + '): no crash and no warning', !crashed && h.alerts.length === 0);
    check('export (' + label + '): backup still produced', typeof h.getExportedText() === 'string');
}

// -- export: one valid entry warns, metadata intact, no media payload ---------
{
    const ls = makeLocalStorage();
    ls.setItem('cp_theme', 'dark');
    ls.setItem('cp_study_videos', JSON.stringify(VID_META));
    const h = makeHarness(ls);
    h.exportData();
    check('export (1 video): exactly one notice', h.alerts.length === 1);
    check('export (1 video): notice says MP4s are NOT in the JSON',
        /MP4/.test(h.alerts[0] || '') && /NOT inside the JSON/i.test(h.alerts[0] || ''));
    check('export (1 video): notice gives per-video transfer guidance', /download/i.test(h.alerts[0] || ''));
    check('export (1 video): notice affirms other data IS included', /fully included/i.test(h.alerts[0] || ''));
    const backup = JSON.parse(h.getExportedText());
    check('export (1 video): metadata still present and exact',
        JSON.stringify(backup.cp_study_videos) === JSON.stringify(VID_META));
    check('export (1 video): no MP4 bytes or media payload in the JSON',
        !/data:video|base64|"blob"|ArrayBuffer/i.test(h.getExportedText()));
}

// -- import: video metadata present => combined limitation+success message ----
{
    const ls = makeLocalStorage();
    const h = makeHarness(ls);
    const backup = JSON.stringify({ cp_theme: 'dark', cp_study_videos: VID_META, lesson_links: {} });
    h.importData(importEvent(backup));
    const escaped = h.confirm();
    check('import (with videos): handled, reloads', escaped === null && h.wasReloaded());
    check('import (with videos): single combined alert', h.alerts.length === 1);
    check('import (with videos): success is still reported',
        /imported successfully/i.test(h.alerts[0] || '') && /reload/i.test(h.alerts[0] || ''));
    check('import (with videos): limitation stated, no full-restore claim',
        /metadata only/i.test(h.alerts[0] || '') && /don’t contain the MP4|don't contain the MP4/i.test(h.alerts[0] || ''));
    check('import (with videos): metadata preserved in storage',
        ls.getItem('cp_study_videos') === JSON.stringify(VID_META));
}

// -- import: no video metadata => original message unchanged ------------------
{
    const ls = makeLocalStorage();
    const h = makeHarness(ls);
    h.importData(importEvent(JSON.stringify({ cp_theme: 'dark', lesson_links: {} })));
    h.confirm();
    check('import (no videos): classic success message unchanged',
        h.alerts.length === 1 && h.alerts[0] === 'Data imported successfully. The page will now reload to apply changes.');
}

// -- import: failed restore still rolls back; failure alert, no video note ----
{
    const ls = makeLocalStorage();
    ls.setItem('probe', 'before');
    const h = makeHarness(ls);
    h.importData(importEvent(JSON.stringify({ a: '1', b: '2', cp_study_videos: VID_META })));
    let writes = 0;
    const realSet = ls.setItem.bind(ls);
    ls.setItem = (k, v) => { if (++writes === 2) throw new Error('QuotaExceededError (simulated)'); realSet(k, v); };
    const escaped = h.confirm();
    ls.setItem = realSet;
    check('import failure (with videos): rollback intact, no reload, handled',
        ls.getItem('probe') === 'before' && ls.length === 1 && !h.wasReloaded() && escaped === null);
    check('import failure (with videos): failure alert only, no video note',
        h.alerts.length === 1 && /import failed/i.test(h.alerts[0]) && !/metadata only/i.test(h.alerts[0]));
}

// =============================================================================
// Part B — unavailable-video row annotation (Study Tools scope)
// =============================================================================
const annotateSrc = slice('function markVideoRowMissing(id) {', 'function renderSaved(kind)');
// the real one-line readJSON implementation
const readJSONLine = html.split('\n').find(l => l.includes('function readJSON(k)'));
if (!readJSONLine) throw new Error('marker not found: function readJSON(k)');

function makeRow(kind, id) {
    const sub = { html: 'Manim video · 7/13/2026', insertAdjacentHTML(pos, h) { this.html += h; } };
    return {
        kind, id, attrs: {},
        hasAttribute(k) { return k in this.attrs; },
        setAttribute(k, v) { this.attrs[k] = v; },
        querySelector(sel) { return sel === '.st-sr-sub' ? sub : null; },
        sub,
    };
}

function makeAnnotateEnv(rows, storedVideosRaw, blobsById) {
    const root = {
        querySelectorAll(sel) {
            const m = sel.match(/data-sid="([^"]+)"/);
            return rows.filter(r => r.kind === 'video' && (!m || r.id === m[1]));
        },
    };
    const localStorage = { getItem: k => (k === 'cp_study_videos' ? storedVideosRaw : null) };
    const vidIdbGet = id => Promise.resolve(blobsById[id]);
    return new Function(
        'root', 'readJSON', 'ST_VIDEOS', 'vidIdbGet', 'indexedDB', 'localStorage',
        readJSONLine + '\n' + annotateSrc + '\nreturn { markVideoRowMissing, annotateMissingVideos };'
    )(root, undefined, 'cp_study_videos', vidIdbGet, {}, localStorage);
}
const flush = () => new Promise(r => setTimeout(r, 0));

(async () => {
    // -- missing blob => unavailable state ------------------------------------
    {
        const rows = [makeRow('video', 'v1'), makeRow('video', 'v2'), makeRow('ws', 'w1')];
        const env = makeAnnotateEnv(rows, JSON.stringify([{ id: 'v1' }, { id: 'v2' }]), { v2: { size: 9 } });
        env.annotateMissingVideos();
        await flush();
        check('annotate: missing blob marks the row unavailable',
            rows[0].attrs['data-vid-missing'] === '1' && /video file not in this browser/.test(rows[0].sub.html));
        check('annotate: existing blob leaves its row untouched',
            !('data-vid-missing' in rows[1].attrs) && !/not in this browser/.test(rows[1].sub.html));
        check('annotate: non-video rows untouched', !('data-vid-missing' in rows[2].attrs));
        // idempotent on re-run (rows are re-annotated after every list repaint)
        env.markVideoRowMissing('v1');
        check('annotate: marking is idempotent (no duplicate note)',
            (rows[0].sub.html.match(/not in this browser/g) || []).length === 1);
    }
    // -- malformed metadata must not crash -------------------------------------
    {
        const rows = [makeRow('video', 'v1')];
        const env = makeAnnotateEnv(rows, '{broken json', {});
        let crashed = false;
        try { env.annotateMissingVideos(); await flush(); } catch (e) { crashed = true; }
        check('annotate: malformed cp_study_videos does not crash', !crashed);
        const env2 = makeAnnotateEnv(rows, JSON.stringify([null, 'x', {}]), {});
        try { env2.annotateMissingVideos(); await flush(); } catch (e) { crashed = true; }
        check('annotate: junk entries are skipped without crash', !crashed);
    }
    // -- deleting an unavailable entry still removes the metadata --------------
    {
        const deleteSrc = slice('function deleteItem(kind, id) {', 'const SAVE_NOUN');
        const store = { cp_study_videos: JSON.stringify([{ id: 'v1', topic: 'gone' }, { id: 'v2', topic: 'kept' }]) };
        const localStorage = {
            getItem: k => (k in store ? store[k] : null),
            setItem: (k, v) => { store[k] = String(v); },
        };
        const vidIdbDel = () => Promise.reject(new Error('no such blob')).catch(() => { }); // blob absent
        const deleteItem = new Function(
            'localStorage', 'readJSON', 'SAVE_KEYS', 'vidIdbDel', 'renderSaved',
            readJSONLine + '\n' + deleteSrc + '\nreturn deleteItem;'
        )(localStorage, undefined, { video: 'cp_study_videos' }, vidIdbDel, () => { });
        let crashed = false;
        try { deleteItem('video', 'v1'); } catch (e) { crashed = true; }
        await flush();
        check('delete: unavailable entry removed without crash',
            !crashed && store.cp_study_videos === JSON.stringify([{ id: 'v2', topic: 'kept' }]));
    }

    console.log('');
    if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
    console.log('ALL SAVED-VIDEO BACKUP CASES PASS');
})();
