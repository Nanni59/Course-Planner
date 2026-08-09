// Regression coverage for the local-first SAT Prep and IELTS engines.
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const marker = 'EXAM PREP ENGINE — SAT and IELTS remain separate local-first sections.';
const markerAt = html.indexOf(marker);
if (markerAt < 0) throw new Error('Exam Prep engine marker not found');
const start = html.indexOf('(function(){', markerAt);
const end = html.indexOf('\n    })();', start);
if (start < 0 || end < 0) throw new Error('Exam Prep engine boundaries not found');
const source = html.slice(start, end + '\n    })();'.length);

function storageStub(seed = {}) {
    const map = new Map(Object.entries(seed).map(([k, v]) => [k, String(v)]));
    return {
        getItem: k => map.has(k) ? map.get(k) : null,
        setItem: (k, v) => map.set(k, String(v)),
        removeItem: k => map.delete(k),
        _json: k => JSON.parse(map.get(k))
    };
}

const roots = {
    satPrep: { classList: { contains: () => false } },
    ieltsPrep: { classList: { contains: () => false } }
};
const localStorage = storageStub();
const windowStub = { addEventListener() {} };
const context = {
    window: windowStub,
    localStorage,
    document: {
        getElementById: id => roots[id] || null,
        querySelector: () => null
    },
    console,
    URL,
    Date,
    Math,
    JSON,
    Object,
    Array,
    String,
    Number,
    setTimeout() {},
    clearTimeout() {},
    requestAnimationFrame() {}
};
vm.runInNewContext(source, context, { filename: 'exam-prep-engine.js' });
const api = windowStub.cpExamPrepTest;
let failed = 0;
function check(label, condition, detail = '') {
    if (condition) console.log('PASS ' + label);
    else { failed++; console.error('FAIL ' + label + (detail ? ': ' + detail : '')); }
}

check('separate SAT and IELTS tab roots exist', /id="satPrep" class="tab-content"/.test(html) && /id="ieltsPrep" class="tab-content"/.test(html));
check('SAT and IELTS launch from Study Tools instead of separate footer buttons',
    !html.includes('id="satPrepBtn"') && !html.includes('id="ieltsPrepBtn"')
    && html.includes("examHubCard('satPrep'") && html.includes("examHubCard('ieltsPrep'"));
const footerOrder = ['studyToolsBtn', 'calendarBtn', 'lessonTrackerBtn', 'assignmentTrackerBtn'].map(id => html.indexOf('id="' + id + '"'));
check('Study Tools retains its original first footer position',
    footerOrder.every((position, index) => position >= 0 && (index === 0 || position > footerOrder[index - 1])));
check('exam routes highlight Study Tools in the footer',
    /satPrep:\s*'studyToolsBtn'/.test(html) && /ieltsPrep:\s*'studyToolsBtn'/.test(html));
check('route slugs are registered', /satPrep:\s*'sat-prep'/.test(html) && /ieltsPrep:\s*'ielts'/.test(html));
check('main tab allow-list contains both tabs', /VALID_MAIN_TABS[^;]+satPrep[^;]+ieltsPrep/.test(html));

const sat = localStorage._json('cp_satPrep_v1');
const ielts = localStorage._json('cp_ieltsPrep_v1');
check('SAT defaults persist under versioned key', sat.schemaVersion === 1 && sat.settings.examDate === '2026-10-03' && sat.settings.timezone === 'Asia/Riyadh');
check('SAT targets use requested defaults', sat.settings.targetTotal === 1500 && sat.settings.targetRW === 720 && sat.settings.targetMathMin === 790 && sat.settings.targetMathMax === 800);
check('SAT schedule excludes ordinary Friday and Saturday sessions', sat.sessions.every(x => ![5, 6].includes(new Date(x.originalDate + 'T12:00:00').getDay())));
check('six planned Bluebook tests are seeded', sat.practiceTests.length === 6 && sat.practiceTests[0].name === 'Practice Test 4' && sat.practiceTests[5].date === '2026-09-27');
check('IELTS defaults persist under separate versioned key', ielts.schemaVersion === 1 && ielts.settings.testType === 'IELTS Academic' && ielts.settings.testDate === '');
check('IELTS overall target defaults to 7.5', ielts.settings.targetOverall === 7.5);

