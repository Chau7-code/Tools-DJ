"""
pipeline_musique.py
--------------------
Script global qui orchestre toute la chaine de traitement musical :

  ÉTAPE 1 — Analyse qualité audio + Cleanup
    → Supprime les prévisualisations < 60s
    → Supprime les fichiers de mauvaise qualité (faux 320, rips YouTube)
    → Re-télécharge les fichiers supprimés en HQ directement dans le dossier
    → Nettoyage des préfixes upgrade_ (sous-étape)

  ÉTAPE 2 — Identification + Renommage + Tags + Dedup
    → Identifie chaque fichier via Shazam (+ iTunes/Spotify en fallback)
    → Utilise le cache Shazam pour éviter les doubles identifications
    → Renomme en format propre : Artiste - Titre.ext
    → Écrit les tags ID3 : genre + date de sortie
    → Supprime les doublons + nettoie les suffixes song-N

Usage :
    python scripts/pipeline_musique.py "C:/chemin/vers/musique"
    python scripts/pipeline_musique.py "C:/chemin/vers/musique" --dry-run
    python scripts/pipeline_musique.py "C:/chemin/vers/musique" --skip-quality
    python scripts/pipeline_musique.py "C:/chemin/vers/musique" --skip-rename
"""

import os
import sys
import re
import argparse
import asyncio
from datetime import datetime

# ─── Setup des chemins ────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from utils import C, AUDIO_EXT, count_audio_files, banner


# =====================================================================
#  ÉTAPE 1 : Analyse qualité + Preview cleanup + Re-téléchargement HQ
# =====================================================================

def step1_quality_check(directory, dry_run=False):
    """Lance l'analyse qualité audio et le re-téléchargement."""
    banner(1, "Analyse qualité audio + Cleanup + Re-téléchargement HQ")

    if dry_run:
        print(f"{C.YELLOW}⚠️  Mode simulation : l'analyse sera affichée mais rien ne sera supprimé.{C.RESET}")
        print(f"{C.YELLOW}   Le re-téléchargement sera aussi ignoré.{C.RESET}\n")

    try:
        from clean_audio import clean_audio_files
        if not dry_run:
            clean_audio_files(directory)
        else:
            files = [f for f in os.listdir(directory) if f.lower().endswith(AUDIO_EXT)]
            print(f"  📊 {len(files)} fichiers audio trouvés dans le dossier")
            print(f"  {C.YELLOW}Simulation : analyse qualité ignorée en mode --dry-run{C.RESET}")
    except Exception as e:
        print(f"{C.RED}Erreur pendant l'analyse qualité : {e}{C.RESET}")

    print(f"\n{C.GREEN}✅ Étape 1 terminée.{C.RESET}")


def step1b_cleanup_upgrades(directory, dry_run=False):
    """
    Sous-étape : nettoie les préfixes upgrade_ dans le dossier principal.
    Les fichiers HQ sont maintenant téléchargés directement dans le dossier
    avec un préfixe upgrade_. On doit :
      - Si un fichier sans préfixe existe, comparer les tailles
      - Garder le meilleur, supprimer l'autre
      - Renommer en retirant le préfixe upgrade_
    """
    print(f"\n{C.BLUE}--- Nettoyage des préfixes upgrade_ ---{C.RESET}\n")

    cleaned = 0
    replaced = 0

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
                        replaced += 1
                    except Exception as e:
                        print(f"    └─ {C.RED}Erreur : {e}{C.RESET}")
                        continue
                else:
                    replaced += 1
            else:
                # L'ancien est plus gros → garder l'ancien, supprimer l'upgrade
                action = "SIMULATION" if dry_run else "SUPPRIMÉ"
                print(f"  {C.YELLOW}[⚠️  {action}]{C.RESET} upgrade_{clean_name} (plus petit que l'original)")
                if not dry_run:
                    try:
                        os.remove(src)
                    except Exception as e:
                        print(f"    └─ {C.RED}Erreur : {e}{C.RESET}")
                continue

        # Renommer sans le préfixe upgrade_
        action = "SIMULATION" if dry_run else "RENOMMÉ"
        print(f"  {C.GREEN}[✏️  {action}]{C.RESET} {fname} → {clean_name}")
        if not dry_run:
            try:
                os.rename(src, dst)
                cleaned += 1
            except Exception as e:
                print(f"    └─ {C.RED}Erreur : {e}{C.RESET}")
        else:
            cleaned += 1

    if cleaned == 0 and replaced == 0:
        print(f"  {C.GREEN}✨ Aucun fichier upgrade_ à traiter.{C.RESET}")
    else:
        mode = " (simulation)" if dry_run else ""
        print(f"\n  ✏️  Préfixes nettoyés{mode} : {cleaned}")
        print(f"  🔄 Anciens remplacés{mode}  : {replaced}")


