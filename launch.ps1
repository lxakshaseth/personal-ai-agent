# PowerShell script to launch Personal AI Agent Desktop Control Center
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Starting Personal AI Agent Desktop Control Center..." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

& ".\.venv\Scripts\python.exe" run_desktop.py
