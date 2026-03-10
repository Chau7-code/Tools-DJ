"""
pipeline_musique.py
--------------------
Script global qui orchestre toute la chaine de traitement musical :

  ÉTAPE 1 — Analyse qualité audio
    → Supprime les fichiers de mauvaise qualité (faux 320, rips YouTube)
    → Re-télécharge les fichiers supprimés en HQ (SoundCloud → YouTube)
    → Les fichiers HQ arrivent dans un dossier [HQ] séparé

  ÉTAPE 2 — Fusion des fichiers upgrade
    → Déplace les fichiers du dossier [HQ] vers le dossier principal
    → Quand un fichier upgrade_ existe, supprime l'ancien et garde l'upgrade
    → Renomme les upgrade_ en retirant le préfixe

  ÉTAPE 3 — Renommage intelligent & Tagging
    → Identifie chaque fichier via Shazam (+ iTunes/Spotify en fallback)
    → Renomme en format propre : Artiste - Titre.ext
    → Écrit les tags ID3 : genre + date de sortie
    → Les doublons reçoivent un suffixe song-1, song-2

  ÉTAPE 4 — Nettoyage des doublons
    → Détecte les fichiers avec le même artiste/titre
    → Garde le meilleur (plus gros, sans suffixe song-N)
    → Supprime les doublons et retire les suffixes song-N

Usage :
    python scripts/pipeline_musique.py "C:/chemin/vers/musique"
    python scripts/pipeline_musique.py "C:/chemin/vers/musique" --dry-run
    python scripts/pipeline_musique.py "C:/chemin/vers/musique" --skip-quality
    python scripts/pipeline_musique.py "C:/chemin/vers/musique" --skip-tags
"""

import os
import sys
import re
import shutil
import argparse
import asyncio
import unicodedata
from datetime import datetime

# ─── Setup des chemins ────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)


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

AUDIO_EXT = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')


def banner(step_num, title):
    """Affiche une bannière d'étape bien visible."""
    print(f"\n{'='*60}")
    print(f"  {C.BOLD}{C.CYAN}ÉTAPE {step_num}{C.RESET} — {C.BOLD}{title}{C.RESET}")
    print(f"{'='*60}\n")


def normalize(text):
    """Normalise un texte pour comparaison."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def count_audio_files(directory):
    """Compte les fichiers audio dans un dossier."""
    return sum(1 for f in os.listdir(directory) if f.lower().endswith(AUDIO_EXT))


# =====================================================================
#  ÉTAPE 1 : Analyse qualité + re-téléchargement HQ
# =====================================================================

def step1_quality_check(directory, dry_run=False):
    """Lance l'analyse qualité audio et le re-téléchargement."""
    banner(1, "Analyse qualité audio + re-téléchargement HQ")

    if dry_run:
        print(f"{C.YELLOW}⚠️  Mode simulation : l'analyse sera affichée mais rien ne sera supprimé.{C.RESET}")
        print(f"{C.YELLOW}   Le re-téléchargement sera aussi ignoré.{C.RESET}\n")

    try:
        from clean_audio import clean_audio_files
        if not dry_run:
            clean_audio_files(directory)
        else:
            # En dry-run on affiche juste les stats
            files = [f for f in os.listdir(directory) if f.lower().endswith(AUDIO_EXT)]
            print(f"  📊 {len(files)} fichiers audio trouvés dans le dossier")
            print(f"  {C.YELLOW}Simulation : analyse qualité ignorée en mode --dry-run{C.RESET}")
    except Exception as e:
        print(f"{C.RED}Erreur pendant l'analyse qualité : {e}{C.RESET}")

    print(f"\n{C.GREEN}✅ Étape 1 terminée.{C.RESET}")


# =====================================================================
#  ÉTAPE 2 : Fusion des fichiers upgrade (dossier [HQ] → principal)
# =====================================================================

