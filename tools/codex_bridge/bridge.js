#!/usr/bin/env node
/*
 * Course Planner - local Codex bridge.
 *
 * Lets a locally run copy of the TikZ service (tools/local_tikz) ask the
 * owner's Codex CLI, signed in with their ChatGPT plan, instead of Gemini.
 * One endpoint, POST /complete {prompt, json, images, role}, runs one
 * `codex exec` in an empty temporary folder with a read-only sandbox and
 * returns {text, model, seconds}. The service falls back to Gemini whenever
 * this answers anything but 200.
 *
 * Safety: listens on 127.0.0.1 by default; every request needs the bearer
 * token kept in %LOCALAPPDATA%\CoursePlanner\codex-bridge.token (created on first start, never
 * printed); browser requests (any Origin header) are refused, and no CORS
 * headers are sent. Codex runs under its own home (%USERPROFILE%\.codex-diagram,
 * signed in once with `codex login`), so none of the owner's instructions,
 * plugins, hooks, memories or MCP servers load; every tool is switched off and
 * a run that still calls one fails. Runs are --ephemeral (no saved sessions).
 * The bridge refuses to start on an untested Codex version or without a login.
 *
 *   node tools/codex_bridge/bridge.js              start the bridge
 *   node tools/codex_bridge/bridge.js --selftest   one tiny prompt per role
 *
 * Settings (environment): CODEX_MODEL (every role), CODEX_MODEL_PLAN /
 * _DRAW / _VERIFY, CODEX_EFFORT_PLAN / _DRAW / _VERIFY, CODEX_BRIDGE_HOST,
 * CODEX_BRIDGE_PORT, CODEX_MAX_JOBS, CODEX_TIMEOUT_S, CODEX_BIN,
 * CODEX_BRIDGE_HOME, CODEX_ALLOW_UNTESTED=1 (accept a newer Codex deliberately).
 */
'use strict';
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, execFile } = require('child_process');

const ROLES = ['plan', 'draw', 'verify'];
// Outside the project folder: that folder syncs to OneDrive.
const TOKEN_FILE = path.join(process.env.LOCALAPPDATA || os.homedir(), 'CoursePlanner', 'codex-bridge.token');
const MAX_BODY = 20 * 1024 * 1024;
const MAX_PROMPT = 60000;
const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const PNG_MAGIC = '89504e47';
const SAFE_ARG = /^[\w.:\-\\/ =]+$/;
// Codex versions these flags and the --json events were checked against.
const TESTED_VERSIONS = ['0.160.0'];
// Every tool-bearing feature codex-cli 0.160.0 enables by default (codex features list).
const DISABLED_FEATURES = ['shell_tool', 'unified_exec', 'browser_use', 'browser_use_external', 'computer_use',
    'in_app_browser', 'apps', 'plugins', 'multi_agent', 'image_generation', 'hooks', 'view_image'];

const env = (name, fallback) => {
    const v = process.env[name];
    return v && v.trim() ? v.trim() : fallback;
};

function readOrCreateToken() {
    try {
        const saved = fs.readFileSync(TOKEN_FILE, 'utf8').trim();
        if (saved.length >= 32) return saved;
    } catch (e) { /* first start */ }
    const token = crypto.randomBytes(32).toString('hex');
    fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true });
    fs.writeFileSync(TOKEN_FILE, token, { mode: 0o600 });
    return token;
}

