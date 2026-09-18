@echo off
setlocal
cd /d "%~dp0..\.."

for /f "delims=" %%V in ('node -p "process.versions.node" 2^>nul') do set "NODE_VERSION=%%V"
if not defined NODE_VERSION (
  echo [FAIL] Node.js was not found in PATH.
  exit /b 1
)

for /f "tokens=1 delims=." %%M in ("%NODE_VERSION%") do set "NODE_MAJOR=%%M"
if %NODE_MAJOR% LSS 22 (
  echo [FAIL] WebMCP smoke test requires Node.js 22 or newer.
  echo Current Node.js: %NODE_VERSION%
  exit /b 1
)

if not exist "tools\webmcp\node_modules\@modelcontextprotocol\client" (
  echo [INFO] Installing WebMCP smoke-test dependencies...
  call npm install --prefix tools\webmcp
  if errorlevel 1 exit /b 1
)

if "%~1"=="" (
  node tools\webmcp\smoke-test.mjs
) else if "%~2"=="" (
  node tools\webmcp\smoke-test.mjs --task-id "%~1"
) else (
  node tools\webmcp\smoke-test.mjs --task-id "%~1" --page "%~2"
)

endlocal
