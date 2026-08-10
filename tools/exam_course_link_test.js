// Exam ↔ course CONNECTIONS and connected-course-PAGE summaries.
// Runs the real exam engine (see exam_link_harness.js) and also checks a few
// source-level guarantees that must hold in index.html.
//
// Run: node tools/exam_course_link_test.js   (exit 0 = pass)
'use strict';
const { buildSandbox, html } = require('./exam_link_harness.js');

let failed = 0;
function check(label, cond, detail = '') {
    if (cond) console.log('PASS  ' + label);
    else { failed++; console.error('FAIL  ' + label + (detail ? ': ' + detail : '')); }
}

const ROSTER = [
    { id: 'c-sat', name: 'SAT Course', days: ['dayA'] },
    { id: 'c-ielts', name: 'IELTS Course', days: ['dayB'] },
    { id: 'c-math', name: 'Calculus & Vectors', days: ['dayA', 'dayB'] }
];

// ---- normalizeLinks: shape, fail-safe, no double-booking --------------------
{
    const s = buildSandbox({}, ROSTER);
    const nl = s.api.normalizeLinks;
    check('links default to no connection', JSON.stringify(nl(null)) === JSON.stringify({ schemaVersion: 1, sat: { courseId: null }, ielts: { courseId: null } }));
    check('a corrupt links payload fails safe to no connection',
        nl('garbage').sat.courseId === null && nl(42).ielts.courseId === null && nl([]).sat.courseId === null);
    check('links keep valid string course ids', nl({ sat: { courseId: 'x' }, ielts: { courseId: 'y' } }).sat.courseId === 'x');
    check('a corrupt store claiming both exams hold one course is repaired',
        nl({ sat: { courseId: 'same' }, ielts: { courseId: 'same' } }).ielts.courseId === null);
}

// ---- connect SAT and IELTS independently -----------------------------------
{
    const s = buildSandbox({}, ROSTER);
    check('SAT connects independently', s.window.cpSetExamCourseLink('sat', 'c-sat').ok === true);
    check('IELTS connects independently', s.window.cpSetExamCourseLink('ielts', 'c-ielts').ok === true);
    check('each connection is read back by course id',
        s.window.cpGetExamCourseLink('sat') === 'c-sat' && s.window.cpGetExamCourseLink('ielts') === 'c-ielts');
    check('a missing course id is rejected', s.window.cpSetExamCourseLink('sat', 'nope').ok === false);
    // change SAT to a different course
    check('SAT can change to another course', s.window.cpSetExamCourseLink('sat', 'c-math').ok === true && s.window.cpGetExamCourseLink('sat') === 'c-math');
    // disconnect
    s.window.cpSetExamCourseLink('sat', null);
    check('SAT can disconnect', s.window.cpGetExamCourseLink('sat') === null);
    check('disconnecting SAT leaves IELTS connected', s.window.cpGetExamCourseLink('ielts') === 'c-ielts');
}

