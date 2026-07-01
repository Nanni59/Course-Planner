// Regression harness: extracts the real math/text normalization pipeline out of
// index.html and runs representative (including previously broken) Gemini worksheet
// outputs through it. Run with:  node tools/worksheet_text_harness.js
// Exits non-zero if any case regresses (fragmentation markers reappear).
const fs = require('fs');
const path = require('path').join(__dirname, '..', 'index.html');
const html = fs.readFileSync(path, 'utf8');

function slice(startMarker, endMarker) {
    const a = html.indexOf(startMarker);
    const b = html.indexOf(endMarker, a);
    if (a < 0 || b < 0) throw new Error('marker not found: ' + startMarker + ' / ' + endMarker);
    return html.slice(a, b);
}

// helpers block: deBold ... normalizeGeneratedContent (ends before subjects section)
const helpers = slice('const deBold', '/* ---------- Subjects from');
// JSON repair helpers
const jsonHelpers = slice('function stripJSON', 'function geminiErr');

const src = helpers + '\n' + jsonHelpers + '\n';
const fns = new Function(src +
    '\nreturn { escMath, escMathFlow, esc, escNL, normalizeGeneratedContent, normalizeGeneratedString, normalizeMathDelimiters, protectLatexJsonEscapes, stripJSON };')();
const { escMath, escMathFlow, normalizeGeneratedContent, protectLatexJsonEscapes, stripJSON } = fns;

// ---- representative model outputs (as raw JSON text, i.e. what Gemini returns) ----
const cases = [
    {
        name: 'q1 well-escaped inline \\( \\)',
        json: String.raw`{"q":"In \\(\\triangle ABC\\), \\(\\angle A = 40^\\circ\\), \\(\\angle B = 60^\\circ\\), and side \\(a = 10\\text{ cm}\\). Find the length of side \\(b\\) to one decimal place."}`
    },
    {
        name: 'q1 single-$ math',
        json: String.raw`{"q":"In $\\triangle ABC$, $\\angle A = 40^\\circ$, $\\angle B = 60^\\circ$, and side $a = 10\\text{ cm}$. Find the length of side $b$ to one decimal place."}`
    },
    {
        name: 'q1 single-backslash latex (model forgot JSON escaping)',
        json: `{"q":"In \\(\\triangle ABC\\), \\(\\angle A = 40^\\circ\\), and side \\(a = 10cm\\). Find side \\(b\\)."}`.replace(/\\\\/g, '\\')
    },
    {
        name: 'q3 surveyor prose + math',
        json: String.raw`{"q":"A surveyor measures the angle of elevation to the top of a tree from point \\(A\\) as \\(30^\\circ\\). They then walk \\(20\\text{ m}\\) directly away from the tree to point \\(B\\) and measure the angle of elevation as \\(20^\\circ\\). If points \\(A\\) and \\(B\\) are on level ground, what is the height of the tree to one decimal place?"}`
    },
    {
        name: 'q5 obtuse triangle with display \\[ \\]',
        json: String.raw`{"q":"An obtuse triangle has sides \\[a = 15cm\\], \\[b = 20cm\\], and angle \\[\\angle A = 40^\\circ\\]. Determine the measure of angle \\[\\angle B\\]."}`
    },
    {
        name: 'q with $$ display delimiters',
        json: String.raw`{"q":"In $$\\triangle DEF$$, side $$d = 8m$$, side $$e = 12m$$, and $$\\angle D = 35^\\circ$$. Find the measure of $$\\angle E$$ to the nearest degree."}`
    },
    {
        name: 'SCREENSHOT: newline-fragmented around every math span',
        json: String.raw`{"q":"In\n\\(\\triangle ABC\\)\n,\n\\(\\angle A = 40^\\circ\\)\n,\n\\(\\angle B = 60^\\circ\\)\n, and side\n\\(a = 10\\text{ cm}\\)\n. Find the length of side\n\\(b\\)\nto one decimal place."}`
    },
    {
        name: 'SCREENSHOT: newlines + $$ wrapping combined',
        json: String.raw`{"q":"Two observers are\n$$10\\text{ km}$$\napart. Observer\n$$A$$\nsees a hot air balloon at an angle of elevation of\n$$45^\\circ$$\n. What is the altitude of the balloon?"}`
    },
    {
        name: 'answer with numbered steps must keep line breaks',
        json: String.raw`{"q":"ok","answer":"Use the sine law:\n\\(\\frac{a}{\\sin A} = \\frac{b}{\\sin B}\\)\n2. Substitute values.\n3. Solve for \\(b\\), giving \\(b = 13.2\\) cm."}`
    },
    {
        name: 'legit long display equation must stay display',
        json: String.raw`{"q":"Derive the result.","answer":"Start from the identity below.\n$$\\frac{a}{\\sin A} = \\frac{b}{\\sin B} = \\frac{c}{\\sin C} = 2R \\quad\\text{for any triangle inscribed in a circle of radius } R$$\nThen substitute."}`
    },
    {
        name: 'SCREENSHOT answer: empty \\(\\) blob must vanish',
        json: String.raw`{"q":"ok","answer":"So \\(\\sin P \\approx 0.5312\\)\\(\\)P = \\arcsin(0.5312) \\approx 32.08^\\circ."}`,
        expect: { answerHasNoEmptyMath: true }
    },
    {
        name: 'SCREENSHOT answer: \\(a) label typo must not swallow prose',
        json: String.raw`{"q":"ok","answer":"So \\(\\angle C = 70^\\circ\\). \\(a) To find side \\(a = BC\\), use the Sine Law."}`,
        expect: { answerKeepsProseSpaces: ['To find side', 'use the Sine Law'] }
    }
];

