"""
cleanup_duplicates.py
-----------------------
1. Supprime les fichiers audio de moins de 60 secondes (previsualisation SoundCloud etc.)
2. Supprime les doublons (meme artiste + meme titre, en comparant les tags ID3 et le nom de fichier)

Usage :
    python cleanup_duplicates.py "C:/Music/DJ/toutes les musique - Copie1 [HQ]"
    python cleanup_duplicates.py "C:/Music/DJ/toutes les musique - Copie1 [HQ]" --dry-run
"""

import os
import sys
import re
import json
import argparse
import subprocess
import unicodedata
import time
from checkpoint import CheckpointManager

# ─── Couleurs ANSI ─────────────────────────────────────────────────
class C:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BLUE   = '\033[94m'
    RESET  = '\033[0m'

# ─── Chemins ffprobe ───────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
FFPROBE = os.path.join(parent_dir, 'ffmpeg_local', 'ffprobe.exe') if os.name == 'nt' else 'ffprobe'
if not os.path.exists(FFPROBE):
    FFPROBE = 'ffprobe'

# ─── Helpers ───────────────────────────────────────────────────────
def normalize(text):
    """Normalise un texte pour la comparaison : minuscules, sans accents, sans ponctuation."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_duration(filepath):
    """Retourne la durée en secondes via ffprobe, ou None si erreur."""
    try:
        cmd = [
            FFPROBE, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json', filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception:
        return None

def get_id3_tags(filepath):
    """Retourne (artist, title) depuis les tags ID3, ou None si indisponible."""
    try:
        from mutagen.easyid3 import EasyID3
        tags = EasyID3(filepath)
        artist = tags.get('artist', [None])[0]
        title  = tags.get('title',  [None])[0]
        return artist, title
    except Exception:
        return None, None

def extract_artist_title_from_filename(filename):
    """Essaie d'extraire artiste et titre depuis 'Artiste - Titre.mp3'."""
    base = os.path.splitext(filename)[0]
    # Nettoyage des préfixes upgrade_
    base = re.sub(r'^upgrade_', '', base)
    parts = base.split(' - ', 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return '', base.strip()

def dedup_key(artist, title):
    """Clé normalisée pour comparaison de doublons."""
    return normalize(artist) + '::' + normalize(title)

# ─── MAIN ──────────────────────────────────────────────────────────
def run(directory, dry_run=False, min_duration=60):
    if not os.path.isdir(directory):
        print(f"{C.RED}Erreur: dossier inexistant : {directory}{C.RESET}")
        sys.exit(1)

    if dry_run:
        print(f"{C.YELLOW}⚠️  Mode simulation (--dry-run) : aucun fichier ne sera supprimé.{C.RESET}")

    print(f"\n{C.BLUE}=== Nettoyage : doublons & prévisualisations ==={C.RESET}")
    print(f"Dossier  : {directory}")
    print(f"Durée min: {min_duration}s\n")

    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'))
    ]

    # Checkpoint : pause/reprise
    mgr = CheckpointManager("cleanup_duplicates", directory)
    mgr.start()
    remaining = mgr.get_remaining_files(sorted(files))

    deleted_preview = 0
    deleted_dupes   = 0
    seen = {}  # key -> (filepath, size)

    try:
        for fp in remaining:
            # Pause synchrone
            while mgr.is_paused:
                time.sleep(0.3)

            fname = os.path.basename(fp)

            # ── 1. Vérification de la durée ──────────────────────────
            duration = get_duration(fp)
            if duration is None:
                print(f"{C.YELLOW}[?] Durée inconnue{C.RESET} {fname}")
            elif duration < min_duration:
                print(f"{C.RED}[❌ PREVIEW {duration:.0f}s]{C.RESET} {fname}")
                if not dry_run:
                    try:
                        os.remove(fp)
                        deleted_preview += 1
                    except Exception as e:
                        print(f"    └─ Erreur suppression: {e}")
                else:
                    deleted_preview += 1
                mgr.save_progress(fp)
                continue  # plus besoin de vérifier les doublons

            # ── 2. Récupération artiste / titre ──────────────────────
            artist, title = get_id3_tags(fp)
            if not artist or not title:
                artist, title = extract_artist_title_from_filename(fname)

            key = dedup_key(artist, title)

            if not key.strip('::'):
                # Pas de clé exploitable, on garde
                print(f"{C.YELLOW}[~] Clé vide, ignoré{C.RESET}  {fname}")
                mgr.save_progress(fp)
                continue

            if key in seen:
                prev_fp, prev_size = seen[key]
                cur_size = os.path.getsize(fp)

                # Garder le fichier le plus lourd (meilleure qualité)
                if cur_size >= prev_size:
                    # Le fichier précédent est le doublon
                    to_delete = prev_fp
                    seen[key] = (fp, cur_size)
                else:
                    to_delete = fp

                print(f"{C.RED}[❌ DOUBLON]{C.RESET} {os.path.basename(to_delete)}")
                print(f"    └─ Conservé : {os.path.basename(seen[key][0])}")

                if not dry_run:
                    try:
                        os.remove(to_delete)
                        deleted_dupes += 1
                    except Exception as e:
                        print(f"    └─ Erreur suppression: {e}")
                else:
                    deleted_dupes += 1
            else:
                seen[key] = (fp, os.path.getsize(fp))
                dur_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
                print(f"{C.GREEN}[✅ OK {dur_str}]{C.RESET} {fname}")

            mgr.save_progress(fp)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}⚠️  Interruption ! Progression sauvegardée dans .checkpoint.json{C.RESET}")
        mgr.stop()
        return

    # ─── Résumé ─────────────────────────────────────────────────
    print(f"\n{C.BLUE}=== Résumé ==={C.RESET}")
    print(f"  🗑️  Prévisualisations supprimées : {deleted_preview}")
    print(f"  🗑️  Doublons supprimés           : {deleted_dupes}")
    mode = "(simulation)" if dry_run else ""
    print(f"  ✅  Fichiers conservés           : {len(seen)} {mode}")

    mgr.finish()


if __name__ == '__main__':
    if os.name == 'nt':
        os.system('color')

    parser = argparse.ArgumentParser(description="Supprime prévisualisations (<60s) et doublons d'un dossier musical.")
    parser.add_argument('dossier', help="Dossier à nettoyer")
    parser.add_argument('--dry-run', action='store_true', help="Simulation : affiche sans supprimer")
    parser.add_argument('--min', type=int, default=60, help="Durée minimale en secondes (défaut: 60)")
    args = parser.parse_args()

    run(os.path.abspath(args.dossier), dry_run=args.dry_run, min_duration=args.min)
