import os
import sys
import re
import yt_dlp
from urllib.parse import urlparse, parse_qs
import uuid
import shutil
import subprocess
import requests
import zipfile
import time
import json

# Configuration par défaut
UPLOAD_FOLDER = 'downloads'
FFMPEG_FOLDER = 'ffmpeg_local'

def setup(upload_folder, ffmpeg_folder):
    global UPLOAD_FOLDER, FFMPEG_FOLDER
    UPLOAD_FOLDER = upload_folder
    FFMPEG_FOLDER = ffmpeg_folder
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(FFMPEG_FOLDER, exist_ok=True)

def get_local_ffmpeg_path():
    """Retourne le chemin vers FFmpeg local s'il existe"""
    if os.name == 'nt':  # Windows
        ffmpeg_exe = os.path.join(FFMPEG_FOLDER, 'ffmpeg.exe')
        ffprobe_exe = os.path.join(FFMPEG_FOLDER, 'ffprobe.exe')
    else:  # Linux/Mac
        ffmpeg_exe = os.path.join(FFMPEG_FOLDER, 'ffmpeg')
        ffprobe_exe = os.path.join(FFMPEG_FOLDER, 'ffprobe')
    
    if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
        return FFMPEG_FOLDER
    return None

def check_ffmpeg():
    """Vérifie si FFmpeg est disponible et retourne le chemin si trouvé"""
    # Essayer de trouver FFmpeg dans le PATH d'abord (Linux favorise ça)
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)

    # Ensuite vérifier FFmpeg local
    local_ffmpeg = get_local_ffmpeg_path()
    if local_ffmpeg:
        return local_ffmpeg
    
    # Vérifier les emplacements communs sur Windows
    if os.name == 'nt':
        common_paths = [
            r'C:\\ffmpeg\\bin',
            r'C:\\Program Files\\ffmpeg\\bin',
            r'C:\\Program Files (x86)\\ffmpeg\\bin',
            os.path.join(os.path.expanduser('~'), 'ffmpeg', 'bin'),
        ]
        for path in common_paths:
            if os.path.exists(os.path.join(path, 'ffmpeg.exe')):
                return path
    
    # Essayer de lancer ffmpeg pour vérifier s'il est dans le PATH sans shutil.which
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, 
                      timeout=5,
                      check=True)
        return "system"  # FFmpeg est dans le PATH
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return None