function show(label, s) {
    console.log('  ' + label + ': ' + JSON.stringify(s));
}

let failures = 0;
for (const c of cases) {
    console.log('== ' + c.name + ' ==');
    let parsed;
    try {
        parsed = JSON.parse(protectLatexJsonEscapes(stripJSON(c.json)));
    } catch (e) {
        console.log('  JSON.parse FAILED: ' + e.message);
        failures++;
        continue;
    }
    const norm = normalizeGeneratedContent(parsed, null);
    show('normalized.q   ', norm.q);
    const qHtml = escMathFlow(norm.q); // worksheet question path
    show('q html (flow)  ', qHtml);
    const flags = [];
    if (qHtml.includes('<br>')) flags.push('q HAS <br> (line fragmentation!)');
    if (/\$\$[\s\S]*?\$\$/.test(qHtml)) flags.push('q HAS $$ display math (block fragmentation!)');
    if (/\\\[[\s\S]*?\\\]/.test(qHtml)) flags.push('q HAS \\[ \\] display math (block fragmentation!)');
    if (norm.answer != null) {
        const aHtml = escMath(norm.answer); // answer-key path keeps step breaks
        show('answer html    ', aHtml);
        if (/frac[\s\S]*<br>[\s\S]*Substitute/.test(aHtml) === false && /Substitute/.test(aHtml) && !/<br>2\. Substitute|<br>.*Substitute/.test(aHtml)) flags.push('answer lost its step line breaks!');
        if (/\\\(\\frac\{a\}/.test(aHtml) && /quad/.test(aHtml)) flags.push('long display equation was wrongly demoted to inline!');
        const exp = c.expect || {};
        if (exp.answerHasNoEmptyMath && /\\\(\s*\\\)/.test(aHtml)) flags.push('empty \\(\\) survived (renders as red error blob)');
        if (exp.answerKeepsProseSpaces) {
            for (const phrase of exp.answerKeepsProseSpaces) {
                if (!aHtml.includes(phrase)) flags.push('prose "' + phrase + '" was swallowed/space-collapsed');
            }
        }
    }
    if (flags.length) failures++;
    console.log(flags.length ? '  FLAGS: ' + flags.join(' | ') : '  OK');
    console.log('');
}
console.log(failures ? ('FAILED: ' + failures + ' case(s)') : 'ALL CASES PASSED');
process.exit(failures ? 1 : 0);
