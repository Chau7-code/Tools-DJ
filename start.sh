#!/bin/bash
# start.sh - Lanceur pour Armbian / Orange Pi

# S'assurer qu'on est dans le bon dossier
cd "$(dirname "$0")"

# Vérifier si l'environnement virtuel existe
if [ ! -d "venv" ]; then
    echo "L'environnement virtuel 'venv' n'existe pas."
    echo "Veuillez lancer ./setup.sh d'abord."
    exit 1
fi

PYTHON_BIN="./venv/bin/python"

show_menu() {
    clear
    echo "==================================================="
    echo "   CONVERTISSEUR MUSIQUE - MENU PRINCIPAL (LINUX)"
    echo "==================================================="
    echo ""
    echo "1. Lancer l'interface Web (app.py) au premier plan"
    echo "2. Lancer le Bot Discord (bot.py) au premier plan"
    echo "3. Lancer les DEUX en arrière-plan (via tmux)"
    echo "4. Voir les logs / Rejoindre la session tmux (si option 3 activée)"
    echo "5. Arrêter tout (Fermer la session tmux)"
    echo "6. Installer/Mettre à jour les dépendances"
    echo ""
    echo "--- Outils ---"
    echo "7.  Tagging dates + genres (add_release_date.py)"
    echo "8.  Renommer les fichiers (rename_tracks.py)"
    echo "9.  Tagging + Renommage combinés"
    echo "10. Nettoyage doublons (cleanup_duplicates.py)"
    echo "11. Choisir les outils à exécuter"
    echo "0.  Quitter"
    echo ""
    read -p "Votre choix : " choix
}

while true; do
    show_menu
    case $choix in
        1)
            clear
            echo "Lancement de l'interface Web..."
            echo "Ouvrez votre navigateur sur http://IP_DE_VOTRE_ORANGE_PI:5000"
            echo "Appuyez sur CTRL+C pour arrêter le serveur."
            echo ""
            $PYTHON_BIN app.py
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        2)
            clear
            echo "Lancement du Bot Discord..."
            echo "Assurez-vous d'avoir configuré votre token dans le fichier .env"
            echo "Appuyez sur CTRL+C pour arrêter le bot."
            echo ""
            $PYTHON_BIN bot.py
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        3)
            clear
            echo "Lancement de l'interface Web et du Bot dans tmux..."
            tmux new-session -d -s converthub -n "WebApp" "$PYTHON_BIN app.py"
            tmux new-window -t converthub -n "DiscordBot" "$PYTHON_BIN bot.py"
            echo "Les deux systèmes tournent en arrière-plan !"
            echo "Même si vous fermez ce terminal SSH, ils continueront de fonctionner."
            echo "Utilisez l'option 4 pour voir ce qu'il se passe."
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        4)
            clear
            echo "Vous allez être attaché à la session tmux."
            echo "Pour DÉTACHER (sortir sans arrêter les scripts) : Appuyez sur CTRL+B, puis relâchez et appuyez sur D"
            echo "Pour basculer entre Web et Bot : Appuyez sur CTRL+B, puis relâchez et appuyez sur N (Next)"
            echo "Appuyez sur Entrée pour rejoindre la session..."
            read
            tmux attach-session -t converthub || echo "Aucune session en cours. Lancez l'option 3 d'abord."
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        5)
            clear
            echo "Arrêt des processus en arrière-plan..."
            tmux kill-session -t converthub 2>/dev/null
            echo "Session arrêtée."
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        6)
            clear
            ./setup.sh
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        7)
            clear
            read -p "Chemin du dossier MP3 : " tagfolder
            echo ""
            echo "Tagging en cours (dates + genres)..."
            $PYTHON_BIN scripts/add_release_date.py "$tagfolder"
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        8)
            clear
            read -p "Chemin du dossier audio : " renfolder
            echo ""
            read -p "Mode simulation ? (O/N) : " dryrun
            if [[ "$dryrun" =~ ^[Oo]$ ]]; then
                echo "Simulation du renommage..."
                $PYTHON_BIN scripts/rename_tracks.py "$renfolder" --dry-run
            else
                echo "Renommage en cours..."
                $PYTHON_BIN scripts/rename_tracks.py "$renfolder"
            fi
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        9)
            clear
            read -p "Chemin du dossier MP3 : " trfolder
            echo ""
            read -p "Mode simulation pour le renommage ? (O/N) : " dryrun
            if [[ "$dryrun" =~ ^[Oo]$ ]]; then
                echo "Tagging + Renommage (simulation)..."
                $PYTHON_BIN scripts/add_release_date.py "$trfolder" --rename --dry-run
            else
                echo "Tagging + Renommage..."
                $PYTHON_BIN scripts/add_release_date.py "$trfolder" --rename
            fi
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        10)
            clear
            read -p "Chemin du dossier audio : " cleanfolder
            echo ""
            read -p "Mode simulation ? (O/N) : " dryrun
            if [[ "$dryrun" =~ ^[Oo]$ ]]; then
                echo "Simulation du nettoyage..."
                $PYTHON_BIN scripts/cleanup_duplicates.py "$cleanfolder" --dry-run
            else
                echo "Nettoyage en cours..."
                $PYTHON_BIN scripts/cleanup_duplicates.py "$cleanfolder"
            fi
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        11)
            clear
            echo "==================================================="
            echo "   SÉLECTION MULTIPLE DES OUTILS"
            echo "==================================================="
            echo ""
            read -p "Chemin du dossier : " mfolder
            echo ""
            echo "Quels outils voulez-vous exécuter ?"
            echo "(Répondez O pour Oui, N pour Non)"
            echo ""
            read -p "1. Nettoyage doublons (O/N) : " do_clean
            read -p "2. Tagging dates + genres (O/N) : " do_tag
            read -p "3. Renommage des fichiers (O/N) : " do_rename
            echo ""
            read -p "Mode simulation pour le renommage ? (O/N) : " dryrun
            echo ""

            if [[ "$do_clean" =~ ^[Oo]$ ]]; then
                echo ""
                echo "--- Nettoyage des doublons ---"
                $PYTHON_BIN scripts/cleanup_duplicates.py "$mfolder"
            fi

            if [[ "$do_tag" =~ ^[Oo]$ ]]; then
                echo ""
                echo "--- Tagging dates + genres ---"
                $PYTHON_BIN scripts/add_release_date.py "$mfolder"
            fi

            if [[ "$do_rename" =~ ^[Oo]$ ]]; then
                echo ""
                echo "--- Renommage des fichiers ---"
                if [[ "$dryrun" =~ ^[Oo]$ ]]; then
                    $PYTHON_BIN scripts/rename_tracks.py "$mfolder" --dry-run
                else
                    $PYTHON_BIN scripts/rename_tracks.py "$mfolder"
                fi
            fi

            echo ""
            echo "=== Tous les outils sélectionnés ont été exécutés ==="
            read -p "Appuyez sur Entrée pour continuer..."
            ;;
        0)
            exit 0
            ;;
        *)
            echo "Choix invalide."
            sleep 1
            ;;
    esac
done