def download_ffmpeg_windows():
    """Télécharge et installe FFmpeg pour Windows automatiquement"""
    ffmpeg_exe = os.path.join(FFMPEG_FOLDER, 'ffmpeg.exe')
    ffprobe_exe = os.path.join(FFMPEG_FOLDER, 'ffprobe.exe')
    
    # Si déjà installé, retourner
    if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
        return True
    
    try:
        # URL pour télécharger FFmpeg Windows (version statique)
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        
        print("Téléchargement de FFmpeg en cours...")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        zip_path = os.path.join(FFMPEG_FOLDER, 'ffmpeg.zip')
        total_size = int(response.headers.get('content-length', 0))
        
        with open(zip_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        if int(progress) % 10 == 0:  # Afficher tous les 10%
                            print(f"Téléchargement: {int(progress)}%")
        
        print("Extraction de FFmpeg...")
        # Créer un dossier temporaire pour l'extraction
        temp_extract_dir = os.path.join(FFMPEG_FOLDER, 'temp_extract')
        os.makedirs(temp_extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Extraire tout dans le dossier temporaire
            zip_ref.extractall(temp_extract_dir)
        
        # Chercher ffmpeg.exe et ffprobe.exe dans les sous-dossiers
        for root, dirs, files in os.walk(temp_extract_dir):
            for file in files:
                if file == 'ffmpeg.exe' and not os.path.exists(ffmpeg_exe):
                    source = os.path.join(root, file)
                    shutil.copy2(source, ffmpeg_exe)
                elif file == 'ffprobe.exe' and not os.path.exists(ffprobe_exe):
                    source = os.path.join(root, file)
                    shutil.copy2(source, ffprobe_exe)
        
        if not (os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe)):
            print("Erreur: FFmpeg non trouvé après extraction")
            return False
            
    except Exception as e:
        print(f"Erreur lors du téléchargement de FFmpeg: {str(e)}")
        return False
    finally:
        # Nettoyer le fichier zip et le dossier temporaire
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
    
    return True

def ensure_ffmpeg():
    """S'assure que FFmpeg est disponible, le télécharge si nécessaire (synchrone)"""
    # Vérifier d'abord si FFmpeg existe
    ffmpeg_location = check_ffmpeg()
    if ffmpeg_location == "system":
        return "system"  # On va utiliser juste "ffmpeg" dans les appels
    if ffmpeg_location is not None:
        # Convertir en chemin absolu
        return os.path.abspath(ffmpeg_location)
    
    # Si on est sur Windows et FFmpeg n'est pas trouvé, le télécharger
    if os.name == 'nt':
        print("FFmpeg non trouvé. Téléchargement automatique en cours...")
        print("Cela peut prendre quelques minutes. Veuillez patienter...")
        if download_ffmpeg_windows():
            local_path = get_local_ffmpeg_path()
            if local_path:
                # Convertir en chemin absolu
                return os.path.abspath(local_path)
            else:
                raise Exception("FFmpeg installé mais introuvable. Veuillez réessayer.")
        else:
            raise Exception("Impossible de télécharger FFmpeg automatiquement. Veuillez l'installer manuellement.")
    
    raise Exception("FFmpeg n'est pas installé. Sur Linux (Armbian), installez-le avec: sudo apt-get install ffmpeg")

def get_ffmpeg_exe_path():
    """Retourne le chemin complet vers l'exécutable FFmpeg"""
    try:
        ffmpeg_dir = ensure_ffmpeg()
        if ffmpeg_dir == "system":
            return "ffmpeg"
        if os.name == 'nt':
            return os.path.join(ffmpeg_dir, 'ffmpeg.exe')
        else:
            return os.path.join(ffmpeg_dir, 'ffmpeg')
    except:
        return 'ffmpeg' # Fallback to system path


def is_youtube_url(url):
    parsed = urlparse(url)
    return 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc

def is_soundcloud_url(url):
    parsed = urlparse(url)
    return 'soundcloud.com' in parsed.netloc

def is_spotify_url(url):
    parsed = urlparse(url)
    return 'spotify.com' in parsed.netloc

def is_instagram_url(url):
    parsed = urlparse(url)
    return 'instagram.com' in parsed.netloc

def is_playlist(url):
    parsed = urlparse(url)
    if 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc:
        return 'list=' in parsed.query
    elif 'soundcloud.com' in parsed.netloc:
        return '/sets/' in parsed.path
    elif 'spotify.com' in parsed.netloc:
        return '/playlist/' in parsed.path or '/album/' in parsed.path
    return False

def sanitize_filename(filename):
    import unicodedata
    # Secure filename: remove accents, allow only alphanumeric, space, dot, dash, underscore
    filename = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
    filename = re.sub(r'[^\w\s.-]', '_', filename)
    filename = re.sub(r'[_]+', '_', filename)  # Collapse multiple underscores
    # Prevent extremely long filenames and strip trailing dots/spaces
    return filename.strip(' .')[:200]

def cleanup_temp_files(directory, base_path):
    try:
        base_name = os.path.basename(base_path)
        temp_extensions = ['.m4a', '.webm', '.mp4', '.opus', '.ogg', '.flac', '.wav', '.mkv', '.avi']
        
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            if file.startswith(base_name) and any(file.endswith(ext) for ext in temp_extensions):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Impossible de supprimer {file}: {e}")
    except Exception as e:
        print(f"Erreur lors du nettoyage des fichiers temporaires: {e}")

def cleanup_all_temp_files(directory):
    try:
        temp_extensions = ['.m4a', '.webm', '.mp4', '.opus', '.ogg', '.flac', '.wav', '.mkv', '.avi', '.part', '.ytdl']
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            if any(file.endswith(ext) for ext in temp_extensions) and os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except PermissionError:
                    pass
                except Exception as e:
                    print(f"Impossible de supprimer {file}: {e}")
    except Exception as e:
        print(f"Erreur lors du nettoyage général: {e}")

def clean_old_files(directory, max_age_seconds):
    """Supprime les fichiers plus vieux que max_age_seconds"""
    try:
        if not os.path.exists(directory):
            return
        now = time.time()
        count = 0
        for f in os.listdir(directory):
            fp = os.path.join(directory, f)
            if os.path.isfile(fp):
                # Vérifier si le fichier est plus vieux que max_age_seconds
                if os.stat(fp).st_mtime < now - max_age_seconds:
                    try:
                        os.remove(fp)
                        count += 1
                    except Exception:
                        pass
        if count > 0:
            print(f"[Cleanup] Suppression de {count} anciens fichiers dans {directory}")
    except Exception as e:
        print(f"[Cleanup] Erreur lors du nettoyage de {directory}: {e}")

def check_and_clean_folder(directory, limit_bytes):
    """Vérifie la taille du dossier et supprime les fichiers les plus anciens si nécessaire"""
    try:
        if not os.path.exists(directory):
            return

        total_size = 0
        files = []

        for dirpath, dirnames, filenames in os.walk(directory):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    size = os.path.getsize(fp)
                    total_size += size
                    files.append((fp, os.path.getmtime(fp), size))
                except OSError:
                    pass
        
        print(f"[Storage] Taille actuelle: {total_size / (1024*1024*1024):.2f} GB / {limit_bytes / (1024*1024*1024):.2f} GB")

        if total_size > limit_bytes:
            # Trier par date de modification (plus ancien en premier)
            files.sort(key=lambda x: x[1])
            
            deleted_size = 0
            for fp, mtime, size in files:
                try:
                    os.remove(fp)
                    deleted_size += size
                    total_size -= size
                    print(f"[Storage] Suppression de {fp} ({size/1024:.2f} KB)")
                    if total_size <= limit_bytes:
                        break
                except Exception as e:
                    print(f"[Storage] Erreur suppression {fp}: {e}")
            
            print(f"[Storage] Nettoyage terminé. Espace libéré: {deleted_size / (1024*1024):.2f} MB")
            
    except Exception as e:
        print(f"[Storage] Erreur lors de la vérification du dossier: {e}")


def get_playlist_title(url, source_type):
    try:
        if source_type == 'spotify':
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                match = re.search(r'<title>(.*?)</title>', response.text)
                if match:
                    title = match.group(1)
                    title = title.replace(' | Spotify', '').replace(' - Spotify', '')
                    return title.strip()
            return "Spotify_Playlist"
        else:
            ydl_opts = {'extract_flat': True, 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title', 'Playlist')
    except Exception as e:
        print(f"Erreur titre playlist: {e}")
        return "Playlist"

def process_playlist(url, source_type, progress_id=None, progress_dict=None):
    raw_title = get_playlist_title(url, source_type)
    playlist_name = sanitize_filename(raw_title)
    if not playlist_name:
        playlist_name = "Playlist"
        
    temp_uuid = str(uuid.uuid4())
    base_temp_dir = os.path.join(UPLOAD_FOLDER, temp_uuid)
    playlist_dir = os.path.join(base_temp_dir, playlist_name)
    downloaded_files = []

    if not os.path.exists(playlist_dir):
        os.makedirs(playlist_dir)

    if source_type == 'spotify':
            try:
                import spotipy
                from spotipy.oauth2 import SpotifyClientCredentials
            except ImportError:
                raise Exception("spotipy n'est pas installé.")
            
            from dotenv import load_dotenv
            load_dotenv()
            client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
            client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")

            if not client_id or not client_secret:
                raise Exception("Les identifiants Spotify (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) ne sont pas définis dans les variables d'environnement.")

            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id,
                                                                       client_secret=client_secret))
            
            playlist_id = url.split('/')[-1].split('?')[0]
            
            if '/album/' in url:
                results = sp.album_tracks(playlist_id)
                tracks = results['items']
                while results['next']:
                    results = sp.next(results)
                    tracks.extend(results['items'])
    try:
        if source_type == 'spotify':
                try:
                    import spotipy
                    from spotipy.oauth2 import SpotifyClientCredentials
                except ImportError:
                    raise Exception("spotipy n'est pas installé.")
                
                from dotenv import load_dotenv
                load_dotenv()
                client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
                client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")

                if not client_id or not client_secret:
                    raise Exception("Les identifiants Spotify (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) ne sont pas définis dans les variables d'environnement.")

                sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id,
                                                                           client_secret=client_secret))
                
                playlist_id = url.split('/')[-1].split('?')[0]
                
                if '/album/' in url:
                    try:
                        results = sp.album_tracks(playlist_id)
                        tracks = results['items']
                        while results['next']:
                            results = sp.next(results)
                            tracks.extend(results['items'])
                        
                        # For albums, track info is directly in 'items'
                        track_items = [{'track': t} for t in tracks]
                    except Exception as e:
                        if "404" in str(e):
                            raise Exception("Cet album Spotify est introuvable ou privé. Vérifiez le lien ou rendez-le public.")
                        raise e
                else: # Assume playlist
                    try:
                        results = sp.playlist_items(playlist_id)
                        track_items = results['items']
                        while results['next']:
                            results = sp.next(results)
                            track_items.extend(results['items'])
                    except Exception as e:
                        if "404" in str(e):
                            if 'pt=' in url:
                                raise Exception("Cette playlist Spotify est introuvable. Il semble s'agir d'une playlist privée partagée avec un lien spécial (pt=...). Notre outil ne peut télécharger que des playlists publiques. Veuillez la rendre publique dans Spotify.")
                            else:
                                raise Exception("La playlist Spotify est introuvable ou privée (Erreur 404). Vérifiez le lien ou rendez-la publique.")
                        raise e

                total_items = len(track_items)
                if total_items == 0:
                    raise Exception("Aucune piste trouvée dans la playlist/album Spotify.")

                for i, item in enumerate(track_items):
                    try:
                        track = item.get('track')
                        if not track:
                            print(f"Skipping item {i+1}: No track data found.")
                            continue

                        track_name = track.get('name')
                        artists = ", ".join([artist['name'] for artist in track.get('artists', [])])
                        search_query = f"{track_name} {artists}"
                        
                        if progress_id and progress_dict is not None:
                            progress_dict[progress_id] = {
                                'percent': (i / total_items) * 100,
                                'status': 'downloading',
                                'message': f'Téléchargement piste {i+1}/{total_items}: "{track_name}"'
                            }
                        
                        # Call the fallback downloader for each individual track
                        # The custom_filename ensures the file is named correctly in the playlist directory
                        output_filename = sanitize_filename(f"{track_name} - {artists}") + ".mp3"
                        output_full_path = os.path.join(playlist_dir, output_filename)

                        item_path, item_filename = download_youtube(
                            f"ytsearch1:{search_query}",
                            output_full_path,
                            custom_filename=output_filename, # Pass the desired filename
                            progress_id=None, # Do not update global progress for individual tracks
                            progress_dict=None
                        )
                        downloaded_files.append(item_path)
                        
                    except Exception as e:
                        print(f"Erreur sur l'élément Spotify {i+1} ({track_name if 'track_name' in locals() else 'N/A'}): {e}")
                        continue
        else: # YouTube or SoundCloud playlist
            ydl_opts = {
                'format': 'bestaudio/best',
                'extract_flat': True, # Only extract info, don't download
                'quiet': True,
                'no_warnings': True,
            }
            
            if source_type == 'youtube':
                ydl_opts['extract_flat'] = 'in_playlist' # For YouTube, this is better for playlists
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if 'entries' not in info:
                    raise Exception("Aucune entrée trouvée dans la playlist.")
                
                total_items = len(info['entries'])
                if total_items == 0:
                    raise Exception("Aucune piste trouvée dans la playlist.")

                for i, entry in enumerate(info['entries']):
                    if entry is None:
                        print(f"Skipping empty entry {i+1}")
                        continue
                    
                    entry_url = entry.get('url')
                    entry_title = entry.get('title', f"Track {i+1}")
                    
                    if not entry_url:
                        print(f"Skipping entry {i+1} due to missing URL.")
                        continue

                    if progress_id and progress_dict is not None:
                        progress_dict[progress_id] = {
                            'percent': (i / total_items) * 100,
                            'status': 'downloading',
                            'message': f'Téléchargement piste {i+1}/{total_items}: "{entry_title}"'
                        }
                    
                    output_filename = sanitize_filename(entry_title) + ".mp3"
                    output_full_path = os.path.join(playlist_dir, output_filename)

                    try:
                        if source_type == 'youtube':
                            item_path, item_filename = download_youtube(
                                entry_url,
                                output_full_path,
                                custom_filename=output_filename,
                                progress_id=None,
                                progress_dict=None
                            )
                        elif source_type == 'soundcloud':
                            item_path, item_filename = download_soundcloud(
                                entry_url,
                                output_full_path,
                                custom_filename=output_filename,
                                progress_id=None,
                                progress_dict=None
                            )
                        downloaded_files.append(item_path)
                    except Exception as e:
                        print(f"Erreur sur l'élément {source_type} {i+1} ({entry_title}): {e}")
                        continue

        zip_filename = f"{playlist_name}.zip"
        zip_path = os.path.join(UPLOAD_FOLDER, zip_filename)
        
        shutil.make_archive(zip_path.replace('.zip', ''), 'zip', base_temp_dir, playlist_name)
        shutil.rmtree(base_temp_dir)
        
        return zip_path, zip_filename.replace('.zip', '')
        
    except Exception as e:
        if os.path.exists(base_temp_dir):
            shutil.rmtree(base_temp_dir)
        raise e