def step2_merge_upgrades(directory, dry_run=False):
    """
    Fusionne les fichiers du dossier [HQ] dans le dossier principal.
    - Cherche le dossier [HQ] correspondant
    - Déplace les fichiers vers le dossier principal
    - Si un fichier avec le même nom (sans upgrade_) existe, supprime l'ancien
    - Retire le préfixe upgrade_ des fichiers déplacés
    """
    banner(2, "Fusion des fichiers upgrade")

    # Chercher le dossier [HQ]
    parent = os.path.dirname(directory)
    folder_name = os.path.basename(directory)
    hq_dir = os.path.join(parent, f"{folder_name} [HQ]")

    # Chercher aussi dans le dossier lui-même (sous-dossier [HQ])
    hq_dir_inside = os.path.join(directory, "[HQ]")

    actual_hq_dir = None
    if os.path.isdir(hq_dir):
        actual_hq_dir = hq_dir
    elif os.path.isdir(hq_dir_inside):
        actual_hq_dir = hq_dir_inside

    merged = 0
    replaced = 0
    cleaned_prefix = 0

    # ─── Partie A : Fusionner depuis le dossier [HQ] ─────────────
    if actual_hq_dir:
        hq_files = [f for f in os.listdir(actual_hq_dir) if f.lower().endswith(AUDIO_EXT)]
        print(f"📂 Dossier [HQ] trouvé : {actual_hq_dir}")
        print(f"   {len(hq_files)} fichier(s) à fusionner\n")

        for fname in sorted(hq_files):
            src = os.path.join(actual_hq_dir, fname)
            dst = os.path.join(directory, fname)

            # Chercher si un fichier similaire existe déjà (sans upgrade_)
            base_clean = re.sub(r'^upgrade_', '', fname, flags=re.IGNORECASE)
            existing = os.path.join(directory, base_clean)

            if os.path.exists(existing) and normalize(base_clean) != normalize(fname):
                action = "SIMULATION" if dry_run else "REMPLACÉ"
                print(f"  {C.RED}[🔄 {action}]{C.RESET} {base_clean}")
                print(f"    └─ par {C.GREEN}{fname}{C.RESET} (version HQ)")
                if not dry_run:
                    try:
                        os.remove(existing)
                        replaced += 1
                    except Exception as e:
                        print(f"    └─ {C.RED}Erreur suppression ancien : {e}{C.RESET}")

            action = "SIMULATION" if dry_run else "DÉPLACÉ"
            print(f"  {C.GREEN}[📦 {action}]{C.RESET} {fname} → dossier principal")

            if not dry_run:
                try:
                    shutil.move(src, dst)
                    merged += 1
                except Exception as e:
                    print(f"    └─ {C.RED}Erreur déplacement : {e}{C.RESET}")
            else:
                merged += 1

        # Supprimer le dossier [HQ] s'il est vide
        if not dry_run and actual_hq_dir:
            remaining = os.listdir(actual_hq_dir)
            if not remaining:
                try:
                    os.rmdir(actual_hq_dir)
                    print(f"\n  {C.GREEN}🗑️  Dossier [HQ] vide supprimé.{C.RESET}")
                except Exception:
                    pass
    else:
        print(f"  {C.YELLOW}Aucun dossier [HQ] trouvé, étape ignorée.{C.RESET}")
        print(f"  (Recherché : {hq_dir})")

    # ─── Partie B : Nettoyer les fichiers upgrade_ dans le dossier ─
    print(f"\n{C.BLUE}--- Nettoyage des préfixes upgrade_ ---{C.RESET}\n")

    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith(AUDIO_EXT):
            continue
        if not fname.lower().startswith('upgrade_'):
            continue

        src = os.path.join(directory, fname)
        clean_name = re.sub(r'^upgrade_', '', fname, flags=re.IGNORECASE)
        dst = os.path.join(directory, clean_name)

        # Supprimer l'ancien fichier sans préfixe s'il existe
        if os.path.exists(dst):
            old_size = os.path.getsize(dst)
            new_size = os.path.getsize(src)

            if new_size >= old_size:
                # Le fichier upgrade est meilleur ou égal → supprimer l'ancien
                action = "SIMULATION" if dry_run else "SUPPRIMÉ"
                old_mb = old_size / (1024 * 1024)
                new_mb = new_size / (1024 * 1024)
                print(f"  {C.RED}[❌ {action}]{C.RESET} {clean_name} ({old_mb:.1f} Mo)")
                print(f"    └─ Remplacé par {C.GREEN}upgrade_{clean_name} ({new_mb:.1f} Mo){C.RESET}")
                if not dry_run:
                    try:
                        os.remove(dst)
                    except Exception as e:
                        print(f"    └─ {C.RED}Erreur : {e}{C.RESET}")
                        continue
            else:
                # L'ancien est plus gros → garder l'ancien, supprimer l'upgrade
                action = "SIMULATION" if dry_run else "SUPPRIMÉ"
                print(f"  {C.YELLOW}[⚠️  {action}]{C.RESET} upgrade_{clean_name} (plus petit que l'original)")
                if not dry_run:
                    try:
                        os.remove(src)
                    except Exception as e:
                        print(f"    └─ {C.RED}Erreur : {e}{C.RESET}")
                cleaned_prefix += 1
                continue

        # Renommer sans le préfixe upgrade_
        action = "SIMULATION" if dry_run else "RENOMMÉ"
        print(f"  {C.GREEN}[✏️  {action}]{C.RESET} upgrade_{clean_name} → {clean_name}")
        if not dry_run:
            try:
                os.rename(src, dst)
                cleaned_prefix += 1
            except Exception as e:
                print(f"    └─ {C.RED}Erreur : {e}{C.RESET}")
        else:
            cleaned_prefix += 1

    # Résumé
    mode = " (simulation)" if dry_run else ""
    print(f"\n  📊 Fichiers fusionnés depuis [HQ]{mode} : {merged}")
    print(f"  🔄 Anciens fichiers remplacés{mode}     : {replaced}")
    print(f"  ✏️  Préfixes upgrade_ nettoyés{mode}     : {cleaned_prefix}")
    print(f"\n{C.GREEN}✅ Étape 2 terminée.{C.RESET}")


