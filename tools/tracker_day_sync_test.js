// Regression test for the LIVE syncTrackerInputToDayCards implementation in
// index.html (the one that matches cards by h3 text and takes `isComplete`).
// The function is extracted by string markers and run against a minimal DOM stub
// (no jsdom dependency needed — the function only uses querySelectorAll/
// querySelector/textContent/value/checked).
//
// Covers:
//   - matching the correct course only
//   - updating BOTH Day A and Day B cards for the same course
//   - ordinary assignment checkbox synchronization (check and uncheck)
//   - lesson synchronization uses the lesson field/checkbox
//   - split assignments update progress WITHOUT touching the Day-card checkbox
//   - no task-name match leaves cards unchanged
//
// Run: node tools/tracker_day_sync_test.js   (exit 0 = pass)
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

// The live implementation's signature is unique: the parameter is `isComplete`.
const src = slice(
    'function syncTrackerInputToDayCards(courseName, type, taskName, isComplete) {',
    '// Toggle Status functionality (used in tracker tabs)'
);

// ---- minimal DOM stub ---------------------------------------------------------
function makeCard(courseName, opts) {
    opts = opts || {};
    const els = {
        'h3': { textContent: '  ' + courseName + '  ' }, // real markup has whitespace; fn trims
        '.task-lesson-name': { value: opts.lessonName || '' },
        '.task-lesson-checkbox': { checked: !!opts.lessonChecked },
        '.task-assignment-name': { value: opts.assignmentName || '' },
        '.task-assignment-checkbox': { checked: !!opts.assignmentChecked },
    };
    return {
        course: courseName,
        day: opts.day || 'dayA',
        els,
        querySelector(sel) { return els[sel] || null; },
    };
}

function run(cards, args, splitNames) {
    splitNames = splitNames || [];
    const calls = { split: [], completion: [] };
    const documentStub = { querySelectorAll: sel => (sel === '.course-card' ? cards : []) };
    const fn = new Function(
        'document', 'isSplitAssignment', 'updateDayCardSplitProgress', 'updateCardCompletionState',
        src + '\nreturn syncTrackerInputToDayCards;'
    )(
        documentStub,
        (course, name) => splitNames.includes(name),
        (card, course, name) => calls.split.push({ day: card.day, course, name }),
        card => calls.completion.push(card.day + ':' + card.course)
    );
    fn.apply(null, args);
    return calls;
}

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}

const COURSE = 'Calculus & Vectors';
const OTHER = 'English';

// == ordinary assignment: both days updated, other course untouched ==============
{
    const a = makeCard(COURSE, { day: 'dayA', assignmentName: 'HW 5' });
    const b = makeCard(COURSE, { day: 'dayB', assignmentName: 'HW 5' });
    const other = makeCard(OTHER, { day: 'dayA', assignmentName: 'HW 5' }); // same task name, different course
    const calls = run([a, b, other], [COURSE, 'assignment', 'HW 5', true]);

    check('assignment checked on Day A card', a.els['.task-assignment-checkbox'].checked === true);
    check('assignment checked on Day B card', b.els['.task-assignment-checkbox'].checked === true);
    check('other course with same task name untouched', other.els['.task-assignment-checkbox'].checked === false);
    check('completion state refreshed on both matching cards only',
        calls.completion.sort().join() === 'dayA:' + COURSE + ',dayB:' + COURSE);
    check('no split-progress call for a normal assignment', calls.split.length === 0);
}

// == unchecking propagates ========================================================
{
    const a = makeCard(COURSE, { day: 'dayA', assignmentName: 'HW 5', assignmentChecked: true });
    run([a], [COURSE, 'assignment', 'HW 5', false]);
    check('unchecking clears the Day-card checkbox', a.els['.task-assignment-checkbox'].checked === false);
}

// == lessons use the lesson field/checkbox =======================================
{
    const a = makeCard(COURSE, { day: 'dayA', lessonName: 'Unit 3 Lesson 2', assignmentName: 'HW 5' });
    const calls = run([a], [COURSE, 'lesson', 'Unit 3 Lesson 2', true]);
    check('lesson checkbox updated', a.els['.task-lesson-checkbox'].checked === true);
    check('assignment checkbox untouched by a lesson sync', a.els['.task-assignment-checkbox'].checked === false);
    check('completion state refreshed for the lesson card', calls.completion.length === 1);
}

// == split assignment: progress path, checkbox NOT overwritten ===================
{
    const a = makeCard(COURSE, { day: 'dayA', assignmentName: 'Essay Draft' });
    const b = makeCard(COURSE, { day: 'dayB', assignmentName: 'Essay Draft' });
    const calls = run([a, b], [COURSE, 'assignment', 'Essay Draft', true], ['Essay Draft']);

    check('split assignment: progress updated on both cards',
        calls.split.map(c => c.day).sort().join() === 'dayA,dayB' &&
        calls.split.every(c => c.course === COURSE && c.name === 'Essay Draft'));
    check('split assignment: Day-card checkbox NOT overwritten',
        a.els['.task-assignment-checkbox'].checked === false &&
        b.els['.task-assignment-checkbox'].checked === false);
    check('split assignment: completion state still refreshed', calls.completion.length === 2);
}

// == no task-name match: nothing changes =========================================
{
    const a = makeCard(COURSE, { day: 'dayA', assignmentName: 'HW 5' });
    const calls = run([a], [COURSE, 'assignment', 'A Different Task', true]);
    check('name mismatch: checkbox unchanged', a.els['.task-assignment-checkbox'].checked === false);
    check('name mismatch: no completion refresh', calls.completion.length === 0 && calls.split.length === 0);
}

// == task name matching trims whitespace =========================================
{
    const a = makeCard(COURSE, { day: 'dayA', assignmentName: '  HW 5  ' });
    run([a], [COURSE, 'assignment', 'HW 5', true]);
    check('field value is trimmed before matching', a.els['.task-assignment-checkbox'].checked === true);
}

console.log('');
if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
console.log('ALL TRACKER SYNC CASES PASS');
