@echo off
setlocal

for /f "delims=" %%V in ('node -p "process.versions.node" 2^>nul') do set "NODE_VERSION=%%V"
if not defined NODE_VERSION (
  echo [FAIL] Node.js was not found in PATH.
  exit /b 1
)

for /f "tokens=1 delims=." %%M in ("%NODE_VERSION%") do set "NODE_MAJOR=%%M"
if %NODE_MAJOR% LSS 22 (
  echo [FAIL] WebMCP local relay requires Node.js 22 or newer.
  echo Current Node.js: %NODE_VERSION%
  echo The Studio itself can still use the MCP-B browser polyfill without the relay process.
  exit /b 1
)

echo Starting ComfyWorkflowStudio WebMCP local relay...
echo Host: 127.0.0.1
echo Port: 9333
echo Allowed origins:
echo   http://127.0.0.1:5174
echo   http://localhost:5174
echo.
echo Keep this terminal open while testing an MCP client.
echo.

npx -y @mcp-b/webmcp-local-relay@5.1.0 --host 127.0.0.1 --port 9333 --widget-origin "http://127.0.0.1:5174,http://localhost:5174" --label "ComfyWorkflowStudio"

endlocal
