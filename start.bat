@echo off
rem ============================================================
rem  SLMP PLC vezerlo - duplaklikkes indito (Windows)
rem  Ez a fajl csak egy stabil bootstrap: meghivja a run.ps1-et,
rem  ami letolti a legujabb verziot a GitHubrol (ha van), majd
rem  elinditja az alkalmazast. gh es git NEM szukseges.
rem ============================================================
cd /d "%~dp0"
title SLMP PLC vezerlo
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
echo.
pause