// npm installs codex as a .cmd shim, which Node can only start through cmd.exe;
// its launcher script is run with node directly instead, so no shell is involved.
function resolveCodex() {
    const explicit = env('CODEX_BIN', '');
    if (explicit) return { command: explicit, prefix: [], shell: /\.(cmd|bat)$/i.test(explicit) };
    if (process.platform !== 'win32') return { command: 'codex', prefix: [], shell: false };
    for (const raw of (process.env.PATH || '').split(path.delimiter)) {
        const dir = raw.replace(/"/g, '').trim();
        if (!dir) continue;
        if (fs.existsSync(path.join(dir, 'codex.exe'))) return { command: path.join(dir, 'codex.exe'), prefix: [], shell: false };
        if (fs.existsSync(path.join(dir, 'codex.cmd'))) {
            const launcher = path.join(dir, 'node_modules', '@openai', 'codex', 'bin', 'codex.js');
            if (fs.existsSync(launcher)) return { command: process.execPath, prefix: [launcher], shell: false };
            return { command: path.join(dir, 'codex.cmd'), prefix: [], shell: true };
        }
    }
    return { command: 'codex', prefix: [], shell: true };
}

function loadConfig() {
    const all = env('CODEX_MODEL', '');
    const cfg = {
        host: env('CODEX_BRIDGE_HOST', '127.0.0.1'),
        port: Number(env('CODEX_BRIDGE_PORT', '8765')),
        token: env('CODEX_BRIDGE_TOKEN', '') || readOrCreateToken(),
        maxJobs: Math.max(1, Number(env('CODEX_MAX_JOBS', '3')) || 3),
        maxQueue: 24,
        timeoutMs: 1000 * (Number(env('CODEX_TIMEOUT_S', '180')) || 180),
        home: env('CODEX_BRIDGE_HOME', path.join(os.homedir(), '.codex-diagram')),
        // Sol writes the drawing code and checks the picture; Luna does the short
        // JSON jobs (template fit, parameters, diagram plan).
        models: {
            plan: all || env('CODEX_MODEL_PLAN', 'gpt-6-luna'),
            draw: all || env('CODEX_MODEL_DRAW', 'gpt-6.1-sol'),
            verify: all || env('CODEX_MODEL_VERIFY', 'gpt-6.1-sol'),
        },
        efforts: {
            plan: env('CODEX_EFFORT_PLAN', 'low'),
            draw: env('CODEX_EFFORT_DRAW', 'medium'),
            verify: env('CODEX_EFFORT_VERIFY', 'medium'),
        },
        codex: resolveCodex(),
    };
    for (const role of ROLES) {
        if (!/^[\w.\-:]+$/.test(cfg.models[role])) throw new Error(`bad model name for ${role}: ${cfg.models[role]}`);
        if (!/^[a-z]+$/.test(cfg.efforts[role])) throw new Error(`bad reasoning effort for ${role}: ${cfg.efforts[role]}`);
    }
    return cfg;
}

function buildArgs(cfg, role, outFile, imageFiles) {
    return [
        'exec',
        '--model', cfg.models[role],
        '-c', `model_reasoning_effort=${cfg.efforts[role]}`,
        '--sandbox', 'read-only',
        '--skip-git-repo-check',
        '--ephemeral',
        '--ignore-user-config',
        '--ignore-rules',
        ...DISABLED_FEATURES.flatMap(f => ['--disable', f]),
        '-c', 'web_search=disabled',  // not valid TOML, so Codex takes the raw string
        '-c', 'memories.use_memories=false',
        '-c', 'memories.generate_memories=false',
        '--json',
        '--output-last-message', outFile,
        ...imageFiles.flatMap(f => ['--image', f]),
        '--', '-',  // the prompt comes on stdin ("--": an image list cannot swallow it)
    ];
}

function wrapPrompt(prompt, asJson, pictures) {
    const head = 'You are answering as a plain text model for a diagram service. Do not run commands, read or '
        + 'write files, browse, or use any tool: everything you need is below. Reply with the answer only.'
        + (pictures ? ` The ${pictures === 1 ? 'attached image is the rendered picture' : 'attached images are the rendered pictures, in order,'} the request refers to.` : '');
    const tail = asJson ? '\n\nReply with only the JSON value the request asks for: no prose and no Markdown fences.' : '';
    return head + '\n\n' + prompt + tail;
}

const message = e => !e ? '' : typeof e === 'string' ? e : String(e.message || (e.error && e.error.message) || '');

// codex exec --json prints one event per line; a turn counts only when it completed.
function readEvents(stdout) {
    const out = { completed: false, failure: '', toolCalls: 0 };
    for (const line of String(stdout || '').split(/\r?\n/)) {
        if (!line.trim().startsWith('{')) continue;
        let ev;
        try { ev = JSON.parse(line); } catch (e) { continue; }
        if (ev.type === 'turn.completed') out.completed = true;
        else if (ev.type === 'turn.failed') out.failure = message(ev.error) || 'turn failed';
        else if (ev.type === 'error') out.failure = out.failure || message(ev) || 'error';
        else if (ev.type === 'item.started' && ev.item && ev.item.type && ev.item.type !== 'agent_message' && ev.item.type !== 'reasoning') out.toolCalls++;
    }
    return out;
}

// Seconds to rest after the plan's usage limit, or null for any other failure.
// The wording is not a stable interface, so anything unparsed rests 15 minutes.
function limitSeconds(text, now = new Date()) {
    const t = String(text || '');
    if (!/usage limit|rate limit|quota|too many requests/i.test(t)) return null;
    const rel = t.match(/\bin\s+(\d+)\s*(second|minute|hour|day)s?\b/i);
    if (rel) return Number(rel[1]) * { second: 1, minute: 60, hour: 3600, day: 86400 }[rel[2].toLowerCase()];
    const at = t.match(/\bat\s+(\d{1,2}):(\d{2})\s*([AP]M)?/i);
    if (at) {
        let h = Number(at[1]);
        if (at[3]) h = h % 12 + (at[3].toUpperCase() === 'PM' ? 12 : 0);
        const when = new Date(now);
        when.setHours(h, Number(at[2]), 0, 0);
        if (when <= now) when.setDate(when.getDate() + 1);
        return Math.round((when - now) / 1000);
    }
    return 900;
}

function killTree(child) {
    if (process.platform === 'win32') execFile('taskkill', ['/pid', String(child.pid), '/T', '/F'], () => {});
    else child.kill('SIGKILL');
}

// Codex reads its login, AGENTS.md, config and plugins from CODEX_HOME: the bridge's own.
function codexEnv(cfg) {
    return cfg.home ? { ...process.env, CODEX_HOME: cfg.home } : process.env;
}

function spawnCollect(cfg, args, cwd, input) {
    return new Promise(resolve => {
        let command = cfg.codex.command;
        let argv = args;
        if (cfg.codex.shell) {
            if (![command, ...argv].every(a => SAFE_ARG.test(a))) {
                return resolve({ code: -1, stdout: '', stderr: 'refused to pass an unsafe argument through cmd.exe', timedOut: false });
            }
            command = `"${command}"`;
            argv = argv.map(a => `"${a}"`);
        }
        let child;
        try {
            child = spawn(command, argv, { cwd, shell: cfg.codex.shell, windowsHide: true, env: codexEnv(cfg) });
        } catch (e) {
            return resolve({ code: -1, stdout: '', stderr: 'could not start codex: ' + e.message, timedOut: false });
        }
        let stdout = '', stderr = '', timedOut = false, done = false;
        const cap = (s, d) => (s.length > 4e6 ? s : s + d);
        child.stdout.on('data', d => { stdout = cap(stdout, d.toString('utf8')); });
        child.stderr.on('data', d => { stderr = cap(stderr, d.toString('utf8')); });
        const timer = setTimeout(() => { timedOut = true; killTree(child); }, cfg.timeoutMs);
        const finish = (code, extra) => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            resolve({ code, stdout, stderr: stderr + (extra || ''), timedOut });
        };
        child.on('error', e => finish(-1, '\ncould not start codex: ' + e.message));
        child.on('close', code => finish(code));
        child.stdin.on('error', () => {});
        child.stdin.end(input, 'utf8');
    });
}

