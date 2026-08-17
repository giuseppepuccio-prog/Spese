@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Spese - sorveglianza cartelle
".venv\Scripts\python.exe" sorveglia.py
pause
