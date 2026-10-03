@echo off
REM ============================================================
REM  chat-web.bat -- ONE double-click brings up everything:
REM     1) the chat page  on 127.0.0.1:8097  (own minimized window)
REM     2) the engine     on 127.0.0.1:8095  (THIS window, foreground)
REM     3) your browser, at the chat page (opens by itself after ~18 s)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Why the engine runs in THIS window instead of a spawned one: the window you
REM  double-clicked is then the engine's console, so you can always see its log
REM  and closing it stops the service -- and it does not rely on launching a
REM  long-running process through `start` (the first design did, and the spawned
REM  engine window did not survive).
REM
REM  Why a page proxy at all: the engine serves only /v1/*, has NO built-in web
REM  assets in this build (GET / -> 404; NINFER_WEBUI_DIR is advertised in the
REM  help text but the string occurs exactly once in the 1.33 GB binary and there
REM  is no <!DOCTYPE/<html/<script in it), and it sends no CORS headers. So the
REM  page is served by ninfer-chat.py, which also proxies server-side => the
REM  browser sees a single same origin and never hits CORS.
REM
REM  Two windows, two meanings:
REM    this window (the engine)  closing it STOPS THE ENGINE
REM    "NInfer chat page 8097"   closing it only breaks the web page
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
chcp 65001 >NUL
setlocal EnableExtensions
set "ROOT=%~dp0"

REM ---- python: NINFER_PY wins, then the runtime DSH ships, then PATH ----
set "PY=%NINFER_PY%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
set "HAVE_PY="
if exist "%PY%" set "HAVE_PY=1"
if not defined HAVE_PY (
  where python >NUL 2>NUL && set "HAVE_PY=1" && set "PY=python"
)
if not defined HAVE_PY (
  echo [ERROR] no python found. Set NINFER_PY to a python.exe and run this again.
  echo         Looked for: %USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
  pause
  exit /b 3
)

REM ---- 1) chat page on 8097, in its own minimized window ----
REM Point it at another machine's engine with:  set NINFER_ENGINE=192.168.1.20:8095
REM If that engine was started with --api-key:  set NINFER_API_KEY=<that value>
set "ENG=%NINFER_ENGINE%"
if not defined ENG set "ENG=127.0.0.1:8095"
set "KEYARG="
if defined NINFER_API_KEY set "KEYARG=--api-key %NINFER_API_KEY%"
if not defined KEYARG if exist "%ROOT%api-key.txt" set /p KEY=<"%ROOT%api-key.txt"
if not defined KEYARG if exist "%HERE%api-key.txt" set /p KEY=<"%HERE%api-key.txt"
if not defined KEYARG if defined KEY set "KEYARG=--api-key %KEY%"
set "PAGE="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8097 " ^| findstr "LISTENING"') do if not defined PAGE set "PAGE=%%P"
if defined PAGE (
  echo [1/3] chat page already running on 8097 ^(pid %PAGE%^).
) else (
  echo [1/3] starting the chat page on 8097, engine %ENG% ...
  start "NInfer chat page 8097 - closing this window only breaks the page" /min "%PY%" "%ROOT%ninfer-chat.py" --port 8097 --engine %ENG% %KEYARG% --model qwen3.8-27b
)

REM ---- 2) open the browser once the engine has had time to load ----
echo [2/3] the browser will open http://127.0.0.1:8097/ in about 18 s ...
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 18; Start-Process 'http://127.0.0.1:8097/'"

REM ---- 3) the engine, in THIS window ----
echo [3/3] starting the engine below. Leave this window open while you chat.
echo.
echo ============================================================
echo  chat page : http://127.0.0.1:8097/
echo  engine    : http://127.0.0.1:8095/v1   ^(API only, no page^)
echo  no browser wanted?  chat-cli.bat = terminal chat
echo ============================================================
echo.

call "%ROOT%start-ptq1-mtp-8gb.bat"

echo.
echo [chat-web] the engine has exited - closing this window.
pause
