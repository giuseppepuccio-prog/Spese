@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Pubblica le spese su GitHub

echo ============================================================
echo   PUBBLICAZIONE SU GITHUB
echo ============================================================
echo.

rem git viene installato fuori dal PATH della sessione corrente:
rem lo cerchiamo dove finisce di solito
set "GIT=git"
where git >nul 2>&1 || set "GIT=C:\Program Files\Git\cmd\git.exe"
if not exist "%GIT%" if "%GIT%" neq "git" (
  echo ERRORE: non trovo Git. Reinstallalo con: winget install Git.Git
  echo.
  pause
  exit /b 1
)

echo Controllo se ci sono modifiche da salvare...
"%GIT%" add -A
"%GIT%" diff --cached --quiet
if errorlevel 1 (
  echo   Trovate modifiche: le salvo.
  "%GIT%" commit -q -m "aggiorna spese"
) else (
  echo   Nessuna modifica nuova.
)
echo.

echo Invio a GitHub...
echo.
echo   Se e' la prima volta, si aprira' una finestra del browser
echo   per accedere a GitHub. Autorizza e torna qui.
echo.
"%GIT%" push -u origin main
echo.

if errorlevel 1 (
  echo ============================================================
  echo   QUALCOSA NON HA FUNZIONATO
  echo ============================================================
  echo.
  echo   Leggi il messaggio qui sopra:
  echo.
  echo   - "Repository not found"  ^-^-^>  il repository su GitHub
  echo     non esiste o ha un nome diverso da "Spese"
  echo.
  echo   - "failed to push some refs"  ^-^-^>  il repository non era
  echo     vuoto: avvisa e ti do il comando per sistemarlo
  echo.
  echo   - "Authentication failed"  ^-^-^>  accesso non riuscito,
  echo     rilancia e riprova
  echo.
) else (
  echo ============================================================
  echo   FATTO
  echo ============================================================
  echo.
  echo   Ora attiva GitHub Pages, una volta sola:
  echo     Settings  ^>  Pages  ^>  Source: Deploy from a branch
  echo     Branch: main    cartella: /sito    poi Save
  echo.
  echo   Dopo qualche minuto il sito sara' su:
  echo     https://giuseppepuccio-prog.github.io/Spese/
  echo.
)
pause
