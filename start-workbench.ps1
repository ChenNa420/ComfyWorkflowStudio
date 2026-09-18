$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiPort = 8100
$WebPort = 5174
$ComfyUrl = 'http://127.0.0.1:8188'
$WebUrl = 'http://127.0.0.1:5174'
$ApiUrl = 'http://127.0.0.1:8100'
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
if (-not (Test-Path (Join-Path $Root 'node_modules'))) {
    Write-Host '[FAIL] root node_modules is missing. Run npm ci first.' -ForegroundColor Red
    exit 1
}

$apiOwner = Get-PortOwner $ApiPort
$apiState = 'STARTING'
if ($apiOwner) {
    if (Is-ProjectProcess $apiOwner 'api') {
        $apiState = 'ALREADY RUNNING'
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

$apiReady = Wait-Http "$ApiUrl/api/health" 60
$webReady = Wait-Http $WebUrl 60

$comfyReady = $false
try {
    $null = Invoke-WebRequest -UseBasicParsing -Uri "$ComfyUrl/system_stats" -TimeoutSec 2
    $comfyReady = $true
} catch {}

$cdpReady = $false
try {
    $null = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 2
    $cdpReady = $true
} catch {}

$imageDeps = Test-Path (Join-Path $Root 'tools\chatgpt-image\node_modules\playwright-core')

Write-Host ''
Write-Host '----------------------------------------'
Write-Host ("Studio API    {0}  {1}" -f ($(if ($apiReady) { 'PASS' } else { 'FAIL' })), $ApiUrl) -ForegroundColor $(if ($apiReady) { 'Green' } else { 'Red' })
Write-Host ("Studio Web    {0}  {1}" -f ($(if ($webReady) { 'PASS' } else { 'FAIL' })), $WebUrl) -ForegroundColor $(if ($webReady) { 'Green' } else { 'Red' })
Write-Host ("ComfyUI       {0}" -f ($(if ($comfyReady) { 'CONNECTED' } else { 'NOT RUNNING' }))) -ForegroundColor $(if ($comfyReady) { 'Green' } else { 'Yellow' })
Write-Host ("ChatGPT CDP   {0}" -f ($(if ($cdpReady) { 'CONNECTED' } else { 'NOT RUNNING' }))) -ForegroundColor $(if ($cdpReady) { 'Green' } else { 'Yellow' })
Write-Host ("Image Worker  {0}" -f ($(if ($imageDeps) { 'INSTALLED' } else { 'DEPENDENCIES MISSING' }))) -ForegroundColor $(if ($imageDeps) { 'Green' } else { 'Yellow' })
Write-Host 'LM Studio     NOT USED'
Write-Host '----------------------------------------'

if ($webReady) {
    try { Start-Process $WebUrl } catch { Write-Host '[WARN] Browser could not be opened automatically.' -ForegroundColor Yellow }
}

if (-not $apiReady -or -not $webReady) { exit 1 }
