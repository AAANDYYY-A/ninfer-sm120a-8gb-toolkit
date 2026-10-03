@echo off
REM ============================================================
REM  start-ptq1-mtp-lan.bat -- same as start-ptq1-mtp-8gb.bat, but the engine
REM  listens on ALL interfaces so another device's AI agent can reach it.
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Differences vs start-ptq1-mtp-8gb.bat -- ONLY these two:
REM    1) --host 127.0.0.1  ->  0.0.0.0
REM    2) --api-key <value>  added, read from api-key.txt next to this script
REM       The engine supports it natively: its help says
REM       "--api-key KEY   require this bearer or x-api-key value".
REM  Everything else, including the 8 GB sizing, is identical.
REM
REM  SECURITY, stated plainly:
REM    * the engine has NO TLS -- the key travels in clear text over the LAN.
REM      Only use this on a network you trust. Never port-forward this port
REM      and never expose it to the internet.
REM    * the key lives in api-key.txt (plain text, next to this script). Keep
REM      that file out of any repository; rotate it by deleting the file and
REM      starting this script again.
REM    * you must allow the port through Windows Firewall once, in an ADMIN
REM      PowerShell:
REM        New-NetFirewallRule -DisplayName "NInfer 8095" -Direction Inbound ^
REM          -Action Allow -Protocol TCP -LocalPort 8095 -Profile Private
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "KEYFILE=%ROOT%api-key.txt"

if not exist "%KEYFILE%" (
  echo [lan] no api-key.txt yet.
  echo [lan] Create a file named api-key.txt next to this script and put a
  echo [lan] long random string in it - 40 or more letters and digits.
  echo [lan] The deploying agent normally generates this file for you; check
  echo [lan] that the engine pack directory is the one you are running from.
  pause
  exit /b 3
)
set /p KEY=<"%KEYFILE%"
if not defined KEY (
  echo [lan] api-key.txt is empty - put a long random string in it.
  pause
  exit /b 3
)

set "MODEL=%ROOT%models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"

REM ---- usage accounting: a stats port and a structured request log ----
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
  echo   One 8 GB card runs one instance. Stop that one first.
  pause
  exit /b 4
)

echo ============================================================
echo  LAN mode: the engine listens on ALL interfaces, port 8095
echo.
echo    api key : %KEYFILE%
echo    url     : http://THIS-MACHINE-LAN-IP:8095/v1
echo              find the IP with:  ipconfig ^| findstr IPv4
echo    model   : qwen3.8-27b
echo.
echo  Client on the other device:
echo    Base URL  http://THE-IP:8095/v1
echo    API Key   the contents of api-key.txt
echo    Model     qwen3.8-27b
echo.
echo  REMINDERS: no TLS - trusted LAN only; never port-forward this port;
echo  local clients need the same key via  set NINFER_API_KEY=...
echo.
echo  usage accounting:
echo    stats/metrics : http://127.0.0.1:%STATSPORT%/metrics  (also /stats, /health, /v1/load)
echo    request log   : %REQLOG%
echo    dashboard     : double-click usage.bat  ->  http://127.0.0.1:8098/
echo ============================================================
echo.

"%ROOT%engine\ninfer-serve-120a.exe" "%MODEL%" ^
  --host 0.0.0.0 --port 8095 --model-id qwen3.8-27b --api-key "%KEY%" ^
  --stats-port %STATSPORT% --request-log-jsonl "%REQLOG%" ^
  --max-context 262144 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --spec mtp --draft-tokens 4 --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
