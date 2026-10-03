@echo off
REM ============================================================
REM  allow-firewall-8095.bat -- ONE double-click helper
REM
REM  Windows Firewall changes need elevation, which no agent can approve for
REM  you: UAC is designed to require a human click. This file exists so that
REM  the whole thing becomes "double-click once, confirm UAC once".
REM
REM  It adds an inbound TCP rule for port 8095 so another device can reach the
REM  NInfer engine on this machine, then prints the rule back for verification.
REM
REM  Why -Profile Any: this machine also has a Radmin VPN adapter, which Windows
REM  often classifies as a Public network, so a Private-only rule would not cover
REM  it. The engine itself requires --api-key, and that key is the real protection.
REM  NEVER port-forward this port to the internet.
REM
REM  [ADDED BY THE DEPLOYING AGENT 2026-10-03. Not part of the shipped pack.]
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
fltmc >NUL 2>NUL
if errorlevel 1 (
  echo.
  echo Requesting administrator rights - please confirm the UAC prompt.
  echo A second window will open and do the work.
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo  Running elevated - adding the firewall rule for port 8095
echo ============================================================
netsh advfirewall firewall delete rule name="NInfer 8095" >NUL 2>NUL
netsh advfirewall firewall add rule name="NInfer 8095" dir=in action=allow protocol=TCP localport=8095 profile=any
echo.
echo --- verification (the rule as Windows sees it) ---
netsh advfirewall firewall show rule name="NInfer 8095"
echo.
echo If the rule is listed above with Action: Allow, this step is DONE.
echo Next: on the other device, test with the API key from api-key.txt -
echo   curl.exe -sS -o NUL -w "%%{http_code}" -H "Authorization: Bearer KEY" http://THIS-MACHINE-IP:8095/v1/models
echo   expected: 401 without the key, 200 with it.
echo.
pause
