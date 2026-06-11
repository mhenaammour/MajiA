@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Outil de devis IA - Maji

echo ============================================
echo   Outil de devis assiste par IA - Maji
echo ============================================
echo.

REM --- 1. Verifier que Python est installe ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python introuvable.
    echo Installez Python 3.10+ : https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" pendant l'installation.
    echo.
    pause
    exit /b 1
)

REM --- 2. Creer l'environnement virtuel au premier lancement ---
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creation de l'environnement virtuel...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] Impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
)

REM --- 3. Installer les dependances une seule fois ---
if not exist ".venv\installed.flag" (
    echo [2/3] Installation des dependances ^(1 a 2 minutes, une seule fois^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERREUR] Echec de l'installation des dependances.
        pause
        exit /b 1
    )
    echo ok> ".venv\installed.flag"
)

REM --- 4. Lancer l'application ---
echo [3/3] Demarrage... l'app va s'ouvrir dans votre navigateur.
echo Pour l'arreter : fermez cette fenetre ou appuyez sur Ctrl+C.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py

pause
