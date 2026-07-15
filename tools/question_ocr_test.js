// Regression test for the pure functions behind the STEM Video Generator's
// "Scan question" (OCR) button in index.html: scannedPartsText / stripQuestionLabel /
// normalizeScannedText (model JSON -> field text). Extracted by string markers.
//
// Covers:
//   - "Part <label>: <text>" formatting, in order, blank-line separated
//   - the label is normalised: "Part B" / "b)" / "C." all reduce to a bare letter
//   - a lone unlabelled part stays plain text (no invented "Part A")
//   - missing labels fall back to A, B, C… by position
//   - empty/blank/garbage input yields '' rather than throwing
//   - question numbers and mark allocations are stripped, WITHOUT eating real content
//   - normalizeScannedText repairs escapes but never rewords (verbatim guarantee)
//   - THE KEY INVARIANT: output stays parseable by the [data-vidaddpart] counter,
//     which numbers the next part via /\bPart\s+[A-Z]/gi — a scan must not make
//     "Add part" restart at A or skip letters.
//
// Run: node tools/question_ocr_test.js   (exit 0 = pass)
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

const src = slice('function scannedPartsText(parts) {', 'function setOcrBusy(btn, busy) {');
const api = new Function(src + '\nreturn { scannedPartsText, stripQuestionLabel };')();
const scannedPartsText = api.scannedPartsText;
const stripQuestionLabel = api.stripQuestionLabel;

// normalizeScannedText + the escape/glyph repair layer it composes. Pulled in with its
// real dependencies so this pins the LIVE behaviour, not a copy that can drift.
const normalizeScannedText = new Function(
    slice('function normalizeLatexBackslashes(s) {', 'function repairModelMathText(s) {') +
    slice('function repairParsedLatexEscapes(s) {', 'function flattenInlineMath(s) {') +
    slice('function balanceDollarMath(s) {', 'function repairVectorGlyphs(s) {') +
    slice('function repairVectorGlyphs(s) {', 'function normalizeGeneratedString(s) {') +
    slice('function normalizeScannedText(s) {', 'function scannedPartsText(parts) {') +
    '\nreturn normalizeScannedText;'
)();

// The live "Add part" counter, kept in sync with the [data-vidaddpart] handler.
const ADD_PART_COUNTER = /\bPart\s+[A-Z]/gi;
const nextAddPartLabel = text =>
    String.fromCharCode(65 + Math.min((text.match(ADD_PART_COUNTER) || []).length, 25));

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}

// == basic multi-part formatting =================================================
{
    const out = scannedPartsText([
        { label: 'A', text: 'Find $f\'(x)$.' },
        { label: 'B', text: 'Evaluate at $x = 2$.' }
    ]);
    check('parts render as "Part X: text" separated by a blank line',
        out === 'Part A: Find $f\'(x)$.\n\nPart B: Evaluate at $x = 2$.', JSON.stringify(out));
}

// == label normalisation =========================================================
{
    const out = scannedPartsText([
        { label: 'Part B', text: 'one' },
        { label: 'c)', text: 'two' },
        { label: 'D.', text: 'three' },
        { label: ' e ', text: 'four' }
    ]);
    check('"Part B" loses the redundant word', out.indexOf('Part B: one') === 0, JSON.stringify(out));
    check('trailing ")" / "." / whitespace stripped from labels',
        out.indexOf('Part c: two') > 0 && out.indexOf('Part D: three') > 0 && out.indexOf('Part e: four') > 0,
        JSON.stringify(out));
}

// == a single unlabelled part is just the question body ==========================
{
    const out = scannedPartsText([{ label: '', text: 'A ball is thrown at $5$ m/s.' }]);
    check('lone unlabelled part is emitted as plain text (no invented "Part A")',
        out === 'A ball is thrown at $5$ m/s.', JSON.stringify(out));
}

// == missing labels fall back to position ========================================
{
    const out = scannedPartsText([{ text: 'first' }, { text: 'second' }, { label: 'Z', text: 'third' }]);
    check('unlabelled multi-part input is lettered by position, explicit labels kept',
        out === 'Part A: first\n\nPart B: second\n\nPart Z: third', JSON.stringify(out));
}

