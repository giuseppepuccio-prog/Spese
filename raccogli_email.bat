@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   RACCOLTA ESTRATTI DA E-MAIL (facoltativa)
echo ============================================
echo.
echo Serve solo se vuoi inviare gli estratti via mail invece di
echo copiarli nelle cartelle. Richiede una password per app di Google.
echo.
".venv\Scripts\python.exe" raccogli_email.py
echo.
pause
