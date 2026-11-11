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

rem Avec uv : installe Python et les bibliothèques la première fois, puis les
rem met à jour après une nouvelle version de PSN Amis. Un instant si rien n'a changé.
where uv >/dev/null 2>/dev/null
if %errorlevel%==0 (
    if not exist ".venv\Scripts\python.exe" echo Première utilisation : installation de Python et des bibliothèques, patientez...
    uv sync --frozen --no-dev --quiet || goto :erreur
) else if not exist ".venv\Scripts\python.exe" (
    goto :sans_uv
)

".venv\Scripts\python.exe" accepter_amis.py %*
if errorlevel 1 goto :erreur
exit /b 0

:sans_uv
echo L'outil « uv » est introuvable : impossible d'installer Python et les bibliothèques.
echo Installez-le depuis https://docs.astral.sh/uv/ puis relancez ce fichier.
goto :attendre

:erreur
echo.
echo PSN Amis s'est arrêté avec un problème : lisez le message ci-dessus.

:attendre
echo.
pause
exit /b 1