// == empty / malformed input =====================================================
{
    check('undefined input -> empty string', scannedPartsText(undefined) === '');
    check('non-array input -> empty string', scannedPartsText('nope') === '');
    check('empty array -> empty string', scannedPartsText([]) === '');
    check('parts with blank text are dropped',
        scannedPartsText([{ label: 'A', text: '   ' }, { label: 'B', text: '' }]) === '');
    // A null entry is dropped, leaving one part that still carries an explicit label —
    // so it keeps its "Part A:" prefix; only *unlabelled* singles collapse to plain text.
    check('null entries are dropped without throwing',
        scannedPartsText([null, { label: 'A', text: 'kept' }]) === 'Part A: kept',
        JSON.stringify(scannedPartsText([null, { label: 'A', text: 'kept' }])));
}

// == INVARIANT: "Add part" keeps numbering after a scan ==========================
{
    const out = scannedPartsText([
        { label: 'A', text: 'one' }, { label: 'B', text: 'two' }, { label: 'C', text: 'three' }
    ]);
    check('after a 3-part scan, "Add part" offers D (not A)', nextAddPartLabel(out) === 'D',
        'got ' + nextAddPartLabel(out));
}
{
    // Lowercase labels still have to be counted — the live counter is case-insensitive.
    const out = scannedPartsText([{ label: 'a', text: 'one' }, { label: 'b', text: 'two' }]);
    check('lowercase scanned labels are still counted by "Add part"', nextAddPartLabel(out) === 'C',
        'got ' + nextAddPartLabel(out));
}
{
    const out = scannedPartsText([{ label: '', text: 'Just the body, no parts.' }]);
    check('after an unlabelled scan, "Add part" starts at A', nextAddPartLabel(out) === 'A',
        'got ' + nextAddPartLabel(out));
}

// == the real Q2: only the instruction reaches the Question field =================
// The tool handles one question at a time, so the number and the marks are noise. The
// prompt asks Gemini to omit them, but it kept "[2 marks each]" when told to ignore mark
// allocations — hence the deterministic strip these cases pin.
{
    const title = stripQuestionLabel(
        'Q2. [2 marks each] Determine whether the following limits exist or not. ' +
        'Explain either way. If the limit exit, find its value.'
    );
    const body = scannedPartsText([
        { label: 'a', text: '$\\lim_{x\\to 0} \\frac{\\sqrt{16-x}-4}{x}$' },
        { label: 'b', text: '$\\lim_{x\\to 2} \\frac{3x^2-7x+2}{2x^2-x-6}$' }
    ]);
    check('question number and marks are both stripped',
        title === 'Determine whether the following limits exist or not. Explain either way. ' +
                  'If the limit exit, find its value.', JSON.stringify(title));
    check('the instruction does NOT leak into the Parts field',
        body.indexOf('Determine whether') === -1, JSON.stringify(body));
    check('Parts contains only the lettered parts',
        body === 'Part a: $\\lim_{x\\to 0} \\frac{\\sqrt{16-x}-4}{x}$\n\n' +
                 'Part b: $\\lim_{x\\to 2} \\frac{3x^2-7x+2}{2x^2-x-6}$', JSON.stringify(body));
    // The worksheet really does say "exit" instead of "exists" — a transcription must not
    // silently correct it, so this doubles as a verbatim guard.
    check('an original typo is reproduced, not corrected', title.indexOf('If the limit exit,') > 0);
}

// == label forms that SHOULD be stripped =========================================
{
    const cases = [
        ['Q2. Find x', 'Find x'],
        ['Q 2) Find x', 'Find x'],
        ['Question 2: Find x', 'Find x'],
        ['Question #10 Find x', 'Find x'],
        ['questions 3 - Find x', 'Find x'],
        ['2. Find x', 'Find x'],
        ['3) Find x', 'Find x'],
        ['[2 marks each] Find x', 'Find x'],
        ['Find x (3 marks)', 'Find x'],
        ['Q5. [10 pts] Find x', 'Find x'],
        ['Find x [1 mark] and y [2 marks]', 'Find x and y'],
    ];
    cases.forEach(([input, want]) => check('strips: ' + JSON.stringify(input),
        stripQuestionLabel(input) === want, JSON.stringify(stripQuestionLabel(input))));
}

