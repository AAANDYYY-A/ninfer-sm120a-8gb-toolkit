@echo off
REM ============================================================
REM  start-ptq1-mtp-8gb.bat -- 8 GB-card sizing of start-ptq1-mtp.bat
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. This file is NOT part of the
REM   shipped pack and is NOT listed in SHA256SUMS.txt. The shipped
REM   start-ptq1-mtp.bat is left byte-for-byte untouched.]
REM
REM  Deltas vs start-ptq1-mtp.bat (everything else identical):
REM    1) --kv-capacity 17920 -> 8192
REM    2) --no-cuda-graph                       (added)
REM    3) a port guard (a second instance on an 8 GB card is a measured crash)
REM    4) --default-max-tokens 32768 changed to 4096, per docs\04-卡死与循环的防治.md
REM       sections 1-11 and L1: max_tokens must stay at or below the pool token
REM       count. The pool here is 8,192, and the field report is a worker crash --
REM       Paged KV reservation invariant was violated, reproduced 2/2, while
REM       /v1/models still answered 200 -- when a client asked for 32,000. 4096
REM       also leaves room for the prompt's own residency in the pool. The page
REM       proxy enforces the same ceiling.
REM
REM  NOTE ON THE BUILT-IN WEBUI: the engine's help advertises
REM  "NINFER_WEBUI_DIR on GET /", but this build has no web assets at all
REM  (the string appears exactly once, inside the help text; the binary contains
REM   no <!DOCTYPE/<html/<script), and GET / returns 404 even with the variable
REM   set. So the chat page is served by chat-web.bat instead -- see
REM   README-聊天怎么用.md. Do not re-add NINFER_WEBUI_DIR as a "fix": it does
REM   nothing here and only makes the failure look like a configuration problem.
REM
REM  Why the sizing, quoting the engine's own numbers measured on THIS machine
REM  (RTX 5060 8 GB, driver 591.86, model bonsai2_27b_ternary_ptq1_native_mtp.ninfer
REM   6,394,697,216 bytes, sha256 5C4486C8A52687E3F62072C7DD2A320546D0E00D1C019BF137EB02CC944E21B8):
REM
REM    shipped argv                    requires 1,863,978,752  available   817,598,464   FATAL
REM    kv-capacity 7168                requires 1,570,062,080  available   639,004,672   FATAL
REM    kv-capacity 7168 host-kv 1024   requires 1,570,062,080  <-- BYTE-IDENTICAL: host pool is not the driver
REM    max-context 32768               requires 1,570,033,408  <-- only -28,672 B: context is not the driver
REM    + --no-cuda-graph (pool 17920)  requires 1,010,437,888  available   940,736,512   (66.5 MiB short)
REM    + --kv-capacity 8192            STARTS: capacity | KV 8,192 tokens, k8v4, explicit
REM                                            | pages 128/4,096 | runtime 710.0 MiB | free 219.0 MiB
REM
REM  So the pool-independent ~1.31 GiB is CUDA Graphs, and no pool value alone can
REM  close it (tutorial section 5.2 says to change the pool to the numbers the
REM  engine reports -- this is where that lands).
REM
REM  Measured with this argv, one counting request, 1,000 in / 1,000 out:
REM    TTFT 2.4 s / 2.0 s | prefill 481.2 / 570.1 tok/s | decode 59.0 / 60.3 tok/s
REM    total 19.3 / 18.6 s | mtp accepted 780/875 (89.1%) | answer continues 301 302 303 ...
REM  TRADE-OFF, stated plainly: --no-cuda-graph is why it fits AND a reason decode
REM  is ~60 tok/s instead of the 196.8 tok/s the pack measured on a 4080 SUPER.
REM
REM  HOW TO USE: easiest is to double-click chat-web.bat once -- it starts this
REM  engine (in its own window), then the chat page, then opens the browser.
REM  Or double-click this file alone and then open http://127.0.0.1:8097/
REM  (that requires chat-web.bat to have been started too).
REM  Closing this console window stops the engine.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
if not defined MODEL set "MODEL=%ROOT%models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  echo         Put it in %ROOT%models\ or run:  set MODEL=D:\path\to\bonsai2_27b_ternary_ptq1_native_mtp.ninfer  ^&^& start-ptq1-mtp-8gb.bat
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

REM one 8 GB card runs exactly ONE instance (measured 2026-10-01: a second one
REM "loads" via WDDM over-commit and then dies in the D3D12 arena)
set "RUNNING="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8095 " ^| findstr "LISTENING"') do if not defined RUNNING set "RUNNING=%%P"
if defined RUNNING (
  echo [ALREADY RUNNING] service already on port 8095 ^(pid %RUNNING%^).
  echo   One 8 GB card runs one instance -- a second start would crash.
  echo   Stop that instance first - close its console window - then run this again.
  pause
  exit /b 4
)

if not exist "%ROOT%engine\ninfer-serve-120a.exe" (
  echo REFUSE: engine\ninfer-serve-120a.exe is missing from this pack
  pause
  exit /b 4
)
set "ENGINE=%ROOT%engine\ninfer-serve-120a.exe"

echo [engine] %ENGINE%
echo [model ] %MODEL%
echo [sized ] 8 GB profile: --kv-capacity 8192, --no-cuda-graph (see the header for the numbers)
echo.

"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b ^
  --max-context 262144 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --spec mtp --draft-tokens 4 --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