check('local day count ignores elapsed-hour/DST behavior', api.daysRemainingLocal('2026-03-09', '2026-03-07') === 2);
check('local calendar addition crosses month boundary', api.addLocalDays('2026-08-31', 2) === '2026-09-02');
const redos = api.redoSchedule('2026-09-01');
check('missed-question redos are due at about 48 hours and one week', redos[0].due === '2026-09-03' && redos[1].due === '2026-09-08');

const scored = [
    { date: '2026-09-06', rw: 700, math: 780 },
    { date: '2026-09-13', rw: 720, math: 790 },
    { date: '2026-09-20', rw: 730, math: 800 }
];
check('latest-two SAT average uses the two most recent complete tests', api.latestTwoAverage(scored) === 1520);
const domainRows = [
    { date: '2026-08-01', domain: 'Craft and Structure', result: 'incorrect' },
    { date: '2026-08-02', domain: 'Craft and Structure', result: 'correct' },
    { date: '2026-08-03', domain: 'Craft and Structure', result: 'correct' },
    { date: '2026-08-04', domain: 'Craft and Structure', result: 'correct' }
];
const craft = api.satDomainStats(domainRows).find(x => x.domain === 'Craft and Structure');
check('SAT domain accuracy counts correct versus all logged outcomes', craft.total === 4 && craft.correct === 3 && craft.accuracy === 75);
check('SAT domain trend compares recent and earlier practice', craft.trend === 50);

const readyState = {
    settings: { targetTotal: 1500, targetRW: 720, targetMathMin: 790, targetMathMax: 800 },
    practiceTests: [
        { date: '2026-09-20', rw: 720, math: 790, forcedGuesses: 2 },
        { date: '2026-09-27', rw: 730, math: 800, forcedGuesses: 1 }
    ]
};
check('SAT readiness applies latest-two, section, Math range, and timing rules', api.satReadinessFor(readyState) === true);
readyState.practiceTests[1].forcedGuesses = 4;
check('SAT readiness fails when timing guesses are uncontrolled', api.satReadinessFor(readyState) === false);
const advisoryState = {
    settings: readyState.settings,
    practiceTests: [{ date: '2026-09-20', rw: 690, math: 780, forcedGuesses: 2 }],
    errors: [
        { date: '2026-09-19', domain: 'Standard English Conventions', result: 'incorrect' },
        { date: '2026-09-20', domain: 'Standard English Conventions', result: 'correct' }
    ]
};
const advice = api.satRecommendations(advisoryState, '2026-09-20').join(' ');
check('recommendations include Math maintenance and grammar-book rules', advice.includes('maintenance level') && advice.includes('Erica Meltzer'));

check('IELTS .25 average rounds up to the next half band', api.ieltsOverallBand({ Listening: 7.5, Reading: 7.5, Writing: 7, Speaking: 7 }) === 7.5);
check('IELTS .75 average rounds up to the next whole band', api.ieltsOverallBand({ Listening: 8, Reading: 8, Writing: 7.5, Speaking: 7.5 }) === 8);
check('IELTS requires all four sections before calculating overall', api.ieltsOverallBand({ Listening: 8, Reading: 8, Writing: 7.5 }) === null);

const oldSat = api.normalizeSat({ settings: { targetTotal: 1510 }, practiceTests: [] });
const oldIelts = api.normalizeIelts({ settings: { targetOverall: 8 }, resources: [] });
check('incomplete SAT data migrates without losing supplied values', oldSat.settings.targetTotal === 1510 && Array.isArray(oldSat.sessions) && oldSat.schemaVersion === 1);
check('incomplete IELTS data migrates without losing supplied values', oldIelts.settings.targetOverall === 8 && Array.isArray(oldIelts.maintenance) && oldIelts.schemaVersion === 1);

