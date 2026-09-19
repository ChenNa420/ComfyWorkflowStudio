$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $LauncherDir
$ConfigPath = Join-Path $LauncherDir 'launcher-config.json'

$config = [ordered]@{
    webUrl = 'http://127.0.0.1:5174'
    apiUrl = 'http://127.0.0.1:8100'
    comfyUrl = 'http://127.0.0.1:8188'
    comfyStartBat = ''
}

if (Test-Path $ConfigPath) {
    try {
        $loaded = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($key in @('webUrl','apiUrl','comfyUrl','comfyStartBat')) {
            if ($null -ne $loaded.$key -and [string]$loaded.$key) {
                $config[$key] = [string]$loaded.$key
            }
        }
    } catch {}
}

function Save-Config {
    $config | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Start-ProjectScript([string]$Name) {
    $path = Join-Path $Root $Name
    if (-not (Test-Path $path)) {
        [System.Windows.Forms.MessageBox]::Show("找不到脚本：$path", '童语工坊 Launcher') | Out-Null
        return
    }
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$path`""
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $Root -ArgumentList $args -WindowStyle Hidden
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(220, $false)) { return $false }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Open-Url([string]$Url) {
    try { Start-Process $Url } catch {
        [System.Windows.Forms.MessageBox]::Show("无法打开：$Url", '童语工坊 Launcher') | Out-Null
    }
}

function Open-Folder([string]$Path) {
    if (-not (Test-Path $Path)) {
        try { New-Item -ItemType Directory -Force -Path $Path | Out-Null } catch {}
    }
    if (Test-Path $Path) { Start-Process explorer.exe $Path }
}

function Select-ComfyBat {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = '选择 ComfyUI 启动 BAT'
    $dialog.Filter = 'Windows Batch (*.bat)|*.bat|All files (*.*)|*.*'
    if ($config.comfyStartBat -and (Test-Path $config.comfyStartBat)) {
        $dialog.InitialDirectory = Split-Path -Parent $config.comfyStartBat
        $dialog.FileName = Split-Path -Leaf $config.comfyStartBat
    }
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $config.comfyStartBat = $dialog.FileName
        Save-Config
        return $true
    }
    return $false
}

function Start-ComfyUI {
    if (-not $config.comfyStartBat -or -not (Test-Path $config.comfyStartBat)) {
        if (-not (Select-ComfyBat)) { return }
    }
    $working = Split-Path -Parent $config.comfyStartBat
    Start-Process -FilePath 'cmd.exe' -WorkingDirectory $working -ArgumentList '/c', ('"' + $config.comfyStartBat + '"')
}

$form = New-Object System.Windows.Forms.Form
$form.Text = '童语工坊 Launcher'
$form.ClientSize = New-Object System.Drawing.Size(660, 390)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(14,18,24)
$form.ForeColor = [System.Drawing.Color]::Gainsboro
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'ComfyWorkflowStudio Launcher'
$title.Location = New-Object System.Drawing.Point(22, 14)
$title.Size = New-Object System.Drawing.Size(420, 30)
$title.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 15, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(97,214,77)
$form.Controls.Add($title)

$version = New-Object System.Windows.Forms.Label
$version.Text = 'v1.0'
$version.Location = New-Object System.Drawing.Point(562, 21)
$version.Size = New-Object System.Drawing.Size(70, 22)
$version.TextAlign = 'MiddleRight'
$version.ForeColor = [System.Drawing.Color]::FromArgb(140,150,165)
$form.Controls.Add($version)

function Add-SectionLabel([string]$Text, [int]$X, [System.Drawing.Color]$Color) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point($X, 56)
    $label.Size = New-Object System.Drawing.Size(185, 24)
    $label.TextAlign = 'MiddleCenter'
    $label.ForeColor = $Color
    $label.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($label)
}

$orange = [System.Drawing.Color]::FromArgb(255,105,0)
$green = [System.Drawing.Color]::FromArgb(55,200,35)
$blue = [System.Drawing.Color]::FromArgb(31,159,255)
$muted = [System.Drawing.Color]::FromArgb(44,51,62)

Add-SectionLabel '-- SERVICES --' 26 $orange
Add-SectionLabel '-- BROWSER --' 238 $green
Add-SectionLabel '-- STATUS --' 450 $blue

function Add-Button([string]$Text, [int]$X, [int]$Y, [System.Drawing.Color]$Accent, [scriptblock]$OnClick, [int]$Width = 185) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Location = New-Object System.Drawing.Point($X, $Y)
    $button.Size = New-Object System.Drawing.Size($Width, 38)
    $button.FlatStyle = 'Flat'
    $button.FlatAppearance.BorderColor = $Accent
    $button.FlatAppearance.BorderSize = 1
    $button.BackColor = [System.Drawing.Color]::FromArgb(17,22,29)
    $button.ForeColor = $Accent
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    $button.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9.5, [System.Drawing.FontStyle]::Bold)
    $button.Add_Click($OnClick)
    $form.Controls.Add($button)
    return $button
}

Add-Button '启动工作台' 26 84 $orange { Start-ProjectScript 'start-workbench.ps1' } | Out-Null
Add-Button '停止工作台' 26 128 $orange { Start-ProjectScript 'stop-workbench.ps1' } | Out-Null
Add-Button '重启工作台' 26 172 $orange {
    Start-ProjectScript 'stop-workbench.ps1'
    Start-Sleep -Milliseconds 1800
    Start-ProjectScript 'start-workbench.ps1'
} | Out-Null
Add-Button '启动 ComfyUI' 26 216 $orange { Start-ComfyUI } | Out-Null

Add-Button '打开童语工坊' 238 84 $green { Open-Url $config.webUrl } | Out-Null
Add-Button '打开 API' 238 128 $green { Open-Url $config.apiUrl } | Out-Null
Add-Button '打开 ComfyUI' 238 172 $green { Open-Url $config.comfyUrl } | Out-Null
Add-Button '设置 ComfyUI BAT' 238 216 $green { [void](Select-ComfyBat) } | Out-Null

$statusLabels = @{}
function Add-Status([string]$Key, [string]$Text, [int]$Y) {
    $label = New-Object System.Windows.Forms.Label
    $label.Text = "●  $Text"
    $label.Location = New-Object System.Drawing.Point(466, $Y)
    $label.Size = New-Object System.Drawing.Size(165, 26)
    $label.ForeColor = [System.Drawing.Color]::FromArgb(115,125,140)
    $label.Font = New-Object System.Drawing.Font('Consolas', 9.5, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($label)
    $statusLabels[$Key] = $label
}

Add-Status 'api' 'API      8100' 88
Add-Status 'web' 'WEB      5174' 124
Add-Status 'comfy' 'ComfyUI  8188' 160
Add-Status 'cdp' 'GPT CDP  9222' 196
Add-Status 'relay' 'Relay    9333' 232

$separator = New-Object System.Windows.Forms.Panel
$separator.Location = New-Object System.Drawing.Point(20, 268)
$separator.Size = New-Object System.Drawing.Size(620, 1)
$separator.BackColor = [System.Drawing.Color]::FromArgb(48,58,70)
$form.Controls.Add($separator)

$folderColor = [System.Drawing.Color]::FromArgb(210,116,38)
Add-Button 'Project' 20 286 $folderColor { Open-Folder $Root } 112 | Out-Null
Add-Button 'Output' 142 286 $folderColor { Open-Folder (Join-Path $Root 'storage\outputs') } 112 | Out-Null
Add-Button 'Workflows' 264 286 $folderColor { Open-Folder (Join-Path $Root 'workflows') } 112 | Out-Null
Add-Button 'Logs' 386 286 $folderColor { Open-Folder (Join-Path $Root 'storage\logs') } 112 | Out-Null
Add-Button 'GPT Browser' 508 286 $folderColor { Open-Folder (Join-Path $Root 'storage\chatgpt-image-browser') } 132 | Out-Null

$hint = New-Object System.Windows.Forms.Label
$hint.Text = '桌面快捷方式双击即可打开此面板 · 状态每 3 秒自动刷新'
$hint.Location = New-Object System.Drawing.Point(20, 342)
$hint.Size = New-Object System.Drawing.Size(620, 26)
$hint.TextAlign = 'MiddleCenter'
$hint.ForeColor = [System.Drawing.Color]::FromArgb(100,112,128)
$form.Controls.Add($hint)

function Refresh-Status {
    $checks = @{
        api = Test-Port 8100
        web = Test-Port 5174
        comfy = Test-Port 8188
        cdp = Test-Port 9222
        relay = Test-Port 9333
    }
    foreach ($key in $checks.Keys) {
        $statusLabels[$key].ForeColor = if ($checks[$key]) {
            [System.Drawing.Color]::FromArgb(58,210,86)
        } else {
            [System.Drawing.Color]::FromArgb(118,128,142)
        }
    }
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 3000
$timer.Add_Tick({ Refresh-Status })
$timer.Start()

$form.Add_Shown({ Refresh-Status })
$form.Add_FormClosed({ $timer.Stop(); $timer.Dispose() })
[void]$form.ShowDialog()
