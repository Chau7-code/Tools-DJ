import os
import sys
import argparse
import re
import asyncio
import requests
from dotenv import load_dotenv
from checkpoint import CheckpointManager

try:
    from shazamio import Shazam
except ImportError:
    print("shazamio required: pip install shazamio")
    sys.exit(1)

try:
    from mutagen.id3 import ID3, TDRC, TYER, TORY, TCON, ID3NoHeaderError
except ImportError:
    print("mutagen required: pip install mutagen")
    sys.exit(1)

# Optional Spotify fallback
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_OK = True
except ImportError:
    SPOTIPY_OK = False

# Paths & env
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(script_dir), '.env'))

sp = None
if SPOTIPY_OK:
    cid = os.getenv('SPOTIFY_CLIENT_ID')
    csec = os.getenv('SPOTIFY_CLIENT_SECRET')
    if cid and csec:
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=cid, client_secret=csec))
        except Exception:
            pass

class C:
    G = '\033[92m'; Y = '\033[93m'; R = '\033[91m'; B = '\033[94m'; X = '\033[0m'


def is_remix(text):
    if not text: return False
    return bool(re.search(r'\b(remix|edit|bootleg|mashup|flip|vip|mix)\b', text.lower()))


def extract_filename_query(filepath):
    """Fallback: build a search query from the filename."""
    base = os.path.splitext(os.path.basename(filepath))[0]
    base = re.sub(r'^upgrade_', '', base, flags=re.IGNORECASE)
    base = re.sub(r'SoundLoadMate\.com', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\[.*?\]|\(.*?\)', '', base)
    base = base.replace('_', ' ').replace('-', ' ')
    base = re.sub(r'feat\.|ft\.|&|,', ' ', base, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', base).strip()


async def analyze_with_shazam(shazam, filepath):
    """Use Shazam audio fingerprint to identify track + get year & genre."""
    try:
        out = await asyncio.wait_for(shazam.recognize(filepath), timeout=30.0)
        track = out.get('track')
        if not track:
            return None

        title = track.get('title', '')
        artist = track.get('subtitle', '')
        genre = track.get('genres', {}).get('primary', '')
        year = None

        # Extract year from metadata sections
        for section in track.get('sections', []):
            if section.get('type') == 'SONG':
                for meta in section.get('metadata', []):
                    if meta.get('title') == 'Released':
                        year = meta.get('text')

        return {
            'artist': artist,
            'title': title,
            'year': year,
            'genre': genre
        }

    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


def search_itunes(query):
    """Fallback: search iTunes for release date and genre."""
    try:
        params = {"term": query, "entity": "song", "limit": 1, "country": "FR"}
        resp = requests.get("https://itunes.apple.com/search", params=params, timeout=10)
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            t = data["results"][0]
            release = t.get("releaseDate", "")
            return release[:4] if release else None, t.get("primaryGenreName", "")
    except Exception:
        pass
    return None, None


def search_spotify(query):
    """Fallback 2: Spotify."""
    if not sp or not query: return None, None
    try:
        results = sp.search(q=query, type='track', limit=1)
        items = results.get('tracks', {}).get('items', [])
        if items:
            t = items[0]
            rd = t['album']['release_date']
            year = rd.split('-')[0] if rd else None
            genres = []
            for a in t.get('artists', []):
                try:
                    info = sp.artist(a['id'])
                    if info and info.get('genres'):
                        genres = info['genres'][:2]
                        break
                except Exception:
                    pass
            return year, ", ".join(genres).title() if genres else None
    except Exception:
        pass
    return None, None


def write_tags(filepath, year, genre):
    """Write ID3v2.3 tags for Rekordbox."""
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
        print(f"    └─ {C.R}Write error: {e}{C.X}")
    return False


async def process(directory):
    if not os.path.exists(directory):
        print(f"{C.R}Directory not found: {directory}{C.X}")
        sys.exit(1)

    print(f"\n{C.B}=== Tagging Tracks (Shazam Audio Analysis → iTunes/Spotify fallback) ==={C.X}")
    print(f"Folder: {directory}\n")

    # Collecter tous les MP3
    all_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.mp3'):
                all_files.append(os.path.join(root, file))
    all_files.sort()

    # Checkpoint : pause/reprise
    mgr = CheckpointManager("add_release_date", directory)
    mgr.start()
    remaining = mgr.get_remaining_files(all_files)

    shazam = Shazam()
    tagged = 0; remixes = 0; failed = 0; file_count = 0

    try:
        for filepath in remaining:
            await mgr.wait_if_paused()

            file = os.path.basename(filepath)
            print(f"🎵 {C.Y}{file}{C.X}")

            # Skip if filename is obviously a remix
            if is_remix(file):
                print(f"    └─ {C.Y}Skipped (remix in filename){C.X}")
                remixes += 1
                mgr.save_progress(filepath)
                continue

            # Recreate Shazam instance every 20 files to avoid rate-limit stalls
            file_count += 1
            if file_count % 20 == 0:
                shazam = Shazam()
                await asyncio.sleep(3)

            # === Step 1: Shazam audio fingerprint ===
            print(f"    └─ Analyzing audio...")
            result = await analyze_with_shazam(shazam, filepath)

            year = None
            genre = None

            if result:
                s_title = result['title']
                s_artist = result['artist']
                year = result['year']
                genre = result['genre']

                print(f"    └─ Shazam: {s_artist} - {s_title}")

                # Check if Shazam identified it as a remix
                if is_remix(s_title) or is_remix(s_artist):
                    print(f"    └─ {C.Y}Skipped (remix detected by Shazam){C.X}")
                    remixes += 1
                    mgr.save_progress(filepath)
                    continue

                # If Shazam found a match but no year, use iTunes with the clean artist+title
                if not year:
                    print(f"    └─ Shazam has no date, checking iTunes...")
                    year, genre_it = search_itunes(f"{s_artist} {s_title}")
                    if not genre and genre_it:
                        genre = genre_it

            # === Step 2: Fallback to iTunes/Spotify if Shazam timed out ===
            if not year:
                fallback_query = extract_filename_query(filepath)
                if fallback_query:
                    print(f"    └─ Fallback iTunes: {fallback_query[:50]}...")
                    year, genre_it = search_itunes(fallback_query)
                    if not genre and genre_it:
                        genre = genre_it

            if not year and sp:
                fallback_query = extract_filename_query(filepath)
                if fallback_query:
                    print(f"    └─ Fallback Spotify: {fallback_query[:50]}...")
                    year, genre_sp = search_spotify(fallback_query)
                    if not genre and genre_sp:
                        genre = genre_sp

            # === Step 3: Write tags ===
            if not year:
                print(f"    └─ {C.R}Not found anywhere.{C.X}")
                failed += 1
                mgr.save_progress(filepath)
                continue

            print(f"    └─ {C.G}→ Year: {year}, Genre: {genre or 'Unknown'}{C.X}")

            if write_tags(filepath, year, genre):
                print(f"    └─ {C.G}✅ Tags written!{C.X}")
                tagged += 1
            else:
                failed += 1

            mgr.save_progress(filepath)

            # Delay between files to avoid Shazam rate-limiting
            await asyncio.sleep(3)
    except KeyboardInterrupt:
        print(f"\n{C.Y}⚠️  Interruption ! Progression sauvegardée dans .checkpoint.json{C.X}")
        mgr.stop()
        return directory

    print(f"\n{C.B}=== Summary ==={C.X}")
    print(f"✅ Tagged: {tagged}")
    print(f"⏭  Remixes: {remixes}")
    print(f"❌ Failed: {failed}")

    mgr.finish()
    return directory


if __name__ == "__main__":
    if os.name == 'nt':
        os.system('color')
    parser = argparse.ArgumentParser(description="Tag MP3s with release year & genre via Shazam audio analysis.")
    parser.add_argument("folder", help="MP3 folder")
    parser.add_argument("--rename", action="store_true",
                        help="Renommer les fichiers avec leur vrai nom après le tagging")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation du renommage (si --rename est activé)")
    args = parser.parse_args()
    asyncio.run(process(args.folder))

    if args.rename:
        # Import depuis le meme dossier scripts/
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from rename_tracks import run as rename_run
        print(f"\n{C.B}=== Lancement du renommage ==={C.X}")
        asyncio.run(rename_run(os.path.abspath(args.folder), dry_run=args.dry_run))