const satRecords = api.satCalendarRecords();
const ids = satRecords.map(x => x.examLink.id);
check('SAT Calendar records use stable namespaced identifiers', ids.length === new Set(ids).size && ids.every(x => x.startsWith('sat:')));
const simulatedCalendar = new Map();
[...satRecords, ...api.satCalendarRecords()].forEach(x => simulatedCalendar.set(x.examLink.id, x));
check('repeated SAT Calendar insertion is idempotent by stable link id', simulatedCalendar.size === satRecords.length);
check('Calendar bridge finds existing linked IDs before inserting', html.includes("x.examLink&&x.examLink.id===raw.examLink.id"));
check('Calendar edits preserve examLink metadata', /Object\.assign\(\{\},old,d,\{id:old\.id/.test(html));
check('backup import normalizes optional exam payloads', html.includes('window.cpNormalizeExamPrepBackup(importedData)'));
check('exam notes render through textContent/DOM nodes', source.includes("function h(tag,cls,text)") && source.includes('e.textContent=String(text)'));
check('resource URLs are restricted to http and https', source.includes("/^https?:$/.test(u.protocol)"));
check('exam controls explicitly inherit the Century Gothic font stack',
    /\.exam-shell button, \.exam-shell input, \.exam-shell select, \.exam-shell textarea \{\s*font-family:'Century Gothic'/.test(html));
check('invalid font shorthand no longer makes exam buttons fall back to Arial',
    !html.includes('font:600 13px inherit') && !html.includes('font:500 13px inherit'));
check('title case keeps small words lowercase and replaces and with an ampersand',
    api.titleCaseText('Craft and Structure or Expression because Timing') === 'Craft & Structure or Expression because Timing');
check('title case preserves exam acronyms', api.titleCaseText('SAT and IELTS practice') === 'SAT & IELTS Practice');
check('CSS auto-capitalization was removed', !/\.exam-shell\s*\{[^}]*text-transform\s*:\s*capitalize/.test(html));
check('section navigation keeps panel spacing and protects hovered buttons from clipping',
    /\.exam-section-nav \{[^}]*padding:5px 2px 7px;[^}]*margin:-5px 0 18px/.test(html));
check('stacked plan and deadline entries have explicit breathing room',
    /\.exam-card > \.exam-entry \+ \.exam-entry \{ margin-top:16px; \}/.test(html));
check('summary cards have space before the first practice entry',
    /\.exam-card > \.exam-summary-grid \+ \.exam-entry/.test(html));
check('SAT and IELTS use distinct blue and red accent palettes',
    /#satPrep \{[\s\S]*?--exam-accent:#2474b5;/.test(html)
    && /#ieltsPrep \{[\s\S]*?--exam-accent:#d7193f;/.test(html));
check('exam eyebrow headings were removed and SAT title is shortened',
    !source.includes('Digital SAT preparation') && !source.includes('Academic IELTS preparation')
    && source.includes("setupShell(satRoot,'sat','SAT'"));
check('exam hub cards use locally embedded official logo assets',
    html.includes("satMark: '<img src=\"data:image/png;base64,") && html.includes("ieltsMark: '<svg")
    && html.includes('viewBox="35.57 33.59 261.68 75.1"')
    && html.includes("examHubCard('satPrep', I.satMark") && html.includes("examHubCard('ieltsPrep', I.ieltsMark"));
check('exam logos retain the generator icon-box dimensions',
    /\.st-exam-card \.st-ico \{ padding:8px; box-sizing:border-box; overflow:hidden; \}/.test(html)
    && /\.st-exam-card-sat \.st-ico \{ padding:0; background:#0068b5; \}/.test(html));
check('IELTS logo uses the inverted white-on-red treatment',
    html.includes('.st-exam-card-ielts .st-ico { background:#d7193f; }')
    && /ieltsMark: '<svg[^']*<path fill="#fff"/.test(html));
check('exam hub cards do not add brand outlines on hover',
    !html.includes('.st-exam-card-sat:hover') && !html.includes('.st-exam-card-ielts:hover'));
check('exam return control reuses the generator back-arrow component',
    source.includes('class="st-back exam-back"') && source.includes('aria-label="Back to Study Tools"')
    && !source.includes('>← Study Tools</button>'));
check('resources render without completion checkboxes',
    !source.includes("check.setAttribute('aria-label','Mark '+x.title+' complete')"));
check('exam dialogs reuse themed dropdowns and Calendar date pickers',
    source.includes("window.cpThemeSelect?.(select)")
    && source.includes("window.cpBindCalendarPickers?.(card)")
    && html.includes('window.cpBindCalendarPickers=bindCalendarPickers'));
check('global date picker uses Calendar arrows with mode-aware monochrome color',
    html.includes('.cal-date-picker .cal-picker-nav[data-picker-prev]::before')
    && html.includes('.cal-date-picker .cal-picker-nav[data-picker-next]::before')
    && /\.cal-date-picker \.cal-picker-nav\[data-picker-next\] \{ color:#fff; \}/.test(html)
    && html.includes('font-size:0; color:#111;')
    && !source.includes('aria-label="Previous month">‹'));

if (failed) {
    console.error('\n' + failed + ' exam prep test(s) failed.');
    process.exit(1);
}
console.log('\nAll exam prep tests passed.');
