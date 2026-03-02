# 🎵 Antigravity Music (Convertisseur & Bot Discord)

Une solution asynchrone complète pour télécharger, identifier et convertir des musiques depuis **YouTube, SoundCloud, Spotify et Instagram**.

## ✨ Nouvelles Fonctionnalités Premium (Mise à jour 2026)

L'application a été entièrement réécrite pour des performances et une expérience utilisateur maximales :
- 🚀 **Backend FastAPI Asynchrone** : Fini les blocages ! Le backend gère désormais d'énormes charges de téléchargements via des tâches non-bloquantes (`asyncio`) et un système Server-Sent Events (SSE) natif.
- 🎨 **Nouvelle UI/UX Glassmorphism** : Interface ultra-moderne avec Tailwind CSS, "Dark Mode", effets de flou "Glass" et animations dynamiques, sans rechargement de page.
- 🛡️ **Sécurité & Anti-DDoS** : Toutes les clés API sont cachées, les limites de téléchargements par fichier (500Mo) et les nettoyeurs d'injections sont codés en dur.
- 🧹 **Nettoyage Automatique** : Le serveur purge en arrière-plan et silencieusement tous les anciens fichiers de plus de 2 heures.
- ☁️ **Contournement des Limites Discord (GoFile)** : Le Bot Discord détecte automatiquement si un fichier dépasse 24 Mo et l'envoie sur le cloud GoFile gratuitement avant de donner un lien direct, brisant la limite imposée par Discord.
- 🔍 **Identification Musicale Améliorée** : Écoute les timecodes via Shazam, puis nettoie intelligemment les titres par expressions régulières (Regex) en faisant des recherches progressives sur l'API Spotify (Stricte puis Souple) pour garantir un taux de trouvaille de presque 100%.

## 📋 Prérequis

*   **Python 3.8+** avec `pip` installé (Cochez "Add Python to PATH").
*   **FFmpeg** : Le script le télécharge tout seul sur Windows si vous ne l'avez pas.

## � Installation & Lancement

1.  Clonez ce dépôt.
2.  Double-cliquez sur `setup.bat` pour installer le nouvel écosystème FastAPI.
3.  Double-cliquez sur `start.bat` pour lancer le Serveur Web ou le Bot Discord au choix.

*Note : Pour le bot Discord, assurez-vous d'avoir renseigné `DISCORD_TOKEN` dans le fichier `.env`. Pour le mixage Spotify, remplissez `SPOTIPY_CLIENT_ID` et `SPOTIPY_CLIENT_SECRET` dans le `.env` ou directement sur l'interface web.*

## 🎮 Interface Web

Visitez http://127.0.0.1:5000.
- **Convertisseur :** Entrez l'URL, téléchargez en MP3 ou ZIP (pour les playlists).
- **Identifier :** Fournissez vos timecodes et laissez Shazam retrouver la chanson en téléchargeant le bon extrait de la vidéo/l'audio ! 
- **Mixer :** Assemblez plusieurs playlists Spotify en une seule playlist privée en 1 clic.

## 🤖 Devenir Administrateur du Bot Discord

-   `!convert <url>` -> Transforme n'importe quel post Youtube, Insta, SoundCloud, ou Spotify en MP3 natif ou lien GoFile si la musique est trop grosse !
-   Le Bot est programmé pour n'écouter que sur le salon textuel paramétré **`musique`**.

## � Structure Technique
- `app.py` -> Cœur du Serveur HTTP FastAPI.
- `bot.py` -> Cœur du Bot Discord Asynchrone.
- `downloader.py` -> Moteur d'extraction vidéo (yt-dlp), nettoyage de titre, API Spotify.
- `mellangeur.py` -> Traitement API Spotify.
- `templates/index.html` -> Moteur de rendu Frontend Tailwind CSS.
