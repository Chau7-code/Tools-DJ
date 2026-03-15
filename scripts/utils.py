"""
utils.py
--------
Module partagé pour tous les scripts de la pipeline musicale.
Contient les fonctions utilitaires, constantes et classes communes.
"""

import os
import re
import unicodedata


# ─── Couleurs ANSI ─────────────────────────────────────────────────
class C:
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    RED     = '\033[91m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    BOLD    = '\033[1m'
    RESET   = '\033[0m'


# ─── Constantes ────────────────────────────────────────────────────
AUDIO_EXT = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')


# ─── Chemins communs ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PARENT_DIR, 'data')

# FFmpeg / FFprobe
FFPROBE_PATH = 'ffprobe'
FFMPEG_PATH = 'ffmpeg'

if os.name == 'nt':
    FFPROBE_PATH = 'ffprobe.exe'
    FFMPEG_PATH = 'ffmpeg.exe'

_local_ffprobe = os.path.join(PARENT_DIR, 'ffmpeg_local', 'ffprobe.exe')
if os.path.exists(_local_ffprobe):
    FFPROBE_PATH = _local_ffprobe

_local_ffmpeg = os.path.join(PARENT_DIR, 'ffmpeg_local', 'ffmpeg.exe')
if os.path.exists(_local_ffmpeg):
    FFMPEG_PATH = _local_ffmpeg
    _ffmpeg_dir = os.path.dirname(_local_ffmpeg)
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] += os.pathsep + _ffmpeg_dir


# ─── Fonctions utilitaires ────────────────────────────────────────

def normalize(text):
    """Normalise un texte pour comparaison : minuscules, sans accents, sans ponctuation."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def sanitize_filename(name):
    """Supprime les caractères interdits dans un nom de fichier."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > 200:
        name = name[:200]
    return name


def limit_artists(artist_str, max_artists=2):
    """Limite le nombre d'artistes à max_artists (défaut: 2)."""
    if not artist_str:
        return artist_str
    parts = re.split(r'\s*,\s*|\s+&\s+|\s+feat\.?\s+|\s+ft\.?\s+|\s+x\s+', artist_str, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= max_artists:
        return artist_str
    return ', '.join(parts[:max_artists])


def count_audio_files(directory):
    """Compte les fichiers audio dans un dossier."""
    return sum(1 for f in os.listdir(directory) if f.lower().endswith(AUDIO_EXT))


def banner(step_num, title):
    """Affiche une bannière d'étape bien visible."""
    print(f"\n{'='*60}")
    print(f"  {C.BOLD}{C.CYAN}ÉTAPE {step_num}{C.RESET} — {C.BOLD}{title}{C.RESET}")
    print(f"{'='*60}\n")


def get_duration_ffprobe(filepath):
    """Retourne la durée en secondes via ffprobe, ou None si erreur."""
    import subprocess
    import json as _json
    try:
        cmd = [
            FFPROBE_PATH, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json', filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        data = _json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception:
        return None
