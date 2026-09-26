// Regression test for the Study Tools Gemini client in index.html: the model list
// (ST_MODELS / ST_FREE_MODELS / DEFAULT_MODEL) and gemini()'s fallback loop.
// Extracted by string markers and run against a stubbed fetch.
//
// Covers:
//   - the default is a free model and every free model is in the fallback chain
//   - a daily-quota 429 or a retired model's 404 moves on to the next free model
//   - the user's chosen model is tried first, then the free chain without repeats
//   - Gemma is asked without responseSchema, and its JSON is still parsed from text
//   - a Gemma 400 moves on, while a Gemini 400 (bad request / bad key) still fails at once
//
// Run: node tools/gemini_model_fallback_test.js   (exit 0 = pass)
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

const src =
    slice('const ST_MODELS = [', '// ── Phase 3') + '\n' +
    slice('async function gemini(parts, schema) {', '// Gemini sometimes wraps JSON') +
    slice('function stripJSON(s) {', 'function geminiErr(e) {');

function load(fetchImpl, chosenModel) {
    const store = { cp_gemini_key: 'test-key' };
    if (chosenModel) store.cp_gemini_model = chosenModel;
    const localStorage = { getItem: k => (k in store ? store[k] : null) };
    return new Function('fetch', 'localStorage',
        "const ST_KEY_STORE = 'cp_gemini_key'; const ST_MODEL_STORE = 'cp_gemini_model';\n" +
        'const wait = () => Promise.resolve();\n' +
        src +
        "\nconst getModel = () => localStorage.getItem(ST_MODEL_STORE) || DEFAULT_MODEL;\n" +
        "const geminiUrl = model => 'https://generativelanguage.googleapis.com/v1beta/models/' + (model || getModel()) + ':generateContent';\n" +
        'return { gemini, ST_MODELS, ST_FREE_MODELS, DEFAULT_MODEL };'
    )(fetchImpl, localStorage);
}

let failures = 0;
function check(name, cond) {
    console.log((cond ? 'PASS  ' : 'FAIL  ') + name);
    if (!cond) failures++;
}

const reply = text => ({ ok: true, status: 200, json: async () => ({ candidates: [{ content: { parts: [{ text }] } }] }) });
const error = (status, message) => ({ ok: false, status, text: async () => JSON.stringify({ error: { message } }) });

// Answers per model id; records every call as {model, body}.
function fakeFetch(answer) {
    const calls = [];
    const fetchImpl = async (url, opts) => {
        const model = url.split('/models/')[1].split(':')[0];
        const body = JSON.parse(opts.body);
        calls.push({ model, body });
        return answer(model, body);
    };
    return { calls, fetchImpl };
}

(async () => {
    const { ST_MODELS, ST_FREE_MODELS, DEFAULT_MODEL } = load(async () => reply('x'));
    check('the default is a free model', ST_FREE_MODELS.includes(DEFAULT_MODEL));
    check('the default is listed first', ST_MODELS[0].id === DEFAULT_MODEL);
    check('Flash-Lite and Gemma models are in the free chain',
        ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemma-4-31b-it', 'gemma-4-26b-a4b-it'].every(m => ST_FREE_MODELS.includes(m)));
    check('paid models stay out of the fallback chain', !ST_FREE_MODELS.includes('gemini-2.5-pro'));
    check('model ids are unique', new Set(ST_MODELS.map(m => m.id)).size === ST_MODELS.length);

    // Daily quota on the Flash models and a retired id: fall through to the first model that answers.
    let f = fakeFetch(model => model === 'gemini-3.5-flash-lite' ? reply('lite ok')
        : model === 'gemini-3-flash-preview' ? error(404, 'model is no longer available')
        : error(429, 'You exceeded your current quota'));
    let out = await load(f.fetchImpl).gemini([{ text: 'q' }]);
    check('429 / 404 fall through the free models in order',
        out === 'lite ok' && f.calls.map(c => c.model).join() === ST_FREE_MODELS.slice(0, ST_FREE_MODELS.indexOf('gemini-3.5-flash-lite') + 1).join());

    // A chosen model goes first, and the chain does not repeat it.
    f = fakeFetch(model => model === 'gemini-3.8-flash' ? reply('ok') : error(429, 'quota'));
    out = await load(f.fetchImpl, 'gemini-3.1-flash-lite').gemini([{ text: 'q' }]);
    check('the chosen model is tried first, then the default',
        out === 'ok' && f.calls.map(c => c.model).join() === 'gemini-3.1-flash-lite,gemini-3.8-flash');

    // Gemma: no responseSchema, JSON still parsed from a fenced reply.
    const schema = { type: 'OBJECT', properties: { a: { type: 'NUMBER' } } };
    f = fakeFetch(model => model.startsWith('gemma-') ? reply('```json\n{"a": 1}\n```') : error(429, 'quota'));
    out = await load(f.fetchImpl).gemini([{ text: 'q' }], schema);
    const gemmaCall = f.calls.find(c => c.model.startsWith('gemma-'));
    const geminiCall = f.calls.find(c => !c.model.startsWith('gemma-'));
    check('Gemma answers schema calls when every Gemini model is out of quota', out && out.a === 1);
    check('Gemma is asked without JSON mode', gemmaCall && !gemmaCall.body.generationConfig.responseSchema && !gemmaCall.body.generationConfig.responseMimeType);
    check('Gemini is still asked with the schema', !!(geminiCall && geminiCall.body.generationConfig.responseSchema
        && geminiCall.body.generationConfig.responseMimeType === 'application/json'));

    // A Gemma 400 moves on; a Gemini 400 fails at once.
    f = fakeFetch(model => model === 'gemma-4-31b-it' ? error(400, 'JSON mode is not enabled') : reply('next ok'));
    out = await load(f.fetchImpl, 'gemma-4-31b-it').gemini([{ text: 'q' }]);
    check('a Gemma 400 moves on to the next model', out === 'next ok' && f.calls.length === 2);
    f = fakeFetch(() => error(400, 'API key not valid'));
    let threw = null;
    try { await load(f.fetchImpl).gemini([{ text: 'q' }]); } catch (e) { threw = e; }
    check('a Gemini 400 still fails at once', threw && /GEMINI_400/.test(threw.message) && f.calls.length === 1);

    if (failures) {
        console.log('\n' + failures + ' GEMINI MODEL CASE(S) FAILED');
        process.exit(1);
    }
    console.log('\nALL GEMINI MODEL CASES PASS');
})().catch(e => { console.error(e); process.exit(1); });
