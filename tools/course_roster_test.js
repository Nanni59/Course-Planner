// Regression test for the user-editable course roster in index.html.
//
// Courses used to be six hard-coded .course-card blocks plus three literal
// arrays; they now live in localStorage under cp_courses_v1 and every card is
// cloned from #courseCardTemplate. This suite extracts the REAL roster helpers
// by string markers (same approach as backup_roundtrip_test.js) and runs them
// against a stubbed localStorage.
//
// Covers:
//   1. seeding: absent/corrupt key falls back to the original four courses,
//      but a DELIBERATELY emptied roster stays empty (deleting your last course
//      must not resurrect Calculus & Vectors on the next load)
//   2. normalization rejects blank names, '::' names, duplicates and dayless entries
//   3. isCourseOnBothDays follows the roster instead of a hard-coded pair
//   4. renaming a course rewrites its name in EVERY per-course store
//   5. removing a course purges it from every per-course store
//   6. neither operation disturbs the other courses' data
//   7. dropping one day removes only that day's data, priority and move record
//   8. name validation blocks blanks, '::' and case-insensitive duplicates
//   9. the markup really is template-driven (no static named cards left)
//
// Run: node tools/course_roster_test.js   (exit 0 = pass)
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
function check(name, condition) {
    if (condition) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name); }
}

// ---- extract the real code -------------------------------------------------
const store = slice(
    "const LS_COURSES_KEY = 'cp_courses_v1'",
    '            // Builds every Day A/B card from the roster.');
const rewrite = slice(
    '            function rewriteCourseInStorage(oldName, newName) {',
    '            /* The one way the roster changes.');
const validate = slice(
    '            function validateCourseName(rawName, ignoreName) {',
    '            function renderCourseManager()');

// ---- stubs -----------------------------------------------------------------
function makeLocalStorage(seed) {
    const map = new Map(Object.entries(seed || {}).map(([k, v]) => [k, JSON.stringify(v)]));
    return {
        getItem(k) { return map.has(String(k)) ? map.get(String(k)) : null; },
        setItem(k, v) { map.set(String(k), String(v)); },
        removeItem(k) { map.delete(String(k)); },
        _read(k) { const v = map.get(String(k)); return v == null ? null : JSON.parse(v); },
        _has(k) { return map.has(String(k)); }
    };
}

const KEYS = {
    LS_LESSONS_KEY: 'tracker_lessons',
    LS_ASSIGNMENTS_KEY: 'tracker_assignments',
    LS_PAUSED_COURSES_KEY: 'tracker_paused_courses',
    LS_MOVED_COURSES_KEY: 'moved_courses',
    LS_COURSE_CUSTOM_LINKS_KEY: 'course_custom_links',
    LS_SPLIT_ASSIGNMENTS_KEY: 'split_assignments',
    LS_LESSON_LINKS_KEY: 'lesson_links',
    LS_PRIORITIES_KEY: 'course_priorities'
};
const KEY_NAMES = Object.keys(KEYS);

// Builds a live sandbox around the extracted source for one localStorage stub.
function build(ls) {
    const getPausedCourses = () => {
        const raw = ls.getItem(KEYS.LS_PAUSED_COURSES_KEY);
        const paused = (raw ? JSON.parse(raw) : null) || { lesson: [], assignment: [] };
        if (!paused.lesson) paused.lesson = [];
        if (!paused.assignment) paused.assignment = [];
        return paused;
    };
    const body = store + '\n' + rewrite + '\n' + validate + '\n' +
        'return { normalizeCourseList, getCourses, setCourses, getCourseDays, ' +
        'isCourseOnBothDays, isValidCourseName, rewriteCourseInStorage, ' +
        'dropCourseDayData, validateCourseName, ALL_COURSE_NAMES };';
    const args = ['localStorage', 'getPausedCourses'].concat(KEY_NAMES);
    const fn = new Function(...args, body);
    return fn(ls, getPausedCourses, ...KEY_NAMES.map(k => KEYS[k]));
}

