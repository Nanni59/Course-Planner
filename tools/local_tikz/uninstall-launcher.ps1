# Removes the two links install-launcher.ps1 registered for this Windows user.
#   powershell -ExecutionPolicy Bypass -File tools/local_tikz/uninstall-launcher.ps1
foreach ($action in 'start', 'stop') {
    $key = "HKCU:\Software\Classes\courseplanner-tikz-$action"
    if (Test-Path $key) {
        Remove-Item -Path $key -Recurse
        Write-Host "Removed courseplanner-tikz-${action}:"
    }
}
