// Selective, scoped Calendar reconciliation safety for the SAT/IELTS ↔ course
// integration. Runs the REAL exam engine against the REAL Calendar reconcile
// logic (see exam_link_harness.js) over one shared localStorage, so every
// guarantee below is exercised end to end.
//
// Run: node tools/exam_calendar_reconcile_test.js   (exit 0 = pass)
'use strict';
const { buildSandbox } = require('./exam_link_harness.js');

let failed = 0;
function check(label, cond, detail = '') {
    if (cond) console.log('PASS  ' + label);
    else { failed++; console.error('FAIL  ' + label + (detail ? ': ' + detail : '')); }
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const ROSTER = [
    { id: 'c-sat', name: 'SAT Course', days: ['dayA'] },
    { id: 'c-ielts', name: 'IELTS Course', days: ['dayB'] }
];
// A broad, realistic non-exam seed that reconciliation must never disturb.
function seed() {
    return {
        cp_courses_v1: JSON.stringify(ROSTER),
        cp_calendar_categories_v1: JSON.stringify([{ id: 'study', name: 'Study', color: '#7c68c8', order: 2 }]),
        cp_calendar_preferences_v1: JSON.stringify({ weekStart: 1, defaultView: 'week' }),
        cp_calendar_items_v1: JSON.stringify([
            { schemaVersion: 1, id: 'plain1', type: 'task', title: 'Groceries', categoryId: 'personal', startDate: '2026-08-15', allDay: true, completed: false, subtasks: [], reminders: [], recurrence: null, exceptions: {}, trackerLink: null },
            { schemaVersion: 1, id: 'trk1', type: 'task', title: 'Calculus & Vectors', categoryId: 'coursework', startDate: '2026-08-16', allDay: true, completed: false, subtasks: [{ id: 't1', title: 'Homework', completed: false }], reminders: [60], recurrence: null, exceptions: {}, trackerLink: { type: 'lesson' } }
        ]),
        tracker_lessons: JSON.stringify([{ course: 'SAT Course', name: 'L1' }]),
        dayA_data: JSON.stringify({ 'SAT Course': { notes: 'keep' } }),
        cp_lastActiveTab: 'studyTools',
        theme: 'dark',
        cp_study_videos: JSON.stringify([{ id: 'v1' }])
    };
}
// Keys reconciliation is allowed to write; everything else must stay byte-identical.
const TOUCHABLE = new Set(['cp_calendar_items_v1', 'cp_calendar_exceptions_v1', 'cp_satPrep_v1', 'cp_ieltsPrep_v1', 'cp_exam_course_links_v1']);
function unrelated(snap) {
    const out = {};
    Object.keys(snap).forEach(k => { if (!TOUCHABLE.has(k)) out[k] = snap[k]; });
    return out;
}
const examItems = (s, exam) => s.calItems().filter(x => x.examLink && x.examLink.exam === exam);
const plainItems = s => s.calItems().filter(x => !x.examLink);

// ---- baseline: connect + first reconcile -----------------------------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    const beforeUnrelated = unrelated(s.snapshot());
    const rep = s.api.reconcileExamCalendar('both', {});
    check('both reconcile adds SAT and IELTS records', rep.sat.added > 0 && rep.ielts.added > 0);
    check('generated SAT records are tagged with the SAT course id', examItems(s, 'sat').every(x => x.courseId === 'c-sat'));
    check('generated IELTS records are tagged with the IELTS course id', examItems(s, 'ielts').every(x => x.courseId === 'ielts' || x.courseId === 'c-ielts'));
    check('session titles stay the real task titles, not replaced with "SAT"/"IELTS"',
        examItems(s, 'sat').filter(x => x.examLink.kind === 'session').every(x => x.title && x.title !== 'SAT')
        && examItems(s, 'ielts').filter(x => x.examLink.kind === 'maintenance').every(x => x.title && x.title !== 'IELTS'));
    check('pre-existing non-exam Calendar items are preserved', plainItems(s).length === 2);
    check('unrelated localStorage is untouched by reconcile', eq(unrelated(s.snapshot()), beforeUnrelated));
}

