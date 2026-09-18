@echo off
setlocal

set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PROFILE=%ROOT%\storage\chatgpt-image-browser\cdp-profile"
set "PORT=9222"

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
  echo [ERROR] Google Chrome was not found.
  echo Install Chrome or edit tools\chatgpt-image\start-cdp-chrome.cmd with the correct chrome.exe path.
  exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

echo Starting dedicated normal Chrome for ComfyWorkflowStudio...
echo Profile: %PROFILE%
echo CDP: http://127.0.0.1:%PORT%
echo.
echo Sign in to ChatGPT in this window, then keep this Chrome window open while generating images.
echo.

start "ComfyWorkflowStudio ChatGPT Image" "%CHROME%" --remote-debugging-address=127.0.0.1 --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" https://chatgpt.com/

echo.
echo After login, in PowerShell run:
echo   $env:CWS_CHATGPT_IMAGE_CDP_URL="http://127.0.0.1:%PORT%"
echo   node tools/chatgpt-image/worker.js check
echo.
endlocal
