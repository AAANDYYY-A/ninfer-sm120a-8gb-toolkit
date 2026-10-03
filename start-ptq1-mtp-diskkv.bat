@echo off
REM ============================================================
REM  start-ptq1-mtp-diskkv.bat -- MAX tier PLUS the disk KV tier
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Answering "can it run in shared GPU memory": NO for this build.
REM    * the only WDDM switch is --wddm-evictable-budget, and the binary says
REM      "--wddm-evictable-budget needs a Windows build with NINFER_D3D12_RESIDENCY=ON".
REM      A symbol count of this exe: NINFER_D3D12_RESIDENCY appears once (inside that
REM      very error message), ID3D12Device zero times -> residency is NOT compiled in,
REM      so the flag can only fail.
REM    * its meaning is the opposite anyway: "budget against dedicated memory, holding
REM      arenas resident" = a guard AGAINST over-commit, not a way to use shared memory.
REM    * the pack's own receipt records that over-commit on this 8 GB card loads and
REM      then dies (cudaErrorLaunchFailure), which is why the launchers guard the port.
REM    * even if it worked, weights would be read over PCIe every token (PCIe Gen3 x8,
REM      ~6-10 GB/s vs 448 GB/s of VRAM) -> single-digit tok/s, not a speedup.
REM
REM  What the engine DOES offer for "more than VRAM + RAM" is a third KV tier on disk:
REM      --disk-kv-path DIR   evicted continuations write KV and states there, per
REM                           artifact and profile, and SURVIVE RESTARTS
REM      --disk-kv-gib N      disk tier budget (engine default 64 GiB)
REM      --disk-kv-restore    seed a new request's matching prefix from the disk tier
REM      --disk-kv-directstorage  needs a build with NINFER_DIRECTSTORAGE; likely not
REM                           compiled into this exe either, so it is NOT passed here.
REM
REM  TRADE-OFF, stated plainly: the disk tier is the SLOWEST tier. It buys CAPACITY
REM  and persistence (a prefix can come back after a restart), never speed. It also
REM  writes to your SSD - keep --disk-kv-gib sane for the free space you have.
REM
REM  Everything else: same as the MAX launcher (28 GiB host pool, 1M context,
REM  draft-tokens 12, fast-prefill-kernel, device pool 8192).
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "KEYFILE=%ROOT%api-key.txt"
if not exist "%KEYFILE%" (
  echo [diskkv] no api-key.txt yet - create it next to this script with a long
  echo [diskkv] random string in it, then run this again.
  pause
  exit /b 3
)
set /p KEY=<"%KEYFILE%"
if not defined KEY (
  echo [diskkv] api-key.txt is empty.
  pause
  exit /b 3
)

set "MODEL=%ROOT%models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"
set "LOGDIR=%ROOT%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >NUL 2>NUL
set "KVDISK=%ROOT%kvdisk"
if not exist "%KVDISK%" mkdir "%KVDISK%" >NUL 2>NUL
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
echo  MAX + DISK KV tier
echo    host KV pool : 28 GiB       max context : 1048576 tok
echo    device pool  : 8192 tok     decode      : draft 12 + fast prefill
echo    disk tier    : %KVDISK%   budget 64 GiB, restore enabled
echo    url          : http://THIS-MACHINE-LAN-IP:8095/v1
echo    stats        : http://127.0.0.1:%STATSPORT%/stats
echo  Reminder: the disk tier adds CAPACITY and survives restarts; it is the slowest
echo  tier and never a speedup. Watch free disk space in %KVDISK%.
echo ============================================================
echo.

"%ROOT%engine\ninfer-serve-120a.exe" "%MODEL%" ^
  --host 0.0.0.0 --port 8095 --model-id qwen3.8-27b --api-key "%KEY%" ^
  --stats-port %STATSPORT% --request-log-jsonl "%REQLOG%" ^
  --max-context 1048576 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 28672 ^
  --disk-kv-path "%KVDISK%" --disk-kv-gib 64 --disk-kv-restore ^
  --spec mtp --draft-tokens 12 --fast-prefill-kernel --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
