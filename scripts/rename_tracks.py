"""
rename_tracks.py
-----------------
Identifie les fichiers audio via Shazam (+ iTunes/Spotify en fallback),
puis les renomme avec le vrai nom : Artiste - Titre.ext
Et ajoute les tags ID3 : genre + date de sortie.

Gestion des doublons :
  - Si deux fichiers partagent le meme titre, TOUS recoivent un suffixe
    song-1, song-2, etc. pour signaler les doublons.

Fichier de suivi :
  - renamed_tracks.txt : liste ancien_chemin -> nouveau_chemin

Usage standalone :
    python scripts/rename_tracks.py "C:/chemin/vers/musique"
    python scripts/rename_tracks.py "C:/chemin/vers/musique" --dry-run
"""

import os
import sys
import re
import asyncio
import argparse
import unicodedata
import requests
from datetime import datetime
from dotenv import load_dotenv
from checkpoint import CheckpointManager

try:
    from shazamio import Shazam
except ImportError:
    print("shazamio required: pip install shazamio")
    sys.exit(1)

try:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, TDRC, TYER, TORY, TCON, ID3NoHeaderError
    MUTAGEN_OK = True
except ImportError:
    print("mutagen required: pip install mutagen")
    MUTAGEN_OK = False

# Optional Spotify fallback
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_OK = True
except ImportError:
    SPOTIPY_OK = False

# ─── Paths & env ──────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(script_dir), '.env'))

sp = None
if SPOTIPY_OK:
    cid = os.getenv('SPOTIFY_CLIENT_ID')
    csec = os.getenv('SPOTIFY_CLIENT_SECRET')
    if cid and csec:
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=cid, client_secret=csec))
        except Exception:
            pass

# ─── Couleurs ANSI ────────────────────────────────────────────────
class C:
    G = '\033[92m'; Y = '\033[93m'; R = '\033[91m'
    B = '\033[94m'; M = '\033[95m'; X = '\033[0m'


# ─── Helpers ──────────────────────────────────────────────────────
AUDIO_EXT = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')


def sanitize_filename(name):
    """Supprime les caracteres interdits dans un nom de fichier."""
    # Remplacer les caracteres speciaux Windows
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Supprimer les espaces en trop
    name = re.sub(r'\s+', ' ', name).strip()
    # Limiter la longueur
    if len(name) > 200:
        name = name[:200]
    return name