// ---- 1. seeding ------------------------------------------------------------
{
    const api = build(makeLocalStorage({}));
    const names = api.getCourses().map(c => c.name);
    check('absent roster falls back to the original four courses',
        names.join('|') === 'Calculus & Vectors|English|Media Arts|Business Leadership');
    check('seeded roster keeps the original day assignments',
        JSON.stringify(api.getCourses()) === JSON.stringify([
            { name: 'Calculus & Vectors', days: ['dayA', 'dayB'] },
            { name: 'English', days: ['dayA', 'dayB'] },
            { name: 'Media Arts', days: ['dayA'] },
            { name: 'Business Leadership', days: ['dayB'] }
        ]));
    check('ALL_COURSE_NAMES is derived from the roster, not a literal',
        api.ALL_COURSE_NAMES.length === 4 && api.ALL_COURSE_NAMES[0] === 'Calculus & Vectors');
}
{
    const api = build(makeLocalStorage({ cp_courses_v1: [] }));
    check('an emptied roster stays empty (defaults do not come back)',
        api.getCourses().length === 0);
}
{
    const ls = makeLocalStorage({});
    ls.setItem('cp_courses_v1', '{not json');
    check('corrupt roster falls back to defaults', build(ls).getCourses().length === 4);
}
{
    const api = build(makeLocalStorage({ cp_courses_v1: 'nope' }));
    check('non-array roster falls back to defaults', api.getCourses().length === 4);
}

// ---- 2. normalization ------------------------------------------------------
{
    const api = build(makeLocalStorage({}));
    const cleaned = api.normalizeCourseList([
        { name: '  Physics  ', days: ['dayB', 'dayA'] },  // trimmed + day order fixed
        { name: '', days: ['dayA'] },                     // blank
        { name: 'Bad::Name', days: ['dayA'] },            // reserved separator
        { name: 'Physics', days: ['dayA'] },              // duplicate
        { name: 'Nowhere', days: [] },                    // meets on no day
        { name: 'Art', days: ['dayA', 'bogus'] }          // unknown day filtered out
    ]);
    check('normalization trims names and orders days A then B',
        JSON.stringify(cleaned[0]) === JSON.stringify({ name: 'Physics', days: ['dayA', 'dayB'] }));
    check('normalization drops blank, "::", duplicate and dayless entries',
        cleaned.length === 2 && cleaned[1].name === 'Art');
    check('normalization keeps only real day ids',
        JSON.stringify(cleaned[1].days) === JSON.stringify(['dayA']));
    check('normalizeCourseList reports non-arrays as null',
        api.normalizeCourseList('x') === null && api.normalizeCourseList(null) === null);
    check('"::" is rejected as a course name',
        api.isValidCourseName('A::B') === false && api.isValidCourseName('Fine Name') === true);
}

// ---- 3. isCourseOnBothDays -------------------------------------------------
{
    const api = build(makeLocalStorage({
        cp_courses_v1: [
            { name: 'Physics', days: ['dayA', 'dayB'] },
            { name: 'Art', days: ['dayB'] }
        ]
    }));
    check('isCourseOnBothDays follows the roster', api.isCourseOnBothDays('Physics') === true);
    check('single-day course is not on both days', api.isCourseOnBothDays('Art') === false);
    check('unknown course is not on both days', api.isCourseOnBothDays('Gone') === false);
    check('getCourseDays returns a copy',
        JSON.stringify(api.getCourseDays('Art')) === JSON.stringify(['dayB']));
}

// ---- 4-6. rename and remove across every per-course store -------------------
// One fixture touching all eight stores, for the course under test ("Old") and
// a bystander ("Keep") that must never be modified.
function fixture() {
    return {
        cp_courses_v1: [{ name: 'Old', days: ['dayA', 'dayB'] }, { name: 'Keep', days: ['dayA'] }],
        dayA_data: { Old: { notes: 'a-notes' }, Keep: { notes: 'keep-a' } },
        dayB_data: { Old: { notes: 'b-notes' }, Keep: { notes: 'keep-b' } },
        tracker_lessons: [{ course: 'Old', name: 'L1' }, { course: 'Keep', name: 'L2' }],
        tracker_assignments: [{ course: 'Old', name: 'A1' }, { course: 'Keep', name: 'A2' }],
        tracker_paused_courses: { lesson: ['Old', 'Keep'], assignment: ['Old'] },
        moved_courses: { Old: { originalDay: 'dayA', currentDay: 'dayB' }, Keep: { originalDay: 'dayA', currentDay: 'dayB' } },
        course_custom_links: { Old: 'https://old.example', Keep: 'https://keep.example' },
        lesson_links: { 'Old::L1': 'https://l1', 'Keep::L2': 'https://l2' },
        split_assignments: { 'Old::A1': { done: 2 }, 'Keep::A2': { done: 1 } },
        course_priorities: { dayA_Old: 1, dayB_Old: 2, dayA_Keep: 3 }
    };
}

