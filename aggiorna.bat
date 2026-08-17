@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   AGGIORNAMENTO SPESE
echo ============================================
echo.
rem La raccolta via e-mail e' sospesa: i documenti li metti tu nelle cartelle.
rem Per riattivarla in futuro lancia raccogli_email.bat, oppure rimetti qui
rem la chiamata a raccogli_email.py.

echo Leggo tutte le sottocartelle di:
echo   OneDrive\Documenti\07. Spese Personali
echo.
".venv\Scripts\python.exe" build.py
if errorlevel 1 (
  echo.
  echo Qualcosa non ha funzionato. Controlla il messaggio qui sopra.
  pause
  exit /b 1
)
echo.
echo ============================================
echo   Fatto. Per pubblicare online:
echo     git add -A ^&^& git commit -m "aggiorna spese" ^&^& git push
echo ============================================
pause
