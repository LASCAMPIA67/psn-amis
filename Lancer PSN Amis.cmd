@echo off
chcp 65001 >/dev/null
setlocal
title PSN Amis
cd /d "%~dp0"

rem ================================================================
rem  PSN Amis : double-cliquez sur ce fichier pour lancer
rem  l'acceptation automatique des demandes d'amis PSN.
rem  Pour arrêter : touche Q deux fois, ou fermez la fenêtre.
rem ================================================================

if not exist ".venv\Scripts\python.exe" (
    echo Première utilisation : installation des composants, patientez...
    where uv >/dev/null 2>/dev/null || goto :sans_uv
    uv sync --frozen --no-dev || goto :erreur
)

".venv\Scripts\python.exe" accepter_amis.py %*
if errorlevel 1 goto :erreur
exit /b 0

:sans_uv
echo L'outil « uv » est introuvable : impossible d'installer les composants.
echo Installez-le depuis https://docs.astral.sh/uv/ puis relancez ce fichier.
goto :attendre

:erreur
echo.
echo PSN Amis s'est arrêté avec un problème : lisez le message ci-dessus.

:attendre
echo.
pause
exit /b 1