def download_youtube(url, output_path, custom_filename=None, progress_id=None, progress_dict=None):
    base_path = output_path.replace('.mp3', '')
    
    try:
        ffmpeg_location = ensure_ffmpeg()
    except Exception as e:
        raise Exception(f"Erreur FFmpeg: {str(e)}")
    
    if not ffmpeg_location:
        raise Exception("FFmpeg n'est pas disponible.")
    
    def progress_hook(d):
        if progress_id and progress_dict is not None:
            status = d.get('status', '')
            if status == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                speed = d.get('speed', 0)
                
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100
                else:
                    percent = 0
                
                if speed > 0 and total_bytes > 0:
                    remaining_bytes = total_bytes - downloaded_bytes
                    eta_seconds = remaining_bytes / speed
                    eta_approx_min = max(0, int(eta_seconds) - 5)
                    eta_approx_max = max(0, int(eta_seconds) + 5)
                else:
                    eta_seconds = 0
                    eta_approx_min = 0
                    eta_approx_max = 0
                
                progress_dict[progress_id] = {
                    'percent': min(100, max(0, percent)),
                    'eta_seconds': eta_seconds,
                    'eta_approx_min': eta_approx_min,
                    'eta_approx_max': eta_approx_max,
                    'speed': speed,
                    'downloaded': downloaded_bytes,
                    'total': total_bytes
                }
            elif status == 'finished':
                progress_dict[progress_id] = {
                    'percent': 100,
                    'eta_seconds': 0,
                    'eta_approx_min': 0,
                    'eta_approx_max': 0,
                    'status': 'converting'
                }
    
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
        'outtmpl': base_path + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
        'ffmpeg_location': ffmpeg_location,
        'max_filesize': 500 * 1024 * 1024, # Maximum 500 MB
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("Impossible d'extraire les informations.")
                
                title = info.get('title', 'video')
                if custom_filename:
                    final_filename = sanitize_filename(custom_filename)
                else:
                    final_filename = sanitize_filename(title)
                
            except Exception as e:
                raise Exception(f"Erreur YouTube info: {str(e)}")
            
            ydl.download([url])
            cleanup_temp_files(os.path.dirname(output_path), base_path)
            
            if os.path.exists(output_path):
                final_path = output_path
            else:
                files = [f for f in os.listdir(os.path.dirname(output_path)) 
                        if f.startswith(os.path.basename(base_path)) and f.endswith('.mp3')]
                if files:
                    files_with_time = [(f, os.path.getmtime(os.path.join(os.path.dirname(output_path), f))) 
                                      for f in files]
                    files_with_time.sort(key=lambda x: x[1], reverse=True)
                    final_path = os.path.join(os.path.dirname(output_path), files_with_time[0][0])
                else:
                    raise Exception("Fichier MP3 non créé après conversion")
            
            return final_path, final_filename
    except Exception as e:
        raise Exception(f"Erreur lors du téléchargement YouTube: {str(e)}")

