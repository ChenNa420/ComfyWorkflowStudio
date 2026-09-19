@echo off
setlocal

set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PROFILE=%ROOT%\storage\chatgpt-image-browser\cdp-profile"
set "PORT=9222"
set "LEGACY_GPT_URL=https://chatgpt.com/g/g-6aa62443216c819181e35cd36d02e486-tong-yu-gong-fang-aidong-hua-bian-ju-dao-yan"
set "DEFAULT_GPT_URL=https://chatgpt.com/g/g-6aad4e72baa0819194cfc692ad061ac2-tong-yu-gong-fang-man-hua-zhong-shi-dong-hua-dao-yan"
if defined CWS_CHATGPT_IMAGE_URL (
  if /I "%CWS_CHATGPT_IMAGE_URL%"=="%LEGACY_GPT_URL%" (
    set "TARGET_URL=%DEFAULT_GPT_URL%"
  ) else (
    set "TARGET_URL=%CWS_CHATGPT_IMAGE_URL%"
  )
) else (
  set "TARGET_URL=%DEFAULT_GPT_URL%"
)

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
echo GPT: %TARGET_URL%
echo.
echo Sign in to ChatGPT in this window, then keep this Chrome window open while generating images.
echo.

start "ComfyWorkflowStudio ChatGPT Image" "%CHROME%" --remote-debugging-address=127.0.0.1 --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" "%TARGET_URL%"

echo.
echo The image worker now defaults to:
echo   CDP: http://127.0.0.1:%PORT%
echo   GPT: %TARGET_URL%
echo.
echo Check with:
echo   node tools\chatgpt-image\worker.js check
echo.
endlocal
