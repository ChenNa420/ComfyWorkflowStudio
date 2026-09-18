$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiPort = 8100
$WebPort = 5174
$RelayPort = 9333
$CdpPort = 9222
$ComfyUrl = 'http://127.0.0.1:8188'
$WebUrl = 'http://127.0.0.1:5174'
$ApiUrl = 'http://127.0.0.1:8100'
$CdpUrl = 'http://127.0.0.1:9222'
$Python = Join-Path $Root '.venv\Scripts\python.exe'

function Get-PortOwner([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        if (-not $conn) { return $null }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
        return [pscustomobject]@{
            Pid = $conn.OwningProcess
            Name = if ($proc) { $proc.Name } else { '?' }
            CommandLine = if ($proc) { $proc.CommandLine } else { '' }
        }
    } catch {
        return $null
    }
}

function Is-ProjectProcess($Owner, [string]$Kind) {
    if (-not $Owner) { return $false }
    $line = [string]$Owner.CommandLine
    if (-not $line) { return $false }
    $rootEscaped = [regex]::Escape($Root)
    if ($line -notmatch $rootEscaped) { return $false }
    if ($Kind -eq 'api') { return $line -match 'uvicorn' -and $line -match 'backend\.app:app' }
    if ($Kind -eq 'web') { return $line -match 'vite|npm(.cmd)?\s+run\s+dev' }
    return $false
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {}
        Start-Sleep -Milliseconds 750
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Is-ComfyWorkflowStudioApi([string]$Url) {
    try {
        $response = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 3
        return $response.service -eq 'ComfyWorkflowStudio'
    } catch {
        return $false
    }
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ' ComfyWorkflowStudio' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host "Root: $Root"

if (-not (Test-Path $Python)) {
    Write-Host "[FAIL] Python environment missing: $Python" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host '[FAIL] Node.js was not found in PATH.' -ForegroundColor Red
    exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host '[FAIL] npm was not found in PATH.' -ForegroundColor Red
    exit 1
}

$nodeMajor = 0
try {
    $nodeMajor = [int]((node -p "process.versions.node.split('.')[0]") | Select-Object -First 1)
} catch {}

if (-not (Test-Path (Join-Path $Root 'node_modules'))) {
    Write-Host '[FAIL] root node_modules is missing. Run npm ci first.' -ForegroundColor Red
    exit 1
}

$apiOwner = Get-PortOwner $ApiPort
$apiState = 'STARTING'
if ($apiOwner) {
    if ((Is-ProjectProcess $apiOwner 'api') -or (Is-ComfyWorkflowStudioApi $ApiUrl)) {
        $apiState = 'ALREADY RUNNING'
        Write-Host "[INFO] Reusing existing ComfyWorkflowStudio API on port $ApiPort (PID $($apiOwner.Pid))." -ForegroundColor Green
    } else {
        Write-Host "[FAIL] API port $ApiPort is occupied by PID $($apiOwner.Pid) $($apiOwner.Name)" -ForegroundColor Red
        Write-Host "       $($apiOwner.CommandLine)"
        exit 1
    }
} else {
    $apiCommand = "& '$Python' -m uvicorn backend.app:app --host 127.0.0.1 --port $ApiPort"
    Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList '-NoExit','-NoProfile','-Command',$apiCommand
}

$webOwner = Get-PortOwner $WebPort
$webState = 'STARTING'
if ($webOwner) {
    if (Is-ProjectProcess $webOwner 'web') {
        $webState = 'ALREADY RUNNING'
    } else {
        Write-Host "[FAIL] Web port $WebPort is occupied by PID $($webOwner.Pid) $($webOwner.Name)" -ForegroundColor Red
        Write-Host "       $($webOwner.CommandLine)"
        exit 1
    }
} else {
    $webCommand = "npm run dev -- --host 127.0.0.1 --port $WebPort"
    Start-Process powershell.exe -WorkingDirectory $Root -ArgumentList '-NoExit','-NoProfile','-Command',$webCommand
}

$relayOwner = Get-PortOwner $RelayPort
$relayStartedByLauncher = $false
if (-not $relayOwner -and $nodeMajor -ge 22) {
    $relayScript = Join-Path $Root 'tools\webmcp\start-local-relay.cmd'
    if (Test-Path $relayScript) {
        Write-Host "[INFO] Starting persistent local WebMCP Relay on port $RelayPort..." -ForegroundColor Cyan
        Start-Process cmd.exe -WorkingDirectory $Root -ArgumentList '/k', ('"' + $relayScript + '"')
        $relayStartedByLauncher = $true
        $deadline = (Get-Date).AddSeconds(15)
        do {
            Start-Sleep -Milliseconds 500
            $relayOwner = Get-PortOwner $RelayPort
        } while (-not $relayOwner -and (Get-Date) -lt $deadline)
    }
} elseif (-not $relayOwner -and $nodeMajor -lt 22) {
    Write-Host "[WARN] WebMCP Relay requires Node.js 22+; current Node major: $nodeMajor" -ForegroundColor Yellow
}

$cdpReady = $false
try {
    $null = Invoke-WebRequest -UseBasicParsing -Uri "$CdpUrl/json/version" -TimeoutSec 2
    $cdpReady = $true
} catch {}

if (-not $cdpReady) {
    $cdpScript = Join-Path $Root 'tools\chatgpt-image\start-cdp-chrome.cmd'
    if (Test-Path $cdpScript) {
        Write-Host "[INFO] Starting dedicated ChatGPT Chrome on port $CdpPort..." -ForegroundColor Cyan
        Start-Process cmd.exe -WorkingDirectory $Root -ArgumentList '/c', ('"' + $cdpScript + '"')
        $deadline = (Get-Date).AddSeconds(20)
        do {
            Start-Sleep -Milliseconds 750
            try {
                $null = Invoke-WebRequest -UseBasicParsing -Uri "$CdpUrl/json/version" -TimeoutSec 2
                $cdpReady = $true
            } catch {}
        } while (-not $cdpReady -and (Get-Date) -lt $deadline)
    }
}

$apiReady = Wait-Http "$ApiUrl/api/health" 60
$webReady = Wait-Http $WebUrl 60

$comfyReady = $false
try {
    $null = Invoke-WebRequest -UseBasicParsing -Uri "$ComfyUrl/system_stats" -TimeoutSec 2
    $comfyReady = $true
} catch {}

$imageDeps = Test-Path (Join-Path $Root 'tools\chatgpt-image\node_modules\playwright-core')
$relayOwner = Get-PortOwner $RelayPort
$relayReady = $null -ne $relayOwner

Write-Host ''
Write-Host '----------------------------------------'
Write-Host ("Studio API    {0}  {1}" -f ($(if ($apiReady) { 'PASS' } else { 'FAIL' })), $ApiUrl) -ForegroundColor $(if ($apiReady) { 'Green' } else { 'Red' })
Write-Host ("Studio Web    {0}  {1}" -f ($(if ($webReady) { 'PASS' } else { 'FAIL' })), $WebUrl) -ForegroundColor $(if ($webReady) { 'Green' } else { 'Red' })
Write-Host ("ComfyUI       {0}" -f ($(if ($comfyReady) { 'CONNECTED' } else { 'NOT RUNNING' }))) -ForegroundColor $(if ($comfyReady) { 'Green' } else { 'Yellow' })
Write-Host ("ChatGPT CDP   {0}" -f ($(if ($cdpReady) { 'CONNECTED' } else { 'NOT RUNNING' }))) -ForegroundColor $(if ($cdpReady) { 'Green' } else { 'Yellow' })
Write-Host ("Image Worker  {0}" -f ($(if ($imageDeps) { 'INSTALLED' } else { 'DEPENDENCIES MISSING' }))) -ForegroundColor $(if ($imageDeps) { 'Green' } else { 'Yellow' })
Write-Host ("WebMCP Relay  {0}  ws://127.0.0.1:{1}" -f ($(if ($relayReady) { 'CONNECTED' } else { 'NOT RUNNING' })), $RelayPort) -ForegroundColor $(if ($relayReady) { 'Green' } else { 'Yellow' })
Write-Host 'LM Studio     NOT USED'
Write-Host '----------------------------------------'

if ($webReady) {
    try { Start-Process $WebUrl } catch { Write-Host '[WARN] Browser could not be opened automatically.' -ForegroundColor Yellow }
}

if (-not $apiReady -or -not $webReady) { exit 1 }
