"""
Script de re-téléchargement HQ
Usage: python redownload_list.py

Télécharge chaque morceau listé dans TRACKS ci-dessous
et les place dans OUTPUT_DIR.
"""
import os
import sys
import re

# ─── CONFIGURATION ──────────────────────────────────────────────────
OUTPUT_DIR = r"C:\Music\DJ\toutes les musique - Copie1 [HQ]"
# ────────────────────────────────────────────────────────────────────

# Liste des morceaux à télécharger (copiez-collez depuis musiques_introuvables_hq.txt)
TRACKS = [
    "Digital Slaves - Gesaffelstein",
    "Dj Sad, La Traine, Ninocess, pitroipa - Il est marié",
    "Freeze corleone, Alpha Wann - Rap catéchisme",
    "gazo paris nargilé",
    "GIMS - BLESSÉ",
    "GIMS - SANS ARRÊT",
    "Ginger - Boris Brejcha",
    "Hairitage - Undefeated",
    "Innerbloom - RÜFÜS DU SOL",
    "Kate Ryan - Désenchantée (Trym Summer Re-Work)",
    "KRUSH-UP-BRAZIL - RVDENT",
    "Life Is Simple Move Your Body feat Salomé Das TRYM Remix - Maesic Marshall Jefferson TRYM",
    "Love Tonight Edit - Shouse",
    "NeS, BU$HI - VENDREDI À LONDRES",
    "Niska - Médicament ft. Booba",
    "Paris - Nono La Grinta",
    "PLK, Heuss L'enfoiré - Chandon et Moët",
    "Push Up Main Edit - Creeds",
    "RED SPIDER LILY - Fantasm",
    "Tubes Décennies - Ces soirées-là",
    "Tyranny - Gesaffelstein",
    "Vald, Vladimir Cauchemar, Todiefor - QUE DES PROBLEMES RELOADED",
    "Vald, Vladimir Cauchemar, Todiefor - TAL TAL",
    "Videoclub, Adèle Castillon, Mattyeux - Amour plastique",
    "Vladimir Cauchemar, Roshi - Avenue feat. Captaine Roshi",
    "We Are Ravers - TRYM",
    "Woin Woin feat. RK - Larry",
    "elle a mal aux reins quand je la démonte",
    "perocket ket ket ket ket",
    "Petrouchka teck",
    "RELOADED Trickstar Remix",
]

# ─── SETUP ──────────────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from downloader import download_soundcloud, download_youtube, setup as downloader_setup, sanitize_filename

abs_ffmpeg_dir = os.path.join(parent_dir, 'ffmpeg_local')
abs_downloads_dir = os.path.join(parent_dir, 'downloads')
downloader_setup(abs_downloads_dir, abs_ffmpeg_dir)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Cookies SoundCloud optionnels (pour compte Go+)
sc_cookies_file = os.path.join(parent_dir, 'soundcloud_cookies.txt')
if not os.path.exists(sc_cookies_file):
    sc_cookies_file = None

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

if os.name == 'nt':
    os.system('color')

# ─── TÉLÉCHARGEMENT ──────────────────────────────────────────────────
print(f"\n{Colors.BLUE}=== Re-téléchargement HQ ==={Colors.RESET}")
print(f"Destination : {OUTPUT_DIR}")
print(f"Morceaux    : {len(TRACKS)}\n")

failed = []
for i, track in enumerate(TRACKS, 1):
    track = track.strip()
    if not track:
        continue

    # Nettoyage du nom issu de SoundLoadMate ou autre
    clean = re.sub(r'\s*[-–]\s*SoundLoadMate\.com\s*', '', track).strip()
    clean = re.sub(r'\s+', ' ', clean).strip()

    clean_file = sanitize_filename(clean)
    output_path = os.path.join(OUTPUT_DIR, f"{clean_file}.mp3")

    print(f"[{i}/{len(TRACKS)}] 🎵 {clean}")

    # Déjà téléchargé ?
    if os.path.exists(output_path) and os.path.getsize(output_path) > 100_000:
        print(f"    └─ {Colors.YELLOW}Déjà présent, ignoré.{Colors.RESET}")
        continue

    success = False

    # Essai 1 : SoundCloud
    try:
        final_path, _ = download_soundcloud(
            f"scsearch1:{clean}",
            output_path,
            custom_filename=clean_file,
            progress_id=None,
            progress_dict={},
            sc_cookies_file=sc_cookies_file
        )
        print(f"    └─ {Colors.GREEN}✅ SoundCloud OK → {final_path}{Colors.RESET}")
        success = True
    except Exception as e:
        err = str(e)
        if 'PREVIEW_ONLY' in err:
            print(f"    └─ {Colors.YELLOW}⏳ Préview 30s SC, essai YouTube...{Colors.RESET}")
        else:
            print(f"    └─ SC échoué, essai YouTube...")

    # Essai 2 : YouTube
    if not success:
        try:
            final_path, _ = download_youtube(
                f"ytsearch1:{clean} audio",
                output_path,
                custom_filename=clean_file,
                progress_id=None,
                progress_dict={}
            )
            print(f"    └─ {Colors.GREEN}✅ YouTube OK → {final_path}{Colors.RESET}")
            success = True
        except Exception as e2:
            print(f"    └─ {Colors.RED}❌ Introuvable partout.{Colors.RESET}")

    if not success:
        failed.append(clean)

# ─── RÉSUMÉ ──────────────────────────────────────────────────────────
print(f"\n{Colors.BLUE}=== Terminé ==={Colors.RESET}")
print(f"✅ {len(TRACKS) - len(failed)}/{len(TRACKS)} téléchargés avec succès")

if failed:
    print(f"\n{Colors.YELLOW}Morceaux non trouvés ({len(failed)}) :{Colors.RESET}")
    for f in failed:
        print(f"  - {f}")
    # Sauvegarder les introuvables
    failed_path = os.path.join(parent_dir, 'data', 'introuvables_final.txt')
    with open(failed_path, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(failed))
    print(f"\nSauvegardé dans : {failed_path}")
    print("Pensez à chercher sur Beatport, Juno, Bandcamp pour les rares.")