// ---- one course cannot connect to both exams -------------------------------
{
    const s = buildSandbox({}, ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-math');
    const r = s.window.cpSetExamCourseLink('ielts', 'c-math');
    check('a course already on SAT cannot also connect to IELTS', r.ok === false && /already connected/i.test(r.message));
    check('the rejected connection did not change IELTS', s.window.cpGetExamCourseLink('ielts') === null);
}

// ---- rename does not break the connection (id-keyed) -----------------------
{
    const s = buildSandbox({}, ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    // rename the course: same id, new display name (as the roster editor does).
    s.setRoster([{ id: 'c-sat', name: 'Digital SAT', days: ['dayA'] }, { id: 'c-ielts', name: 'IELTS Course', days: ['dayB'] }]);
    check('a rename keeps the SAT connection (resolved by id)', s.window.cpGetExamCourseLink('sat') === 'c-sat');
    const ctx = s.window.cpGetCourseExamContext('c-sat');
    check('the renamed course still resolves to its exam context', ctx && ctx.exam === 'sat');
    // label refresh does not throw and returns cleanly
    check('cpRefreshExamCourseLabels runs without error', (() => { try { s.window.cpRefreshExamCourseLabels(); return true; } catch (e) { return false; } })());
}

// ---- removing a connected course disconnects only its exam, keeps history ---
{
    const s = buildSandbox({}, ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    s.api.reconcileExamCalendar('both', {});
    const satHistory = JSON.stringify(s.sat());
    const satRecordCount = s.calItems().filter(x => x.examLink && x.examLink.exam === 'sat').length;
    // roster removes c-sat; app calls cpDisconnectCourseIfLinked(removedId)
    s.setRoster([{ id: 'c-ielts', name: 'IELTS Course', days: ['dayB'] }]);
    const touched = s.window.cpDisconnectCourseIfLinked('c-sat');
    check('removing a connected course disconnects that exam', touched === true && s.window.cpGetExamCourseLink('sat') === null);
    check('removing a connected course leaves the other exam connected', s.window.cpGetExamCourseLink('ielts') === 'c-ielts');
    check('removing a connected course preserves exam-prep history', JSON.stringify(s.sat()) === satHistory);
    check('removing a connected course keeps its generated Calendar records',
        s.calItems().filter(x => x.examLink && x.examLink.exam === 'sat').length === satRecordCount);
    check('removing a connected course only clears the course tag from its records',
        s.calItems().filter(x => x.examLink && x.examLink.exam === 'sat').every(x => x.courseId === ''));
}

// ---- resetting prep preserves the connection -------------------------------
{
    const s = buildSandbox({}, ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.api.reconcileExamCalendar('sat', {});
    // SAT reset = remove SAT state + SAT Calendar records (does NOT touch links)
    s.localStorage.removeItem('cp_satPrep_v1');
    s.window.cpRemoveExamCalendarItems('sat');
    s.fireStorage('cp_satPrep_v1');
    check('a SAT reset preserves the course connection', s.window.cpGetExamCourseLink('sat') === 'c-sat');
    check('a SAT reset removes only SAT Calendar records', s.calItems().every(x => !x.examLink || x.examLink.exam !== 'sat'));
}

// ---- connected course renders a derived summary; ordinary course does not ---
{
    const s = buildSandbox({}, ROSTER);
    s.window.cpSetExamCourseLink('sat', 'c-sat');
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    const satCtx = s.window.cpGetCourseExamContext('c-sat');
    check('a SAT-connected course resolves to a SAT summary', satCtx && satCtx.exam === 'sat' && satCtx.summary.exam === 'sat');
    check('the SAT summary derives the real fields',
        satCtx.summary.examDate === '2026-10-03' && typeof satCtx.summary.countdownDays === 'number'
        && satCtx.summary.targetTotal === 1500 && typeof satCtx.summary.readiness === 'string'
        && typeof satCtx.summary.sessionsPlanned === 'number');
    const ieltsCtx = s.window.cpGetCourseExamContext('c-ielts');
    check('an IELTS-connected course resolves to an IELTS summary',
        ieltsCtx && ieltsCtx.exam === 'ielts' && ieltsCtx.summary.testType === 'IELTS Academic'
        && ieltsCtx.summary.testDateLabel === 'Not booked' && typeof ieltsCtx.summary.mode === 'string');
    check('an ordinary, unconnected course has no exam context', s.window.cpGetCourseExamContext('c-math') === null);
    check('cpGetExamSummary mirrors the SAT/IELTS summaries',
        s.window.cpGetExamSummary('sat').exam === 'sat' && s.window.cpGetExamSummary('ielts').exam === 'ielts'
        && s.window.cpGetExamSummary('bogus') === null);
}

// ---- the summary reflects live prep changes --------------------------------
{
    const s = buildSandbox({}, ROSTER);
    s.window.cpSetExamCourseLink('ielts', 'c-ielts');
    const before = s.window.cpGetCourseExamContext('c-ielts').summary.testDateLabel;
    // externally set a test date, then let the engine reload
    const ielts = s.ielts();
    ielts.settings.testDate = '2026-11-01';
    s.localStorage.setItem('cp_ieltsPrep_v1', JSON.stringify(ielts));
    s.fireStorage('cp_ieltsPrep_v1');
    const after = s.window.cpGetCourseExamContext('c-ielts').summary;
    check('the derived summary reflects a later prep change',
        before === 'Not booked' && after.testDate === '2026-11-01' && typeof after.countdownDays === 'number');
}

// ---- backup normalization round-trips the links store ----------------------
{
    const s = buildSandbox({}, ROSTER);
    const data = { cp_exam_course_links_v1: { sat: { courseId: 'c-sat' }, ielts: { courseId: 'c-sat' } } };
    s.window.cpNormalizeExamPrepBackup(data);
    check('exam-prep backup normalization repairs a both-booked links store',
        data.cp_exam_course_links_v1.sat.courseId === 'c-sat' && data.cp_exam_course_links_v1.ielts.courseId === null);
    const data2 = { cp_satPrep_v1: { settings: { targetTotal: 1490 } } };
    s.window.cpNormalizeExamPrepBackup(data2);
    check('exam-prep backup still normalizes SAT prep state', data2.cp_satPrep_v1.schemaVersion === 1 && data2.cp_satPrep_v1.settings.targetTotal === 1490);
}

// ---- source-level guarantees (navigation + no new footer buttons) ----------
check('the exam-course links store is versioned', html.includes("const LINKS_KEY='cp_exam_course_links_v1'"));
check('reconciliation requires and validates its scope',
    html.includes('scope must be "sat", "ielts" or "both"'));
check('the footer still has no SAT/IELTS buttons', !html.includes('id="satPrepBtn"') && !html.includes('id="ieltsPrepBtn"'));
check('SAT and IELTS still launch from Study Tools', html.includes("examHubCard('satPrep'") && html.includes("examHubCard('ieltsPrep'"));
check('the /sat-prep and /ielts routes are unchanged', /satPrep:\s*'sat-prep'/.test(html) && /ieltsPrep:\s*'ielts'/.test(html));
check('exam routes still highlight Study Tools in the footer', /satPrep:\s*'studyToolsBtn'/.test(html) && /ieltsPrep:\s*'studyToolsBtn'/.test(html));
check('a connected course page opens the existing prep route',
    html.includes("window.cpSwitchDay(exam === 'sat' ? 'satPrep' : 'ieltsPrep')"));
check('the connected-course summary derives from prep state, not a separate store',
    html.includes('window.cpGetCourseExamContext') && html.includes('renderExpandExamSummary'));
check('per-exam AND update-both actions exist',
    html.includes("runReconcile('sat',{},'sat')") && html.includes("runReconcile('ielts',{includeIntensive:false},'ielts')")
    && html.includes("runReconcile('both',{},'sat')") && html.includes("runReconcile('both',{},'ielts')"));

console.log(failed ? '\n' + failed + ' EXAM COURSE LINK CASE(S) FAILED' : '\nALL EXAM COURSE LINK CASES PASS');
process.exit(failed ? 1 : 0);
