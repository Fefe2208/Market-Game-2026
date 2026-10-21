@echo off
chcp 65001 >nul
REM ============================================================
REM  Market Game 2027 : genere et ouvre le tableau de bord
REM  Double-clic sur ce fichier pour lancer.
REM ============================================================
cd /d "%~dp0"

REM Python installe sur ce PC (sinon on essaie le lanceur "py")
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py"

echo Generation du tableau de bord...
"%PY%" export_dashboard.py
if errorlevel 1 (
  echo.
  echo Une erreur s est produite : lis le message ci-dessus.
  pause
)
