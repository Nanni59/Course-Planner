// Regression test for the Calendar category colour picker's maths in index.html.
// The REAL hx()/hsv2hex()/hex2hsv() are extracted from the #calendarEngine script
// by string markers — no logic is re-implemented here.
//
// Why this suite exists: the picker is a CONTINUOUS gradient, so it can land on any
// point in the HSV space, but a category colour is interpolated into style attributes
// and is dropped on load by okCat() unless it is exactly #rrggbb. Every colour the
// gradient can produce must therefore be legal hex, and hex typed into the picker's
// field must survive the round-trip to the gradient position and back unchanged.
//
// Run: node tools/calendar_color_test.js   (exit 0 = pass)
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

const src = slice('    const hx=n=>Math.max(0', '    function showColorPicker(input){');
const { hsv2hex, hex2hsv } = new Function(src + '\nreturn{hsv2hex,hex2hsv}')();

// The real gate these colours have to pass on load, lifted from the engine so the
// test cannot drift from it.
const okCatSrc = slice('    const okCat=', '\n    function load()');
const okCat = new Function(okCatSrc + '\nreturn okCat')();

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}
const isHex = c => /^#[0-9a-f]{6}$/.test(c);

// == known colours round-trip exactly =========================================
{
    // The 16 swatches the old fixed-palette picker shipped: existing saved categories
    // hold these values, so the gradient must still reproduce them bit-for-bit.
    const legacy = ['#4f8fd8', '#58a65c', '#7c68c8', '#d97a55', '#df5f64', '#e5ad45', '#3fa7a3', '#77828f',
        '#e879a8', '#8854d0', '#2d98da', '#20bf6b', '#eb3b5a', '#fa8231', '#f7b731', '#4b6584'];
    const broken = legacy.filter(c => { const { h, s, v } = hex2hsv(c); return hsv2hex(h, s, v) !== c; });
    check('every legacy preset survives hex -> HSV -> hex', broken.length === 0, broken.join(','));
}
{
    // Achromatic and saturated edges are where naive HSV maths drifts.
    const edges = ['#000000', '#ffffff', '#7f7f7f', '#010203', '#fefefe', '#ff0000', '#00ff00', '#0000ff',
        '#ffff00', '#00ffff', '#ff00ff'];
    const broken = edges.filter(c => { const { h, s, v } = hex2hsv(c); return hsv2hex(h, s, v) !== c; });
    check('black/white/grey/primary edges round-trip', broken.length === 0, broken.join(','));
}

// == the gradient can only ever emit a colour the model accepts ===============
{
    let bad = null;
    for (let i = 0; i < 5000 && !bad; i++) {
        const c = hsv2hex(Math.random() * 360, Math.random(), Math.random());
        if (!isHex(c)) bad = c;
    }
    check('any point in the gradient yields #rrggbb', !bad, bad);
}
{
    // Out-of-band inputs must still clamp to a legal colour rather than produce
    // '#NaNNaNNaN' or a 5/7-digit string that okCat would silently drop.
    const wild = [hsv2hex(0, 0, 0), hsv2hex(360, 1, 1), hsv2hex(-20, -1, -1), hsv2hex(720, 2, 2)];
    check('out-of-range HSV still clamps to #rrggbb', wild.every(isHex), wild.join(','));
}
{
    let bad = null;
    for (let i = 0; i < 5000 && !bad; i++) {
        const c = '#' + [0, 0, 0].map(() => Math.floor(Math.random() * 256).toString(16).padStart(2, '0')).join('');
        const { h, s, v } = hex2hsv(c);
        if (hsv2hex(h, s, v) !== c) bad = c + ' -> ' + hsv2hex(h, s, v);
    }
    check('random hex round-trips exactly (5000 samples)', !bad, bad);
}

// == the colours actually reach the model =====================================
{
    const c = hsv2hex(210, .62, .85);
    check('a gradient colour passes okCat', okCat({ id: 'x', name: 'Test', color: c }), c);
    check('okCat still rejects a non-hex colour', !okCat({ id: 'x', name: 'Test', color: 'rgb(1,2,3)' }));
    check('okCat still rejects a 3-digit hex', !okCat({ id: 'x', name: 'Test', color: '#abc' }));
}

// == hue is preserved so the strip does not jump under the user ===============
{
    // A saturated colour must report back the hue it was built from (within rounding),
    // otherwise the hue thumb drifts every time the picker reopens.
    const drift = [15, 90, 180, 275, 359].filter(h => Math.abs(hex2hsv(hsv2hex(h, .9, .9)).h - h) > 1);
    check('hue survives the round-trip (thumb does not drift)', drift.length === 0, drift.join(','));
}

console.log(failures ? `\n${failures} COLOUR CASE(S) FAILED` : '\nALL COLOUR CASES PASS');
process.exit(failures ? 1 : 0);
