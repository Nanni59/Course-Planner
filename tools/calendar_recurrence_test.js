// Regression test for the Calendar engine's recurrence logic in index.html.
// The REAL normalize()/occurs()/expand() (plus their date helpers pad/ds/date/add)
// are extracted from the #calendarEngine script by string markers and run against
// a stub S/localStorage — no logic is re-implemented here.
//
// Covers: daily / weekdays / weekly / monthly recurrence, interval, count bounds,
// until bounds, occurrence exceptions (cancelled + moved), month boundaries,
// February 29, and local-date behavior (no UTC conversion).
//
// Run: node tools/calendar_recurrence_test.js   (exit 0 = pass)
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

// pad/id/esc/read/write/ds/date/add/mins/tm/time/normalize/load/save/occurs/expand/due —
// everything between these two markers inside the calendarEngine IIFE.
const src = slice("const pad=n=>String(n).padStart", 'function urgency(o){');

// Stub environment: S mirrors the engine's state shape; localStorage only backs
// read/write, which these tests never invoke.
const engine = new Function('localStorage', `
    let S={items:[],cats:[],prefs:{timeFormat:'24'},cursor:new Date(),view:'month',filters:{q:''},shown:[],drag:null};
    ${src}
    return { normalize, occurs, expand, due, ds, date, add, setItems: v => { S.items = v; } };
`)({ getItem: () => null, setItem: () => { } });

const { normalize, occurs, expand, due, ds, date, add, setItems } = engine;

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}

// helper: expand a single item over an inclusive local-date window
function expandOne(item, fromStr, toStr) {
    setItems([normalize(item)].filter(Boolean));
    return expand(date(fromStr), date(toStr));
}
const dates = occ => occ.map(o => o.displayDate);

// == local-date helpers: no UTC conversion =====================================
{
    check('date() parses as LOCAL midnight (day intact)', date('2026-01-02').getDate() === 2 && date('2026-01-02').getHours() === 0);
    check('ds(date(s)) is identity across DST start', ds(date('2026-03-08')) === '2026-03-08');
    check('ds(date(s)) is identity across DST end', ds(date('2026-11-01')) === '2026-11-01');
    const occ = expandOne({ title: 'DST day task', startDate: '2026-03-08' }, '2026-03-01', '2026-03-31');
    check('non-recurring item on DST day keeps its local date', dates(occ).join() === '2026-03-08');
}

// == normalize ==================================================================
{
    check('normalize rejects missing title', normalize({ startDate: '2026-01-01' }) === null);
    check('normalize rejects malformed startDate', normalize({ title: 'x', startDate: '01/01/2026' }) === null);
    const n = normalize({ title: 'x', startDate: '2026-01-01' });
    check('normalize applies defaults', n.type === 'task' && n.allDay === true && n.recurrence === null && n.schemaVersion === 1);
}

// == daily ======================================================================
{
    const occ = expandOne({ title: 'd', startDate: '2026-01-01', recurrence: { freq: 'daily', interval: 1 } }, '2026-01-01', '2026-01-05');
    check('daily: every day in window', dates(occ).join() === '2026-01-01,2026-01-02,2026-01-03,2026-01-04,2026-01-05');
    const occ2 = expandOne({ title: 'd2', startDate: '2026-01-01', recurrence: { freq: 'daily', interval: 2 } }, '2026-01-01', '2026-01-07');
    check('daily: interval 2 skips alternate days', dates(occ2).join() === '2026-01-01,2026-01-03,2026-01-05,2026-01-07');
    const occ3 = expandOne({ title: 'd3', startDate: '2026-01-10', recurrence: { freq: 'daily' } }, '2026-01-01', '2026-01-12');
    check('daily: nothing before the series start', dates(occ3).join() === '2026-01-10,2026-01-11,2026-01-12');
}

// == weekdays ===================================================================
{
    // 2026-01-05 is a Monday; window Mon..Sun
    const occ = expandOne({ title: 'w', startDate: '2026-01-05', recurrence: { freq: 'weekdays' } }, '2026-01-05', '2026-01-11');
    check('weekdays: Mon-Fri only, weekend skipped', dates(occ).join() === '2026-01-05,2026-01-06,2026-01-07,2026-01-08,2026-01-09');
}

// == weekly =====================================================================
{
    // 2026-01-07 is a Wednesday
    const occ = expandOne({ title: 'wk', startDate: '2026-01-07', recurrence: { freq: 'weekly', interval: 1 } }, '2026-01-01', '2026-01-31');
    check('weekly: same weekday each week', dates(occ).join() === '2026-01-07,2026-01-14,2026-01-21,2026-01-28');
    const occ2 = expandOne({ title: 'wk2', startDate: '2026-01-07', recurrence: { freq: 'weekly', interval: 2 } }, '2026-01-01', '2026-02-07');
    check('weekly: interval 2 = every other week', dates(occ2).join() === '2026-01-07,2026-01-21,2026-02-04');
}

