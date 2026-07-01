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
    },
    {
        name: 'SCREENSHOT answer: doubled opener \\(\\( must not leave red blob',
        json: String.raw`{"q":"ok","answer":"Let the sides be \\(\\(a = 5cm, b = 7cm, c = 8cm\\). The largest angle is opposite side \\(c\\)."}`,
        expect: { answerBalancedDelimiters: true, answerNoDoubledDelimiters: true }
    },
    {
        name: 'SCREENSHOT answer: long equation chain must become display (not overflow inline)',
        json: String.raw`{"q":"ok","answer":"Using the Cosine Law: \\(r^2 = p^2 + q^2 - 2pq\\cos R = 15^2 + 18^2 - 2(15)(18)\\cos 40^\\circ = 225 + 324 - 540(0.766) = 549 - 413.6 = 135.4\\). So \\(r = \\sqrt{135.4} \\approx 11.6m\\)."}`,
        expect: { answerHasDisplayChain: true }
    },
    {
        name: 'SCREENSHOT answer: single-$ steps with dropped closing $ must not leave literal $x=',
        json: "{\"q\":\"ok\",\"answer\":\"Substituting:\\n$x = \\\\frac{-5 \\\\pm \\\\sqrt{25+24}}{6}\\n$x = \\\\frac{-5 \\\\pm \\\\sqrt{49}}{6}$\\n$x = \\\\frac{-5 \\\\pm 7}{6}$\"}",
        expect: { answerNoLiteralDollar: true }
    },
    {
        name: 'ANSWER: single-backslash \\pm must survive JSON (protect list)',
        json: "{\"answer\":\"So $x = -5 \\pm 7$ over 6.\",\"q\":\"ok\"}",
        expect: { answerNoLiteralDollar: true, answerKeepsProseSpaces: ['over 6'] }
    },
    {
        name: 'ANSWER: currency must NOT be converted to math',
        json: "{\"q\":\"ok\",\"answer\":\"The ticket costs $5 and the meal costs $12 today.\"}",
        expect: { answerKeepsProseSpaces: ['costs', 'today'] }
    },
    {
        name: 'PDF vector glyphs become LaTeX vectors',
        json: "{\"q\":\"Two vectors ⅑ and ⅒ have magnitudes |⅑| = 15 and |⅒| = 20. The angle between them is 30^∘.\"}",
        expect: { qContains: ['\\vec{u}', '\\vec{v}', '^\\circ'], qNotContains: ['⅑', '⅒', '^∘'] }
    },
    {
        name: 'PDF indexed vector glyphs become subscripted LaTeX vectors',
        json: "{\"q\":\"Two forces ⅑_1 and ⅑_2 act on a particle. The angle between the two forces is 40^âˆ˜.\"}",
        expect: { qContains: ['\\vec{u}_{1}', '\\vec{u}_{2}', '^\\circ'], qNotContains: ['⅑', '^âˆ˜'] }
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
    const expQ = c.expect || {};
    if (expQ.qContains) {
        for (const phrase of expQ.qContains) {
            if (!qHtml.includes(phrase)) flags.push('question lost expected "' + phrase + '"');
        }
    }
    if (expQ.qNotContains) {
        for (const phrase of expQ.qNotContains) {
            if (qHtml.includes(phrase)) flags.push('question still contains bad token "' + phrase + '"');
        }
    }
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
        if (exp.answerNoDoubledDelimiters && (/\\\(\s*\\\(/.test(aHtml) || /\\\)\s*\\\)/.test(aHtml))) flags.push('doubled \\(\\( or \\)\\) survived (red error blob)');
        if (exp.answerBalancedDelimiters) {
            const o = (aHtml.match(/\\\(/g) || []).length, cl = (aHtml.match(/\\\)/g) || []).length;
            if (o !== cl) flags.push('unbalanced inline delimiters (opens=' + o + ' closes=' + cl + ')');
        }
        if (exp.answerHasDisplayChain && !/\\\[[\s\S]*=[\s\S]*=[\s\S]*\\\]/.test(aHtml)) flags.push('long equation chain was NOT promoted to display (will overflow inline)');
        if (exp.answerNoLiteralDollar && /(?<!\\)\$(?!\$)/.test(aHtml.replace(/\\\$/g, ''))) flags.push('stray single $ survived (renders as literal "$x=" text)');
    }
    if (flags.length) failures++;
    console.log(flags.length ? '  FLAGS: ' + flags.join(' | ') : '  OK');
    console.log('');
}
console.log(failures ? ('FAILED: ' + failures + ' case(s)') : 'ALL CASES PASSED');
process.exit(failures ? 1 : 0);
