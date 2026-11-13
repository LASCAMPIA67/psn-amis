@echo off
chcp 65001 >nul
setlocal
title PSN Amis
cd /d "%~dp0"

rem ================================================================
rem  PSN Amis depuis le code source (développement) : double-cliquez
rem  sur ce fichier. Pour une utilisation normale, installez plutôt
rem  PSN Amis avec PSN-Amis-Setup-x.y.z.exe (aucun outil à installer).
rem ================================================================

rem Avec uv : installe Python et les bibliothèques la première fois, puis les met
rem à jour après une nouvelle version de PSN Amis. Un instant si rien n'a changé.
rem Rien n'est retiré de l'environnement : une bibliothèque de développement en
rem cours d'utilisation, Ruff ouvert par un éditeur par exemple, ne gêne pas.
where uv >nul 2>nul
if %errorlevel% neq 0 goto :sans_uv
if not exist ".venv\Scripts\python.exe" echo Première utilisation : installation de Python et des bibliothèques, patientez...
uv sync --frozen --no-dev --inexact --quiet
if %errorlevel% neq 0 (
    if not exist ".venv\Scripts\python.exe" goto :erreur
    echo Mise à jour des bibliothèques impossible pour l'instant : PSN Amis démarre avec celles déjà installées.
)
goto :lancer

:sans_uv
if exist ".venv\Scripts\python.exe" goto :lancer
echo L'outil « uv » est introuvable : impossible d'installer Python et les bibliothèques.
echo Installez-le depuis https://docs.astral.sh/uv/ puis relancez ce fichier.
goto :attendre

:lancer
rem La fenêtre de l'application s'ouvre ; ajoutez --console pour le tableau de bord
rem en couleur des versions 2.x. Les données sont dans %LOCALAPPDATA%\PSN Amis.
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m psn_amis %*
if errorlevel 1 goto :erreur
exit /b 0

:erreur
echo.
echo PSN Amis s'est arrêté avec un problème : lisez le message ci-dessus.

:attendre
echo.
pause
exit /b 1
