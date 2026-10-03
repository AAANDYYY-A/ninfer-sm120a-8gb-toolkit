@echo off
REM ============================================================
REM  start-ptq1-mtp-lan-1m.bat -- MAX variant: 1M context AND fast decode
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Deltas vs start-ptq1-mtp-lan.bat -- ONLY these two:
REM      --host-kv-mib  16384 -> 28672     (16 GiB -> 28 GiB of host KV)
REM      --max-context  262144 -> 1048576  (256K -> 1M logical context)
REM  PLUS the two speed flags from start-ptq1-mtp-fast.bat:
REM      --draft-tokens 4 -> 12        (deeper speculative window)
REM      --fast-prefill-kernel         (faster prefill / shorter TTFT)
REM  Everything else unchanged (device pool 8192, k8v4, --no-cuda-graph).
REM  If you want to isolate one variable at a time use the other launchers:
REM      start-ptq1-mtp-lan.bat       baseline (16 GiB / 256K, draft 4)
REM      start-ptq1-mtp-fast.bat      speed only (16 GiB / 256K, draft 12 + fast prefill)
REM      start-ptq1-mtp-lan-bigctx.bat capacity only (24 GiB / 768K, draft 4)
REM
REM  THE ARITHMETIC, from the engine's own accounting
REM      host_kv_page_group_bytes = 1,646,592 B per 64 tokens = 25.12 KiB per token
REM      needed host pool = max_context / 64 * 1,646,592 B
REM          262144 ->  6.28 GiB      524288 -> 12.56 GiB
REM          786432 -> 18.84 GiB     1048576 -> 25.12 GiB   <-- this file
REM          2097152 -> 50.25 GiB    (impossible here: the box has ~32 GB RAM)
REM      28 GiB gives 18,258 page groups = 1,168,512 tokens, so 1M fits with
REM      ~2.9 GiB of margin. 32 GiB would just fit 1.34M tokens but eats the whole
REM      commit budget, so this file stops at 28.
REM
REM  WHY THIS IS CHEAP IN PRACTICE
REM      The launcher sets NINFER_HOST_PAGEABLE=1, so the host KV is PAGEABLE memory:
REM      the number above is a budget that is accounted against the commit charge, not
REM      a physically pinned block. Measured with a 24 GiB budget: only 2.49 GiB was
REM      actually occupied. If the host allocation is ever refused, the engine says so
REM      at startup with the two numbers it wants - then fall back to 24576 (24 GiB,
REM      start-ptq1-mtp-lan-bigctx.bat) and tell the uploader.
REM
REM  WHAT THIS DOES *NOT* DO: it does not make decoding faster. A bigger host pool is
REM  capacity; longer contexts page more KV over PCIe per step. Speed lives in
REM  start-ptq1-mtp-fast.bat (--draft-tokens 12 + --fast-prefill-kernel).
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "KEYFILE=%ROOT%api-key.txt"
if not exist "%KEYFILE%" (
  echo [1m] no api-key.txt yet - create it next to this script with a long random
  echo [1m] string in it, then run this again.
  pause
  exit /b 3
)
set /p KEY=<"%KEYFILE%"
if not defined KEY (
  echo [1m] api-key.txt is empty.
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
echo  MAX mode: 1M context + draft 12 + fast prefill
echo    host KV pool : 28 GiB      ^(was 16; bigctx file uses 24^)
echo    max context  : 1048576 tok ^(1M^)
echo    device pool  : 8192 tok    ^(unchanged - VRAM is the hard limit^)
echo    decode flags : draft-tokens 12 + fast-prefill-kernel
echo    url          : http://THIS-MACHINE-LAN-IP:8095/v1
echo    api key      : %KEYFILE%
echo    stats        : http://127.0.0.1:%STATSPORT%/stats
echo    request log  : %REQLOG%
echo  Watch the startup "capacity |" line; if it refuses, it prints the numbers it wants.
echo ============================================================
echo.

"%ROOT%engine\ninfer-serve-120a.exe" "%MODEL%" ^
  --host 0.0.0.0 --port 8095 --model-id qwen3.8-27b --api-key "%KEY%" ^
  --stats-port %STATSPORT% --request-log-jsonl "%REQLOG%" ^
  --max-context 1048576 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 28672 ^
  --spec mtp --draft-tokens 12 --fast-prefill-kernel --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
