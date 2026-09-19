$ErrorActionPreference = 'Stop'

$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $LauncherDir
$PythonW = Join-Path $Root '.venv\Scripts\pythonw.exe'
$Launcher = Join-Path $LauncherDir 'ComfyWorkflowStudio-EZi.pyw'

if (-not (Test-Path $PythonW)) {
    Add-Type -AssemblyName System.Windows.Forms
    $message = 'pythonw.exe not found:' + [Environment]::NewLine + $PythonW
    [System.Windows.Forms.MessageBox]::Show(
        $message,
        'ComfyWorkflowStudio Launcher'
    ) | Out-Null
    exit 1
}

$quote = [char]34
Start-Process -FilePath $PythonW -WorkingDirectory $Root -ArgumentList ($quote + $Launcher + $quote)