// == content that must SURVIVE the stripper ======================================
// Each of these would be corrupted by a looser regex.
{
    const keep = [
        // A bare leading number with no delimiter is real content, not a label.
        ['16 - x is the numerator, find the limit.', '16 - x is the numerator, find the limit.'],
        // "Q1" as a physics variable: no delimiter, so it must not be treated as a label.
        ['Q1 is the charge on the first sphere. Find the force.', 'Q1 is the charge on the first sphere. Find the force.'],
        // A number+decimal that is data, not a label.
        ['2.5 kg of water is heated. Find the energy.', '2.5 kg of water is heated. Find the energy.'],
        // "marks" in prose, not an allocation.
        ['Explain what marks the boundary of the region.', 'Explain what marks the boundary of the region.'],
        // Bracketed content that is not a mark allocation.
        ['Find $x$ [see the diagram above].', 'Find $x$ [see the diagram above].'],
    ];
    keep.forEach(([input, want]) => check('keeps: ' + JSON.stringify(input.slice(0, 34)) + '…',
        stripQuestionLabel(input) === want, JSON.stringify(stripQuestionLabel(input))));
}

// == stripper edge cases =========================================================
{
    check('empty -> empty string', stripQuestionLabel('') === '');
    check('undefined -> empty string', stripQuestionLabel(undefined) === '');
    check('null -> empty string', stripQuestionLabel(null) === '');
    check('a label with nothing after it -> empty string', stripQuestionLabel('Q2.') === '');
    // #vidQuestionName is a single-line <input>: newlines cannot render there at all, so
    // they are collapsed deliberately rather than left for the browser to mangle.
    check('newlines collapse to spaces for the single-line input',
        stripQuestionLabel('Q3. Given:\nmass = 5 kg\nvelocity = 3 m/s') ===
        'Q3. Given: mass = 5 kg velocity = 3 m/s'.replace(/^Q3\. /, ''),
        JSON.stringify(stripQuestionLabel('Q3. Given:\nmass = 5 kg\nvelocity = 3 m/s')));
}
{
    // Stripping the label must not disturb "Add part" numbering.
    const body = scannedPartsText([{ label: 'a', text: 'one' }, { label: 'b', text: 'two' }]);
    check('"Add part" offers C after a two-part scan', nextAddPartLabel(body) === 'C',
        'got ' + nextAddPartLabel(body));
    check('a parts-free scan leaves "Add part" at A', nextAddPartLabel(scannedPartsText([])) === 'A');
}

// == normalizeScannedText: repair escapes, NEVER reword ==========================
// A scan is a verbatim transcription. normalizeGeneratedString (the display pipeline)
// rewrites wording — respacing units, collapsing newlines, stripping \text{} around
// ordinary words, wrapping prose in \(…\). Routing scans through it caused the original
// "slightly inaccurate wording" bug; these cases pin the transcription-safe path.
{
    const keep = [
        ['unit spacing is left alone', 'A ball travels 5m in 2s.'],
        ['degree/word spacing left alone', 'Launched at 20m/s at an angle of 30 degrees.'],
        ['prose is not wrapped in \\(…\\)', 'Find the angle where the triangle A B C is right.'],
        ['plain sentence survives untouched', 'State the domain and round to two decimal places.'],
        ['double spaces after a full stop survive', 'First sentence.  Second sentence.'],
    ];
    keep.forEach(([name, input]) => check(name, normalizeScannedText(input) === input,
        JSON.stringify(normalizeScannedText(input)) + ' !== ' + JSON.stringify(input)));
}
{
    const multiline = 'Given:\nmass = 5 kg\nvelocity = 3 m/s';
    check('meaningful newlines are preserved', normalizeScannedText(multiline) === multiline,
        JSON.stringify(normalizeScannedText(multiline)));
}
{
    check('\\text{} around ordinary words is not stripped',
        normalizeScannedText('$x = 5\\text{ if the ball stops}$') === '$x = 5\\text{ if the ball stops}$',
        JSON.stringify(normalizeScannedText('$x = 5\\text{ if the ball stops}$')));
}
{
    // What it SHOULD still repair: doubled backslashes from protectLatexJsonEscapes.
    check('doubled backslashes are collapsed back to LaTeX',
        normalizeScannedText('$\\\\theta = 30^\\\\circ$') === '$\\theta = 30^\\circ$',
        JSON.stringify(normalizeScannedText('$\\\\theta = 30^\\\\circ$')));
    // ...and control-char damage from JSON parsing "\theta" -> TAB + "heta".
    check('TAB+heta is repaired back to \\theta',
        normalizeScannedText('$\theta = 30$') === '$\\theta = 30$',
        JSON.stringify(normalizeScannedText('$\theta = 30$')));
    check('null/undefined -> empty string',
        normalizeScannedText(null) === '' && normalizeScannedText(undefined) === '');
}

console.log('');
if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
console.log('ALL QUESTION OCR CASES PASS');
