// Regression test for the Calendar engine's .ics import in index.html.
// The REAL parseICS()/icsWhen()/icsInstant()/tzShift() (plus the date helpers
// pad/ds/date/add and normalize) are extracted from the #calendarEngine script
// by string markers and run against a stub S/localStorage — no logic is
// re-implemented here.
//
// Covers: floating vs UTC (Z) vs zoned (TZID) DTSTART resolution, DST-sensitive
// zone offsets, overnight/multi-day DTEND clipping, all-day passthrough, and
// malformed input. Expectations are computed from UTC instants rather than
// hardcoded wall-clock, so the suite is correct in ANY local timezone.
//
// Run: node tools/calendar_ics_test.js   (exit 0 = pass)
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

// Base helpers (pad/id/ds/date/add/normalize/…) then the ICS block itself.
const base = slice("const pad=n=>String(n).padStart", 'function urgency(o){');
const ics = slice('/* ---- ICS date-time resolution', '    function importICS(ev){');

const engine = new Function('localStorage', 'Intl', `
    let S={items:[],cats:[],prefs:{timeFormat:'24'},cursor:new Date(),view:'month',filters:{q:''},shown:[],drag:null};
    ${base}
    ${ics}
    return { parseICS, icsWhen, ds, pad };
`)({ getItem: () => null, setItem: () => { } }, Intl);

const { parseICS, ds, pad } = engine;

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}

// Local wall-clock rendering of a UTC instant — the expectation oracle. Mirrors
// what the engine must produce, but derived independently from Date.UTC.
const localOf = (...utc) => {
    const d = new Date(Date.UTC(...utc));
    return { d: ds(d), t: pad(d.getHours()) + ':' + pad(d.getMinutes()) };
};

const ical = body => 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n' + body + '\r\nEND:VCALENDAR';
const vevent = lines => ical('BEGIN:VEVENT\r\nUID:u1@test\r\nSUMMARY:Test event\r\n' + lines + '\r\nEND:VEVENT');
const one = lines => parseICS(vevent(lines))[0];

// == floating stamps are already local wall-clock: pass through untouched ======
{
    const o = one('DTSTART:20260715T140000');
    check('floating DTSTART keeps its wall-clock date', o.startDate === '2026-07-15', o && o.startDate);
    check('floating DTSTART keeps its wall-clock time', o.startTime === '14:00', o && o.startTime);
    check('floating DTSTART is not all-day', o.allDay === false);
}

// == UTC (Z) stamps convert to local ==========================================
{
    const o = one('DTSTART:20260715T180000Z');
    const want = localOf(2026, 6, 15, 18, 0);
    check('UTC DTSTART converts to local date', o.startDate === want.d, o.startDate + ' want ' + want.d);
    check('UTC DTSTART converts to local time', o.startTime === want.t, o.startTime + ' want ' + want.t);
}
{
    // A Z stamp near midnight UTC must be free to land on a different local DATE.
    const o = one('DTSTART:20260715T013000Z');
    const want = localOf(2026, 6, 15, 1, 30);
    check('UTC DTSTART near midnight may shift the local date', o.startDate === want.d && o.startTime === want.t,
        o.startDate + ' ' + o.startTime + ' want ' + want.d + ' ' + want.t);
}

// == zoned (TZID) stamps convert to local, honouring DST ======================
{
    // 14:00 in Toronto on Jul 15 is EDT (UTC-4) => 18:00Z.
    const o = one('DTSTART;TZID=America/Toronto:20260715T140000');
    const want = localOf(2026, 6, 15, 18, 0);
    check('TZID DTSTART resolves via the zone offset (DST/summer)', o.startDate === want.d && o.startTime === want.t,
        o.startDate + ' ' + o.startTime + ' want ' + want.d + ' ' + want.t);
}
{
    // 14:00 in Toronto on Jan 15 is EST (UTC-5) => 19:00Z. Same zone, other offset:
    // this is what the two-pass offset settle in icsInstant() exists for.
    const o = one('DTSTART;TZID=America/Toronto:20260115T140000');
    const want = localOf(2026, 0, 15, 19, 0);
    check('TZID DTSTART resolves via the zone offset (standard/winter)', o.startDate === want.d && o.startTime === want.t,
        o.startDate + ' ' + o.startTime + ' want ' + want.d + ' ' + want.t);
}
{
    // A zone with no DST and a half-hour offset: 09:00 Kolkata => 03:30Z.
    const o = one('DTSTART;TZID=Asia/Kolkata:20260715T090000');
    const want = localOf(2026, 6, 15, 3, 30);
    check('TZID DTSTART handles a half-hour zone offset', o.startDate === want.d && o.startTime === want.t,
        o.startDate + ' ' + o.startTime + ' want ' + want.d + ' ' + want.t);
}
{
    const o = one('DTSTART;TZID=Not/AZone:20260715T140000');
    check('unknown TZID falls back to floating rather than throwing',
        o && o.startDate === '2026-07-15' && o.startTime === '14:00', o && o.startDate + ' ' + o.startTime);
}

