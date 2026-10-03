@echo off
REM ============================================================
REM  start-ptq1-mtp-fast.bat -- SPEED-TUNED variant (LAN + key + stats + log)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Identical to start-ptq1-mtp-lan.bat except TWO speed flags:
REM    --draft-tokens 4 -> 12        (deeper speculative window)
REM    --fast-prefill-kernel         (faster prefill, shorter TTFT)
REM
REM  Why: measured on this machine with the standard counting corpus
REM  (1,133 in / 1,000 out, temperature 0):
REM      draft 4, no fast-prefill : prefill 482.8 tok/s | decode 54.5 tok/s | draft 875/780 = 89.1%
REM  The draft window was only 4 while acceptance was already 89%, which is exactly
REM  the case the pack's docs describe as "window 12 gives about 2.2x on predictable
REM  text" (they measured 278 -> 600 tok/s on a 4080 SUPER).
REM
REM  TRADE-OFF, stated plainly: a deeper draft is SLOWER on unpredictable text
REM  (random numbers, open-ended prose) because every extra draft must be verified.
REM  Keep start-ptq1-mtp-lan.bat around and switch back when you need that.
REM
REM  NOT changed here (and why):
REM    * --kv-capacity stays 8192: VRAM was down to ~211 MiB free, so a bigger
REM      device pool does not fit; a bigger HOST pool (--host-kv-mib) would only add
REM      context capacity, never speed, and 16 GiB is already pinned.
REM    * --no-cuda-graph stays: CUDA Graphs need roughly 850 MiB more VRAM than the
REM      no-graph path, which this card does not have until the desktop frees VRAM.
REM      If you later close enough GPU-using apps to free ~1 GiB, try removing it:
REM      the graph path removes per-step launch overhead.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "KEYFILE=%ROOT%api-key.txt"

if not exist "%KEYFILE%" (
  echo [fast] no api-key.txt yet.
  echo [fast] Create that file next to this script and put a long random
  echo [fast] string in it - 40 or more letters and digits.
  pause
  exit /b 3
)
set /p KEY=<"%KEYFILE%"
if not defined KEY (
  echo [fast] api-key.txt is empty - put a long random string in it.
  pause
  exit /b 3
)

set "MODEL=%ROOT%models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"
set "LOGDIR=%ROOT%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >NUL 2>NUL
set "STATSPORT=8099"
set "REQLOG=%LOGDIR%\requests.jsonl"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  pause
  exit /b 3
)
set "CUDA_BIN=%ROOT%engine"
set "PATH=%CUDA_BIN%;%CUDA_BIN%\x64;%PATH%"
set "NINFER_KV_WINDOW=16384"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"
set "NINFER_TERNARY_PTQ1_FAST=1"

set "RUNNING="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8095 " ^| findstr "LISTENING"') do if not defined RUNNING set "RUNNING=%%P"
if defined RUNNING (
  echo [ALREADY RUNNING] something already listens on 8095 ^(pid %RUNNING%^).
  echo   One 8 GB card runs one instance. Close that window first.
  pause
  exit /b 4
)

echo ============================================================
echo  SPEED-TUNED mode: draft-tokens 12 + fast-prefill-kernel
echo    url        : http://THIS-MACHINE-LAN-IP:8095/v1
echo    api key    : %KEYFILE%
echo    stats      : http://127.0.0.1:%STATSPORT%/metrics
echo    request log: %REQLOG%
echo  Measure it with:  test-speed.bat   ^(prints the engine's own timings^)
echo ============================================================
echo.

"%ROOT%engine\ninfer-serve-120a.exe" "%MODEL%" ^
  --host 0.0.0.0 --port 8095 --model-id qwen3.8-27b --api-key "%KEY%" ^
  --stats-port %STATSPORT% --request-log-jsonl "%REQLOG%" ^
  --max-context 262144 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --spec mtp --draft-tokens 12 --fast-prefill-kernel --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