def download_soundcloud(url, output_path, custom_filename=None, progress_id=None, progress_dict=None, sc_cookies_file=None):
    base_path = output_path.replace('.mp3', '')
    
    try:
        ffmpeg_location = ensure_ffmpeg()
    except Exception as e:
        raise Exception(f"Erreur FFmpeg: {str(e)}")
    
    if not ffmpeg_location:
        raise Exception("FFmpeg n'est pas disponible.")
    
    def progress_hook(d):
        if progress_id and progress_dict is not None:
            status = d.get('status', '')
            if status == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                speed = d.get('speed', 0)
                
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100
                else:
                    percent = 0
                
                progress_dict[progress_id] = {
                    'percent': min(100, max(0, percent)),
                    'status': 'downloading'
                }
            elif status == 'finished':
                progress_dict[progress_id] = {
                    'percent': 100,
                    'status': 'converting'
                }
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': base_path + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'extractor_args': {
            'soundcloud': {
                'client_id': None,
            }
        },
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
        'ffmpeg_location': ffmpeg_location,
        'max_filesize': 500 * 1024 * 1024, # Maximum 500 MB
    }
    
    # Authentification SoundCloud via cookies (pour les abonnes Go+)
    if sc_cookies_file and os.path.exists(sc_cookies_file):
        ydl_opts['cookiefile'] = sc_cookies_file
        print(f"[SoundCloud] 🔓 Cookies chargés depuis : {sc_cookies_file}")
    
    # Check for search URL
    if '/search' in url and '?q=' in url:
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            query = query_params.get('q', [None])[0]
            if query:
                print(f"[SoundCloud] Detected search URL, converting to scsearch1:{query}")
                url = f"scsearch1:{query}"
                # For search results, we might get a playlist-like object. 
                # We want the first result.
                ydl_opts['noplaylist'] = True 
        except Exception as e:
            print(f"[SoundCloud] Error parsing search URL: {e}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("Impossible d'extraire les informations.")
                
                title = info.get('title', 'sound')
                duration = info.get('duration', None)  # Durée en secondes
                if custom_filename:
                    final_filename = sanitize_filename(custom_filename)
                else:
                    final_filename = sanitize_filename(title)
                
                # Détecter les prévisualisations de 30 secondes (sons payants SoundCloud Go+)
                if duration is not None and duration < 60:
                    raise Exception(f"PREVIEW_ONLY:{duration:.0f}s - Ce son est une prévisualisation SoundCloud (< 60s). Utilisez un compte Go+ avec des cookies.")
                
            except Exception as e:
                raise Exception(f"Erreur SoundCloud info: {str(e)}")
            
            ydl.download([url])
            cleanup_temp_files(os.path.dirname(output_path), base_path)
            
            if os.path.exists(output_path):
                final_path = output_path
            else:
                files = [f for f in os.listdir(os.path.dirname(output_path)) 
                        if f.startswith(os.path.basename(base_path)) and f.endswith('.mp3')]
                if files:
                    files_with_time = [(f, os.path.getmtime(os.path.join(os.path.dirname(output_path), f))) 
                                      for f in files]
                    files_with_time.sort(key=lambda x: x[1], reverse=True)
                    final_path = os.path.join(os.path.dirname(output_path), files_with_time[0][0])
                else:
                    raise Exception("Fichier MP3 non créé après conversion")
            
            return final_path, final_filename
    except Exception as e:
        raise Exception(f"Erreur lors du téléchargement SoundCloud: {str(e)}")

def download_spotify(url, output_path, custom_filename=None, progress_id=None, progress_dict=None):
    try:
        ffmpeg_location = ensure_ffmpeg()
    except Exception as e:
        raise Exception(f"Erreur FFmpeg: {str(e)}")
    
    if not ffmpeg_location:
        raise Exception("FFmpeg n'est pas disponible.")
    
    spotdl_installed = False
    try:
        import spotdl
        spotdl_installed = True
    except ImportError:
        spotdl_installed = False

    if not spotdl_installed:
        print("[Spotify] Module spotdl non trouvé, utilisation du fallback YouTube.")
        return download_spotify_fallback(url, output_path, custom_filename, progress_id, progress_dict)

    try:
        if progress_id and progress_dict is not None:
            progress_dict[progress_id] = {
                'percent': 10,
                'status': 'searching'
            }

        if os.name == 'nt':
            ffmpeg_exe = os.path.join(ffmpeg_location, 'ffmpeg.exe')
        else:
            ffmpeg_exe = os.path.join(ffmpeg_location, 'ffmpeg')

        base_path = output_path.replace('.mp3', '')

        cmd = [
            sys.executable, '-m', 'spotdl',
            url,
            '--output', UPLOAD_FOLDER,
            '--format', 'mp3',
            '--bitrate', '320k',
            '--simple-tui',
        ]
        
        from dotenv import load_dotenv
        load_dotenv()
        client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")
        if client_id and client_secret:
            cmd.extend(['--client-id', client_id, '--client-secret', client_secret])

        if os.path.exists(ffmpeg_exe):
            cmd.extend(['--ffmpeg', ffmpeg_exe])
            
        print(f"[Spotify] Exécution de la commande: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False
        )
        
        if result.returncode != 0:
            raise Exception(f"Erreur d'exécution spotdl: {result.stderr}")

        files = [
            (f, os.path.getmtime(os.path.join(UPLOAD_FOLDER, f)))
            for f in os.listdir(UPLOAD_FOLDER)
            if f.endswith('.mp3')
        ]

        if not files:
            raise Exception("Fichier téléchargé introuvable après exécution de spotdl.")

        files.sort(key=lambda x: x[1], reverse=True)
        downloaded_file = files[0][0]
        original_path = os.path.join(UPLOAD_FOLDER, downloaded_file)

        cleanup_temp_files(UPLOAD_FOLDER, base_path)

        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(original_path, output_path)

        if custom_filename:
            final_filename = sanitize_filename(custom_filename)
        else:
            final_filename = sanitize_filename(downloaded_file.replace('.mp3', ''))

        return output_path, final_filename

    except Exception as e:
        print(f"[Spotify] Erreur avec spotdl: {e}. Utilisation du fallback YouTube.")
        try:
            return download_spotify_fallback(url, output_path, custom_filename, progress_id, progress_dict)
        except Exception as e2:
            raise Exception(
                f"Erreur lors du téléchargement Spotify avec spotdl: {e}\n"
                f"Le fallback YouTube a aussi échoué: {e2}"
            )

def download_instagram(url, output_path, custom_filename=None, progress_id=None, progress_dict=None):
    base_path = output_path.replace('.mp3', '')
    
    try:
        ffmpeg_location = ensure_ffmpeg()
    except Exception as e:
        raise Exception(f"Erreur FFmpeg: {str(e)}")
    
    if not ffmpeg_location:
        raise Exception("FFmpeg n'est pas disponible.")
    
    def progress_hook(d):
        if progress_id and progress_dict is not None:
            status = d.get('status', '')
            if status == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100
                else:
                    percent = 0
                
                progress_dict[progress_id] = {
                    'percent': min(100, max(0, percent)),
                    'status': 'downloading'
                }
            elif status == 'finished':
                progress_dict[progress_id] = {
                    'percent': 100,
                    'status': 'converting'
                }
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': base_path + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'ffmpeg_location': ffmpeg_location,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [progress_hook],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("Impossible d'extraire les informations Instagram.")
                
                title = info.get('title', 'instagram_reel')
                if custom_filename:
                    final_filename = sanitize_filename(custom_filename)
                else:
                    final_filename = sanitize_filename(title)
                
            except Exception as e:
                raise Exception(f"Erreur Instagram: {str(e)}")
            
            ydl.download([url])
            cleanup_temp_files(os.path.dirname(output_path), base_path)
            
            if os.path.exists(output_path):
                final_path = output_path
            else:
                files = [f for f in os.listdir(os.path.dirname(output_path)) 
                        if f.startswith(os.path.basename(base_path)) and f.endswith('.mp3')]
                if files:
                    files_with_time = [(f, os.path.getmtime(os.path.join(os.path.dirname(output_path), f))) 
                                      for f in files]
                    files_with_time.sort(key=lambda x: x[1], reverse=True)
                    final_path = os.path.join(os.path.dirname(output_path), files_with_time[0][0])
                else:
                    raise Exception("Fichier MP3 non créé après conversion")
            
            return final_path, final_filename

    except Exception as e:
        raise Exception(f"Erreur lors du téléchargement Instagram: {str(e)}")

def download_spotify_fallback(url, output_path, custom_filename=None, progress_id=None, progress_dict=None):
    parsed = urlparse(url)
    path_parts = parsed.path.strip('/').split('/')

    if len(path_parts) < 2:
        raise Exception("URL Spotify invalide.")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"Impossible de charger la page Spotify (status {resp.status_code}).")

        html = resp.text
        title = None
        artist = None

        meta_desc = re.search(r'<meta\s+property="og:description"\s+content="([^\"]+)"', html, re.IGNORECASE)
        if meta_desc:
            desc = meta_desc.group(1)
            m = re.match(r'([^,]+),\s+[^,]*\s+by\s+([^,]+)', desc)
            if m:
                title = m.group(1).strip()
                artist = m.group(2).strip()

        if not title:
            meta_title = re.search(r'<meta\s+property="og:title"\s+content="([^\"]+)"', html, re.IGNORECASE)
            if meta_title:
                title_raw = meta_title.group(1).strip()
                separators = [' - ', ' – ', ' — ', ' ― ']
                for sep in separators:
                    if sep in title_raw:
                        parts = [p.strip() for p in title_raw.split(sep) if p.strip()]
                        if len(parts) >= 2:
                            artist = parts[0]
                            title = parts[-1]
                            break
                if not title:
                    title = title_raw

        if not artist:
            artist_match = re.search(r'"artists"\s*:\s*\[\s*\{[^\}]*"name"\s*:\s*"([^\"]+)"', html, re.IGNORECASE)
            if artist_match:
                artist = artist_match.group(1).strip()

        if not title or not artist:
             entity_match = re.search(r'Spotify\.Entity\s*=\s*({.*?});', html, re.DOTALL)
             if entity_match:
                 try:
                     data = json.loads(entity_match.group(1))
                     if 'name' in data:
                         title = data['name']
                     if 'artists' in data and len(data['artists']) > 0:
                         artist = data['artists'][0]['name']
                 except:
                     pass

        if not title:
            raise Exception("Impossible de trouver le titre de la musique.")

        search_query = f"{artist} - {title}" if artist else title
        print(f"[Spotify Fallback] Recherche sur YouTube: {search_query}")

        yt_search_url = f"ytsearch1:{search_query}"
        return download_youtube(yt_search_url, output_path, custom_filename, progress_id, progress_dict)

    except Exception as e:
        raise Exception(f"Erreur lors du fallback Spotify: {str(e)}")