// == DTEND: same-day is kept, later-day is clipped ============================
{
    const o = one('DTSTART:20260701T090000\r\nDTEND:20260701T103000');
    check('same-day DTEND keeps its time', o.endTime === '10:30', o.endTime);
}
{
    // The model has no endDate, so an overnight end cannot be represented. It must
    // clip to end-of-day, never emit endTime < startTime.
    const o = one('DTSTART:20260701T220000\r\nDTEND:20260702T020000');
    check('overnight DTEND clips to end of the start day', o.endTime === '23:59', o.endTime);
    check('overnight import keeps its start date', o.startDate === '2026-07-01', o.startDate);
    check('overnight endTime is never before startTime', o.endTime > o.startTime, o.startTime + '->' + o.endTime);
}
{
    const o = one('DTSTART:20260701T090000\r\nDTEND:20260705T170000');
    check('multi-day timed DTEND clips to end of the start day', o.endTime === '23:59', o.endTime);
}
{
    // Defensive: an end BEFORE the start is malformed; drop it rather than clip.
    const o = one('DTSTART:20260702T090000\r\nDTEND:20260701T170000');
    check('DTEND on an earlier date yields no endTime', o.endTime === '', JSON.stringify(o.endTime));
}
{
    // A Z-stamped pair must be compared AFTER conversion, not on the raw text.
    const o = one('DTSTART:20260701T140000Z\r\nDTEND:20260701T160000Z');
    const s = localOf(2026, 6, 1, 14, 0), e = localOf(2026, 6, 1, 16, 0);
    const sameLocalDay = s.d === e.d;
    check('UTC DTEND is compared against the CONVERTED start date',
        sameLocalDay ? o.endTime === e.t : o.endTime === '23:59',
        o.startDate + ' ' + o.startTime + '->' + o.endTime);
}

// == all-day events ===========================================================
{
    const o = one('DTSTART;VALUE=DATE:20260701\r\nDTEND;VALUE=DATE:20260702');
    check('all-day DTSTART is flagged allDay', o.allDay === true);
    check('all-day DTSTART keeps its literal date (no UTC shift)', o.startDate === '2026-07-01', o.startDate);
    check('all-day event carries no times', o.startTime === '' && o.endTime === '');
}
{
    // Date-only DTSTART without VALUE=DATE is still all-day (8-char form).
    const o = one('DTSTART:20260701');
    check('bare 8-char DTSTART is treated as all-day', o.allDay === true && o.startDate === '2026-07-01');
}
{
    const o = one('DTSTART;VALUE=DATE:20260701\r\nDTEND;VALUE=DATE:20260705');
    check('multi-day all-day import survives (start date intact)',
        o.allDay === true && o.startDate === '2026-07-01', o.startDate);
}

// == malformed input ==========================================================
{
    check('unparseable DTSTART is dropped, not imported as garbage',
        parseICS(vevent('DTSTART:not-a-date')).length === 0);
    check('event without DTSTART is dropped', parseICS(ical('BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:No start\r\nEND:VEVENT')).length === 0);
    check('empty calendar yields no events', parseICS(ical('')).length === 0);
}

// == folded lines + escaping still work (pre-existing behaviour) ===============
{
    const o = parseICS(ical('BEGIN:VEVENT\r\nUID:u@t\r\nSUMMARY:Long\r\n  title\r\nDTSTART:20260715T140000\r\nEND:VEVENT'))[0];
    check('folded SUMMARY line is unfolded', o.title === 'Long title', o.title);
}

console.log(failures ? `\n${failures} ICS CASE(S) FAILED` : '\nALL ICS CASES PASS');
process.exit(failures ? 1 : 0);