// ---- idempotency -----------------------------------------------------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.api.reconcileExamCalendar('sat', {});
    const afterFirst = s.raw('cp_calendar_items_v1');
    const count1 = s.calItems().length;
    const rep2 = s.api.reconcileExamCalendar('sat', {});
    check('a repeated reconcile adds and removes nothing', rep2.sat.added === 0 && rep2.sat.removed === 0);
    check('a repeated reconcile reports every record unchanged', rep2.sat.updated === 0 && rep2.sat.unchanged > 0);
    check('repeated reconcile does not duplicate records', s.calItems().length === count1);
    check('repeated reconcile leaves the Calendar string identical', s.raw('cp_calendar_items_v1') === afterFirst);
}

// ---- SAT-only scope isolation ----------------------------------------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    s.api.reconcileExamCalendar('both', {});
    const ieltsBefore = examItems(s, 'ielts');
    const unrelatedBefore = unrelated(s.snapshot());
    const plainBefore = plainItems(s);
    // Simulate a Calendar reschedule of one SAT session, then a SAT-only reconcile.
    const items = s.calItems();
    const sess = items.find(x => x.examLink && x.examLink.id.startsWith('sat:session:'));
    sess.startDate = '2026-12-24';
    s.localStorage.setItem('cp_calendar_items_v1', JSON.stringify(items));
    s.fireStorage('cp_calendar_items_v1');
    s.api.reconcileExamCalendar('sat', {});
    check('SAT-only reconcile pulls the reschedule into the SAT row',
        s.sat().sessions.find(x => 'sat:session:' + x.id === sess.examLink.id).date === '2026-12-24');
    check('SAT-only reconcile leaves every IELTS record byte-identical', eq(examItems(s, 'ielts'), ieltsBefore));
    check('SAT-only reconcile leaves non-exam Calendar items identical', eq(plainItems(s), plainBefore));
    check('SAT-only reconcile leaves unrelated localStorage identical', eq(unrelated(s.snapshot()), unrelatedBefore));
}

// ---- IELTS-only scope isolation + maintenance-only never adds intensive -----
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    s.api.reconcileExamCalendar('both', {});
    const satBefore = examItems(s, 'sat');
    s.api.reconcileExamCalendar('ielts', { includeIntensive: false });
    check('IELTS maintenance-only reconcile adds no intensive records',
        examItems(s, 'ielts').every(x => x.examLink.kind !== 'intensive'));
    check('IELTS-only reconcile leaves every SAT record byte-identical', eq(examItems(s, 'sat'), satBefore));
}

// ---- both === SAT then IELTS (deterministic) -------------------------------
{
    const a = buildSandbox(seed(), ROSTER);
    a.window.cpSetExamCourseLink('sat', 'c-sat');
    a.window.cpSetExamCourseLink('ielts', 'c-ielts');
    a.api.reconcileExamCalendar('both', {});
    const b = buildSandbox(seed(), ROSTER);
    b.window.cpSetExamCourseLink('sat', 'c-sat');
    b.window.cpSetExamCourseLink('ielts', 'c-ielts');
    b.api.reconcileExamCalendar('sat', {});
    b.api.reconcileExamCalendar('ielts', {});
    // Compare by stable link id + the exam-owned fields (createdAt timestamps differ).
    const shape = list => list.map(x => ({ id: x.examLink.id, title: x.title, startDate: x.startDate, courseId: x.courseId, type: x.type }))
        .sort((m, n) => m.id.localeCompare(n.id));
    check('both-scope equals running SAT then IELTS independently',
        eq(shape(a.calItems().filter(x => x.examLink)), shape(b.calItems().filter(x => x.examLink))));
}

// ---- only stale records in the selected namespace are removed ---------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    s.api.reconcileExamCalendar('both', {});
    const ieltsBefore = examItems(s, 'ielts');
    const total = s.calItems().length;
    // Externally delete ONE SAT deadline row, then reconcile SAT.
    const sat = s.sat();
    const gone = sat.deadlines.pop();
    s.localStorage.setItem('cp_satPrep_v1', JSON.stringify(sat));
    s.fireStorage('cp_satPrep_v1');
    const rep = s.api.reconcileExamCalendar('sat', {});
    check('deleting one SAT source row prunes exactly one SAT record', rep.sat.removed === 1);
    check('the pruned record is the deleted deadline',
        !s.calItems().some(x => x.examLink && x.examLink.id === 'sat:deadline:' + gone.id));
    check('pruning stays within the SAT namespace (IELTS untouched)', eq(examItems(s, 'ielts'), ieltsBefore));
    check('exactly one record disappears overall', s.calItems().length === total - 1);
}

