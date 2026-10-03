@echo off
REM ============================================================
REM  agent.bat -- run the local model as an AI agent (tools + loop)
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM
REM  Needs the engine running:  double-click chat-web.bat  (or start-ptq1-mtp-8gb.bat)
REM  Then type a task here, e.g.:
REM      现在几点？然后在工作目录里创建 hello.txt，写入当前时间。
REM      看一下工作目录里有什么，然后用一句话总结。
REM
REM  Default endpoint is the guarded proxy (8097), so the agent also gets the
REM  max_tokens clamp and the L3 delivery guard. Use --base http://127.0.0.1:8095/v1
REM  to talk to the engine directly (no guard, no clamp).
REM
REM  Guardrails (docs\04-卡死与循环的防治.md): step cap, consecutive pure-tool-call
REM  turns, repeated identical calls. File tools are confined to agent-work\.
REM ============================================================
chcp 65001 >NUL
setlocal
set "ROOT=%~dp0"
set "PY=%NINFER_PY%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%ROOT%agent-work" mkdir "%ROOT%agent-work" >NUL 2>NUL

echo ============================================================
echo  本地 AI agent ^(工具循环^)
echo  引擎必须已启动：先双击 chat-web.bat 或 start-ptq1-mtp-8gb.bat
echo  工作目录：%ROOT%agent-work    输入 /exit 退出
echo ============================================================
echo.
"%PY%" "%ROOT%agent-min.py" --root "%ROOT%agent-work" --log "%ROOT%agent-work\agent-run.jsonl" --base http://127.0.0.1:8097/v1 %*
echo.
echo [agent exited]
pause
