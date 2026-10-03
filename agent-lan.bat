@echo off
REM ============================================================
REM  agent-lan.bat -- run this agent against a REMOTE NInfer engine
REM                  (the same toolkit used locally, pointed at another host)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Use it on the OTHER device after copying this toolkit folder there, or use
REM  your own agent client instead - any OpenAI-compatible client works:
REM      Base URL : http://SERVER-IP:8095/v1
REM      API Key  : the 48 characters in the server's api-key.txt
REM      Model    : qwen3.8-27b
REM      max_tokens: 4096 or less (the engine's KV pool is 8192; see the manual's
REM                  section 1-11 - asking for 32000 crashes the worker)
REM
REM  This script asks for the base URL and the key if they are not supplied, so
REM  nothing machine-specific is baked into it.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
chcp 65001 >NUL
setlocal EnableExtensions
set "HERE=%~dp0"
set "PY=%NINFER_PY%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"

if not defined NINFER_BASE set /p NINFER_BASE=Engine base URL, e.g. http://192.168.1.10:8095/v1 :
if not defined NINFER_API_KEY if exist "%HERE%api-key.txt" set /p NINFER_API_KEY=<"%HERE%api-key.txt"
if not defined NINFER_API_KEY set /p NINFER_API_KEY=API key from the server's api-key.txt :

if not exist "%HERE%agent-work" mkdir "%HERE%agent-work" >NUL 2>NUL

echo ============================================================
echo  base : %NINFER_BASE%
echo  tools: get_time / list_dir / read_file / write_file (no shell tool)
echo  The file tools are confined to: %HERE%agent-work
echo  Type a task, /exit to quit.
echo ============================================================
echo.

"%PY%" "%HERE%agent\agent-min.py" --base %NINFER_BASE% --api-key %NINFER_API_KEY% --root "%HERE%agent-work" --log "%HERE%agent-work\agent-run.jsonl" %*
echo.
echo [agent-lan exited]
pause
