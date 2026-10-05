// Local Codex bridge (tools/codex_bridge/bridge.js): event parsing, usage-limit
// rests, argument safety, and the HTTP endpoint end to end against a fake codex.
const assert = require('assert');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const bridge = require('./codex_bridge/bridge.js');

// Events: only a completed turn counts; a failed turn's message is the reason.
let ev = bridge.readEvents([
    '{"type":"thread.started"}', 'progress text', '{"type":"turn.started"}',
    '{"type":"item.started","item":{"type":"command_execution"}}',
    '{"type":"item.started","item":{"type":"agent_message"}}',
    '{"type":"turn.completed","usage":{}}'].join('\n'));
assert.deepStrictEqual(ev, { completed: true, failure: '', toolCalls: 1 });
ev = bridge.readEvents('{"type":"error","message":"stream error"}\n{"type":"turn.failed","error":{"message":"You\'ve hit your usage limit."}}');
assert.strictEqual(ev.completed, false);
assert.strictEqual(ev.failure, "You've hit your usage limit.");

// Usage limits rest the bridge; other failures do not count as limits.
assert.strictEqual(bridge.limitSeconds('model overloaded'), null);
assert.strictEqual(bridge.limitSeconds("You've hit your usage limit. Try again in 45 minutes."), 2700);
assert.strictEqual(bridge.limitSeconds("You've hit your usage limit."), 900);
assert.strictEqual(bridge.limitSeconds('usage limit, try again at 3:30 PM', new Date(2026, 9, 5, 15, 0, 0)), 1800);
assert.strictEqual(bridge.limitSeconds('usage limit, try again at 9:00 AM', new Date(2026, 9, 5, 21, 0, 0)), 12 * 3600);

// Arguments: read-only sandbox, the role's model and effort, prompt on stdin after "--".
const cfg = {
    token: 'a'.repeat(64), maxJobs: 2, maxQueue: 1, timeoutMs: 20000,
    models: { plan: 'gpt-6-luna', draw: 'gpt-6.1-sol', verify: 'gpt-6.1-sol' },
    efforts: { plan: 'low', draw: 'medium', verify: 'medium' },
};
const args = bridge.buildArgs(cfg, 'draw', 'out.txt', ['a.png', 'b.png']);
assert.deepStrictEqual(args.slice(0, 5), ['exec', '--model', 'gpt-6.1-sol', '-c', 'model_reasoning_effort=medium']);
assert(args.join(' ').includes('--sandbox read-only') && args.join(' ').includes('--output-last-message out.txt'));
// isolation: no saved sessions, none of the owner's config or rules, every tool off
for (const flag of ['--ephemeral', '--ignore-user-config', '--ignore-rules', '--disable shell_tool', '--disable unified_exec',
    '--disable browser_use', '--disable computer_use', '--disable plugins', '--disable hooks', '-c web_search=disabled',
    '-c memories.use_memories=false']) assert(args.join(' ').includes(flag), flag);
assert.deepStrictEqual(args.slice(-6), ['--image', 'a.png', '--image', 'b.png', '--', '-']);
assert(bridge.wrapPrompt('Q', true, 0).includes('Reply with only the JSON value'));
assert(bridge.wrapPrompt('Q', false, 2).includes('attached images are the rendered pictures, in order,'));

// Validation: roles, prompt size, PNG-only images.
const PNG = Buffer.from('89504e470d0a1a0a00', 'hex').toString('base64');
assert(bridge.validate({ prompt: 'x', role: 'draw', images: [PNG] }).job);
assert(bridge.validate({ prompt: 'x', role: 'shell' }).error);
assert(bridge.validate({ prompt: '' }).error);
assert(bridge.validate({ prompt: 'x', images: [Buffer.from('GIF89a').toString('base64')] }).error);
assert(bridge.validate({ prompt: 'x', images: [PNG, PNG, PNG, PNG, PNG] }).error);

// End to end against a fake codex that reports what it was given.
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cp-bridge-test-'));
const fake = path.join(dir, 'fake-codex.js');
fs.writeFileSync(fake, `
const fs = require('fs');
const a = process.argv.slice(2);
if (a[0] === '--version') { console.log('codex-cli ' + (process.env.FAKE_VERSION || '0.160.0')); process.exit(0); }
if (a[0] === 'login') {
  const s = process.env.FAKE_LOGIN || 'Logged in using ChatGPT';
  console.log(s); process.exit(/^Logged/.test(s) ? 0 : 1);
}
let input = '';
process.stdin.on('data', d => input += d);
process.stdin.on('end', () => {
  const say = o => process.stdout.write(JSON.stringify(o) + '\\n');
  say({ type: 'thread.started' }); say({ type: 'turn.started' });
  if (process.env.FAKE_MODE === 'limit') {
    say({ type: 'turn.failed', error: { message: "You've hit your usage limit. Try again in 45 minutes." } });
    process.exit(1);
  }
  if (process.env.FAKE_MODE === 'empty') { say({ type: 'turn.completed' }); return; }
  if (process.env.FAKE_MODE === 'tool') say({ type: 'item.started', item: { type: 'command_execution', command: 'dir' } });
  const images = a.flatMap((x, i) => x === '--image' ? [fs.readFileSync(a[i + 1]).subarray(0, 4).toString('hex')] : []);
  fs.writeFileSync(a[a.indexOf('--output-last-message') + 1], JSON.stringify({ args: a, stdin: input, images, cwd: fs.readdirSync('.'), home: process.env.CODEX_HOME }));
  say({ type: 'turn.completed', usage: {} });
});`);
cfg.codex = { command: process.execPath, prefix: [fake], shell: false };
cfg.home = path.join(dir, 'codex-home');