function bystanderIntact(ls) {
    return ls._read('dayA_data').Keep.notes === 'keep-a'
        && ls._read('dayB_data').Keep.notes === 'keep-b'
        && ls._read('tracker_lessons').some(i => i.course === 'Keep')
        && ls._read('tracker_assignments').some(i => i.course === 'Keep')
        && ls._read('tracker_paused_courses').lesson.includes('Keep')
        && !!ls._read('moved_courses').Keep
        && ls._read('course_custom_links').Keep === 'https://keep.example'
        && ls._read('lesson_links')['Keep::L2'] === 'https://l2'
        && !!ls._read('split_assignments')['Keep::A2']
        && ls._read('course_priorities').dayA_Keep === 3;
}

{
    const ls = makeLocalStorage(fixture());
    build(ls).rewriteCourseInStorage('Old', 'New');

    check('rename moves Day A/B card data',
        ls._read('dayA_data').New.notes === 'a-notes' && !('Old' in ls._read('dayA_data'))
        && ls._read('dayB_data').New.notes === 'b-notes');
    check('rename updates both tracker item lists',
        ls._read('tracker_lessons')[0].course === 'New'
        && ls._read('tracker_assignments')[0].course === 'New');
    check('rename updates the paused lists',
        ls._read('tracker_paused_courses').lesson.includes('New')
        && !ls._read('tracker_paused_courses').lesson.includes('Old')
        && ls._read('tracker_paused_courses').assignment.includes('New'));
    check('rename updates moved_courses and custom links',
        !!ls._read('moved_courses').New && !ls._read('moved_courses').Old
        && ls._read('course_custom_links').New === 'https://old.example');
    check('rename rewrites the "Course::Item" composite keys',
        ls._read('lesson_links')['New::L1'] === 'https://l1'
        && !('Old::L1' in ls._read('lesson_links'))
        && !!ls._read('split_assignments')['New::A1']);
    check('rename rewrites both day priority keys',
        ls._read('course_priorities').dayA_New === 1
        && ls._read('course_priorities').dayB_New === 2
        && !('dayA_Old' in ls._read('course_priorities')));
    check('rename leaves every other course untouched', bystanderIntact(ls));
}

{
    const ls = makeLocalStorage(fixture());
    build(ls).rewriteCourseInStorage('Old', null);

    check('remove purges Day A/B card data',
        !('Old' in ls._read('dayA_data')) && !('Old' in ls._read('dayB_data')));
    check('remove purges both tracker item lists',
        ls._read('tracker_lessons').every(i => i.course !== 'Old')
        && ls._read('tracker_assignments').every(i => i.course !== 'Old'));
    check('remove purges the paused lists',
        !ls._read('tracker_paused_courses').lesson.includes('Old')
        && !ls._read('tracker_paused_courses').assignment.includes('Old'));
    check('remove purges moved_courses and custom links',
        !ls._read('moved_courses').Old && !ls._read('course_custom_links').Old);
    check('remove purges the "Course::Item" composite keys',
        !('Old::L1' in ls._read('lesson_links'))
        && !('Old::A1' in ls._read('split_assignments')));
    check('remove purges both day priority keys',
        !('dayA_Old' in ls._read('course_priorities'))
        && !('dayB_Old' in ls._read('course_priorities')));
    check('remove leaves every other course untouched', bystanderIntact(ls));
}

// ---- 7. dropping a single day ----------------------------------------------
{
    const ls = makeLocalStorage(fixture());
    build(ls).dropCourseDayData('Old', 'dayB');

    check('dropping a day clears only that day\'s card data',
        !('Old' in ls._read('dayB_data')) && ls._read('dayA_data').Old.notes === 'a-notes');
    check('dropping a day clears only that day\'s priority',
        !('dayB_Old' in ls._read('course_priorities'))
        && ls._read('course_priorities').dayA_Old === 1);
    check('dropping a day clears the stale move record',
        !ls._read('moved_courses').Old && !!ls._read('moved_courses').Keep);
    check('dropping a day keeps tracker items (they are not day-scoped)',
        ls._read('tracker_lessons').some(i => i.course === 'Old'));
}

// ---- 8. name validation ----------------------------------------------------
{
    const api = build(makeLocalStorage({
        cp_courses_v1: [{ name: 'Physics', days: ['dayA'] }]
    }));
    check('validation rejects a blank name', api.validateCourseName('   ', null).ok === false);
    check('validation rejects "::" in a name', api.validateCourseName('A::B', null).ok === false);
    check('validation rejects a case-insensitive duplicate',
        api.validateCourseName('physics', null).ok === false);
    check('validation lets a row keep its own name',
        api.validateCourseName('Physics', 'Physics').ok === true);
    check('validation trims an accepted name',
        api.validateCourseName('  Chemistry ', null).name === 'Chemistry');
}

