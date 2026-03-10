@echo off
echo ===================================================
echo    Installation des dependances du projet
echo ===================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas installe ou n'est pas dans le PATH.
    echo Veuillez installer Python depuis https://www.python.org/downloads/
    pause
    exit /b
)

echo Mise a jour de pip...
python -m pip install --upgrade pip >nul 2>&1

echo Installation des bibliotheques Python...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] Une erreur est survenue lors de l'installation.
    pause
    exit /b
)

echo.
echo ===================================================
echo    Installation terminee avec succes !
echo ===================================================
echo.
echo Vous pouvez maintenant utiliser start.bat pour lancer le projet.
pause
