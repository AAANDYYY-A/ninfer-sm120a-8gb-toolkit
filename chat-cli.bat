@echo off
REM ============================================================
REM  chat-cli.bat -- terminal chat for the NInfer engine (no browser)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Use this when the browser page misbehaves: it removes every browser-side
REM  variable (CORS, streaming, extensions, cache) and talks straight to the
REM  engine on 127.0.0.1:8095.
REM
REM  Start the engine first:  start-ptq1-mtp-8gb.bat
REM ============================================================
chcp 65001 >NUL
setlocal
set "HERE=%~dp0"
set "PY=%NINFER_PY%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%HERE%ninfer-cli.py" --engine 127.0.0.1:8095 --model qwen3.8-27b
echo.
echo [chat-cli exited]
pause
