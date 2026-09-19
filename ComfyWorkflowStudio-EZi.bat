@Echo off&&cd /D %~dp0
Title 'ComfyWorkflowStudio-EZi'

if not exist ".venv\Scripts\pythonw.exe" (
  echo [FAIL] Missing .venv\Scripts\pythonw.exe
  echo Please create the project virtual environment first.
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "launcher\ComfyWorkflowStudio-EZi.pyw"
exit /b 0
