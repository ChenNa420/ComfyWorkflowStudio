@echo off
setlocal
cd /d "%~dp0..\.."

if "%~1"=="" (
  echo Usage: tools\webmcp\test-gpt-vision.cmd gdt-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx PAGE
  exit /b 2
)
if "%~2"=="" (
  echo Usage: tools\webmcp\test-gpt-vision.cmd gdt-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx PAGE
  exit /b 2
)

for /f "delims=" %%V in ('node -p "process.versions.node" 2^>nul') do set "NODE_VERSION=%%V"
if not defined NODE_VERSION (
  echo [FAIL] Node.js was not found in PATH.
  exit /b 1
)

for /f "tokens=1 delims=." %%M in ("%NODE_VERSION%") do set "NODE_MAJOR=%%M"
if %NODE_MAJOR% LSS 22 (
  echo [FAIL] GPT visual probe requires Node.js 22 or newer.
  echo Current Node.js: %NODE_VERSION%
  exit /b 1
)

if not exist "tools\webmcp\node_modules\@modelcontextprotocol\client" (
  echo [INFO] Installing WebMCP client dependencies...
  call npm install --prefix tools\webmcp
  if errorlevel 1 exit /b 1
)

if not exist "tools\chatgpt-image\node_modules\playwright-core" (
  echo [FAIL] ChatGPT browser worker dependencies are missing.
  echo Run: npm install --prefix tools\chatgpt-image
  exit /b 1
)

powershell.exe -NoProfile -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',9333); exit 0 } catch { exit 1 } finally { $c.Dispose() }"
if errorlevel 1 (
  echo [FAIL] WebMCP Relay is not running on 127.0.0.1:9333.
  echo Run start-workbench.cmd and keep the Comic Story page open with WebMCP 6/6.
  exit /b 2
)

curl.exe --silent --fail http://127.0.0.1:9222/json/version >nul 2>nul
if errorlevel 1 (
  echo [FAIL] ChatGPT CDP Chrome is not running on 127.0.0.1:9222.
  echo Open the Studio image engine and click "打开专用 Chrome", then log in to ChatGPT.
  exit /b 2
)

node tools\webmcp\gpt-visual-smoke.mjs --task-id "%~1" --page "%~2"
endlocal
