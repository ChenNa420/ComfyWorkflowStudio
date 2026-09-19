@echo off
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0launcher\ComfyWorkflowStudio-Launcher.ps1"
exit /b 0
