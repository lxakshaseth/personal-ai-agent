@echo off
title Personal AI Agent - Desktop Control Center
cd /d "%~dp0"
echo Starting Personal AI Desktop Agent...
.venv\Scripts\python.exe run_desktop.py
pause
