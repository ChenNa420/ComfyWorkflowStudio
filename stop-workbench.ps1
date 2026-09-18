$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiPort = 8100
$WebPort = 5174
$RelayPort = 9333
$CdpPort = 9222
$CdpProfile = (Join-Path $Root 'storage\chatgpt-image-browser\cdp-profile')

function Get-PortOwner([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        if (-not $conn) { return $null }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
        return [pscustomobject]@{
            Pid = $conn.OwningProcess
            Name = if ($proc) { $proc.Name } else { '?' }
            CommandLine = if ($proc) { [string]$proc.CommandLine } else { '' }
        }
    } catch {
        return $null
    }
}

function Stop-Ids([int[]]$Ids, [string]$Label) {
    $unique = @($Ids | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    if (-not $unique.Count) {
        Write-Host ("{0,-16} NOT RUNNING" -f $Label) -ForegroundColor DarkGray
        return
    }

    foreach ($pidValue in $unique) {
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
        } catch {
            Write-Host ("[WARN] Could not stop {0} PID {1}: {2}" -f $Label, $pidValue, $_.Exception.Message) -ForegroundColor Yellow
        }
    }
    Write-Host ("{0,-16} STOPPED  PID {1}" -f $Label, ($unique -join ', ')) -ForegroundColor Green
}

function Stop-ProjectApi {
    $owner = Get-PortOwner $ApiPort
    if (-not $owner) {
        Write-Host ("{0,-16} NOT RUNNING" -f 'Studio API') -ForegroundColor DarkGray
        return
    }
    $line = [string]$owner.CommandLine
    $rootMatch = $line -match [regex]::Escape($Root)
    $apiMatch = $line -match 'uvicorn' -and $line -match 'backend\.app:app'
    if (-not ($rootMatch -and $apiMatch)) {
        Write-Host "[SKIP] Port $ApiPort is owned by another process; not stopping it." -ForegroundColor Yellow
        Write-Host "       PID $($owner.Pid) $($owner.Name) $line"
        return
    }

    $ids = @($owner.Pid)
    $launchers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match 'powershell|pwsh' -and
        [string]$_.CommandLine -match [regex]::Escape($Root) -and
        [string]$_.CommandLine -match 'backend\.app:app'
    }
    $ids += @($launchers.ProcessId)
    Stop-Ids $ids 'Studio API'
}

function Stop-ProjectWeb {
    $owner = Get-PortOwner $WebPort
    if (-not $owner) {
        Write-Host ("{0,-16} NOT RUNNING" -f 'Studio Web') -ForegroundColor DarkGray
        return
    }
    $line = [string]$owner.CommandLine
    $rootMatch = $line -match [regex]::Escape($Root)
    $webMatch = $line -match 'vite|npm(.cmd)?\s+run\s+dev'
    if (-not ($rootMatch -and $webMatch)) {
        Write-Host "[SKIP] Port $WebPort is owned by another process; not stopping it." -ForegroundColor Yellow
        Write-Host "       PID $($owner.Pid) $($owner.Name) $line"
        return
    }

    $ids = @($owner.Pid)
    $launchers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match 'powershell|pwsh|cmd' -and
        [string]$_.CommandLine -match [regex]::Escape($Root) -and
        [string]$_.CommandLine -match 'npm(.cmd)?\s+run\s+dev|vite'
    }
    $ids += @($launchers.ProcessId)
    Stop-Ids $ids 'Studio Web'
}

function Stop-ProjectRelay {
    $owner = Get-PortOwner $RelayPort
    if (-not $owner) {
        Write-Host ("{0,-16} NOT RUNNING" -f 'WebMCP Relay') -ForegroundColor DarkGray
        return
    }
    $line = [string]$owner.CommandLine
    $relayMatch = $line -match 'webmcp-local-relay' -and $line -match '9333'
    if (-not $relayMatch) {
        Write-Host "[SKIP] Port $RelayPort is owned by another process; not stopping it." -ForegroundColor Yellow
        Write-Host "       PID $($owner.Pid) $($owner.Name) $line"
        return
    }

    $ids = @($owner.Pid)
    $launchers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        [string]$_.CommandLine -match 'start-local-relay\.cmd|webmcp-local-relay' -and
        ([string]$_.CommandLine -match [regex]::Escape($Root) -or [string]$_.CommandLine -match '9333')
    }
    $ids += @($launchers.ProcessId)
    Stop-Ids $ids 'WebMCP Relay'
}

function Stop-DedicatedChatGptChrome {
    $profileEscaped = [regex]::Escape($CdpProfile)
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^chrome\.exe$' -and
        (
            ([string]$_.CommandLine -match '--remote-debugging-port=9222') -or
            ([string]$_.CommandLine -match $profileEscaped)
        )
    }

    if (-not $processes) {
        $owner = Get-PortOwner $CdpPort
        if ($owner) {
            Write-Host "[SKIP] Port $CdpPort is in use, but it is not the ComfyWorkflowStudio dedicated Chrome." -ForegroundColor Yellow
            Write-Host "       PID $($owner.Pid) $($owner.Name) $($owner.CommandLine)"
        } else {
            Write-Host ("{0,-16} NOT RUNNING" -f 'ChatGPT CDP') -ForegroundColor DarkGray
        }
        return
    }

    Stop-Ids @($processes.ProcessId) 'ChatGPT CDP'
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ' ComfyWorkflowStudio Shutdown' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host ''
Write-Host 'Stopping only ComfyWorkflowStudio-owned services:' -ForegroundColor Cyan
Write-Host '  API 8100 / Web 5174 / WebMCP Relay 9333 / dedicated ChatGPT Chrome 9222'
Write-Host '  ComfyUI is NOT touched. LM Studio is NOT touched.'
Write-Host ''

Stop-ProjectApi
Stop-ProjectWeb
Stop-ProjectRelay
Stop-DedicatedChatGptChrome

Start-Sleep -Milliseconds 800

Write-Host ''
Write-Host '----------------------------------------'
foreach ($item in @(
    @{ Name = 'Studio API'; Port = $ApiPort },
    @{ Name = 'Studio Web'; Port = $WebPort },
    @{ Name = 'WebMCP Relay'; Port = $RelayPort },
    @{ Name = 'ChatGPT CDP'; Port = $CdpPort }
)) {
    $owner = Get-PortOwner $item.Port
    Write-Host ("{0,-16} {1}" -f $item.Name, ($(if ($owner) { "STILL LISTENING PID $($owner.Pid)" } else { 'STOPPED' }))) -ForegroundColor $(if ($owner) { 'Yellow' } else { 'Green' })
}
Write-Host 'ComfyUI          UNCHANGED'
Write-Host 'LM Studio        UNCHANGED'
Write-Host '----------------------------------------'
