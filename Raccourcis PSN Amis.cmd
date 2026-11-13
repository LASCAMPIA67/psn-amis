@echo off
chcp 65001 >nul
setlocal
title PSN Amis - raccourcis
cd /d "%~dp0"

rem ================================================================
rem  Raccourcis de PSN Amis : double-cliquez sur ce fichier pour
rem  ajouter PSN Amis au Bureau, au démarrage de Windows, ou pour
rem  retirer ces raccourcis.
rem ================================================================

if not exist ".venv\Scripts\python.exe" (
    echo Lancez d'abord PSN Amis une fois avec « Lancer PSN Amis.cmd », puis revenez ici.
    goto :attendre
)

echo Raccourcis de PSN Amis
echo.
echo   1. Raccourci sur le Bureau
echo   2. Raccourci sur le Bureau + ouverture automatique au démarrage de Windows
echo   3. Retirer les raccourcis
echo   4. Ne rien changer
echo.
choice /c 1234 /n /m "Votre choix (1, 2, 3 ou 4) : "
set choix=%errorlevel%
echo.
if %choix%==1 ".venv\Scripts\python.exe" outils\raccourcis.py
if %choix%==2 ".venv\Scripts\python.exe" outils\raccourcis.py --demarrage
if %choix%==3 ".venv\Scripts\python.exe" outils\raccourcis.py --retirer

:attendre
echo.
pause
