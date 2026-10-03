@echo off
REM ============================================================
REM  start-ptq1-mtp-lan-bigctx.bat -- BIG CONTEXT variant (LAN + key + stats + log)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Deltas vs start-ptq1-mtp-lan.bat -- ONLY these two:
REM      --host-kv-mib  16384 -> 24576     (16 GiB -> 24 GiB of host-side KV)
REM      --max-context  262144 -> 786432   (256K -> 768K logical context)
REM  Everything else (device pool 8192, k8v4, --no-cuda-graph, draft 4, LLM flags) unchanged.
REM
REM  WHY BOTH NUMBERS HAVE TO MOVE TOGETHER
REM    The engine enforces, at startup:
REM        host pages + device pages  >=  logical context pages      (page = 64 tokens)
REM    and for k8v4 it costs roughly 25 KiB of host pool per token of logical
REM    context (the pack's own tutorial, section 2). So:
REM        --max-context 262144 needed only ~6.6 GiB  <- the 16 GiB pool was
REM        never the limit; the --max-context value was.
REM        --max-context 786432 needs ~18.8 GiB       <- fits inside 24 GiB.
REM        --max-context 1048576 needs ~26.5 GiB      <- does NOT fit in 24 GiB;
REM                                                      raise the pool to 28 GiB first.
REM    If the arithmetic is off for this artifact, the engine REFUSES at startup and
REM    prints the two numbers it wants - change the pool to that number, do not guess.
REM
REM  WHAT THIS DOES *NOT* DO
REM    It does not make decoding faster. A bigger host pool is CAPACITY: whatever does
REM    not fit the 8,192-token device pool lives in host RAM and is paged back over
REM    PCIe on demand, which costs time. Longer contexts therefore mean more paging
REM    per step, not fewer. Speed knobs live in start-ptq1-mtp-fast.bat
REM    (draft-tokens 12 + fast-prefill-kernel) and in freeing VRAM for CUDA Graphs.
REM
REM  RAM COST: 24 GiB is a *budget*, and the engine currently only occupies a few GiB
REM  of it (measured: 2.49 GiB in use with a 16 GiB budget). This box has ~32 GB
REM  physical RAM, so if cudaMallocHost ever refuses, the engine says so at startup --
REM  then drop back to 20480.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "KEYFILE=%ROOT%api-key.txt"
if not exist "%KEYFILE%" (
  echo [bigctx] no api-key.txt yet - create it next to this script with a long
  echo [bigctx] random string in it, then run this again.
  pause
  exit /b 3
)
set /p KEY=<"%KEYFILE%"
if not defined KEY (
  echo [bigctx] api-key.txt is empty.
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
echo  BIG CONTEXT mode
echo    host KV pool : 24 GiB      ^(was 16 GiB^)
echo    max context  : 786432 tok  ^(was 262144^)
echo    device pool  : 8192 tok    ^(unchanged - VRAM is the hard limit^)
echo    url          : http://THIS-MACHINE-LAN-IP:8095/v1
echo    api key      : %KEYFILE%
echo    stats        : http://127.0.0.1:%STATSPORT%/stats
echo    request log  : %REQLOG%
echo  Watch the startup line "capacity |" - it prints the accepted numbers.
echo ============================================================
echo.

"%ROOT%engine\ninfer-serve-120a.exe" "%MODEL%" ^
  --host 0.0.0.0 --port 8095 --model-id qwen3.8-27b --api-key "%KEY%" ^
  --stats-port %STATSPORT% --request-log-jsonl "%REQLOG%" ^
  --max-context 786432 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 24576 ^
  --spec mtp --draft-tokens 4 --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
