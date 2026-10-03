@echo off
REM ============================================================
REM  test-speed.bat -- one-click speed measurement (the engine's own numbers)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Sends the pack's standard counting corpus (1..300 then continue, i.e. about
REM  1,133 prompt tokens in / 1,000 tokens out, temperature 0) and prints the
REM  AUTHORITATIVE timings taken from the engine's own response JSON:
REM      timings.prompt_per_second      = prefill tok/s
REM      timings.predicted_per_second   = decode tok/s
REM      timings.draft_n / draft_n_accepted = speculative acceptance
REM  No guessing, no parsing of console logs.
REM
REM  Point it at another machine with:  set NINFER_ENGINE=192.168.1.10:8095
REM  It reads the API key from api-key.txt next to this script when present.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
chcp 65001 >NUL
setlocal EnableExtensions
set "HERE=%~dp0"
set "PY=%NINFER_PY%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"

set "ENG=%NINFER_ENGINE%"
if not defined ENG set "ENG=127.0.0.1:8095"
set "KEY="
if defined NINFER_API_KEY set "KEY=%NINFER_API_KEY%"
if not defined KEY if exist "%HERE%api-key.txt" set /p KEY=<"%HERE%api-key.txt"

echo ============================================================
echo  speed test  -  engine %ENG%
echo  corpus      -  1..300 then continue, max_tokens 1000, temperature 0
echo ============================================================
echo.

"%PY%" "%HERE%tools\speedtest.py" --engine %ENG% --key "%KEY%"
echo.
pause
