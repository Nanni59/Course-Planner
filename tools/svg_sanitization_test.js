// Regression test for cleanEmbeddedSvg (index.html): the single choke point
// through which every backend TikZ SVG passes before being inlined via
// innerHTML (worksheet/guide/flashcard visuals, directly or via
// isolateEmbeddedSvg).
//
// Threat model under test (deliberately narrow — see the comment on the real
// function): strip active content a compromised/misbehaving TikZ backend
// could return — <script>, <foreignObject>, on*= handlers, javascript: URLs —
// while preserving everything legitimate pdf2svg output relies on (<g>,
// <path>, <defs>, <clipPath>, <use href="#…">, transforms, viewBox, styles).
// General hostile-HTML sanitization is out of scope; nothing else feeds this
// path.
//
// Run: node tools/svg_sanitization_test.js   (exit 0 = pass)
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

const src = slice('function cleanEmbeddedSvg(svg) {', 'function escRegExp');
const cleanEmbeddedSvg = new Function(src + '\nreturn cleanEmbeddedSvg;')();

let failures = 0;
function check(name, cond, detail) {
    if (cond) console.log('PASS  ' + name);
    else { failures++; console.log('FAIL  ' + name + (detail ? '  -> ' + detail : '')); }
}
// no active-content form may survive in sanitized output
function assertInert(name, input, extra) {
    const out = cleanEmbeddedSvg(input);
    const bad = [];
    if (/<script/i.test(out)) bad.push('<script>');
    if (/<foreignObject/i.test(out)) bad.push('<foreignObject>');
    if (/\son[a-z0-9_-]+\s*=/i.test(out)) bad.push('on*= handler');
    if (/j\s*a\s*v\s*a\s*s\s*c\s*r\s*i\s*p\s*t\s*:/i.test(out)) bad.push('javascript: url');
    check(name, bad.length === 0 && (!extra || extra(out)), bad.length ? 'survived: ' + bad.join(', ') + ' | out: ' + out.slice(0, 120) : 'extra check failed: ' + out.slice(0, 160));
    return out;
}

// == active content removal =====================================================
assertInert('script block removed (with contents)',
    '<svg viewBox="0 0 10 10"><script>fetch("https://evil")</script><path d="M0 0"/></svg>',
    out => !/fetch|evil/.test(out) && /<path d="M0 0"\/>/.test(out));
assertInert('mixed-case SCRIPT removed',
    '<svg><ScRiPt type="text/js">alert(1)</sCrIpT><g/></svg>',
    out => !/alert/.test(out) && /<g\/>/.test(out));
assertInert('unclosed script removed to end',
    '<svg><path d="M1 1"/><script>steal()',
    out => !/steal/.test(out) && /<path d="M1 1"\/>/.test(out));
assertInert('foreignObject removed (with HTML contents)',
    '<svg><foreignObject><iframe src="https://evil"></iframe><div onclick="x()">hi</div></foreignObject><circle r="2"/></svg>',
    out => !/iframe|evil|hi/.test(out) && /<circle r="2"\/>/.test(out));
assertInert('mixed-case ForeignObject removed',
    '<svg><FOREIGNOBJECT width="10"><body>x</body></foreignobject><rect width="1"/></svg>',
    out => /<rect width="1"\/>/.test(out));
assertInert('double-quoted event handler removed',
    '<svg onload="alert(1)"><path d="M0 0" onclick="alert(2)"/></svg>',
    out => /<svg>/.test(out) && /<path d="M0 0"\/>/.test(out));
assertInert('single-quoted event handler removed',
    "<svg onload='alert(1)'><g onmouseover='p()'/></svg>");
assertInert('unquoted event handler removed',
    '<svg onload=alert(1)><path d="M2 2" onerror=boom()/></svg>',
    out => /<path d="M2 2"\/>/.test(out));
