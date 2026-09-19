$ErrorActionPreference = 'Stop'

$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $LauncherDir
$Launcher = Join-Path $LauncherDir 'ComfyWorkflowStudio-Launcher.ps1'
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop '童语工坊 Launcher.lnk'

if (-not (Test-Path $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`""
$shortcut.WorkingDirectory = $Root
$shortcut.Description = '童语工坊 · ComfyWorkflowStudio Launcher'
$shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,15"
$shortcut.Save()

Write-Host ''
Write-Host 'Desktop shortcut created:' -ForegroundColor Green
Write-Host "  $ShortcutPath"
Write-Host ''
Write-Host 'Double-click "童语工坊 Launcher" on the desktop to open the launcher panel.'
