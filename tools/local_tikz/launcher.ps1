# Starts or stops the local TikZ diagram service (Docker + the TikZ container +
# the Codex bridge) without a window. Opened by the site's Start / Stop buttons
# through the courseplanner-tikz-start: and courseplanner-tikz-stop: links that
# install-launcher.ps1 registers. Those links pass nothing to this script: each
# link's action is fixed when it is registered, so a web page cannot add input.
#
# Log: tools/local_tikz/launcher.log (the bridge's own output: bridge.log / bridge.err.log).
param([Parameter(Mandatory = $true)][ValidateSet('start', 'stop')][string]$Action)
# Not 'Stop': docker and node write progress to stderr, which Windows PowerShell
# turns into errors. Every step below checks its own result and throws.
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$log = Join-Path $PSScriptRoot 'launcher.log'
function Write-Log($message) {
    Add-Content -Path $log -Value ('{0:yyyy-MM-dd HH:mm:ss} {1}: {2}' -f (Get-Date), $Action, $message)
}
# A link-opened process may not have the newest PATH (Docker, node, codex).
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

function Get-BridgeProcess {
    Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
        Where-Object { $_.CommandLine -like '*codex_bridge*bridge.js*' }
}
# At most a few seconds: `docker info` blocks while the engine boots, and the wait
# loop below must keep closing Docker's window meanwhile.
function Test-DockerEngine([int]$timeoutMs = 3000) {
    $out = Join-Path $env:TEMP 'cp-docker-info.out'
    $p = Start-Process -FilePath (Get-Command docker).Source -ArgumentList 'info' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError ($out + '.err')
    $null = $p.Handle  # without reading the handle now, ExitCode is empty after exit
    if (-not $p.WaitForExit($timeoutMs)) {
        try { $p.Kill() } catch { }
        return $false
    }
    return $p.ExitCode -eq 0
}
# Docker Desktop opens its window when it starts (unless "Open Docker Dashboard
# when Docker Desktop starts" is off in its settings). Closing a window sends it
# to the tray: Docker keeps running. Every visible window of its processes is
# closed, not only the one .NET reports as the main window.
Add-Type -Namespace CpLauncher -Name Win -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
public delegate bool EnumProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
'@
function Close-DockerWindow {
    $ids = @(Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    if (-not $ids.Count) { return }
    $closed = New-Object System.Collections.ArrayList
    $callback = [CpLauncher.Win+EnumProc]{
        param($h, $l)
        $owner = 0
        [void][CpLauncher.Win]::GetWindowThreadProcessId($h, [ref]$owner)
        if ($ids -contains $owner -and [CpLauncher.Win]::IsWindowVisible($h)) {
            [void][CpLauncher.Win]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)  # WM_CLOSE
            [void]$closed.Add($h)
        }
        $true
    }
    [void][CpLauncher.Win]::EnumWindows($callback, [IntPtr]::Zero)
    if ($closed.Count) { Write-Log "closed $($closed.Count) Docker Desktop window(s); Docker keeps running in the tray" }
}

# One launcher at a time (a double click must not start two bridges).
$mutex = New-Object System.Threading.Mutex($false, 'Local\CoursePlannerTikzLauncher')
if (-not $mutex.WaitOne(0)) { Write-Log 'another launcher is already running'; exit 0 }
try {
    if ($Action -eq 'stop') {
        docker rm -f cp-tikz-local *> $null
        Get-BridgeProcess | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
        # Docker Desktop and its WSL machine hold about 1 GB while running.
        docker desktop stop --timeout 120 *> $null
        Write-Log 'stopped the container, the bridge and Docker Desktop'
        exit 0
    }

    # 1. The Docker engine.
    if (-not (Test-DockerEngine)) {
        Write-Log 'starting Docker Desktop'
        docker desktop start --detach *> $null
        $deadline = (Get-Date).AddSeconds(180)
        $ready = $false
        while (-not $ready -and (Get-Date) -lt $deadline) {
            Close-DockerWindow
            $ready = Test-DockerEngine
            if (-not $ready) { Start-Sleep -Milliseconds 300 }
        }
        if (-not $ready) { throw 'Docker Desktop did not start' }
        # the dashboard can open just after the engine is ready
        for ($i = 0; $i -lt 10; $i++) { Close-DockerWindow; Start-Sleep -Milliseconds 500 }
    }

    # 2. The Codex bridge. It checks its Codex version and login first and exits
    #    when either is wrong; the container is then not started, so the site
    #    keeps using the online renderer instead of a service that cannot draw.
    if (-not (Get-BridgeProcess)) {
        $bridge = Join-Path $root 'tools\codex_bridge\bridge.js'
        Start-Process -FilePath (Get-Command node).Source -ArgumentList ('"' + $bridge + '"') `
            -WorkingDirectory $root -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $PSScriptRoot 'bridge.log') `
            -RedirectStandardError (Join-Path $PSScriptRoot 'bridge.err.log')
        Write-Log 'started the bridge'
    }
    $port = if ($env:CODEX_BRIDGE_PORT) { [int]$env:CODEX_BRIDGE_PORT } else { 8765 }
    $listening = $false
    for ($i = 0; $i -lt 30 -and -not $listening; $i++) {
        Start-Sleep -Seconds 1
        $listening = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        if (-not $listening -and -not (Get-BridgeProcess)) { break }
    }
    if (-not (Test-Path (Join-Path $env:LOCALAPPDATA 'CoursePlanner\codex-bridge.token'))) { $listening = $false }
    if (-not $listening) {
        $why = Get-Content (Join-Path $PSScriptRoot 'bridge.err.log') -Tail 3 -ErrorAction SilentlyContinue
        throw ('the bridge did not start: ' + ($why -join ' '))
    }

    # 3. The TikZ container, rebuilt from the working copy (only changed layers rebuild).
    #    Its own process: docker writes build progress to stderr, which this
    #    script's 'Stop' preference would otherwise treat as a failure.
    $out = Join-Path $PSScriptRoot 'start.out.log'
    $err = Join-Path $PSScriptRoot 'start.err.log'
    $run = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -Wait -PassThru `
        -ArgumentList @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $PSScriptRoot 'start.ps1') + '"')) `
        -RedirectStandardOutput $out -RedirectStandardError $err
    if ($run.ExitCode -ne 0) {
        throw ('start.ps1 failed (exit ' + $run.ExitCode + '): ' + ((Get-Content $err -Tail 3 -ErrorAction SilentlyContinue) -join ' '))
    }
    Write-Log 'the local diagram service is running'
}
catch {
    Write-Log ('failed: ' + $_)
    exit 1
}
finally {
    $mutex.ReleaseMutex()
}