def limit_artists(artist_str, max_artists=2):
    """Limite le nombre d'artistes a max_artists (defaut: 2)."""
    if not artist_str:
        return artist_str
    # Separer par les delimiteurs courants : ", ", " & ", " feat. ", " ft. ", " x "
    parts = re.split(r'\s*,\s*|\s+&\s+|\s+feat\.?\s+|\s+ft\.?\s+|\s+x\s+', artist_str, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= max_artists:
        return artist_str
    return ', '.join(parts[:max_artists])


def normalize_for_comparison(text):
    """Normalise un texte pour comparaison (minuscules, sans accents)."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_filename_query(filepath):
    """Construit une requete de recherche a partir du nom de fichier."""
    base = os.path.splitext(os.path.basename(filepath))[0]
    base = re.sub(r'^upgrade_', '', base, flags=re.IGNORECASE)
    base = re.sub(r'SoundLoadMate\.com', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\[.*?\]|\(.*?\)', '', base)
    base = base.replace('_', ' ').replace('-', ' ')
    base = re.sub(r'feat\.|ft\.|\&|,', ' ', base, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', base).strip()


# ─── Identification ──────────────────────────────────────────────

async def identify_with_shazam(shazam, filepath):
    """Identifie une piste via l'empreinte audio Shazam (+ year + genre)."""
    try:
        out = await asyncio.wait_for(shazam.recognize(filepath), timeout=30.0)
        track = out.get('track')
        if not track:
            return None

        year = None
        for section in track.get('sections', []):
            if section.get('type') == 'SONG':
                for meta in section.get('metadata', []):
                    if meta.get('title') == 'Released':
                        year = meta.get('text')

        return {
            'artist': track.get('subtitle', ''),
            'title': track.get('title', ''),
            'genre': track.get('genres', {}).get('primary', ''),
            'year': year,
        }
    except (asyncio.TimeoutError, Exception):
        return None


def search_itunes(query):
    """Recherche iTunes pour artiste/titre/genre/year."""
    try:
        params = {"term": query, "entity": "song", "limit": 1, "country": "FR"}
        resp = requests.get("https://itunes.apple.com/search", params=params, timeout=10)
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            t = data["results"][0]
            artist = t.get("artistName", "")
            title = t.get("trackName", "")
            genre = t.get("primaryGenreName", "")
            release = t.get("releaseDate", "")
            year = release[:4] if release else None
            if artist and title:
                return {'artist': artist, 'title': title, 'genre': genre, 'year': year}
    except Exception:
        pass
    return None


def search_spotify(query):
    """Recherche Spotify pour artiste/titre/year."""
    if not sp or not query:
        return None
    try:
        results = sp.search(q=query, type='track', limit=1)
        items = results.get('tracks', {}).get('items', [])
        if items:
            t = items[0]
            # Prendre max 2 artistes de Spotify
            all_artists = [a['name'] for a in t.get('artists', [])]
            artist = ', '.join(all_artists[:2])
            title = t.get('name', '')
            rd = t['album'].get('release_date', '')
            year = rd.split('-')[0] if rd else None
            # Essayer de récupérer le genre depuis l'artiste
            genre = ''
            try:
                for a in t.get('artists', []):
                    info = sp.artist(a['id'])
                    if info and info.get('genres'):
                        genre = ', '.join(info['genres'][:2]).title()
                        break
            except Exception:
                pass
            if artist and title:
                return {'artist': artist, 'title': title, 'genre': genre, 'year': year}
    except Exception:
        pass
    return None


async def identify_track(shazam, filepath):
    """
    Pipeline complet d'identification :
      1. Shazam (empreinte audio)
      2. iTunes (recherche par nom de fichier)
      3. Spotify (recherche par nom de fichier)
    Retourne {'artist': ..., 'title': ..., 'genre': ...} ou None.
    """
    # Etape 1 : Shazam
    result = await identify_with_shazam(shazam, filepath)
    if result and result.get('artist') and result.get('title'):
        return result, 'Shazam'

    # Etape 2 : iTunes fallback
    query = extract_filename_query(filepath)
    if query:
        result = search_itunes(query)
        if result:
            return result, 'iTunes'

    # Etape 3 : Spotify fallback
    if query:
        result = search_spotify(query)
        if result:
            return result, 'Spotify'

    return None, None


# ─── Construction du nouveau nom ──────────────────────────────────

def build_new_filename(artist, title, ext):
    """Construit le nouveau nom de fichier : Artiste - Titre.ext (max 2 artistes)."""
    artist = limit_artists(artist, max_artists=2)
    name = f"{artist} - {title}"
    name = sanitize_filename(name)
    if not name:
        return None
    return name + ext


# ─── Écriture des tags ID3 (genre + date) ─────────────────────────

def write_tags(filepath, year, genre):
    """Écrit les tags ID3v2.3 (année + genre) pour Rekordbox."""
    if not MUTAGEN_OK:
        return False
    try:
        try:
            audio = ID3(filepath)
        except ID3NoHeaderError:
            audio = ID3()

        changed = False
        if year:
            y = str(year)
            audio.add(TYER(encoding=3, text=y))
            audio.add(TDRC(encoding=3, text=y))
            audio.add(TORY(encoding=3, text=y))
            changed = True
        if genre:
            audio.add(TCON(encoding=3, text=genre))
            changed = True
        if changed:
            audio.save(filepath, v2_version=3)
            return True
    except Exception as e:
        print(f"    └─ {C.R}Erreur tags: {e}{C.X}")
    return False


# ─── Gestion des doublons ────────────────────────────────────────

def handle_duplicates(rename_map):
    """
    Detecte les titres en double et ajoute des suffixes song-1, song-2, etc.

    rename_map : dict {ancien_chemin: nouveau_nom_base (sans ext)}
    Retourne un nouveau dict avec les suffixes appliques.
    """
    # Regrouper par nom normalise
    from collections import defaultdict
    groups = defaultdict(list)
    for old_path, new_base in rename_map.items():
        ext = os.path.splitext(old_path)[1]
        key = normalize_for_comparison(new_base)
        groups[key].append((old_path, new_base, ext))

    final_map = {}
    for key, entries in groups.items():
        if len(entries) == 1:
            # Pas de doublon
            old_path, new_base, ext = entries[0]
            final_map[old_path] = new_base + ext
        else:
            # Doublons detectes : ajouter suffixe a TOUS
            for i, (old_path, new_base, ext) in enumerate(entries, 1):
                final_map[old_path] = f"{new_base} song-{i}{ext}"

    return final_map


# ─── Processus principal ─────────────────────────────────────────

async def run(directory, dry_run=False, log_file=None):
    """
    Orchestre l'identification et le renommage.

    Args:
        directory: Dossier contenant les fichiers audio
        dry_run: Si True, simule sans renommer
        log_file: Chemin du fichier .txt de suivi (defaut: renamed_tracks.txt dans le dossier)
    """
    if not os.path.isdir(directory):
        print(f"{C.R}Erreur: dossier inexistant : {directory}{C.X}")
        sys.exit(1)

    if log_file is None:
        log_file = os.path.join(directory, "renamed_tracks.txt")

    if dry_run:
        print(f"{C.Y}⚠️  Mode simulation (--dry-run) : aucun fichier ne sera renommé.{C.X}")

    print(f"\n{C.B}=== Renommage des fichiers audio (identification Shazam → iTunes → Spotify) ==={C.X}")
    print(f"Dossier : {directory}\n")

    # Collecter les fichiers audio
    audio_files = []
    for f in os.listdir(directory):
        if f.lower().endswith(AUDIO_EXT):
            audio_files.append(os.path.join(directory, f))

    if not audio_files:
        print(f"{C.Y}Aucun fichier audio trouvé.{C.X}")
        return

    print(f"Fichiers trouvés : {len(audio_files)}\n")

    # ─── Checkpoint : pause/reprise ────────────────────────────
    mgr = CheckpointManager("rename_tracks", directory)
    mgr.start()
    remaining = mgr.get_remaining_files(sorted(audio_files))

    shazam = Shazam()
    rename_map = {}   # ancien_chemin -> nouveau_nom_base (sans ext)
    tag_info = {}     # ancien_chemin -> {'year': ..., 'genre': ...}
    skipped = 0
    failed = 0
    tagged_existing = 0
    file_count = 0

    try:
        for filepath in remaining:
            await mgr.wait_if_paused()

            fname = os.path.basename(filepath)
            print(f"🎵 {C.Y}{fname}{C.X}")

            # Recreer Shazam tous les 20 fichiers
            file_count += 1
            if file_count % 20 == 0:
                shazam = Shazam()
                await asyncio.sleep(3)

            # Identification
            print(f"    └─ Identification en cours...")
            result, source = await identify_track(shazam, filepath)

            if not result:
                print(f"    └─ {C.R}Non identifié, fichier ignoré.{C.X}")
                failed += 1
                mgr.save_progress(filepath)
                await asyncio.sleep(2)
                continue

            artist = result['artist']
            title = result['title']
            genre = result.get('genre', '')
            year = result.get('year', None)
            print(f"    └─ {C.G}[{source}] {artist} - {title}{C.X}")
            if genre or year:
                parts = []
                if genre: parts.append(f"Genre: {genre}")
                if year: parts.append(f"Année: {year}")
                print(f"    └─ {' | '.join(parts)}")

            # Si Shazam n'a pas trouvé l'année, chercher via iTunes
            if not year:
                query = extract_filename_query(filepath)
                if query:
                    try:
                        params = {"term": query, "entity": "song", "limit": 1, "country": "FR"}
                        resp = requests.get("https://itunes.apple.com/search", params=params, timeout=10)
                        data = resp.json()
                        if data.get("resultCount", 0) > 0:
                            t = data["results"][0]
                            release = t.get("releaseDate", "")
                            if release:
                                year = release[:4]
                            if not genre:
                                genre = t.get("primaryGenreName", "")
                    except Exception:
                        pass

            ext = os.path.splitext(filepath)[1]
            new_base = build_new_filename(artist, title, '')

            if not new_base:
                print(f"    └─ {C.R}Nom résultant vide, fichier ignoré.{C.X}")
                failed += 1
                mgr.save_progress(filepath)
                continue

            # Stocker les infos de tags pour écriture après renommage
            tag_info[filepath] = {'year': year, 'genre': genre}

            # Verifier si le fichier porte deja le bon nom
            current_base = os.path.splitext(fname)[0]
            if normalize_for_comparison(current_base) == normalize_for_comparison(new_base):
                print(f"    └─ {C.G}✅ Nom déjà correct.{C.X}")
                # Écrire les tags même si le nom est déjà bon
                if (year or genre) and filepath.lower().endswith('.mp3'):
                    if write_tags(filepath, year, genre):
                        tag_parts = []
                        if year: tag_parts.append(f"{year}")
                        if genre: tag_parts.append(f"{genre}")
                        print(f"    └─ {C.G}🏷️  Tags écrits: {' | '.join(tag_parts)}{C.X}")
                        tagged_existing += 1
                skipped += 1
                mgr.save_progress(filepath)
                continue

            rename_map[filepath] = new_base
            mgr.save_progress(filepath)

            # Delai entre fichiers pour eviter le rate-limiting
            await asyncio.sleep(3)
    except KeyboardInterrupt:
        print(f"\n{C.Y}⚠️  Interruption ! Progression sauvegardée dans .checkpoint.json{C.X}")
        mgr.stop()
        return

    # ─── Gestion des doublons ─────────────────────────────────
    if not rename_map:
        print(f"\n{C.Y}Aucun fichier à renommer.{C.X}")
        return

    print(f"\n{C.B}=== Vérification des doublons ==={C.X}")
    final_map = handle_duplicates(rename_map)

    # Compter les doublons
    duplicates = sum(1 for v in final_map.values() if re.search(r'song-\d+', v))
    if duplicates:
        print(f"{C.M}⚠️  {duplicates} fichier(s) avec titre en double → suffixes song-N ajoutés.{C.X}")
    else:
        print(f"{C.G}Aucun doublon détecté.{C.X}")

    # ─── Renommage ────────────────────────────────────────────
    print(f"\n{C.B}=== Renommage ==={C.X}")
    renamed = 0
    tagged = 0
    errors = 0
    log_entries = []

    for old_path, new_name in sorted(final_map.items()):
        old_name = os.path.basename(old_path)
        new_path = os.path.join(os.path.dirname(old_path), new_name)

        # Eviter d'ecraser un fichier existant qui ne fait pas partie du renommage
        if os.path.exists(new_path) and new_path not in final_map:
            # Ajouter un numero pour eviter l'ecrasement
            base, ext = os.path.splitext(new_name)
            counter = 1
            while os.path.exists(new_path):
                new_name = f"{base} song-{counter}{ext}"
                new_path = os.path.join(os.path.dirname(old_path), new_name)
                counter += 1

        action = "SIMULATION" if dry_run else "RENOMMÉ"
        print(f"  {C.Y}{old_name}{C.X}")
        print(f"    → {C.G}{new_name}{C.X} [{action}]")

        if not dry_run:
            try:
                os.rename(old_path, new_path)
                renamed += 1
                log_entries.append(f"{new_path}")

                # Écrire les tags ID3 (genre + année) sur le fichier renommé
                info = tag_info.get(old_path, {})
                t_year = info.get('year')
                t_genre = info.get('genre')
                if (t_year or t_genre) and new_path.lower().endswith('.mp3'):
                    if write_tags(new_path, t_year, t_genre):
                        tag_parts = []
                        if t_year: tag_parts.append(f"{t_year}")
                        if t_genre: tag_parts.append(f"{t_genre}")
                        print(f"    └─ {C.G}🏷️  Tags: {' | '.join(tag_parts)}{C.X}")
                        tagged += 1
            except Exception as e:
                print(f"    └─ {C.R}Erreur: {e}{C.X}")
                errors += 1
        else:
            renamed += 1
            log_entries.append(f"{new_path}")

    # ─── Écriture du fichier de suivi ─────────────────────────
    if log_entries:
        mode = 'a' if os.path.exists(log_file) else 'w'
        with open(log_file, mode, encoding='utf-8') as f:
            f.write(f"\n# === Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            if dry_run:
                f.write("# MODE SIMULATION\n")
            for entry in log_entries:
                f.write(entry + "\n")
        print(f"\n{C.G}📄 Fichier de suivi : {log_file}{C.X}")

    # ─── Résumé ───────────────────────────────────────────────
    total_tagged = tagged + tagged_existing
    mode_str = " (simulation)" if dry_run else ""
    print(f"\n{C.B}=== Résumé ==={C.X}")
    print(f"  ✅ Renommés{mode_str}      : {renamed}")
    print(f"  🏷️  Tags écrits          : {total_tagged}")
    print(f"  ⏭️  Déjà corrects        : {skipped}")
    print(f"  ❌ Non identifiés       : {failed}")
    print(f"  ⚠️  Doublons détectés    : {duplicates}")
    if errors:
        print(f"  🚫 Erreurs              : {errors}")

    mgr.finish()


# ─── Point d'entrée ──────────────────────────────────────────────

if __name__ == "__main__":
    if os.name == 'nt':
        os.system('color')

    parser = argparse.ArgumentParser(
        description="Identifie et renomme les fichiers audio avec leur vrai nom (Artiste - Titre)."
    )
    parser.add_argument("dossier", help="Dossier contenant les fichiers audio")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation : affiche les renommages sans les effectuer")
    parser.add_argument("--log", default=None,
                        help="Chemin du fichier de suivi .txt (défaut: renamed_tracks.txt dans le dossier)")
    args = parser.parse_args()

    asyncio.run(run(os.path.abspath(args.dossier), dry_run=args.dry_run, log_file=args.log))
