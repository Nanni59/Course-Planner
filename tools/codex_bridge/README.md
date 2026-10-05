# Local Codex bridge

Lets a copy of the TikZ service running on this PC draw and check diagrams with
the Codex CLI (signed in with your ChatGPT plan) instead of Gemini. Personal,
local use only: other visitors, the GitHub Pages site and the Hugging Face
Space are unchanged.

```
site (local mode on) -> TikZ service in Docker (localhost:7860) -> bridge (127.0.0.1:8765) -> codex exec
        \-> the Space whenever localhost:7860 does not answer        \-> Gemini whenever the bridge fails
```

## One-time setup

1. Install the tested Codex CLI version: `npm install -g @openai/codex@0.160.0`.
   The bridge refuses any other version until it is tested (or you set
   `CODEX_ALLOW_UNTESTED=1` deliberately and run the self-test).
2. Sign Codex in **for the bridge's own home** (it does not use your normal
   `.codex` folder, so your instructions, plugins, hooks and memories never load):
   ```
   $env:CODEX_HOME = "$env:USERPROFILE\.codex-diagram"; codex login; Remove-Item Env:CODEX_HOME
   ```
3. Install Docker Desktop (WSL2). Optional: cap its memory by putting
   ```
   [wsl2]
   memory=4GB
   ```
   in `%UserProfile%\.wslconfig`, then `wsl --shutdown`.
4. Register the Start/Stop links: `powershell -ExecutionPolicy Bypass -File tools/local_tikz/install-launcher.ps1`
   (undo: `uninstall-launcher.ps1`).
5. Check the models: `node tools/codex_bridge/bridge.js --selftest`.
6. Open the site once with `?tikz=local` (for example
   `https://nanni59.github.io/Course-Planner/?tikz=local`). That shows the
   **Local diagram service** section under Connect API on this browser only;
   `?tikz=space` hides it again.

## Using it

Turn on **Draw diagrams with the service on this computer** under Connect API.
Then:

- **Start** (or "Start it" when a worksheet asks) opens the
  `courseplanner-tikz-start:` link; the browser asks once (tick "always allow").
  The launcher starts Docker Desktop, the bridge and the container without a
  console window, in about 50 s from cold; a progress panel shows each step.
  Allow "local network access" when the browser asks. Docker Desktop's own
  window is closed as soon as it appears (Docker keeps running in the tray); to
  stop it showing at all, turn off Settings > General > "Open Docker Dashboard
  when Docker Desktop starts".
- **Stop** removes the container, stops the bridge and quits Docker Desktop (frees about 1 GB).
- Whenever the service does not answer, diagrams use the online renderer and a
  note says so. Logs: `tools/local_tikz/launcher.log`, `bridge.log`, `bridge.err.log`.

## Models

| Role | Used for | Default |
|---|---|---|
| `plan` | template fit check, template parameters, diagram plan (short JSON) | `gpt-6-luna`, low effort |
| `draw` | writing and repairing TikZ | `gpt-6.1-sol`, medium effort |
| `verify` | the picture check (PASS / COSMETIC / FAIL) | `gpt-6.1-sol`, medium effort |

Override with environment variables before starting the bridge, e.g. to try
Luna everywhere: `$env:CODEX_MODEL = 'gpt-6-luna'`. Per role:
`CODEX_MODEL_PLAN`, `CODEX_MODEL_DRAW`, `CODEX_MODEL_VERIFY`,
`CODEX_EFFORT_PLAN` / `_DRAW` / `_VERIFY`. Also `CODEX_MAX_JOBS` (default 3),
`CODEX_TIMEOUT_S` (180), `CODEX_BRIDGE_PORT` (8765), `CODEX_BRIDGE_HOME`, `CODEX_BIN`.

## Safety

- Codex runs under its own home (`%USERPROFILE%\.codex-diagram`) with
  `--ephemeral` (no saved sessions), `--ignore-user-config`, `--ignore-rules`,
  read-only sandbox, web search and memories off, and every tool feature
  disabled (shell, browser, computer use, apps, plugins, hooks, sub-agents,
  image tools). A run that still calls a tool is rejected, and the service asks
  Gemini instead. Each run uses a new empty temporary folder, deleted afterwards.
- The bridge listens on 127.0.0.1, needs the token in
  `%LOCALAPPDATA%\CoursePlanner\codex-bridge.token` (created on first start,
  never printed, outside the OneDrive-synced project folder), refuses browser
  requests, and sends no CORS headers. The container gets the token from the start script.
- The container's port is published on 127.0.0.1 only. It answers only the
  owner's pages (`CORS_ORIGINS`: the GitHub Pages site and the local preview)
  and only under `localhost` / `127.0.0.1` (`TRUSTED_HOSTS`), so another website
  cannot use it, even by pointing its own domain at 127.0.0.1.
- Diagrams from it pass the same SVG sanitizer as the Space's.
- The Start/Stop links carry no input: each is registered with a fixed action.
- The bridge will not start on an untested Codex version or without a login in
  its own home; the launcher then leaves the container off, so the site keeps
  using the online renderer.

## If the container cannot reach the bridge

`/health` on the service (http://localhost:7860/health) shows `bridge.last_error`.
If it says the bridge is unreachable, start the bridge with
`$env:CODEX_BRIDGE_HOST = '0.0.0.0'` (still token-protected; Windows may ask to
allow it through the firewall: allow Private networks only).
