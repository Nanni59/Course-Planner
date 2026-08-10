// Shared harness for the exam↔course integration suites.
//
// Runs the REAL Exam Prep engine IIFE from index.html inside a vm sandbox, wired
// to a faithful in-memory Calendar bridge built from the REAL Calendar functions
// (normalize + cpGetExamCalendarItems + cpReconcileExamCalendar +
// cpSetExamCalendarCourse + cpCalendarReload + cpGetCourseCalendarUpcoming) that
// the app installs on window. Both share ONE localStorage stub, so the exam
// engine's transactional snapshot/rollback runs against the same strings the app
// would touch. A controllable roster stands in for window.cpGetCourses.
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

function slice(startMarker, endMarker) {
    const a = html.indexOf(startMarker);
    const b = html.indexOf(endMarker, a);
    if (a < 0 || b < 0) throw new Error('marker not found: ' + startMarker + ' / ' + endMarker);
    return html.slice(a, b);
}

// --- exam engine IIFE (identical extraction to exam_prep_test.js) ------------
const marker = 'EXAM PREP ENGINE — SAT and IELTS remain separate local-first sections.';
const markerAt = html.indexOf(marker);
if (markerAt < 0) throw new Error('Exam Prep engine marker not found');
const examStart = html.indexOf('(function(){', markerAt);
const examEnd = html.indexOf('\n    })();', examStart);
if (examStart < 0 || examEnd < 0) throw new Error('Exam Prep engine boundaries not found');
const examSource = html.slice(examStart, examEnd + '\n    })();'.length);

// --- real Calendar bridge pieces --------------------------------------------
const realNormalize = slice('    function normalize(x){', '\n    // Category colours are interpolated');
const realGetItems = slice('    window.cpGetExamCalendarItems=exam=>{', '\n    window.cpUpsertExamCalendarItems');
const realReconcile = slice('    window.cpReconcileExamCalendar=(exam,records,validLinkIds)=>{', '\n    // Upcoming generated records');
const realSetCourse = slice('    window.cpSetExamCalendarCourse=(exam,courseId,courseName)=>{', '\n    // Refresh only the denormalized');
const realReload = slice('    window.cpCalendarReload=()=>{', '\n    // Stamp (or clear');
const realUpcoming = slice('    window.cpGetCourseCalendarUpcoming=(courseId,limit)=>{', '\n    // Day A/B Autofill');
const realRemove = slice('    window.cpRemoveExamCalendarItems=exam=>{', '\n    // Reload the persisted Calendar');

// A tiny Calendar host: real normalize/reconcile logic over a localStorage-backed
// S.items, with the DOM-facing bits (root/render/notify) stubbed out.
const prelude = `
    let S = { items: [] };
    const root = { classList: { contains: () => false } };
    function render() {}
    function notifyExamCalendar() {}
    let __seq = 0;
    function id() { return 'cal_test_' + (++__seq); }
    function ds(d){ const p = n => String(n).padStart(2,'0'); return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate()); }
    function load(){ let raw = []; try { raw = JSON.parse(localStorage.getItem('cp_calendar_items_v1')) || []; } catch(e){ raw = []; } S.items = raw.map(normalize).filter(Boolean); }
    function save(){ localStorage.setItem('cp_calendar_items_v1', JSON.stringify(S.items)); }
    let __ROSTER = [];
    window.__setRoster = list => { __ROSTER = Array.isArray(list) ? list : []; };
    window.cpGetCourses = () => __ROSTER.map(c => ({ id: c.id, name: c.name, days: (c.days || []).slice() }));
`;

function storageStub(seed = {}) {
    const map = new Map(Object.entries(seed).map(([k, v]) => [k, typeof v === 'string' ? v : JSON.stringify(v)]));
    let failSpec = null; // { key, n, count } — throw on the nth setItem for `key`
    return {
        getItem: k => map.has(k) ? map.get(k) : null,
        setItem: (k, v) => {
            if (failSpec && k === failSpec.key) {
                failSpec.count++;
                if (failSpec.count >= failSpec.n) { failSpec = null; throw new Error('QuotaExceededError'); }
            }
            map.set(String(k), String(v));
        },
        removeItem: k => map.delete(k),
        _failOnKey: (k, n) => { failSpec = { key: k, n: n || 1, count: 0 }; },
        _clearFail: () => { failSpec = null; },
        key: i => Array.from(map.keys())[i],
        get length() { return map.size; },
        _json: k => { const v = map.get(k); return v == null ? null : JSON.parse(v); },
        _raw: k => (map.has(k) ? map.get(k) : null),
        _snapshot: () => Object.fromEntries(map),
        _keys: () => Array.from(map.keys())
    };
}

// Builds a fresh sandbox. `seed` seeds localStorage; `roster` is the course list
// window.cpGetCourses returns. Returns handles for driving and inspecting it.
function buildSandbox(seed = {}, roster = []) {
    const localStorage = storageStub(seed);
    const roots = {
        satPrep: { classList: { contains: () => false } },
        ieltsPrep: { classList: { contains: () => false } }
    };
    // A working event bus so tests can faithfully simulate the engine reloading
    // its in-memory SAT/IELTS after a storage change (the real 'storage' listener).
    const listeners = {};
    const windowStub = {
        addEventListener(type, fn) { (listeners[type] || (listeners[type] = [])).push(fn); },
        dispatchEvent(evt) { (listeners[evt && evt.type] || []).slice().forEach(fn => fn(evt)); return true; }
    };
    function CustomEventCtor(type, init) { this.type = type; this.detail = init && init.detail; }
    const context = {
        window: windowStub,
        localStorage,
        document: { getElementById: id => roots[id] || null, querySelector: () => null },
        console, URL, Date, Math, JSON, Object, Array, String, Number, Set, Map, RegExp, Boolean,
        setTimeout() {}, clearTimeout() {}, requestAnimationFrame() {}, CustomEvent: CustomEventCtor
    };
    const source = prelude + '\n' + realNormalize + '\n' + realGetItems + realReconcile
        + realSetCourse + realReload + realUpcoming + realRemove + '\n' + examSource;
    vm.runInNewContext(source, context, { filename: 'exam-integration-sandbox.js' });
    windowStub.__setRoster(roster);
    return {
        window: windowStub,
        api: windowStub.cpExamPrepTest,
        localStorage,
        setRoster: list => windowStub.__setRoster(list),
        // Simulate a storage change so the engine reloads its in-memory prep state,
        // exactly as its real 'storage' listener does (cross-tab / external edit).
        fireStorage: key => windowStub.dispatchEvent({ type: 'storage', key }),
        // Inject a one-shot storage-write failure to exercise rollback: the nth
        // setItem for `key` throws QuotaExceededError, then the hook clears.
        failOnKey: (key, n) => localStorage._failOnKey(key, n),
        clearFail: () => localStorage._clearFail(),
        snapshot: () => localStorage._snapshot(),
        raw: key => localStorage._raw(key),
        calItems: () => localStorage._json('cp_calendar_items_v1') || [],
        sat: () => localStorage._json('cp_satPrep_v1'),
        ielts: () => localStorage._json('cp_ieltsPrep_v1'),
        links: () => localStorage._json('cp_exam_course_links_v1')
    };
}

module.exports = { buildSandbox, slice, html };
