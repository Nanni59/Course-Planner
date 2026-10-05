# Runs the TikZ service on this computer in Docker (the same image as the
# Hugging Face Space), drawing through the local Codex bridge.
#
# Normally run by launcher.ps1 (the site's Start button). By hand:
#   1. node tools/codex_bridge/bridge.js        (leave it running)
#   2. powershell -ExecutionPolicy Bypass -File tools/local_tikz/start.ps1
#   3. open the site once with ?tikz=local       (?tikz=space hides it again)
#
# Optional Gemini fallback keys: put GEMINI_API_KEY=... lines in
# .local-tikz.env at the project root (git-ignored). Stop: docker rm -f cp-tikz-local
# Not 'Stop': docker writes build progress to stderr; each step checks its exit code.
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
# Kept outside the project folder, which syncs to OneDrive.
$tokenFile = Join-Path $env:LOCALAPPDATA 'CoursePlanner\codex-bridge.token'
if (-not (Test-Path $tokenFile)) {
    throw "Start the bridge first (node tools/codex_bridge/bridge.js); it creates $tokenFile."
}
$name = 'cp-tikz-local'
$bridgePort = if ($env:CODEX_BRIDGE_PORT) { $env:CODEX_BRIDGE_PORT } else { '8765' }

# Rebuilds only what changed (normally just the app.py layer).
docker build -t $name (Join-Path $root 'hf_space_tikz')
if ($LASTEXITCODE -ne 0) { throw 'docker build failed' }

docker rm -f $name *> $null

# The token goes to the container through this process's environment, not the command line.
$env:LLM_BRIDGE_TOKEN = (Get-Content -Raw $tokenFile).Trim()
$runArgs = @('run', '-d', '--name', $name,
    '-p', '127.0.0.1:7860:7860',
    '-e', "LLM_BRIDGE_URL=http://host.docker.internal:$bridgePort",
    '-e', 'LLM_BRIDGE_TOKEN',
    # Only the owner's pages may call it, and only as localhost (no DNS rebinding).
    '-e', 'CORS_ORIGINS=https://nanni59.github.io,http://localhost:3000,http://127.0.0.1:3000',
    '-e', 'TRUSTED_HOSTS=localhost,127.0.0.1')
$envFile = Join-Path $root '.local-tikz.env'
if (Test-Path $envFile) { $runArgs += @('--env-file', $envFile) }
docker @runArgs $name
$code = $LASTEXITCODE
Remove-Item Env:LLM_BRIDGE_TOKEN
if ($code -ne 0) { throw 'docker run failed' }
Write-Host "TikZ service running on http://localhost:7860 (health: http://localhost:7860/health)"
