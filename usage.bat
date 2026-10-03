@echo off
REM ============================================================
REM  usage.bat -- open the API usage dashboard (call volume, tokens, speed)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Reads two things from the running engine:
REM    * the structured request log  logs\requests.jsonl
REM      (the engine writes it when started with --request-log-jsonl, which
REM       start-ptq1-mtp-lan.bat now passes)
REM    * the stats port             http://127.0.0.1:8099  (/v1/load, /metrics)
REM      (enabled by --stats-port in the same launcher)
REM
REM  Then serves the dashboard on http://127.0.0.1:8098/ and opens the browser.
REM  Closing this window stops only the dashboard, never the engine.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
chcp 65001 >NUL
setlocal EnableExtensions
set "HERE=%~dp0"
set "PY=%NINFER_PY%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"

set "REQLOG=%HERE%logs\requests.jsonl"
if not exist "%HERE%logs" mkdir "%HERE%logs" >NUL 2>NUL

set "KEYARG="
if defined NINFER_API_KEY set "KEYARG=--api-key %NINFER_API_KEY%"
if not defined KEYARG if exist "%HERE%api-key.txt" set "KEYARG=--api-key-file "%HERE%api-key.txt""

set "RUNNING="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8098 " ^| findstr "LISTENING"') do if not defined RUNNING set "RUNNING=%%P"
if defined RUNNING (
  echo [usage] dashboard already running on 8098 ^(pid %RUNNING%^) - opening it.
  start "" http://127.0.0.1:8098/
  exit /b 0
)

if not exist "%REQLOG%" (
  echo [usage] note: %REQLOG% does not exist yet.
  echo [usage]        Start the engine with start-ptq1-mtp-lan.bat - it passes
  echo [usage]        --request-log-jsonl so this file gets created on the first request.
)

echo ============================================================
echo  API usage dashboard
echo    url       : http://127.0.0.1:8098/
echo    request log: %REQLOG%
echo    stats port : http://127.0.0.1:8099
echo  Closing this window stops only the dashboard.
echo ============================================================
echo.
start "" http://127.0.0.1:8098/
"%PY%" "%HERE%usage-dashboard.py" --port 8098 --request-log "%REQLOG%" --stats http://127.0.0.1:8099 %KEYARG%
echo.
echo [usage exited]
pause