// ---- 9. the markup is template-driven --------------------------------------
check('a single course-card template drives both days',
    html.includes('<template id="courseCardTemplate">')
    && (html.match(/<div class="course-card"/g) || []).length === 1);
check('no course name is hard-coded into a card any more',
    !/class="course-card" data-course-name="[^"]/.test(html));
check('both day grids start empty and are filled by renderCourseCards',
    html.includes('<div id="dayA" class="tab-content active">\r\n            <div class="course-grid"></div>')
    && html.includes('<div id="dayB" class="tab-content">\r\n            <div class="course-grid"></div>')
    && html.includes('function renderCourseCards()'));
check('the roster is the single source for every course consumer',
    html.includes('window.cpGetCourseNames')            // Calendar
    && html.includes('window.cpSyncCourseRoster=syncCourses')
    && html.includes('window.cpSyncStudySubjects = syncSubjectOptions')
    && html.includes('ALL_COURSE_NAMES = getCourses().map(c => c.name)'));
check('the Calendar subject list reads the roster from storage',
    html.includes("localStorage.getItem('cp_courses_v1')") && html.includes('courses.includes(o.title)'));
check('the Backup tab hosts the course editor',
    html.includes('id="courseManagerList"') && html.includes('id="courseAddForm"'));

// ---- 10. day toggles reuse the Calendar checkbox system ---------------------
// .cal-square-check resolves --cal-* tokens, which deliberately cannot live on
// :root (a custom property holding var() resolves on the declaring element, so
// :root would freeze light-mode values). .course-manager therefore has to appear
// in BOTH token scopes or the boxes lose their fill and their white tick.
check('.course-manager joins the light --cal-* token scope',
    /#calendarTab, \.cal-toast[^{]*\.cal-picker,\r?\n\s*\.course-manager \{/.test(html));
check('.course-manager joins the dark --cal-* token scope',
    /body\.dark-mode \.cal-picker,\r?\n\s*body\.dark-mode \.course-manager \{/.test(html));
check('rendered day toggles carry the Calendar checkbox class',
    html.includes("box.className = 'cal-square-check'"));
check('the add-course form uses the same checkbox class',
    /id="courseAddDayA" data-day="dayA"/.test(html)
    && /id="courseAddDayB" data-day="dayB"/.test(html)
    && (html.match(/class="cal-square-check" type="checkbox"/g) || []).length === 2);
check('bespoke checkbox styling was removed in favour of the shared one',
    !html.includes('.cm-day input[type="checkbox"] {'));
check('Day A toggles re-point the accent to the shared Day A blue',
    html.includes('.cm-day .cal-square-check[data-day="dayA"] { --cal-accent: var(--color-day-a); }'));
check('Day B toggles re-point the accent to the shared Day B orange',
    html.includes('.cm-day .cal-square-check[data-day="dayB"] { --cal-accent: var(--color-day-b); }'));
check('the tick itself is still owned by the Calendar :checked rules',
    !/\.cm-day[^\n]*:checked[^\n]*background-image/.test(html));

// ---- 11. the Backup tab's three actions share the app's green --------------
const GREEN = 'linear-gradient(145deg, #58A65C, #4a9152)';
check('Export to JSON uses the shared green',
    html.includes('id="exportJsonBtn"') && html.includes('background: ' + GREEN));
check('Import from JSON uses the shared green',
    (html.match(/background: linear-gradient\(145deg, #58A65C, #4a9152\)/g) || []).length === 2);
check('Add course uses the shared green',
    html.includes('background: linear-gradient(145deg, var(--color-tracker-green), #4a9152);'));
check('no blue or orange button gradients remain in the Backup tab',
    !html.includes('linear-gradient(135deg, #4f93f0, #3b82f6)')
    && !html.includes('linear-gradient(135deg, #f0974f, #e67e22)'));
check('the light-only Backup panels gained dark-mode counterparts',
    html.includes('body.dark-mode .bk-panel {') && html.includes('body.dark-mode .bk-title {')
    && html.includes('class="bk-panel"') && html.includes('class="bk-icon"'));

console.log(failures ? `\n${failures} COURSE ROSTER CASE(S) FAILED` : '\nALL COURSE ROSTER CASES PASS');
process.exit(failures ? 1 : 0);
