$ErrorActionPreference = 'Stop'

$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $LauncherDir
$PythonW = Join-Path $Root '.venv\Scripts\pythonw.exe'
$Launcher = Join-Path $LauncherDir 'ComfyWorkflowStudio-EZi.pyw'
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop '童语工坊 Launcher.lnk'

if (-not (Test-Path $PythonW)) {
    throw "pythonw.exe not found: $PythonW"
}
if (-not (Test-Path $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $PythonW
$quote = [char]34
$shortcut.Arguments = "$quote$Launcher$quote"
$shortcut.WorkingDirectory = $Root
$shortcut.Description = '童语工坊 · ComfyWorkflowStudio Launcher'
$shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,15"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host ''
Write-Host 'Desktop shortcut created:' -ForegroundColor Green
Write-Host "  $ShortcutPath"
Write-Host ''
Write-Host 'Double-click "童语工坊 Launcher" to open the Python launcher panel.'
