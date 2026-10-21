@echo off
chcp 65001 >nul
REM ============================================================
REM  Market Game 2027 : genere le classeur Excel Market_Game_2027.xlsx
REM  Double-clic sur ce fichier pour lancer.
REM ============================================================
cd /d "%~dp0"

REM Python installe sur ce PC (sinon on essaie le lanceur "py")
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py"

REM openpyxl sert a ecrire le fichier Excel : on l'installe s'il manque
"%PY%" -c "import openpyxl" 2>nul || "%PY%" -m pip install openpyxl

echo Generation du classeur Excel...
"%PY%" export_excel.py
if errorlevel 1 (
  echo.
  echo Une erreur s est produite : lis le message ci-dessus.
  pause
) else (
  start "" "Market_Game_2027.xlsx"
)
