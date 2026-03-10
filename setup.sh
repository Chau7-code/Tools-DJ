#!/bin/bash
# setup.sh - Script d'installation pour Armbian / Orange Pi

echo "==================================================="
echo "   Installation des dépendances du projet (Linux)"
echo "==================================================="
echo ""

# Vérifier si on est en root (utile pour apt)
if [ "$EUID" -ne 0 ]; then
  echo "Il est recommandé de lancer ce script avec sudo la première fois"
  echo "pour l'installation des paquets système (apt)."
  echo "Commande : sudo ./setup.sh"
  echo "Ou appuyez sur Entrée pour continuer si les paquets système sont déjà installés..."
  read -r
fi

echo "1. Mise à jour et installation des paquets système..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg tmux

echo ""
echo "2. Création de l'environnement virtuel Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Environnement 'venv' créé."
else
    echo "L'environnement virtuel 'venv' existe déjà."
fi

echo ""
echo "3. Installation des bibliothèques Python..."
# Utilisation du pip de l'environnement virtuel
./venv/bin/python -m pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERREUR] Une erreur est survenue lors de l'installation."
    exit 1
fi

echo ""
echo "==================================================="
echo "   Installation terminée avec succès !"
echo "==================================================="
echo ""
echo "N'oubliez pas de rendre le fichier start.sh exécutable :"
echo "chmod +x start.sh"
echo ""
echo "Vous pouvez maintenant utiliser ./start.sh pour lancer le projet."