# =====================================================================
#  ÉTAPE 2 : Identification + Renommage + Tags + Dedup
# =====================================================================

def step2_rename(directory, dry_run=False):
    """Lance le renommage via Shazam/iTunes/Spotify (avec cache)."""
    banner(2, "Identification + Renommage (Shazam → iTunes → Spotify)")

    try:
        from rename_tracks import run as rename_run

        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(rename_run(directory, dry_run=dry_run))
    except Exception as e:
        print(f"{C.RED}Erreur pendant le renommage : {e}{C.RESET}")

    print(f"\n{C.GREEN}✅ Renommage terminé.{C.RESET}")


def step2b_cleanup_dupes(directory, dry_run=False):
    """Lance le nettoyage unifié des doublons."""
    print(f"\n{C.BLUE}--- Nettoyage des doublons ---{C.RESET}\n")

    try:
        from cleanup_all_dupes import run as cleanup_run
        cleanup_run(directory, dry_run=dry_run)
    except Exception as e:
        print(f"{C.RED}Erreur pendant le nettoyage des doublons : {e}{C.RESET}")

    print(f"\n{C.GREEN}✅ Étape 2 terminée.{C.RESET}")


# =====================================================================
#  ORCHESTRATEUR PRINCIPAL
# =====================================================================

def run_pipeline(directory, dry_run=False, skip_quality=False, skip_rename=False,
                 skip_dupes=False):
    """
    Orchestre toute la chaine de traitement en 2 étapes.
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
        steps.append("1. Analyse qualité + Cleanup + Re-téléchargement HQ")
        steps.append("   └─ Nettoyage des préfixes upgrade_")
    if not skip_rename:
        steps.append("2. Identification + Renommage + Tags (Shazam)")
    if not skip_dupes:
        steps.append("   └─ Nettoyage des doublons + suffixes song-N")

    print(f"\n  📋 Étapes prévues :")
    for s in steps:
        print(f"     {s}")
    print()

    # ─── Exécution des étapes ──────────────────────────────────
    if not skip_quality:
        step1_quality_check(directory, dry_run)
        step1b_cleanup_upgrades(directory, dry_run)

    if not skip_rename:
        step2_rename(directory, dry_run)

    if not skip_dupes:
        step2b_cleanup_dupes(directory, dry_run)

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
        description="Pipeline global : qualité → renommage → tagging → doublons",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection"
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection" --dry-run
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection" --skip-quality
  python scripts/pipeline_musique.py "C:/Music/DJ/ma_collection" --skip-rename
        """
    )
    parser.add_argument('dossier', help="Dossier contenant les fichiers audio")
    parser.add_argument('--dry-run', action='store_true',
                        help="Simulation : affiche tout sans modifier les fichiers")
    parser.add_argument('--skip-quality', action='store_true',
                        help="Ignorer l'étape 1 (analyse qualité + re-téléchargement)")
    parser.add_argument('--skip-rename', action='store_true',
                        help="Ignorer l'étape 2 (renommage Shazam & Tagging)")
    parser.add_argument('--skip-dupes', action='store_true',
                        help="Ignorer le nettoyage des doublons")
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
        skip_dupes=args.skip_dupes
    )
