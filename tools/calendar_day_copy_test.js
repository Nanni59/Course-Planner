// Regression checks for Calendar -> Day A/B copy integration in index.html.
// Run: node tools/calendar_day_copy_test.js   (exit 0 = pass)
'use strict';

const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

function slice(start, end) {
    const a = html.indexOf(start);
    const b = html.indexOf(end, a);
    if (a < 0 || b < 0) throw new Error('marker not found: ' + start + ' / ' + end);
    return html.slice(a, b);
}

let failures = 0;
function check(name, condition) {
    if (condition) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name); }
}

const editor = slice('    function editor(seed)', '\n    function collect(f,subs)');
const calendarCopy = slice('    function sendDay(f,o,subs)', '\n    function settings()');
const autofill = slice('            function autofillAllCards()', '\n            function createAssignmentRow');
const collect = slice('    function collect(f,subs)', '\n    function saveEditor');
const daySubtasks = slice('            function dayCardSubtaskData(card)', '\n            // --- Embed/Link Rendering Logic');
const saveDay = slice('            function saveData(dayId)', '\n            window.cpSaveDay = saveData;');
const loadDay = slice('            function loadDay(dayId)', '\n            // ---');
const expandedCard = slice('            function openExpandCard(courseName, dayId)', '\n            let expandCardPreviousFocus');
const calendarAutofillHelper = slice('    window.cpGetCalendarTasksForDate=dateKey=>', '\n    function month');
const calendarInteractions = slice('    let subtaskHoverCloseTimer=null;', '\n    function bindMonthDrag');
const calendarPickers = slice('    let calendarPickerOutside=null', '\n    function bindCalendarLinkPreviews');
const calendarSettings = slice('    function settings()', '\n    function reminderStrip');
const daySubtaskStyles = slice('        .day-card-subtasks {', '\n        .day-card-subtasks-title {');
const hoverChecklistStyles = slice('        .cal-subtask-hover, .cal-subtask-quick {', '\n        .cal-subtask-quick { padding:8px; }');
const helperWindow = {};
new Function('window', 'date', 'expand', 'courses', calendarAutofillHelper)(
    helperWindow,
    value => value,
    () => [
        { displayDate: '2026-07-18', completed: false, type: 'task', title: 'Calculus & Vectors', subtasks: [{ id: 's1', title: 'Review vectors', completed: false }] },
        { displayDate: '2026-07-18', completed: true, type: 'task', title: 'English', subtasks: [{ id: 's2', title: 'Skip completed item', completed: false }] },
        { displayDate: '2026-07-18', completed: false, type: 'event', title: 'English', subtasks: [{ id: 's3', title: 'Skip event', completed: false }] },
        { displayDate: '2026-07-18', completed: false, type: 'task', title: 'Custom subject', subtasks: [{ id: 's4', title: 'Skip custom subject', completed: false }] }
    ],
    ['Calculus & Vectors', 'English', 'Media Arts', 'Business Leadership']
);
const scheduledByCourse = helperWindow.cpGetCalendarTasksForDate('2026-07-18');