# ===== MUSIC RECOGNITION FUNCTIONS =====

def parse_timecode(timecode_str, default_to_minutes=False):
    """Parse timecode in various formats to seconds"""
    try:
        timecode_str = timecode_str.strip()
        if 'h' in timecode_str.lower():
            parts = timecode_str.lower().split('h')
            if len(parts) == 2:
                hours = float(parts[0])
                minutes_part = parts[1].strip()
                if minutes_part == '':
                    return hours * 3600
                elif '.' in minutes_part or ':' in minutes_part:
                    sep = '.' if '.' in minutes_part else ':'
                    time_parts = minutes_part.split(sep)
                    if len(time_parts) == 2:
                        return hours * 3600 + float(time_parts[0]) * 60 + float(time_parts[1])
                else:
                    return hours * 3600 + float(minutes_part) * 60
        elif ':' in timecode_str:
            parts = timecode_str.split(':')
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
        elif '.' in timecode_str:
            parts = timecode_str.split('.')
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
        
        val = float(timecode_str)
        if default_to_minutes:
            return val * 60
        return val
    except ValueError:
        raise Exception(f"Format de timecode invalide: {timecode_str}")


def trim_audio(input_path, output_path, start_time=None, end_time=None):
    """Trim audio file using FFmpeg"""
    ffmpeg_location = ensure_ffmpeg()
    if not ffmpeg_location:
        raise Exception("FFmpeg n'est pas disponible.")
    
    ffmpeg_exe = os.path.join(ffmpeg_location, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    
    # -ss before -i is faster, but less accurate. 
    # -ss after -i is accurate.
    # Since we want to cut precise parts of a song, accuracy is important.
    # We use re-encoding to ensure clean cuts and avoid timestamp issues.
    
    cmd = [ffmpeg_exe]
    
    if start_time is not None:
        cmd.extend(['-ss', str(start_time)])
        
    cmd.extend(['-i', input_path])
    
    if end_time is not None:
        # If start_time is set, -to is relative to the beginning of the file (because -ss is before -i? No wait)
        # If -ss is BEFORE -i, it seeks input.
        # If -ss is AFTER -i, it decodes until start.
        
        # Let's put -ss BEFORE -i for speed, but then -to might behave differently?
        # Actually, if we use -ss before -i, the timestamps are reset to 0.
        # So if we want to stop at minute 50 of the ORIGINAL, we need to calculate duration.
        # But user says "-fin 50.00" (50th minute of the song).
        
        # If we use -ss before -i, we are seeking. The output stream starts at 0.
        # So if start is 10min and end is 50min, duration is 40min.
        # We should use -t (duration) = end - start.
        
        if start_time:
            duration = end_time - start_time
            if duration <= 0:
                raise Exception("Le temps de fin doit être supérieur au temps de début.")
            cmd.extend(['-t', str(duration)])
        else:
            cmd.extend(['-to', str(end_time)])
            
    cmd.extend(['-acodec', 'libmp3lame', '-ab', '192k', '-y', output_path])
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if not os.path.exists(output_path):
            raise Exception(f"Fichier coupé non créé: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise Exception(f"Erreur lors de la coupe audio: {error_msg}")


def extract_audio_segment(input_path, output_path, start_time, duration=10):
    """Extract audio segment using FFmpeg"""
    ffmpeg_location = ensure_ffmpeg()
    if not ffmpeg_location:
        raise Exception("FFmpeg n'est pas disponible.")
    
    ffmpeg_exe = os.path.join(ffmpeg_location, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    cmd = [ffmpeg_exe, '-ss', str(start_time), '-i', input_path, '-t', str(duration), 
           '-acodec', 'libmp3lame', '-ab', '192k', '-y', output_path]
    
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    if not os.path.exists(output_path):
        raise Exception(f"Fichier non créé: {output_path}")
    return output_path


def clean_music_title(title):
    if not title:
        return ""
    import re
    # Enlever (feat. Artist), [feat. Artist], - Radio Edit, etc.
    cleaned = re.sub(r'(?i)\(feat[^)]+\)', '', title)
    cleaned = re.sub(r'(?i)\[feat[^]]+\]', '', cleaned)
    cleaned = re.sub(r'(?i)[(-]\s*(radio edit|remix|feat\..*)\b', '', cleaned)
    return cleaned.strip()

async def search_track_links(track_name, artist_name):
    """Search for track links on various platforms"""
    links = {}
    spotify_uri = None
    
    clean_track = clean_music_title(track_name)
    clean_artist = clean_music_title(artist_name)
    
    # Try Spotify API first if credentials exist
    try:
        from dotenv import load_dotenv
        load_dotenv()
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        if client_id and client_secret:
            print(f"[Spotify] Identifiants trouvés, recherche via API...")
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            
            auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            
            query_strict = f"track:{clean_track} artist:{clean_artist}"
            results = sp.search(q=query_strict, type='track', limit=1)
            
            if not results['tracks']['items']:
                query_loose = f"{clean_artist} {clean_track}"
                print(f"[Spotify] Recherche stricte échouée, essai souple: {query_loose}")
                results = sp.search(q=query_loose, type='track', limit=1)
            
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
                links['spotify'] = track['external_urls']['spotify']
                spotify_uri = track['uri']
                # Add direct play link (URI)
                links['spotify_uri'] = spotify_uri
                print(f"[Spotify] URI trouvé: {spotify_uri}")
            else:
                print(f"[Spotify] Aucune piste trouvée via API pour {clean_track}")
        else:
            print(f"[Spotify] Pas d'identifiants (SPOTIFY_CLIENT_ID/SECRET) dans .env")
    except Exception as e:
        print(f"Erreur Spotify API: {e}")

    try:
        ffmpeg_location = ensure_ffmpeg()
        ydl_opts = {
            'quiet': True,
            'ffmpeg_location': ffmpeg_location,
            'extract_flat': True,
        }
        
        search_query = f"{clean_artist} {clean_track}" if clean_artist else clean_track
        
        # Youtube search
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
                if info and 'entries' in info and len(info['entries']) > 0:
                    links['youtube'] = f"https://www.youtube.com/watch?v={info['entries'][0]['id']}"
        except:
            pass
            
        # Fallback Spotify search link if API failed
        if 'spotify' not in links:
            links['spotify'] = f"https://open.spotify.com/search/{search_query.replace(' ', '+')}"
            
        links['soundcloud'] = f"https://soundcloud.com/search?q={search_query.replace(' ', '%20')}"
        
    except Exception as e:
        print(f"Erreur recherche liens: {e}")
        
    return links


def play_spotify_uri(uri):
    """Launch Spotify URI on local machine (Windows only)"""
    if os.name == 'nt' and uri and uri.startswith('spotify:'):
        try:
            print(f"[Spotify] Lancement de {uri}...")
            os.system(f"start {uri}")
            return True
        except Exception as e:
            print(f"[Spotify] Erreur lancement: {e}")
    return False


def download_for_recognition(url, output_path):
    """Download complete audio for recognition"""
    ffmpeg_location = ensure_ffmpeg()
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace('.mp3', '.%(ext)s'),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'quiet': False,
        'ffmpeg_location': ffmpeg_location,
        'keepvideo': False,
        'max_filesize': 500 * 1024 * 1024, # Maximum 500 MB
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"[Recognition] Téléchargement audio...")
        info = ydl.extract_info(url, download=True)
        if os.path.exists(output_path):
            print(f"[Recognition] Audio: {info.get('duration', 0)}s ({info.get('duration', 0)/60:.1f} min)")
            return output_path
        base_path = output_path.replace('.mp3', '')
        directory = os.path.dirname(output_path)
        files = [f for f in os.listdir(directory) if f.startswith(os.path.basename(base_path)) and f.endswith('.mp3')]
        if files:
            return os.path.join(directory, files[0])
        raise Exception("MP3 non créé")


def format_timecode(seconds):
    """Format seconds to H:M:S style (e.g. 1H30.14 or 07.10)"""
    try:
        seconds = int(float(seconds))
    except:
        return str(seconds)
    
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    
    if h > 0:
        return f"{h}H{m:02d}.{s:02d}"
    else:
        return f"{m:02d}.{s:02d}"


def recognize_music_from_url_sync(url, timecodes=None, progress_id=None, progress_dict=None, keep_file=False):
    """Sync wrapper for recognize_music_from_url"""
    import asyncio
    import sys
    
    # Fix for Windows "Event loop is closed" error
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    return asyncio.run(recognize_music_from_url(url, timecodes, progress_id, progress_dict, keep_file))

def validate_audio_file(file_path):
    """
    Validates an uploaded file to ensure it's a real audio file and doesn't contain malicious code.
    Returns (True, None) if valid, (False, error_message) if invalid.
    """
    if not os.path.exists(file_path):
        return False, "Fichier introuvable"

    file_size = os.path.getsize(file_path)
    if file_size > 50 * 1024 * 1024:  # 50MB max for uploaded audio
        return False, "Le fichier est trop volumineux (max 50MB)"
        
    # Check Magic Numbers (first few bytes)
    # Common audio magic numbers:
    # ID3 (MP3): 49 44 33
    # M4A: ... 66 74 79 70 4D 34 41
    # RIFF (WAV): 52 49 46 46
    # OGG: 4F 67 67 53
    # FLAC: 66 4C 61 43
    # WEBM: 1A 45 DF A3
    
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
            
            is_valid_header = False
            
            # MP3 (ID3)
            if header.startswith(b'ID3'):
                is_valid_header = True
            # MP3 (without ID3, ADTS sync word usually FF FB / FF F3)
            elif len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
                is_valid_header = True
            # WAV
            elif header.startswith(b'RIFF'):
                is_valid_header = True
            # OGG
            elif header.startswith(b'OggS'):
                is_valid_header = True
            # FLAC
            elif header.startswith(b'fLaC'):
                is_valid_header = True
            # M4A / MP4
            elif b'ftyp' in header:
                is_valid_header = True
            # WEBM / MKV
            elif header.startswith(b'\x1a\x45\xdf\xa3'):
                is_valid_header = True

            if not is_valid_header:
                return False, "Type de fichier audio non supporté ou invalide (entête incorrecte)"
                
            # Malware/PHP scanning
            # Reset pointer to scan for PHP or script tags in the first 16KB 
            # (sometimes attackers put PHP code in MP3 ID3 tags)
            f.seek(0)
            chunk = f.read(16384).lower()
            
            suspicious_patterns = [
                b'<?php',
                b'<script',
                b'system(',
                b'exec(',
                b'eval(',
                b'shell_exec('
            ]
            
            for pattern in suspicious_patterns:
                if pattern in chunk:
                    return False, "Le fichier contient des données suspectes et a été bloqué"
                    
    except Exception as e:
        return False, f"Erreur lors de la validation du fichier: {str(e)}"
        
    return True, "Fichier valide"

def recognize_music_from_file_sync(file_path, timecodes=None, progress_id=None, progress_dict=None):
    """Sync wrapper for recognize_music_from_file"""
    import asyncio
    import sys
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    return asyncio.run(recognize_music_from_file(file_path, timecodes, progress_id, progress_dict))

async def recognize_music_from_file(file_path, timecodes=None, progress_id=None, progress_dict=None):
    """Recognize music from an uploaded local file using Shazam"""
    from shazamio import Shazam
    temp_uuid = str(uuid.uuid4())
    result_to_return = {'found': False, 'message': 'Erreur inconnue'}
    
    try:
        # Default timecodes
        if not timecodes:
            timecodes = [30, 60, 90]
        
        print(f"[Recognition] Initialisation Shazam sur fichier...")
        shazam = Shazam()
        
        results = []
        print(f"[Recognition] Analyse de {len(timecodes)} timecodes...")
        
        for i, timecode in enumerate(timecodes):
            segment_path = None
            try:
                print(f"[Recognition] Traitement timecode {i+1}/{len(timecodes)}: {timecode}s")
                segment_path = os.path.join(UPLOAD_FOLDER, f"{temp_uuid}_segment_{i}.mp3")
                
                print(f"[Recognition] Extraction segment...")
                extract_audio_segment(file_path, segment_path, timecode, duration=10)
                
                print(f"[Recognition] Envoi à Shazam...")
                result = await shazam.recognize(segment_path)
                
                if os.path.exists(segment_path):
                    os.remove(segment_path)
                
                if result and 'track' in result:
                    track_info = result['track']
                    title = track_info.get('title', 'Inconnu')
                    artist = track_info.get('subtitle', 'Inconnu')
                    print(f"[Recognition] TROUVÉ: {title} - {artist}")
                    
                    results.append({
                        'timecode': timecode,
                        'formatted_timecode': format_timecode(timecode),
                        'title': title,
                        'artist': artist,
                        'shazam_url': track_info.get('url', None),
                        'cover_art': track_info.get('images', {}).get('coverart', None),
                        'raw_result': result
                    })
                    
            except Exception as e:
                print(f"[Recognition] ERREUR au timecode {timecode}s: {e}")
                if segment_path and os.path.exists(segment_path):
                    try: os.remove(segment_path)
                    except: pass
                continue
        
        if not results:
            print("[Recognition] Aucune musique trouvée.")
            result_to_return = {'found': False, 'message': 'Aucune musique reconnue dans ce fichier'}
        else:
            print(f"[Recognition] {len(results)} résultats trouvés.")
            best_result = results[0]
            
            all_tracks_links = []
            for res in results:
                links = await search_track_links(res['title'], res['artist'])
                res['links'] = links
                all_tracks_links.append(res)
            
            result_to_return = {
                'found': True,
                'results': all_tracks_links,
                'title': best_result['title'],
                'artist': best_result['artist'],
                'timecode': best_result['timecode'],
                'formatted_timecode': best_result['formatted_timecode'],
                'cover_art': best_result['cover_art'],
                'shazam_url': best_result['shazam_url'],
                'links': all_tracks_links[0]['links']
            }
        
    except Exception as e:
        print(f"[Recognition] ERREUR GLOBALE: {e}")
        for f in os.listdir(UPLOAD_FOLDER):
            if f.startswith(temp_uuid) and '_segment_' in f:
                try: os.remove(os.path.join(UPLOAD_FOLDER, f))
                except: pass
        raise e
    finally:
        # Delete original uploaded file after processing
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[Recognition] Upload supprimé: {file_path}")
            except Exception as e:
                print(f"[Recognition] Erreur suppression upload: {e}")
                
    return result_to_return


async def recognize_music_from_url(url, timecodes=None, progress_id=None, progress_dict=None, keep_file=False):
    """Recognize music from URL using Shazam"""
    from shazamio import Shazam
    temp_uuid = str(uuid.uuid4())
    temp_audio_path = os.path.join(UPLOAD_FOLDER, f"{temp_uuid}.mp3")
    final_path = None
    result_to_return = {'found': False, 'message': 'Erreur inconnue'}  # Default result
    
    try:
        # Determine source type
        if is_youtube_url(url):
            source_type = 'youtube'
        elif is_soundcloud_url(url):
            source_type = 'soundcloud'
        elif is_spotify_url(url):
            source_type = 'spotify'
        elif is_instagram_url(url):
            source_type = 'instagram'
        else:
            raise Exception("URL non supportée")
        
        # Download audio
        print(f"[Recognition] Téléchargement depuis {source_type}...")
        
        if source_type == 'youtube':
            final_path, _ = download_youtube(url, temp_audio_path, progress_id=progress_id, progress_dict=progress_dict)
        elif source_type == 'soundcloud':
            final_path, _ = download_soundcloud(url, temp_audio_path, progress_id=progress_id, progress_dict=progress_dict)
        elif source_type == 'spotify':
            final_path, _ = download_spotify(url, temp_audio_path, progress_id=progress_id, progress_dict=progress_dict)
        elif source_type == 'instagram':
            final_path, _ = download_instagram(url, temp_audio_path, progress_id=progress_id, progress_dict=progress_dict)
        else:
            # Fallback
            final_path = download_for_recognition(url, temp_audio_path)
        
        # Default timecodes
        if not timecodes:
            timecodes = [30, 60, 90]
        
        # Analyze each timecode
        print(f"[Recognition] Initialisation Shazam...")
        shazam = Shazam()
        
        results = []
        print(f"[Recognition] Analyse de {len(timecodes)} timecodes: {timecodes}")
        
        for i, timecode in enumerate(timecodes):
            segment_path = None
            try:
                print(f"[Recognition] Traitement timecode {i+1}/{len(timecodes)}: {timecode}s")
                segment_path = os.path.join(UPLOAD_FOLDER, f"{temp_uuid}_segment_{i}.mp3")
                
                # Extract segment
                print(f"[Recognition] Extraction segment vers {segment_path}")
                extract_audio_segment(final_path, segment_path, timecode, duration=10)
                
                # Recognize
                print(f"[Recognition] Envoi à Shazam...")
                result = await shazam.recognize(segment_path)
                
                # Cleanup segment
                if os.path.exists(segment_path):
                    os.remove(segment_path)
                
                if result and 'track' in result:
                    track_info = result['track']
                    title = track_info.get('title', 'Inconnu')
                    artist = track_info.get('subtitle', 'Inconnu')
                    print(f"[Recognition] TROUVÉ: {title} - {artist}")
                    
                    results.append({
                        'timecode': timecode,
                        'formatted_timecode': format_timecode(timecode),
                        'title': title,
                        'artist': artist,
                        'shazam_url': track_info.get('url', None),
                        'cover_art': track_info.get('images', {}).get('coverart', None),
                        'raw_result': result
                    })
                else:
                    print(f"[Recognition] Rien trouvé au timecode {timecode}s")
                    
            except Exception as e:
                print(f"[Recognition] ERREUR au timecode {timecode}s: {e}")
                if segment_path and os.path.exists(segment_path):
                    try:
                        os.remove(segment_path)
                    except:
                        pass
                continue
        
        # Prepare result
        if not results:
            print("[Recognition] Aucune musique trouvée via Shazam. Tentative de récupération des métadonnées de la source...")
            try:
                ydl_opts = {'quiet': True, 'extract_flat': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and info.get('title'):
                        title = info.get('title')
                        artist = info.get('artist') or info.get('uploader') or info.get('channel') or 'Inconnu'
                        
                        fallback_result = {
                            'timecode': 0,
                            'formatted_timecode': '00.00',
                            'title': title,
                            'artist': artist,
                            'shazam_url': None,
                            'cover_art': info.get('thumbnail'),
                            'raw_result': {'fallback': True}
                        }
                        results.append(fallback_result)
                        print(f"[Recognition] Fallback réussi: {title} - {artist}")
            except Exception as e:
                print(f"[Recognition] Erreur lors du fallback: {e}")

        if not results:
            print("[Recognition] Aucune musique trouvée.")
            result_to_return = {'found': False, 'message': 'Aucune musique reconnue'}
        else:
            print(f"[Recognition] {len(results)} musiques trouvées.")
            # If multiple results, return the list
            # For backward compatibility, we also return the "best" (first) result fields
            best_result = results[0]
            
            # Search links for ALL found tracks
            all_tracks_links = []
            for res in results:
                links = await search_track_links(res['title'], res['artist'])
                res['links'] = links
                all_tracks_links.append(res)
            
            result_to_return = {
                'found': True,
                'results': all_tracks_links, # New field with all results
                # Legacy fields for bot.py compatibility (uses first result)
                'title': best_result['title'],
                'artist': best_result['artist'],
                'timecode': best_result['timecode'],
                'formatted_timecode': best_result['formatted_timecode'],
                'cover_art': best_result['cover_art'],
                'shazam_url': best_result['shazam_url'],
                'links': all_tracks_links[0]['links']
            }
        
    except Exception as e:
        print(f"[Recognition] ERREUR GLOBALE: {e}")
        # Clean up segments
        for f in os.listdir(UPLOAD_FOLDER):
            if f.startswith(temp_uuid) and '_segment_' in f:
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, f))
                except:
                    pass
        raise e
    finally:
        # This executes AFTER all analyses
        if not keep_file and final_path and os.path.exists(final_path):
            print(f"[Recognition] Suppression: {final_path}")
            try:
                os.remove(final_path)
            except Exception as e:
                print(f"[Recognition] Erreur suppression: {e}")
        elif keep_file and final_path and os.path.exists(final_path):
            print(f"[Recognition] Fichier conservé: {final_path}")
    
    return result_to_return