# =====================================================================
#  ÉTAPE 3 : Renommage intelligent (Shazam + iTunes + Spotify)
# =====================================================================

def step3_rename(directory, dry_run=False):
    """Lance le renommage via Shazam/iTunes/Spotify."""
    banner(3, "Renommage intelligent (Shazam → iTunes → Spotify)")

    try:
        from rename_tracks import run as rename_run

        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(rename_run(directory, dry_run=dry_run))
    except Exception as e:
        print(f"{C.RED}Erreur pendant le renommage : {e}{C.RESET}")

    print(f"\n{C.GREEN}✅ Étape 3 terminée.{C.RESET}")


# =====================================================================
#  ÉTAPE 4 : Nettoyage des doublons (song-N, mêmes titres, etc.)
# =====================================================================

def step4_cleanup_dupes(directory, dry_run=False):
    """
    Lance le nettoyage des doublons en deux passes :
      1. cleanup_duplicates.py : supprime prévisualisations + doublons généraux
      2. cleanup_rename_dupes.py : nettoie les doublons spécifiques au renommage
    """
    banner(4, "Nettoyage des doublons")

    # Passe 1 : Doublons généraux + prévisualisations
    print(f"{C.BLUE}--- Passe 1 : Prévisualisations + doublons généraux ---{C.RESET}\n")
    try:
        from cleanup_duplicates import run as cleanup_run
        cleanup_run(directory, dry_run=dry_run)
    except Exception as e:
        print(f"{C.RED}Erreur pendant le nettoyage général : {e}{C.RESET}")

    print()

    # Passe 2 : Doublons de renommage (song-N)
    print(f"{C.BLUE}--- Passe 2 : Doublons de renommage (song-N) ---{C.RESET}\n")
    try:
        from cleanup_rename_dupes import run as rename_dupes_run
        rename_dupes_run(directory, dry_run=dry_run)
    except Exception as e:
        print(f"{C.RED}Erreur pendant le nettoyage des doublons de renommage : {e}{C.RESET}")

    print(f"\n{C.GREEN}✅ Étape 4 terminée.{C.RESET}")