async function runCodex(cfg, job) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cp-codex-'));
    const started = Date.now();
    const model = cfg.models[job.role];
    try {
        const imageFiles = job.images.map((b64, i) => {
            const file = path.join(dir, `picture-${i + 1}.png`);
            fs.writeFileSync(file, Buffer.from(b64, 'base64'));
            return file;
        });
        const outFile = path.join(dir, 'reply.txt');
        const args = [...cfg.codex.prefix, ...buildArgs(cfg, job.role, outFile, imageFiles)];
        const run = await spawnCollect(cfg, args, dir, wrapPrompt(job.prompt, job.json, imageFiles.length));
        const seconds = Math.round((Date.now() - started) / 100) / 10;
        if (run.timedOut) return { status: 504, body: { error: `codex timed out after ${Math.round(cfg.timeoutMs / 1000)} s`, model, seconds } };
        const ev = readEvents(run.stdout);
        const reply = fs.existsSync(outFile) ? fs.readFileSync(outFile, 'utf8').trim() : '';
        const lastErr = run.stderr.trim().split(/\r?\n/).filter(Boolean).slice(-1)[0] || '';
        const effort = cfg.efforts[job.role];
        let why = ev.failure;
        if (!why && run.code !== 0) why = lastErr || `codex exited with code ${run.code}`;
        if (!why && !ev.completed) why = 'codex did not complete the turn';
        if (!why && !reply) why = 'codex returned an empty reply';
        if (why) {
            const rest = limitSeconds(why + '\n' + run.stderr.slice(-600));
            if (rest) return { status: 429, body: { error: why.slice(0, 300), retry_after: rest, model, effort, seconds } };
            return { status: 502, body: { error: why.slice(0, 300), model, effort, seconds } };
        }
        // Every tool is switched off: a tool call means the isolation broke, so the
        // reply is not trusted (the service then asks Gemini).
        if (ev.toolCalls) return { status: 502, body: { error: `codex used ${ev.toolCalls} tool call(s) although every tool is disabled`, model, effort, seconds } };
        return { status: 200, body: { text: reply, model, effort, seconds } };
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
}