function call(server, { method = 'POST', url = '/complete', body, headers = {} }) {
    return new Promise((resolve, reject) => {
        const data = body === undefined ? '' : JSON.stringify(body);
        const req = http.request({ host: '127.0.0.1', port: server.address().port, method, path: url, headers: {
            Authorization: 'Bearer ' + cfg.token, 'Content-Type': 'application/json', ...headers } }, res => {
            let text = '';
            res.on('data', d => text += d);
            res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(text), headers: res.headers }));
        });
        req.on('error', reject);
        req.end(data);
    });
}

(async () => {
    const server = bridge.createServer(cfg);
    await new Promise(r => server.listen(0, '127.0.0.1', r));
    try {
        // Refusals: no token, a browser origin, a wrong role.
        assert.strictEqual((await call(server, { body: { prompt: 'x' }, headers: { Authorization: 'Bearer nope' } })).status, 401);
        const browser = await call(server, { body: { prompt: 'x' }, headers: { Origin: 'https://evil.example' } });
        assert.strictEqual(browser.status, 403);
        assert.strictEqual(browser.headers['access-control-allow-origin'], undefined);
        assert.strictEqual((await call(server, { body: { prompt: 'x', role: 'shell' } })).status, 400);
        assert.strictEqual((await call(server, { body: { prompt: 'x' }, headers: { 'Content-Type': 'text/plain' } })).status, 415);
        const health = await call(server, { method: 'GET', url: '/health' });
        assert.strictEqual(health.status, 200);
        assert.strictEqual(health.body.models.draw, 'gpt-6.1-sol');

        // A drawing call: the role's model, the picture as a PNG file, the prompt on stdin.
        process.env.FAKE_MODE = 'ok';
        const ok = await call(server, { body: { prompt: 'Draw a triangle.', json: true, role: 'draw', images: [PNG] } });
        assert.strictEqual(ok.status, 200, JSON.stringify(ok.body));
        assert.strictEqual(ok.body.model, 'gpt-6.1-sol');
        const seen = JSON.parse(ok.body.text);
        assert(seen.args.includes('read-only') && seen.args[seen.args.indexOf('--model') + 1] === 'gpt-6.1-sol');
        assert.deepStrictEqual(seen.images, ['89504e47']);
        assert(seen.stdin.includes('Draw a triangle.') && seen.stdin.includes('Reply with only the JSON value'));
        assert.deepStrictEqual(seen.cwd.sort(), ['picture-1.png'], seen.cwd);  // an empty folder but for the picture
        assert.strictEqual(seen.home, cfg.home);  // the bridge's own Codex home, not the owner's
        assert.strictEqual(ok.body.effort, 'medium');
        const plan = JSON.parse((await call(server, { body: { prompt: 'Fit?', role: 'plan' } })).body.text);
        assert.strictEqual(plan.args[plan.args.indexOf('--model') + 1], 'gpt-6-luna');

        // Usage limit -> 429 with the rest time; a completed turn with no reply -> 502.
        process.env.FAKE_MODE = 'limit';
        const limited = await call(server, { body: { prompt: 'x' } });
        assert.strictEqual(limited.status, 429);
        assert.strictEqual(limited.body.retry_after, 2700);
        process.env.FAKE_MODE = 'empty';
        const empty = await call(server, { body: { prompt: 'x' } });
        assert.strictEqual(empty.status, 502);
        assert.match(empty.body.error, /empty reply/);
        // A tool call although every tool is off: the reply is not trusted.
        process.env.FAKE_MODE = 'tool';
        const tool = await call(server, { body: { prompt: 'x' } });
        assert.strictEqual(tool.status, 502);
        assert.match(tool.body.error, /tool call/);

        // Start-up checks: a tested version and a login in the bridge's home.
        delete process.env.FAKE_MODE;
        assert.strictEqual(await bridge.preflight(cfg), null);
        assert(fs.existsSync(cfg.home));
        process.env.FAKE_VERSION = '0.999.0';
        assert.match(await bridge.preflight(cfg), /not a tested version/);
        process.env.CODEX_ALLOW_UNTESTED = '1';
        assert.strictEqual(await bridge.preflight(cfg), null);
        delete process.env.CODEX_ALLOW_UNTESTED; delete process.env.FAKE_VERSION;
        process.env.FAKE_LOGIN = 'Not logged in';
        assert.match(await bridge.preflight(cfg), /not signed in.*codex login/s);
        delete process.env.FAKE_LOGIN;

        // Temporary folders are removed after each run.
        assert.strictEqual(fs.readdirSync(os.tmpdir()).filter(n => n.startsWith('cp-codex-')).length, 0);
    } finally {
        server.close();
        delete process.env.FAKE_MODE;
        fs.rmSync(dir, { recursive: true, force: true });
    }

    // At most maxJobs at a time; beyond the queue the bridge says busy.
    const gate = bridge.limiter(1, 1);
    let release;
    const first = gate.run(() => new Promise(r => { release = r; }));
    const second = gate.run(() => 'second');
    await assert.rejects(gate.run(() => 'third'), /queue is full/);
    assert.deepStrictEqual(gate.stats(), { running: 1, queued: 1 });
    release('first');
    assert.deepStrictEqual(await Promise.all([first, second]), ['first', 'second']);
    console.log('PASS codex bridge: events, usage limits, arguments, validation, endpoint, queue');
})().catch(err => { console.error(err); process.exit(1); });