check('Calendar editor has no Course field', !editor.includes('<label>Course</label>') && !editor.includes('name="course"'));
check('Calendar editor has no Tracker link', !editor.includes('<label>Tracker link</label>') && !editor.includes('name="trackerLink"'));
check('Calendar editor has no Reminder offsets', !editor.includes('<label>Reminder offsets</label>') && !editor.includes('name="reminders"'));
check('Calendar editor has no Occurrence count', !editor.includes('<label>Occurrence count</label>') && !editor.includes('name="count"'));
check('new Calendar saves disable removed link/reminder/count data', collect.includes('reminders:[]') && collect.includes('trackerLink:null') && !collect.includes('count:'));
check('Send copy receives current subtasks', editor.includes('sendDay(f,o,subs)') && calendarCopy.includes('collect(f,subs)'));
check('subtasks do not overwrite lesson/assignment title', calendarCopy.includes('if(name&&!hasSubtasks)'));
check('notes use the Day-card input pipeline', calendarCopy.includes("notes.dispatchEvent(new Event('input',{bubbles:true}))"));
check('subtasks use the Day-card copy helper', calendarCopy.includes('window.cpAppendDayCardSubtasks(card,d.subtasks)'));
check('Day data persists copied subtasks', saveDay.includes('subtasks: subtasks'));
check('Day data restores copied subtasks', loadDay.includes('renderDayCardSubtasks(card, courseData.subtasks || [])'));
check('subtask rows use independent card checkboxes', daySubtasks.includes('day-card-subtask-checkbox') && !daySubtasks.includes('task-checkbox day-card-subtask-checkbox'));
check('copied subtask section is labeled Tasks:', daySubtasks.includes("${index ? '' : 'Tasks:'}</div>"));
check('Day-card Tasks section is separated from Assignment', daySubtaskStyles.includes('border-top: 1px solid #eee;') && daySubtaskStyles.includes('padding-top: 10px;'));
check('copied task names use editable Day-card fields', daySubtasks.includes('<textarea class="day-card-subtask-title"') && daySubtasks.includes("?.value.trim()"));
check('copied tasks reuse the Lesson/Assignment three-column layout', daySubtasks.includes('class="task-main day-card-subtask-row') && daySubtasks.includes('<div class="task-name-wrapper">'));
check('Day-card task edits sync to Calendar', html.includes('window.cpUpdateCalendarSubtask(row.dataset.subtaskId, { title: target.value })'));
check('Calendar subtask saves sync back to Day cards', html.includes('window.cpSyncDaySubtasksFromCalendar(d.subtasks)'));
check('Autofill requests today\'s Calendar tasks', autofill.includes('window.cpGetCalendarTasksForDate(todayKey)'));
check('Autofill appends course-matched Calendar subtasks', autofill.includes('calendarTasks[courseName]') && autofill.includes('window.cpAppendDayCardSubtasks(card, scheduledTasks)'));
check('Calendar exposes date and subject matched tasks', html.includes('window.cpGetCalendarTasksForDate=dateKey=>') && html.includes("courses.includes(o.title)"));
check('Calendar Autofill returns only eligible course tasks', scheduledByCourse['Calculus & Vectors']?.[0]?.title === 'Review vectors' && !scheduledByCourse.English && !scheduledByCourse['Custom subject']);
check('Calendar urgency exclamation marks were removed', !html.includes("content:'!'") && !html.includes('content:"!"'));
check('all-day Calendar item titles remain bold', html.includes('.cal-all-cell .cal-item-title { font-weight:750; }'));
check('hover checklist uses enabled square checkboxes', calendarInteractions.includes('data-hover-sub=') && !calendarInteractions.includes('disabled aria-hidden'));
check('Calendar uses one canonical square checkbox style', html.includes('.cal-square-check {') && html.includes('.cal-square-check:checked {'));
check('Calendar field styling preserves canonical checkbox geometry', html.includes('.cal-field input:not([type="checkbox"])') && !html.includes('.cal-field input, .cal-field select'));
check('Calendar modals use a dedicated scrolling body', editor.includes('class="cal-modal-body"') && calendarSettings.includes('class="cal-modal-body"') && html.includes('.cal-modal-body::-webkit-scrollbar'));
check('Calendar modal header and footer share the themed surface', html.includes('body.dark-mode .cal-modal-head, body.dark-mode .cal-modal-actions { background:var(--cal-surface)'));
check('Calendar date and time fields avoid native browser pickers', editor.includes('data-cal-picker="date"') && editor.includes('data-cal-picker="time"') && !editor.includes('type="date"') && !editor.includes('type="time"'));
check('Calendar provides themed date and time picker dialogs', calendarPickers.includes("openCalendarDatePicker(input)") && calendarPickers.includes("openCalendarTimePicker(input)") && html.includes('cal-date-picker') && html.includes('cal-time-picker'));
check('Calendar picker receives dark-mode color tokens', html.includes('body.dark-mode .cal-color-picker, body.dark-mode .cal-picker'));
check('Calendar picker controls use Century Gothic longhands', html.includes(".cal-picker button { font-family:'Century Gothic'") && !html.includes('font:700 19px/1 inherit') && !html.includes('font:600 12px/1 inherit'));
check('dark Calendar fields do not erase checkbox ticks', html.includes('body.dark-mode .cal-field input:not([type="checkbox"])') && html.includes('body.dark-mode .cal-square-check:checked {') && html.includes('stroke=\'white\''));
check('all Calendar form checkboxes receive the canonical style', html.includes("scope.querySelectorAll('input[type=\"checkbox\"]')") && html.includes("classList.add('cal-square-check')"));
check('hover checklist uses the canonical checkbox style', calendarInteractions.includes('class="cal-square-check cal-subtask-hover-check"'));
check('hover checklist text uses semi-bold Century Gothic', hoverChecklistStyles.includes(".cal-subtask-hover-row { display:flex") && hoverChecklistStyles.includes("font-family:'Century Gothic','Futura','Montserrat',sans-serif; font-size:11px; font-weight:600;") && hoverChecklistStyles.includes(".cal-subtask-hover-hint {") && hoverChecklistStyles.includes("font-size:9px; font-weight:600;"));
check('legacy circular Calendar checkbox styling was removed', !html.includes('.cal-quick-subtask input[type="checkbox"]'));
check('hover checklist updates Calendar subtasks directly', calendarInteractions.includes("updateOccurrence(p.dataset.id,p.dataset.occ,{subtasks:subs},true)"));
check('Calendar item single-click opens details', calendarInteractions.includes("editor(find(e.dataset.id,e.dataset.occ))") && !calendarInteractions.includes("addEventListener('dblclick'"));
check('separate circular quick checklist was removed', !calendarInteractions.includes('function openSubtaskQuick'));
check('expanded cards render copied tasks', expandedCard.includes("const subtaskRows = li.querySelectorAll('.day-card-subtask-row')") && expandedCard.includes("${firstTask ? 'Tasks:' : ''}</div>"));
check('expanded task names proxy to the Day card', expandedCard.includes("realInput.dispatchEvent(new Event('input', { bubbles: true }))"));
check('expanded task checkboxes proxy to the Day card', expandedCard.includes("syncType === 'subtask'") && expandedCard.includes("realRow?.querySelector('.day-card-subtask-checkbox')"));
check('repeated copies deduplicate by subtask id', daySubtasks.includes('const ids = new Set') && daySubtasks.includes('!ids.has(subtaskId)'));
check('subtask-only cards hide empty lesson/assignment controls', html.includes('if (hasSubtasks && !lessonVal && !hasAnyAssignment)'));
check('Course filter was removed', !slice('    function filterUI()', '\n    function itemHTML').includes('data-filter="course"'));

console.log(failures ? `\n${failures} DAY-COPY CASE(S) FAILED` : '\nALL DAY-COPY CASES PASS');
process.exit(failures ? 1 : 0);
