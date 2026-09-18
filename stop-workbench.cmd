@echo off
title ComfyWorkflowStudio Shutdown
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-workbench.ps1"
pause