// ---- a manually-deleted record is recreated while its source exists ---------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.api.reconcileExamCalendar('sat', {});
    let items = s.calItems();
    const target = items.find(x => x.examLink && x.examLink.id === 'sat:exam:sat-exam');
    items = items.filter(x => x !== target);
    s.localStorage.setItem('cp_calendar_items_v1', JSON.stringify(items));
    const rep = s.api.reconcileExamCalendar('sat', {});
    check('a manually deleted record is recreated on the next reconcile',
        rep.sat.added >= 1 && s.calItems().some(x => x.examLink && x.examLink.id === 'sat:exam:sat-exam'));
}

// ---- stable Calendar id + user-owned fields survive an update --------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.api.reconcileExamCalendar('sat', {});
    const items = s.calItems();
    const rec = items.find(x => x.examLink && x.examLink.kind === 'session');
    const keepId = rec.id;
    rec.url = 'https://user.example';
    rec.subtasks = [{ id: 'u1', title: 'my subtask', completed: false }];
    rec.reminders = [15];
    rec.recurrence = { freq: 'weekly', interval: 1 };
    rec.exceptions = { '2026-09-01': { cancelled: true } };
    rec.startDate = '2026-11-11';
    rec.notes = 'user note';
    s.localStorage.setItem('cp_calendar_items_v1', JSON.stringify(items));
    s.fireStorage('cp_calendar_items_v1');
    s.api.reconcileExamCalendar('sat', {});
    const after = s.calItems().find(x => x.examLink && x.examLink.id === rec.examLink.id);
    check('the stable Calendar id survives an update', after.id === keepId);
    check('user URL / subtasks / reminders / recurrence / exceptions survive reconcile',
        after.url === 'https://user.example' && after.subtasks.length === 1 && after.subtasks[0].id === 'u1'
        && eq(after.reminders, [15]) && after.recurrence && after.recurrence.freq === 'weekly'
        && after.exceptions['2026-09-01'] && after.exceptions['2026-09-01'].cancelled === true);
    check('a user Calendar reschedule survives reconcile (round-trips, not reset)', after.startDate === '2026-11-11');
    check('a user Calendar note survives reconcile', after.notes === 'user note');
}

// ---- identical titles in different courses never cross-update ---------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    s.api.reconcileExamCalendar('both', {});
    const items = s.calItems();
    const satRec = items.find(x => x.examLink && x.examLink.exam === 'sat' && x.examLink.kind === 'session');
    const ieltsRec = items.find(x => x.examLink && x.examLink.exam === 'ielts' && x.examLink.kind === 'maintenance');
    satRec.title = 'Study Block';
    ieltsRec.title = 'Study Block';
    s.localStorage.setItem('cp_calendar_items_v1', JSON.stringify(items));
    s.fireStorage('cp_calendar_items_v1');
    s.api.reconcileExamCalendar('sat', {});
    const ieltsAfter = s.calItems().find(x => x.examLink && x.examLink.id === ieltsRec.examLink.id);
    check('a SAT reconcile never touches an IELTS record that shares its title',
        ieltsAfter.title === 'Study Block' && ieltsAfter.courseId === (ieltsRec.courseId));
}

// ---- failure rolls back exact prior values; both-scope is atomic ------------
{
    const s = buildSandbox(seed(), ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    const before = s.snapshot();
    s.failOnKey('cp_calendar_items_v1', 1);
    let threw = false;
    try { s.api.reconcileExamCalendar('sat', {}); } catch (e) { threw = true; }
    check('a SAT-only write failure throws', threw);
    check('a SAT-only failure restores every key to its exact prior string', eq(s.snapshot(), before));

    const s2 = buildSandbox(seed(), ROSTER);
    s2.window.cpSetExamCourseLink('sat', 'c-sat');
    s2.window.cpSetExamCourseLink('ielts', 'c-ielts');
    const before2 = s2.snapshot();
    s2.failOnKey('cp_calendar_items_v1', 2); // succeed through SAT, fail during IELTS
    let threw2 = false;
    try { s2.api.reconcileExamCalendar('both', {}); } catch (e) { threw2 = true; }
    check('a both-scope failure during IELTS throws', threw2);
    check('a both-scope failure atomically restores the whole SAT+IELTS+Calendar state', eq(s2.snapshot(), before2));
}

console.log(failed ? '\n' + failed + ' RECONCILE CASE(S) FAILED' : '\nALL EXAM CALENDAR RECONCILE CASES PASS');
process.exit(failed ? 1 : 0);
