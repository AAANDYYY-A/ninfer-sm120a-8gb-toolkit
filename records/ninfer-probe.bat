@echo off
REM ============================================================
REM  ninfer-probe.bat -- sizing probe for the sm_120a engine pack
REM
REM  This is NOT a pack file. It is a workspace-side probe whose ONLY
REM  purpose is to find the pool numbers this 8 GB card can actually hold.
REM  Everything except --kv-capacity / --host-kv-mib is byte-for-byte the
REM  argv of the shipped start-ptq1-mtp.bat, and the six KV env lines are
REM  copied from it verbatim.
REM
REM  Why: the shipped launcher ships --kv-capacity 17920 for a 4080-class
REM  card. On this RTX 5060 8 GB the engine refused with
REM      requested Engine runtime reservation requires 1863978752 bytes,
REM      but only 817598464 bytes are available for runtime capacity
REM  which is the case tutorial section 5.2 covers: change the pool to the
REM  numbers the engine reports ("don't guess").
REM
REM  usage:  ninfer-probe.bat <kv-capacity> [host-kv-mib] [max-context] ["extra flags"]
REM ============================================================
setlocal
set "ROOT=D:\AI-FAST\infer-engine-sm120a-20261002"
set "ENGINE=%ROOT%\engine\ninfer-serve-120a.exe"
set "MODEL=%ROOT%\models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"
set "CUDA_BIN=%ROOT%\engine"
set "PATH=%CUDA_BIN%;%CUDA_BIN%\x64;%PATH%"

REM ---- the six env lines, verbatim from start-ptq1-mtp.bat ----
set "NINFER_KV_WINDOW=16384"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"
set "NINFER_TERNARY_PTQ1_FAST=1"

set "KV=%~1"
if not defined KV set "KV=7168"
set "HOSTKV=%~2"
if not defined HOSTKV set "HOSTKV=16384"
set "CTX=%~3"
if not defined CTX set "CTX=262144"
set "EXTRA=%~4"

echo [probe ] kv-capacity=%KV%  host-kv-mib=%HOSTKV%  max-context=%CTX%  extra=[%EXTRA%]
echo [engine] %ENGINE%
echo [model ] %MODEL%

"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b ^
  --max-context %CTX% --kv-capacity %KV% --kv-dtype k8v4 --host-kv-mib %HOSTKV% ^
  --prefill-chunk 1024 --spec mtp --draft-tokens 4 ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20 %EXTRA%

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
