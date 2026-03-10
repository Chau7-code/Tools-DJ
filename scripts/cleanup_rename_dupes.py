"""
cleanup_rename_dupes.py
-----------------------
Supprime les doublons créés par le script rename_tracks.py
et nettoie les suffixes song-N.

Le script de renommage peut créer des doublons :
  - Fichiers avec suffixes song-1, song-2 (même titre identifié par Shazam)
  - L'ancien fichier non renommé coexiste avec le nouveau nom propre
  - Variantes du même morceau (remix, feat., etc. identifiés pareil)

Logique :
  1. Regroupe les fichiers par clé normalisée (nom de fichier sans song-N)
  2. Quand un groupe a plusieurs fichiers, garde le MEILLEUR :
     - Plus gros fichier (meilleure qualité audio)
     - Préférence au fichier sans suffixe "song-N"
  3. Supprime les doublons inférieurs
  4. Renomme le fichier conservé en retirant le suffixe song-N

Usage :
    python scripts/cleanup_rename_dupes.py "C:/chemin/vers/musique"
    python scripts/cleanup_rename_dupes.py "C:/chemin/vers/musique" --dry-run
"""

import os
import sys
import re
import argparse
import unicodedata
from collections import defaultdict

# ─── Couleurs ANSI ─────────────────────────────────────────────────
class C:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BLUE   = '\033[94m'
    MAGENTA = '\033[95m'
    RESET  = '\033[0m'

AUDIO_EXT = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')


# ─── Helpers ───────────────────────────────────────────────────────

def normalize(text):
    """Normalise un texte pour comparaison : minuscules, sans accents, sans ponctuation."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def strip_song_suffix(name):
    """Retire le suffixe 'song-N' ajouté par rename_tracks.py."""
    return re.sub(r'\s*song-\d+$', '', name, flags=re.IGNORECASE).strip()


def has_song_suffix(name):
    """Vérifie si le nom contient un suffixe 'song-N'."""
    return bool(re.search(r'\s*song-\d+$', name, flags=re.IGNORECASE))


def extract_dedup_key(filename):
    """
    Extrait une clé de déduplication à partir du nom de fichier.
    Utilise UNIQUEMENT le nom de fichier (pas les tags ID3)
    pour que song-1 et song-2 soient toujours regroupés.
    """
    base = os.path.splitext(filename)[0]

    # Retirer le suffixe song-N pour la comparaison
    base_clean = strip_song_suffix(base)

    # Retirer préfixes courants (upgrade_, etc.)
    base_clean = re.sub(r'^upgrade_', '', base_clean, flags=re.IGNORECASE)

    return normalize(base_clean)


def pick_best_file(files_info):
    """
    Parmi une liste de (filepath, size, has_suffix), choisit le meilleur :
      1. Préférence au fichier SANS suffixe song-N
      2. À suffixe égal, garder le plus gros (meilleure qualité)
    Retourne (best, doublons_à_supprimer)
    """
    # Trier : sans suffixe d'abord, puis par taille décroissante
    sorted_files = sorted(files_info, key=lambda x: (x[2], -x[1]))
    best = sorted_files[0]
    to_delete = sorted_files[1:]
    return best, to_delete


# ─── Processus principal ────────────────────────────────────────────

def run(directory, dry_run=False):
    if not os.path.isdir(directory):
        print(f"{C.RED}Erreur: dossier inexistant : {directory}{C.RESET}")
        sys.exit(1)

    if dry_run:
        print(f"{C.YELLOW}⚠️  Mode simulation (--dry-run) : aucun fichier ne sera modifié.{C.RESET}")

    print(f"\n{C.BLUE}=== Nettoyage des doublons de renommage ==={C.RESET}")
    print(f"Dossier : {directory}\n")

    # Collecter tous les fichiers audio
    audio_files = []
    for f in os.listdir(directory):
        if f.lower().endswith(AUDIO_EXT):
            audio_files.append(os.path.join(directory, f))

    if not audio_files:
        print(f"{C.YELLOW}Aucun fichier audio trouvé.{C.RESET}")
        return

    print(f"Fichiers audio trouvés : {len(audio_files)}\n")

    # ─── Étape 1 : Regrouper par clé normalisée (NOM DE FICHIER uniquement) ──
    print(f"{C.BLUE}--- Analyse des fichiers ---{C.RESET}\n")

    groups = defaultdict(list)  # clé -> [(filepath, size, has_suffix)]

    for fp in sorted(audio_files):
        fname = os.path.basename(fp)
        base = os.path.splitext(fname)[0]
        size = os.path.getsize(fp)
        suffix = has_song_suffix(base)

        # Clé par nom de fichier UNIQUEMENT (pas ID3 — sinon song-1 et song-2
        # peuvent avoir des tags différents et ne pas être regroupés)
        key = extract_dedup_key(fname)

        if not key:
            print(f"  {C.YELLOW}[~] Clé vide, ignoré{C.RESET}  {fname}")
            continue

        groups[key].append((fp, size, suffix))

    # ─── Étape 2 : Supprimer les doublons + retirer les suffixes song-N ──
    print(f"\n{C.BLUE}--- Détection des doublons et nettoyage des suffixes ---{C.RESET}\n")

    total_deleted = 0
    total_renamed = 0
    total_kept = 0
    total_groups_with_dupes = 0

    for key, files_info in sorted(groups.items()):
        if len(files_info) == 1:
            # Pas de doublon — mais vérifier si le suffixe song-N doit être retiré
            fp, size, suffix = files_info[0]
            fname = os.path.basename(fp)
            size_mb = size / (1024 * 1024)

            if suffix:
                # Fichier seul avec un suffixe song-N → retirer le suffixe
                base = os.path.splitext(fname)[0]
                ext = os.path.splitext(fname)[1]
                clean_name = strip_song_suffix(base) + ext
                clean_path = os.path.join(directory, clean_name)

                # Vérifier que le nom propre n'existe pas déjà
                if os.path.exists(clean_path):
                    print(f"  {C.YELLOW}[⚠️  CONFLIT]{C.RESET} {fname} → {clean_name} existe déjà")
                    total_kept += 1
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

        # Renommer le fichier gardé en retirant le suffixe song-N
        if best_suffix:
            base = os.path.splitext(best_name)[0]
            ext = os.path.splitext(best_name)[1]
            clean_name = strip_song_suffix(base) + ext
            clean_path = os.path.join(directory, clean_name)

            # Vérifier que le nom propre n'existe pas déjà
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


# ─── Point d'entrée ──────────────────────────────────────────────

if __name__ == '__main__':
    if os.name == 'nt':
        os.system('color')

    parser = argparse.ArgumentParser(
        description="Supprime les doublons de renommage (song-1, song-2) et retire les suffixes."
    )
    parser.add_argument('dossier', help="Dossier contenant les fichiers audio")
    parser.add_argument('--dry-run', action='store_true',
                        help="Simulation : affiche sans modifier")
    args = parser.parse_args()

    run(os.path.abspath(args.dossier), dry_run=args.dry_run)