# =====================================================================
#  ORCHESTRATEUR PRINCIPAL
# =====================================================================

def run_pipeline(directory, dry_run=False, skip_quality=False, skip_rename=False,
                 skip_merge=False, skip_dupes=False):
    """
    Orchestre toute la chaine de traitement.
    """
    start_time = datetime.now()

    print(f"\n{'='*60}")
    print(f"  {C.BOLD}{C.CYAN}🎵 PIPELINE MUSIQUE — TRAITEMENT GLOBAL 🎵{C.RESET}")
    print(f"{'='*60}")
    print(f"\n  📂 Dossier : {directory}")
    print(f"  📊 Fichiers audio : {count_audio_files(directory)}")
    print(f"  🔧 Mode : {'SIMULATION' if dry_run else 'RÉEL'}")

    steps = []
    if not skip_quality:
        steps.append("1. Analyse qualité + re-téléchargement HQ")
    if not skip_merge:
        steps.append("2. Fusion des fichiers upgrade")
    if not skip_rename:
        steps.append("3. Renommage intelligent & Tagging (Shazam)")
    if not skip_dupes:
        steps.append("4. Nettoyage des doublons")

    print(f"\n  📋 Étapes prévues :")
    for s in steps:
        print(f"     {s}")
    print()

    # ─── Exécution des étapes ──────────────────────────────────
    if not skip_quality:
        step1_quality_check(directory, dry_run)

    if not skip_merge:
        step2_merge_upgrades(directory, dry_run)

    if not skip_rename:
        step3_rename(directory, dry_run)

    if not skip_dupes:
        step4_cleanup_dupes(directory, dry_run)

    # ─── Résumé final ──────────────────────────────────────────
    elapsed = datetime.now() - start_time
    minutes = int(elapsed.total_seconds() // 60)
    seconds = int(elapsed.total_seconds() % 60)

    final_count = count_audio_files(directory)

    print(f"\n{'='*60}")
    print(f"  {C.BOLD}{C.GREEN}🎉 PIPELINE TERMINÉ !{C.RESET}")
    print(f"{'='*60}")
    print(f"\n  ⏱️  Durée totale : {minutes}m {seconds}s")
    print(f"  📊 Fichiers audio restants : {final_count}")
    if dry_run:
        print(f"  ⚠️  Mode simulation — aucune modification effectuée")
    print()


# ─── Point d'entrée ──────────────────────────────────────────────

if __name__ == '__main__':
    if os.name == 'nt':
        os.system('color')

    parser = argparse.ArgumentParser(
        description="Pipeline global : qualité → upgrade → renommage → tagging → doublons",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection"
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection" --dry-run
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection" --skip-quality
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection" --skip-quality --skip-rename
        """
    )
    parser.add_argument('dossier', help="Dossier contenant les fichiers audio")
    parser.add_argument('--dry-run', action='store_true',
                        help="Simulation : affiche tout sans modifier les fichiers")
    parser.add_argument('--skip-quality', action='store_true',
                        help="Ignorer l'étape 1 (analyse qualité + re-téléchargement)")
    parser.add_argument('--skip-merge', action='store_true',
                        help="Ignorer l'étape 2 (fusion des fichiers upgrade)")
    parser.add_argument('--skip-rename', action='store_true',
                        help="Ignorer l'étape 3 (renommage Shazam & Tagging)")
    parser.add_argument('--skip-dupes', action='store_true',
                        help="Ignorer l'étape 4 (nettoyage doublons)")
    args = parser.parse_args()

    target = os.path.abspath(args.dossier)
    if not os.path.isdir(target):
        print(f"{C.RED}Erreur: dossier inexistant : {target}{C.RESET}")
        sys.exit(1)

    run_pipeline(
        target,
        dry_run=args.dry_run,
        skip_quality=args.skip_quality,
        skip_rename=args.skip_rename,
        skip_merge=args.skip_merge,
        skip_dupes=args.skip_dupes
    )
