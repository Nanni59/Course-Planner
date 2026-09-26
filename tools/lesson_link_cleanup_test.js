// Regression test for pruneLessonAssignmentLinks in index.html: deleting tracker
// items (one item, a whole course via Delete All Tasks / the card X, or a tracker
// Reset) must also drop the saved lesson -> assignment links
// (tracker_lesson_assignments_map), or re-adding a lesson with the same name brings
// its old assignments back onto the Day card. The real function is extracted by
// string markers and run against a stubbed localStorage.
//
// Run: node tools/lesson_link_cleanup_test.js   (exit 0 = pass)
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
const src = slice('function pruneLessonAssignmentLinks(', 'function deleteTrackerItem(');

const KEY = 'tracker_lesson_assignments_map';
function makeStore(map) {
    const data = new Map([[KEY, JSON.stringify(map)]]);
    return {
        getItem: k => (data.has(k) ? data.get(k) : null),
        setItem: (k, v) => data.set(k, String(v)),
        read: () => JSON.parse(data.get(KEY)),
    };
}
function run(map, ...args) {
    const ls = makeStore(map);
    new Function('localStorage', src + '\nreturn pruneLessonAssignmentLinks;')(ls)(...args);
    return ls.read();
}

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + JSON.stringify(detail) : '')); }
}

const seed = () => ({
    'English::Unit 1': ['Essay', 'Quiz'],
    'English::Unit 2': ['Reading'],
    'English::Poetry': [],                    // lesson imported without assignments
    'English::__orphan__': ['Journal'],       // assignment-only import
    'Media Arts::Unit 1': ['Storyboard'],
});

{
    const m = run(seed(), 'lesson', 'English', 'Unit 1');
    check('deleting one lesson drops only that lesson\'s link',
        !('English::Unit 1' in m) && 'English::Unit 2' in m && 'Media Arts::Unit 1' in m, m);
}
{
    const m = run(seed(), 'assignment', 'English', 'Essay');
    check('deleting one assignment removes it from its lesson link',
        JSON.stringify(m['English::Unit 1']) === '["Quiz"]', m);
}
{
    const m = run(seed(), 'assignment', 'English', 'Reading');
    check('a link emptied by deleting its last assignment is dropped', !('English::Unit 2' in m), m);
}
{
    const m = run(seed(), 'lesson', 'English');
    check('Delete All Tasks (lessons) drops every lesson link for that course only',
        Object.keys(m).join('|') === 'English::__orphan__|Media Arts::Unit 1', m);
}
{
    const m = run(seed(), 'assignment', 'English');
    check('Delete All Tasks (assignments) drops that course\'s assignment links, keeps lessons imported without any',
        Object.keys(m).join('|') === 'English::Poetry|Media Arts::Unit 1', m);
}
{
    const m = run(seed(), 'lesson');
    check('lesson tracker Reset drops every lesson link, keeps assignment-only imports',
        Object.keys(m).join('|') === 'English::__orphan__', m);
}
{
    const m = run(seed(), 'assignment');
    check('assignment tracker Reset drops every assignment link',
        Object.keys(m).join('|') === 'English::Poetry', m);
}
{
    const ls = makeStore({});
    ls.setItem(KEY, '{not json');
    let threw = false;
    try { new Function('localStorage', src + '\nreturn pruneLessonAssignmentLinks;')(ls)('lesson', 'English'); } catch (e) { threw = true; }
    check('a damaged map is left alone instead of throwing', !threw && ls.getItem(KEY) === '{not json');
}

console.log('');
if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
console.log('ALL LESSON LINK CLEANUP CASES PASS');
