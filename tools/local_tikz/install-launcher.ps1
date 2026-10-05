# Registers two links for this Windows user (no admin rights needed):
#   courseplanner-tikz-start:  -> launcher.ps1 -Action start
#   courseplanner-tikz-stop:   -> launcher.ps1 -Action stop
# so the site's Start / Stop buttons (Connect API, local diagram service) can run
# the launcher. The browser asks before opening either link. Neither passes
# anything to the script, so a web page cannot add input. Undo: uninstall-launcher.ps1.
#
#   powershell -ExecutionPolicy Bypass -File tools/local_tikz/install-launcher.ps1
$ErrorActionPreference = 'Stop'
$launcher = (Resolve-Path (Join-Path $PSScriptRoot 'launcher.ps1')).Path
foreach ($action in 'start', 'stop') {
    $key = "HKCU:\Software\Classes\courseplanner-tikz-$action"
    New-Item -Path "$key\shell\open\command" -Force | Out-Null
    Set-Item -Path $key -Value "URL:Course Planner local diagrams ($action)"
    New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    # No "%1": the link text never reaches the command line. conhost --headless runs
    # PowerShell with no console window at all (-WindowStyle Hidden alone still
    # shows one when Windows Terminal hosts consoles).
    $command = "conhost.exe --headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`" -Action $action"
    Set-Item -Path "$key\shell\open\command" -Value $command
    Write-Host "Registered courseplanner-tikz-${action}: -> $command"
}
