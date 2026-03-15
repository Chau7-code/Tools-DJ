"""
cleanup_all_dupes.py
--------------------
Script unifié de nettoyage des doublons (fusion de cleanup_duplicates.py + cleanup_rename_dupes.py).

Logique en un seul passage :
  1. Regroupe les fichiers par clé normalisée (tags ID3 OU nom de fichier)
  2. Quand un groupe a plusieurs fichiers, garde le MEILLEUR :
     - Plus gros fichier (meilleure qualité audio)
     - Préférence au fichier sans suffixe "song-N"
  3. Supprime les doublons inférieurs
  4. Retire les suffixes song-N orphelins

Note : La vérification durée < 60s est maintenant intégrée dans clean_audio.py (étape 1).

Usage :
    python scripts/cleanup_all_dupes.py "C:/chemin/vers/musique"
    python scripts/cleanup_all_dupes.py "C:/chemin/vers/musique" --dry-run
"""

import os
import sys
import re
import argparse
import time
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from checkpoint import CheckpointManager
from utils import C, normalize, AUDIO_EXT


# ─── Helpers ───────────────────────────────────────────────────────

def strip_song_suffix(name):
    """Retire le suffixe 'song-N' ajouté par rename_tracks.py."""
    return re.sub(r'\s*song-\d+$', '', name, flags=re.IGNORECASE).strip()


def has_song_suffix(name):
    """Vérifie si le nom contient un suffixe 'song-N'."""
    return bool(re.search(r'\s*song-\d+$', name, flags=re.IGNORECASE))


def get_id3_tags(filepath):
    """Retourne (artist, title) depuis les tags ID3, ou (None, None)."""
    try:
        from mutagen.easyid3 import EasyID3
        tags = EasyID3(filepath)
        artist = tags.get('artist', [None])[0]
        title  = tags.get('title',  [None])[0]
        return artist, title
    except Exception:
        return None, None


