@echo off
set "PS1=%~dp0run_tests.ps1"
set "ARGS=%*"
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "Get-Item '%PS1%' | Unblock-File -ErrorAction SilentlyContinue; & '%PS1%' %ARGS%"
if ERRORLEVEL 1 pause