// == monthly ====================================================================
{
    const occ = expandOne({ title: 'm', startDate: '2026-01-15', recurrence: { freq: 'monthly', interval: 1 } }, '2026-01-01', '2026-04-30');
    check('monthly: same day-of-month', dates(occ).join() === '2026-01-15,2026-02-15,2026-03-15,2026-04-15');
    const occ2 = expandOne({ title: 'm2', startDate: '2026-01-15', recurrence: { freq: 'monthly', interval: 2 } }, '2026-01-01', '2026-05-31');
    check('monthly: interval 2 = every other month', dates(occ2).join() === '2026-01-15,2026-03-15,2026-05-15');
}

// == count bounds ===============================================================
{
    const occ = expandOne({ title: 'c', startDate: '2026-01-01', recurrence: { freq: 'daily', count: 3 } }, '2026-01-01', '2026-01-31');
    check('count: exactly N occurrences', dates(occ).join() === '2026-01-01,2026-01-02,2026-01-03');
    // count is consumed from the SERIES start even when the window begins later
    const occ2 = expandOne({ title: 'c2', startDate: '2026-01-01', recurrence: { freq: 'daily', count: 5 } }, '2026-01-04', '2026-01-31');
    check('count: window past start sees only the remainder', dates(occ2).join() === '2026-01-04,2026-01-05');
}

// == until bounds ===============================================================
{
    const occ = expandOne({ title: 'u', startDate: '2026-01-01', recurrence: { freq: 'daily', until: '2026-01-04' } }, '2026-01-01', '2026-01-31');
    check('until: inclusive end bound', dates(occ).join() === '2026-01-01,2026-01-02,2026-01-03,2026-01-04');
}

// == occurrence exceptions ======================================================
{
    const base = { title: 'e', startDate: '2026-01-01', recurrence: { freq: 'daily' } };
    const occ = expandOne(Object.assign({}, base, { exceptions: { '2026-01-02': { cancelled: true } } }), '2026-01-01', '2026-01-04');
    check('exception: cancelled occurrence omitted', dates(occ).join() === '2026-01-01,2026-01-03,2026-01-04');

    const occ2 = expandOne(Object.assign({}, base, { exceptions: { '2026-01-02': { startDate: '2026-01-06', startTime: '09:00' } } }), '2026-01-01', '2026-01-07');
    const moved = occ2.filter(o => o.occurrenceDate === '2026-01-02');
    check('exception: moved occurrence shows at its new date', moved.length === 1 && moved[0].displayDate === '2026-01-06' && moved[0].startTime === '09:00');
    check('exception: moved occurrence not duplicated at old date', !occ2.some(o => o.displayDate === '2026-01-02'));

    // exception moved INTO the window from an occurrence outside it
    const occ3 = expandOne(Object.assign({}, base, { recurrence: { freq: 'daily', until: '2026-01-03' }, exceptions: { '2026-01-03': { startDate: '2026-01-20' } } }), '2026-01-15', '2026-01-25');
    check('exception: occurrence moved into a later window appears there', dates(occ3).join() === '2026-01-20');
}

// == month boundaries ===========================================================
{
    const occ = expandOne({ title: 'b', startDate: '2026-01-30', recurrence: { freq: 'daily' } }, '2026-01-30', '2026-02-02');
    check('daily crosses Jan->Feb boundary', dates(occ).join() === '2026-01-30,2026-01-31,2026-02-01,2026-02-02');
    const occ2 = expandOne({ title: 'b2', startDate: '2026-01-31', recurrence: { freq: 'monthly' } }, '2026-01-01', '2026-04-30');
    check('monthly on the 31st skips short months', dates(occ2).join() === '2026-01-31,2026-03-31');
}

// == February 29 ================================================================
{
    const occ = expandOne({ title: 'f', startDate: '2024-02-28', recurrence: { freq: 'daily' } }, '2024-02-28', '2024-03-01');
    check('daily includes Feb 29 in a leap year', dates(occ).join() === '2024-02-28,2024-02-29,2024-03-01');
    const occ2 = expandOne({ title: 'f2', startDate: '2024-01-29', recurrence: { freq: 'monthly' } }, '2024-01-01', '2024-04-30');
    check('monthly on the 29th hits Feb 29 in a leap year', dates(occ2).join() === '2024-01-29,2024-02-29,2024-03-29,2024-04-29');
    const occ3 = expandOne({ title: 'f3', startDate: '2026-01-29', recurrence: { freq: 'monthly' } }, '2026-01-01', '2026-04-30');
    check('monthly on the 29th skips Feb in a non-leap year', dates(occ3).join() === '2026-01-29,2026-03-29,2026-04-29');
    const occ4 = expandOne({ title: 'f4', startDate: '2024-02-29' }, '2024-02-01', '2024-03-31');
    check('non-recurring item ON Feb 29 keeps its date', dates(occ4).join() === '2024-02-29');
}

// == due(): local time, not UTC =================================================
{
    const [o] = expandOne({ title: 't', startDate: '2026-07-14', startTime: '09:30', allDay: false }, '2026-07-14', '2026-07-14');
    const d = due(o);
    check('due() builds a LOCAL datetime', d.getFullYear() === 2026 && d.getMonth() === 6 && d.getDate() === 14 && d.getHours() === 9 && d.getMinutes() === 30);
}

console.log('');
if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
console.log('ALL RECURRENCE CASES PASS');