function limiter(max, maxQueue) {
    let running = 0;
    const queue = [];
    return {
        run(fn) {
            if (running >= max && queue.length >= maxQueue) {
                return Promise.reject(Object.assign(new Error('bridge queue is full'), { busy: true }));
            }
            return new Promise((resolve, reject) => {
                const go = () => {
                    running++;
                    Promise.resolve().then(fn).then(resolve, reject).finally(() => {
                        running--;
                        const next = queue.shift();
                        if (next) next();
                    });
                };
                if (running < max) go(); else queue.push(go);
            });
        },
        stats: () => ({ running, queued: queue.length }),
    };
}

function authorized(req, token) {
    const given = Buffer.from(String(req.headers.authorization || ''));
    const want = Buffer.from('Bearer ' + token);
    return given.length === want.length && crypto.timingSafeEqual(given, want);
}

function readJson(req) {
    return new Promise((resolve, reject) => {
        if (!/^application\/json\b/i.test(String(req.headers['content-type'] || ''))) {
            return reject(Object.assign(new Error('expected application/json'), { status: 415 }));
        }
        let size = 0;
        const chunks = [];
        req.on('data', c => {
            size += c.length;
            if (size > MAX_BODY) { reject(Object.assign(new Error('request too large'), { status: 413 })); req.destroy(); return; }
            chunks.push(c);
        });
        req.on('end', () => {
            try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
            catch (e) { reject(Object.assign(new Error('invalid JSON'), { status: 400 })); }
        });
        req.on('error', reject);
    });
}

// The job, or a reason it is refused.
function validate(body) {
    if (!body || typeof body !== 'object') return { error: 'expected a JSON object' };
    const { prompt, json = false, images = [], role = 'plan' } = body;
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > MAX_PROMPT) return { error: 'prompt must be 1-60000 characters' };
    if (!ROLES.includes(role)) return { error: 'role must be one of ' + ROLES.join(', ') };
    if (!Array.isArray(images) || images.length > MAX_IMAGES) return { error: `at most ${MAX_IMAGES} images` };
    for (const img of images) {
        if (typeof img !== 'string' || !/^[A-Za-z0-9+/=\s]+$/.test(img)) return { error: 'images must be base64 PNG' };
        const bytes = Buffer.from(img, 'base64');
        if (bytes.length > MAX_IMAGE_BYTES || bytes.subarray(0, 4).toString('hex') !== PNG_MAGIC) return { error: 'images must be base64 PNG under 4 MB' };
    }
    return { job: { prompt, json: Boolean(json), images, role } };
}