assertInert('mixed-case event handler removed',
    '<svg OnLoAd="alert(1)" ONERROR=\'x()\'><path d="M3 3"/></svg>',
    out => /<path d="M3 3"\/>/.test(out));
assertInert('data-onward attribute names are not handlers but on*= variants are',
    '<svg onpointerdown="p()" on-custom="q()"><path d="M4 4"/></svg>',
    out => /<path d="M4 4"\/>/.test(out));
assertInert('href="javascript:..." removed',
    '<svg><a href="javascript:alert(1)"><text>click</text></a></svg>',
    out => /<text>click<\/text>/.test(out));
assertInert("single-quoted xlink:href javascript removed",
    "<svg><a xlink:href='javascript:alert(1)'>x</a></svg>");
assertInert('mixed-case JaVaScRiPt: removed',
    '<svg><a href="JaVaScRiPt:alert(1)">x</a></svg>');
assertInert('whitespace-smuggled java\\tscript: removed',
    '<svg><a href="  java\tscri\npt:alert(1)">x</a></svg>');
assertInert('unquoted javascript: href removed',
    '<svg><a href=javascript:alert(1)>x</a></svg>');

// == legitimate pdf2svg/TikZ output preserved ===================================
{
    // structurally faithful pdf2svg-style fixture: defs/glyphs, use href="#id",
    // clipPath, nested g transforms, style attributes
    const fixture = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="181pt" height="94pt" viewBox="0 0 181 94" version="1.1">',
        '<defs>',
        '<g><symbol overflow="visible" id="glyph0-1"><path style="stroke:none;" d="M 4.1 -1.2 C 3.9 -0.5 3.4 0 2.7 0 Z"/></symbol></g>',
        '<clipPath id="clip1"><path d="M 0 0 L 181 0 L 181 94 L 0 94 Z"/></clipPath>',
        '</defs>',
        '<g clip-path="url(#clip1)" clip-rule="nonzero">',
        '<path style="fill:none;stroke-width:0.79;stroke:rgb(0%,0%,0%);stroke-opacity:1;" d="M 0 0 L 56.69 0 "/>',
        '<g transform="matrix(1,0,0,-1,12.6,80.2)"><use xlink:href="#glyph0-1"/><use href="#glyph0-1" x="7.2"/></g>',
        '</g>',
        '</svg>'
    ].join('\n');
    const out = cleanEmbeddedSvg(fixture);
    check('fixture: XML declaration removed', !/<\?xml/.test(out));
    check('fixture: DOCTYPE removed', !/<!DOCTYPE/i.test(out));
    check('fixture: starts with <svg after cleaning', /^<svg/.test(out));
    for (const keep of ['<defs>', '<clipPath id="clip1">', '<symbol overflow="visible" id="glyph0-1">',
        '<use xlink:href="#glyph0-1"/>', '<use href="#glyph0-1" x="7.2"/>',
        'transform="matrix(1,0,0,-1,12.6,80.2)"', 'clip-path="url(#clip1)"',
        'style="fill:none;stroke-width:0.79;stroke:rgb(0%,0%,0%);stroke-opacity:1;"',
        'viewBox="0 0 181 94"']) {
        check('fixture keeps ' + keep.slice(0, 44), out.includes(keep));
    }
    // structure otherwise byte-identical: only the two prolog lines went away
    const expected = fixture.split('\n').slice(2).join('\n');
    check('fixture: geometry byte-identical to input minus prolog', out === expected);
}

// == misc =======================================================================
check('empty/null input yields empty string', cleanEmbeddedSvg(null) === '' && cleanEmbeddedSvg('') === '');
check('plain safe svg passes through', cleanEmbeddedSvg('<svg><path d="M0 0"/></svg>') === '<svg><path d="M0 0"/></svg>');

console.log('');
if (failures) { console.log(failures + ' FAILURE(S)'); process.exit(1); }
console.log('ALL SVG SANITIZATION CASES PASS');