def extract_artist_title_from_filename(filename):
    """Extrait artiste et titre depuis 'Artiste - Titre.ext'."""
    base = os.path.splitext(filename)[0]
    base = re.sub(r'^upgrade_', '', base)
    base = strip_song_suffix(base)
    parts = base.split(' - ', 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return '', base.strip()


def dedup_key(artist, title):
    """Clé normalisée pour comparaison de doublons."""
    a = normalize(artist)
    t = normalize(title)
    return f"{a}::{t}" if a or t else ''


def pick_best_file(files_info):
    """
    Parmi une liste de (filepath, size, has_suffix), choisit le meilleur :
      1. Préférence au fichier SANS suffixe song-N
      2. À suffixe égal, garder le plus gros (meilleure qualité)
    Retourne (best, doublons_à_supprimer)
    """
    sorted_files = sorted(files_info, key=lambda x: (x[2], -x[1]))
    best = sorted_files[0]
    to_delete = sorted_files[1:]
    return best, to_delete


# ─── MAIN ──────────────────────────────────────────────────────────

def run(directory, dry_run=False):
    if not os.path.isdir(directory):
        print(f"{C.RED}Erreur: dossier inexistant : {directory}{C.RESET}")
        sys.exit(1)

    if dry_run:
        print(f"{C.YELLOW}⚠️  Mode simulation (--dry-run) : aucun fichier ne sera modifié.{C.RESET}")

    print(f"\n{C.BLUE}=== Nettoyage unifié : doublons + suffixes song-N ==={C.RESET}")
    print(f"Dossier : {directory}\n")

    # Collecter tous les fichiers audio
    audio_files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(AUDIO_EXT)
    ]

    if not audio_files:
        print(f"{C.YELLOW}Aucun fichier audio trouvé.{C.RESET}")
        return

    print(f"Fichiers audio trouvés : {len(audio_files)}\n")

    # Checkpoint : pause/reprise
    mgr = CheckpointManager("cleanup_all_dupes", directory)
    mgr.start()

    # ─── Étape 1 : Regrouper par clé normalisée ──────────────────
    print(f"{C.BLUE}--- Analyse des fichiers ---{C.RESET}\n")

    groups = defaultdict(list)  # clé -> [(filepath, size, has_suffix)]

    for fp in sorted(audio_files):
        fname = os.path.basename(fp)
        base = os.path.splitext(fname)[0]
        size = os.path.getsize(fp)
        suffix = has_song_suffix(base)

        # Essayer d'abord les tags ID3
        artist, title = get_id3_tags(fp)
        if artist and title:
            key = dedup_key(artist, strip_song_suffix(title))
        else:
            # Fallback sur le nom de fichier
            artist, title = extract_artist_title_from_filename(fname)
            key = dedup_key(artist, title)

        if not key or key == '::':
            print(f"  {C.YELLOW}[~] Clé vide, ignoré{C.RESET}  {fname}")
            continue

        groups[key].append((fp, size, suffix))

    # ─── Étape 2 : Supprimer doublons + retirer suffixes song-N ──
    print(f"\n{C.BLUE}--- Détection des doublons et nettoyage ---{C.RESET}\n")

    total_deleted = 0
    total_renamed = 0
    total_kept = 0
    total_groups_with_dupes = 0

    try:
        for key, files_info in sorted(groups.items()):
            # Pause synchrone
            while mgr.is_paused:
                time.sleep(0.3)

            if len(files_info) == 1:
                # Pas de doublon — mais vérifier si le suffixe song-N doit être retiré
                fp, size, suffix = files_info[0]
                fname = os.path.basename(fp)
                size_mb = size / (1024 * 1024)

                if suffix:
                    base = os.path.splitext(fname)[0]
                    ext = os.path.splitext(fname)[1]
                    clean_name = strip_song_suffix(base) + ext
                    clean_path = os.path.join(directory, clean_name)

                    if os.path.exists(clean_path):
                        print(f"  {C.YELLOW}[⚠️  CONFLIT]{C.RESET} {fname} → {clean_name} existe déjà")
                        total_kept += 1
                        mgr.save_progress(fp)
                        continue

                    action = "SIMULATION" if dry_run else "RENOMMÉ"
                    print(f"  {C.GREEN}[✏️  {action}]{C.RESET} {fname} → {clean_name} ({size_mb:.1f} Mo)")

                    if not dry_run:
                        try:
                            os.rename(fp, clean_path)
                            total_renamed += 1
                        except Exception as e:
                            print(f"    └─ {C.RED}Erreur: {e}{C.RESET}")
                    else:
                        total_renamed += 1
                else:
                    print(f"  {C.GREEN}[✅ OK]{C.RESET} {fname} ({size_mb:.1f} Mo)")

                total_kept += 1
                mgr.save_progress(fp)
                continue

            # ─── Doublons détectés ! ──────────────────────────────────
            total_groups_with_dupes += 1
            best, to_delete = pick_best_file(files_info)
            best_fp, best_size, best_suffix = best

            best_name = os.path.basename(best_fp)
            best_mb = best_size / (1024 * 1024)

            print(f"  {C.MAGENTA}[🔄 DOUBLONS x{len(files_info)}]{C.RESET} Clé: \"{key[:60]}\"")

            # Supprimer les doublons
            for dup_fp, dup_size, dup_suffix in to_delete:
                dup_name = os.path.basename(dup_fp)
                dup_mb = dup_size / (1024 * 1024)
                action = "SIMULATION" if dry_run else "SUPPRIMÉ"

                print(f"    └─ {C.RED}❌ {action}: {dup_name} ({dup_mb:.1f} Mo){C.RESET}")

                if not dry_run:
                    try:
                        os.remove(dup_fp)
                        total_deleted += 1
                    except Exception as e:
                        print(f"       └─ {C.RED}Erreur: {e}{C.RESET}")
                else:
                    total_deleted += 1

                mgr.save_progress(dup_fp)

            # Renommer le fichier gardé en retirant le suffixe song-N
            if best_suffix:
                base = os.path.splitext(best_name)[0]
                ext = os.path.splitext(best_name)[1]
                clean_name = strip_song_suffix(base) + ext
                clean_path = os.path.join(directory, clean_name)

                if os.path.exists(clean_path) and clean_path != best_fp:
                    print(f"    └─ {C.YELLOW}⚠️  {best_name} garderait son suffixe (conflit nom){C.RESET}")
                    print(f"    └─ {C.GREEN}✅ GARDÉ : {best_name} ({best_mb:.1f} Mo){C.RESET}")
                else:
                    action = "SIMULATION" if dry_run else "RENOMMÉ"
                    print(f"    └─ {C.GREEN}✅ GARDÉ + {action} : {best_name} → {clean_name} ({best_mb:.1f} Mo){C.RESET}")
                    if not dry_run:
                        try:
                            os.rename(best_fp, clean_path)
                            total_renamed += 1
                        except Exception as e:
                            print(f"       └─ {C.RED}Erreur renommage: {e}{C.RESET}")
                    else:
                        total_renamed += 1
            else:
                print(f"    └─ {C.GREEN}✅ GARDÉ : {best_name} ({best_mb:.1f} Mo){C.RESET}")

            total_kept += 1
            mgr.save_progress(best_fp)

    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}⚠️  Interruption ! Progression sauvegardée dans .checkpoint.json{C.RESET}")
        mgr.stop()
        return

    # ─── Résumé ─────────────────────────────────────────────────
    mode = " (simulation)" if dry_run else ""
    print(f"\n{C.BLUE}=== Résumé ==={C.RESET}")
    print(f"  📊 Fichiers analysés          : {len(audio_files)}")
    print(f"  🔄 Groupes avec doublons      : {total_groups_with_dupes}")
    print(f"  🗑️  Doublons supprimés{mode}    : {total_deleted}")
    print(f"  ✏️  Suffixes song-N retirés{mode}: {total_renamed}")
    print(f"  ✅ Fichiers conservés          : {total_kept}")

    if (total_deleted > 0 or total_renamed > 0) and not dry_run:
        print(f"\n  {C.GREEN}💾 Nettoyage terminé avec succès !{C.RESET}")
    elif total_deleted == 0 and total_renamed == 0:
        print(f"\n  {C.GREEN}✨ Aucun doublon ni suffixe à nettoyer !{C.RESET}")

    mgr.finish()


# ─── Point d'entrée ──────────────────────────────────────────────

if __name__ == '__main__':
    if os.name == 'nt':
        os.system('color')

    parser = argparse.ArgumentParser(
        description="Nettoyage unifié : supprime les doublons et retire les suffixes song-N."
    )
    parser.add_argument('dossier', help="Dossier contenant les fichiers audio")
    parser.add_argument('--dry-run', action='store_true',
                        help="Simulation : affiche sans modifier")
    args = parser.parse_args()

    run(os.path.abspath(args.dossier), dry_run=args.dry_run)