function createServer(cfg, run = runCodex) {
    const limit = limiter(cfg.maxJobs, cfg.maxQueue);
    return http.createServer(async (req, res) => {
        const send = (status, body) => {
            res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
            res.end(JSON.stringify(body));
        };
        if (req.headers.origin) return send(403, { error: 'browser requests are not accepted' });
        if (!authorized(req, cfg.token)) return send(401, { error: 'unauthorized' });
        if (req.method === 'GET' && req.url === '/health') {
            return send(200, { ok: true, models: cfg.models, efforts: cfg.efforts, ...limit.stats() });
        }
        if (req.method !== 'POST' || req.url !== '/complete') return send(404, { error: 'not found' });
        let body;
        try { body = await readJson(req); } catch (e) { return send(e.status || 400, { error: e.message }); }
        const { job, error } = validate(body);
        if (error) return send(400, { error });
        try {
            const out = await limit.run(() => run(cfg, job));
            console.log(`[bridge] ${job.role} ${out.body.model || ''} -> ${out.status} in ${out.body.seconds} s`
                + (out.status === 200 ? '' : `: ${out.body.error}`));
            send(out.status, out.body);
        } catch (e) {
            send(e.busy ? 503 : 500, { error: e.busy ? e.message : 'bridge error: ' + String(e.message).slice(0, 200) });
        }
    });
}

// A short codex command (--version, login status) under the bridge's home.
function codexCommand(cfg, args) {
    return spawnCollect({ ...cfg, timeoutMs: 30000 }, [...cfg.codex.prefix, ...args], os.homedir(), '');
}

// Refuse to start on a Codex version whose flags and events were not checked, or
// without a login in the bridge's own home. null when ready, else what to do.
async function preflight(cfg) {
    fs.mkdirSync(cfg.home, { recursive: true });
    const ver = await codexCommand(cfg, ['--version']);
    const version = ((ver.stdout + ver.stderr).match(/codex-cli\s+(\d+\.\d+\.\d+)/) || [])[1] || '';
    if (!version) return 'could not run codex --version: ' + (ver.stderr.trim().split(/\r?\n/).pop() || 'not installed?');
    if (!TESTED_VERSIONS.includes(version) && env('CODEX_ALLOW_UNTESTED', '') !== '1') {
        return `codex-cli ${version} is not a tested version (${TESTED_VERSIONS.join(', ')}). Install one with `
            + `npm install -g @openai/codex@${TESTED_VERSIONS[TESTED_VERSIONS.length - 1]}, or set CODEX_ALLOW_UNTESTED=1 `
            + 'to try this one, then run --selftest.';
    }
    const login = await codexCommand(cfg, ['login', 'status']);
    if (login.code !== 0 || !/logged in/i.test(login.stdout + login.stderr) || /not logged in/i.test(login.stdout + login.stderr)) {
        return `Codex is not signed in for the bridge's home (${cfg.home}). In PowerShell run:\n`
            + `  $env:CODEX_HOME = "${cfg.home}"; codex login; Remove-Item Env:CODEX_HOME`;
    }
    return null;
}

async function selfTest(cfg) {
    let ok = true;
    for (const role of ROLES) {
        const out = await runCodex(cfg, { prompt: 'Reply with the single word READY.', json: false, images: [], role });
        ok = ok && out.status === 200;
        console.log(`${role.padEnd(6)} ${cfg.models[role]} (${cfg.efforts[role]}): ${out.status} in ${out.body.seconds} s - `
            + (out.status === 200 ? JSON.stringify(out.body.text.slice(0, 60)) : out.body.error));
    }
    return ok;
}

if (require.main === module) {
    const cfg = loadConfig();
    const how = cfg.codex.prefix.length ? `node ${cfg.codex.prefix[0]}` : cfg.codex.command;
    preflight(cfg).then(problem => {
        if (problem) {
            console.error('[bridge] not starting: ' + problem);
            process.exit(2);
        }
        if (process.argv.includes('--selftest')) {
            console.log(`[bridge] self-test using ${how}, home ${cfg.home}`);
            selfTest(cfg).then(ok => process.exit(ok ? 0 : 1));
            return;
        }
        createServer(cfg).listen(cfg.port, cfg.host, () => {
            console.log(`[bridge] listening on http://${cfg.host}:${cfg.port} (token in ${TOKEN_FILE})`);
            console.log(`[bridge] codex: ${how}, home ${cfg.home}`);
            console.log(`[bridge] models: plan ${cfg.models.plan} (${cfg.efforts.plan}), draw ${cfg.models.draw} (${cfg.efforts.draw}), verify ${cfg.models.verify} (${cfg.efforts.verify}); ${cfg.maxJobs} at a time`);
        });
    });
}

module.exports = { loadConfig, buildArgs, wrapPrompt, readEvents, limitSeconds, limiter, validate, createServer, runCodex, preflight, TESTED_VERSIONS };
