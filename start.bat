@echo off
title Lanceur Convertisseur Musique
cls

:MENU
echo ===================================================
echo    CONVERTISSEUR MUSIQUE - MENU PRINCIPAL
echo ===================================================
echo.
echo 1. Lancer l'interface Web (app.py)
echo 2. Lancer le Bot Discord (bot.py)
echo 3. Lancer les deux (Web + Bot)
echo 4. Installer/Mettre a jour les dependances
echo.
echo --- Outils ---
echo 5. Tagging dates + genres (add_release_date.py)
echo 6. Renommer les fichiers (rename_tracks.py)
echo 7. Tagging + Renommage combines
echo 8. Nettoyage doublons (cleanup_duplicates.py)
echo 9. Choisir les outils a executer
echo 10. Pipeline global (qualite + upgrade + renommage + doublons)
echo 0. Quitter
echo.
set /p choix="Votre choix (0-10) : "

if "%choix%"=="1" goto WEB
if "%choix%"=="2" goto BOT
if "%choix%"=="3" goto BOTH
if "%choix%"=="4" goto INSTALL
if "%choix%"=="5" goto TAG
if "%choix%"=="6" goto RENAME
if "%choix%"=="7" goto TAG_RENAME
if "%choix%"=="8" goto CLEANUP
if "%choix%"=="9" goto MULTI
if "%choix%"=="10" goto PIPELINE
if "%choix%"=="0" goto END

echo Choix invalide.
goto MENU

:WEB
cls
echo Lancement de l'interface Web...
echo Ouvrez votre navigateur sur http://127.0.0.1:5000
echo Appuyez sur CTRL+C pour arreter le serveur.
echo.
python app.py
pause
goto MENU

:BOT
cls
echo Lancement du Bot Discord...
echo Assurez-vous d'avoir configure votre token dans le fichier .env
echo Appuyez sur CTRL+C pour arreter le bot.
echo.
python bot.py
pause
goto MENU

:BOTH
cls
echo Lancement de l'interface Web et du Bot Discord...
echo Deux nouvelles fenetres vont s'ouvrir.
echo Ne fermez pas ces fenetres pour garder les services actifs.
echo.
start "Interface Web - app.py" cmd /k "title Interface Web - app.py & python app.py"
start "Bot Discord - bot.py" cmd /k "title Bot Discord - bot.py & python bot.py"
pause
goto MENU

:INSTALL
cls
call setup.bat
goto MENU

:TAG
cls
set /p tagfolder="Chemin du dossier MP3 : "
echo.
echo Tagging en cours (dates + genres)...
python scripts\add_release_date.py "%tagfolder%"
pause
goto MENU

:RENAME
cls
set /p renfolder="Chemin du dossier audio : "
echo.
set /p dryrun="Mode simulation ? (O/N) : "
if /i "%dryrun%"=="O" (
    echo Simulation du renommage...
    python scripts\rename_tracks.py "%renfolder%" --dry-run
) else (
    echo Renommage en cours...
    python scripts\rename_tracks.py "%renfolder%"
)
pause
goto MENU

:TAG_RENAME
cls
set /p trfolder="Chemin du dossier MP3 : "
echo.
set /p dryrun="Mode simulation pour le renommage ? (O/N) : "
if /i "%dryrun%"=="O" (
    echo Tagging + Renommage (simulation)...
    python scripts\add_release_date.py "%trfolder%" --rename --dry-run
) else (
    echo Tagging + Renommage...
    python scripts\add_release_date.py "%trfolder%" --rename
)
pause
goto MENU

:CLEANUP
cls
set /p cleanfolder="Chemin du dossier audio : "
echo.
set /p dryrun="Mode simulation ? (O/N) : "
if /i "%dryrun%"=="O" (
    echo Simulation du nettoyage...
    python scripts\cleanup_duplicates.py "%cleanfolder%" --dry-run
) else (
    echo Nettoyage en cours...
    python scripts\cleanup_duplicates.py "%cleanfolder%"
)
pause
goto MENU

:MULTI
cls
echo ===================================================
echo    SELECTION MULTIPLE DES OUTILS
echo ===================================================
echo.
set /p mfolder="Chemin du dossier : "
echo.
echo Quels outils voulez-vous executer ?
echo (Repondez O pour Oui, N pour Non)
echo.
set /p do_clean="1. Nettoyage doublons (O/N) : "
set /p do_tag="2. Tagging dates + genres (O/N) : "
set /p do_rename="3. Renommage des fichiers (O/N) : "
echo.
set /p dryrun="Mode simulation pour le renommage ? (O/N) : "
echo.

if /i "%do_clean%"=="O" (
    echo.
    echo --- Nettoyage des doublons ---
    python scripts\cleanup_duplicates.py "%mfolder%"
)

if /i "%do_tag%"=="O" (
    echo.
    echo --- Tagging dates + genres ---
    python scripts\add_release_date.py "%mfolder%"
)

if /i "%do_rename%"=="O" (
    echo.
    echo --- Renommage des fichiers ---
    if /i "%dryrun%"=="O" (
        python scripts\rename_tracks.py "%mfolder%" --dry-run
    ) else (
        python scripts\rename_tracks.py "%mfolder%"
    )
)

echo.
echo === Tous les outils selectionnes ont ete executes ===
pause
goto MENU

:PIPELINE
cls
echo ===================================================
echo    PIPELINE GLOBAL - TRAITEMENT COMPLET
echo ===================================================
echo.
set /p pipefolder="Chemin du dossier audio : "
echo.
set /p dryrun="Mode simulation ? (O/N) : "
echo.
set skip_flags=
set /p do_quality="Inclure l'analyse qualite ? (O/N) : "
if /i "%do_quality%"=="N" set skip_flags=%skip_flags% --skip-quality
set /p do_merge="Inclure la fusion des upgrades ? (O/N) : "
if /i "%do_merge%"=="N" set skip_flags=%skip_flags% --skip-merge
set /p do_ren="Inclure le renommage Shazam & Tagging ? (O/N) : "
if /i "%do_ren%"=="N" set skip_flags=%skip_flags% --skip-rename
set /p do_dup="Inclure le nettoyage doublons ? (O/N) : "
if /i "%do_dup%"=="N" set skip_flags=%skip_flags% --skip-dupes
echo.
if /i "%dryrun%"=="O" (
    echo Lancement du pipeline en simulation...
    python scripts\pipeline_musique.py "%pipefolder%" --dry-run %skip_flags%
) else (
    echo Lancement du pipeline...
    python scripts\pipeline_musique.py "%pipefolder%" %skip_flags%
)
pause
goto MENU

:END
exit
