# 🎵 Convertisseur & Bot Discord & Pipeline Musique

Une suite d'outils complète pour télécharger, identifier, nettoyer et convertir des musiques depuis **YouTube, SoundCloud, Spotify et Instagram**. Inclut un Bot Discord, un backend Web, et des scripts puissants d'organisation locale (`Pipeline`).

---

## ✨ Fonctionnalités Principales

### 1. ☁️ Le Bot Discord
- `!convert <url>` : Télécharge un post (YouTube, Insta, SoundCloud, Spotify) et l'envoie en MP3 sur Discord.
- **GoFile Cloud** : Si la musique dépasse la limite Discord (24 Mo), le bot l'uploade gratuitement sur GoFile et fournit le lien !

### 2. 🌍 L'Interface Web (FastAPI)
- **Design Moderne** : Glassmorphism, Dark mode et UI ultra rapide propulsée par FastAPI.
- **Convertisseur :** Entrez n'importe quelle URL, téléchargez en MP3 ou ZIP (pour les playlists).
- **Identifier :** Envoyez un fichier ou des timecodes d'une vidéo longue, laissez Shazam retrouver la chanson !
- **Mixer Spotify :** Assemblez plusieurs playlists Spotify en une seule en 1 clic.

### 3. 🛠️ Le Pipeline de Gestion Musicale (Les Scripts Locaux)
Gérez et nettoyez votre bibliothèque MP3 de façon automatisée en utilisant l'option `10` du menu `start.bat` (Pipeline global) :
- **Analyse de Qualité :** Scan vos fichiers (vrai 320kbps vs fake), supprime les mauvais rips, et les retélécharge automatiquement en Haute Qualité.
- **Fusion HQ :** Remplace intelligemment vos anciennes musiques par leurs nouvelles versions haute définition.
- **Renommage Intelligent & Tagging :** Écoute les musiques (Shazam), renomme les fichiers proprement en `Artiste - Titre.mp3`, et écrit les métadonnées ID3 (Genre et Année de sortie) compatibles avec Rekordbox/Serato (en utilisant iTunes/Spotify fallback).
- **Nettoyage des Doublons :** Détecte et supprime les extraits de 30 secondes et garde la meilleure copie de chaque chanson.

---

## 📋 Prérequis

*   **Windows :** Python 3.8+ (avec `Add Python to PATH`). L'outil ffmpeg sera téléchargé automatiquement !
*   **Linux :** `sudo apt install ffmpeg python3-venv` (le script `setup.sh` guide le reste).

---

## ⚙️ Configuration (Variables Sensibles)

Pour que toutes les APIs fonctionnent, vous devez configurer quelques éléments cruciaux sans jamais les partager (ils sont ignorés par GitHub grâce au `.gitignore`) :

1. **Fichier `.env`** (à créer à la racine du projet) :
    Ce fichier stocke vos identifiants pour Spotify et Discord.
    ```env
    # Pour le bot Discord
    DISCORD_TOKEN=votre_token_bot_ici

    # Pour Spotify (Tagging et Mixage de playlists)
    SPOTIFY_CLIENT_ID=votre_client_id_spotify
    SPOTIFY_CLIENT_SECRET=votre_client_secret_spotify
    ```

2. **Accès Haute Qualité SoundCloud** (Optionnel) :
    Pour télécharger des exclusivités SC GO+ en pipeline (et non des previews de 30s) :
    - Installez l'extension Chrome `Get cookies.txt LOCALLY`.
    - Allez sur SoundCloud.com (en étant connecté).
    - Exportez vos cookies et placez le fichier à la racine sous le nom exact : `soundcloud_cookies.txt`.

---

## 🚀 Installation & Lancement

### 🪟 Windows
1. Clonez ou téléchargez ce dépôt.
2. Double-cliquez sur `setup.bat` (Il va installer les modules de `requirements.txt`).
3. Double-cliquez sur `start.bat`. Un grand menu s'affichera proposant :
    - [1] Lancer le Serveur Web
    - [2] Lancer le Bot Discord
    - [10] Lancer le **Pipeline Global de musique** (Analyse, Renommage, Doublons)
    - Et bien plus...

### 🐧 Linux
```bash
git clone <url_du_repo> && cd conversion_musique
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

---

## 📂 Architecture Technique Principale

- `start.bat` / `start.sh` : Lanceurs tout-en-un avec Menu Interactif.
- `app.py` : Serveur FastAPI (Interface en `templates/index.html`).
- `bot.py` : Bot Discord avec contournement GoFile.
- `downloader.py` : Moteur asynchrone (yt-dlp) au cœur de tous les téléchargements.
- `scripts/pipeline_musique.py` : L'Orchestrateur du nettoyage de votre librairie.
- `scripts/clean_audio.py` : Module d'analyse de spectre audio (Qualité).
- `scripts/rename_tracks.py` : Module Shazam / Tagging ID3.
