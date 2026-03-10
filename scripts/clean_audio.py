import os
import subprocess
import argparse
import shutil
import uuid
import json
import re
import sys
import asyncio
import urllib.request

script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from downloader import download_youtube, download_soundcloud, ensure_ffmpeg, sanitize_filename

# Mutagen pour ID3
try:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, TIT2, TPE1, APIC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("Mutagen non installé, les tag ID3 auto ne seront pas appliqués. Installez-le avec 'pip install mutagen'")

# Couleurs ANSI
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

script_dir = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FFPROBE_PATH = 'ffprobe'
DEFAULT_FFMPEG_PATH = 'ffmpeg'

if os.name == 'nt':
    DEFAULT_FFPROBE_PATH = 'ffprobe.exe'
    DEFAULT_FFMPEG_PATH = 'ffmpeg.exe'
    
local_ffprobe = os.path.join(parent_dir, 'ffmpeg_local', 'ffprobe.exe')
if os.path.exists(local_ffprobe):
    DEFAULT_FFPROBE_PATH = local_ffprobe

local_ffmpeg = os.path.join(parent_dir, 'ffmpeg_local', 'ffmpeg.exe')
if os.path.exists(local_ffmpeg):
    DEFAULT_FFMPEG_PATH = local_ffmpeg
    ffmpeg_dir = os.path.dirname(local_ffmpeg)
    os.environ["PATH"] += os.pathsep + ffmpeg_dir

# Fix pydub warning about ffmpeg not found by explicitly pointing to our ffmpeg
try:
    import pydub
    pydub.AudioSegment.converter = DEFAULT_FFMPEG_PATH
except ImportError:
    pass

async def shazam_identify(file_path):
    try:
        from shazamio import Shazam
        shazam = Shazam()
        # Timeout de 20 secondes pour éviter un blocage infini
        out = await asyncio.wait_for(shazam.recognize(file_path), timeout=20.0)
        if out and 'track' in out:
            track = out['track']
            artist = track.get('subtitle', None)
            title = track.get('title', None)
            cover = track.get('images', {}).get('coverart', None)
            return artist, title, cover
    except asyncio.TimeoutError:
        print("    └─ ⏱️ Shazam timeout (>20s), identification ignorée")
    except Exception:
        pass
    return None, None, None

def shazam_identify_sync(file_path):
    import threading
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    result = [None, None, None]
    def run():
        try:
            result[0], result[1], result[2] = asyncio.run(shazam_identify(file_path))
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=30)  # Timeout global de 30 secondes
    if t.is_alive():
        print("    └─ ⏱️ Shazam bloqué, on continue sans identification")
        return None, None, None
    return result[0], result[1], result[2]

def get_audio_info(filepath, ffprobe_path):
    """
    Retourne le bitrate d'un fichier audio en bps et son codec.
    """
    try:
        cmd = [
            ffprobe_path,
            '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name:format=bit_rate',
            '-of', 'json',
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return {"bitrate": None, "codec": "inconnu"}
        
        data = json.loads(result.stdout)
        bitrate = None
        codec = "inconnu"
        
        if 'format' in data and 'bit_rate' in data['format']:
            try:
                bitrate = int(data['format']['bit_rate'])
            except:
                pass
                
        if 'streams' in data and len(data['streams']) > 0:
            if 'codec_name' in data['streams'][0]:
                codec = data['streams'][0]['codec_name'].lower()
        
        return {"bitrate": bitrate, "codec": codec}
    except Exception as e:
        return {"bitrate": None, "codec": "inconnu"}

def analyze_frequency_cutoff(filepath, ffmpeg_path):
    """
    Analyse si le fichier contient des fréquences au-dessus de 16.5 kHz et des pics saturés.
    Retourne:
        - diff_db: la différence de volume moyen (base - highpass)
        - is_fake: True si c'est probablement un rip basse qualité/YouTube
        - is_clipping: True si le fichier sature sévèrement l'analogique (0 dB clips)
    """
    try:
        # Phase 1: Vraiment tout le spectre
        cmd_base = [ffmpeg_path, '-i', filepath, '-af', 'volumedetect', '-f', 'null', '-']
        res_base = subprocess.run(cmd_base, stderr=subprocess.PIPE, text=True)
        out_base = res_base.stderr
        
        mean_base = None
        clipping_samples = 0
        
        m_mean = re.search(r'mean_volume:\s+([\-\d\.]+)\s+dB', out_base)
        m_clip = re.search(r'histogram_0db:\s+(\d+)', out_base)
        
        # Test additionnel si ça écrit +0db ou -0db, certains FFmpeg v5 changent la syntaxe
        if not m_clip:
            m_clip = re.search(r'histogram_.\?0db:\s+(\d+)', out_base)
            
        if m_mean:
            mean_base = float(m_mean.group(1))
        if m_clip:
            clipping_samples = int(m_clip.group(1))

        # Heuristique clipping en PREMIER car indépendante de mean_base !
        is_clipping = False
        # Les musiques modernes (surtout rap/pop) sont masterisées très fort au "plafond" (0dB)
        # Il est normal d'avoir beaucoup d'échantillons à 0dB. On ne supprime plus sur ce seul critère.
        if clipping_samples > 500000:
            pass # On n'active plus le is_clipping pour éviter les faux positifs sur les bons fichiers

        if mean_base is None:
            return None, False, is_clipping

        # Phase 2: Uniquement au-dessus de 16.5 kHz
        cmd_high = [ffmpeg_path, '-i', filepath, '-af', 'highpass=f=16500,volumedetect', '-f', 'null', '-']
        res_high = subprocess.run(cmd_high, stderr=subprocess.PIPE, text=True)
        out_high = res_high.stderr
        
        mean_high = None
        m2 = re.search(r'mean_volume:\s+([\-\d\.]+)\s+dB', out_high)
        if m2:
            mean_high = float(m2.group(1))

        if mean_high is None:
            return None, False, is_clipping

        # Si l'énergie est très faible après le filtre (-60dB ou moins)
        # Mais attention avec la différence: plus la diff est grande, plus y a eu coupure
        diff_db = abs(mean_base - mean_high)
        
        # Heuristique faux 320
        is_fake = False
        if mean_high < -65.0 or diff_db > 45.0:
            is_fake = True

        return diff_db, is_fake, is_clipping

    except Exception as e:
        return None, False, False

def clean_audio_files(directory, min_bitrate_kbps=320, generate_spectrogram=False):
    min_bitrate_bps = min_bitrate_kbps * 1000
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    log_file_path = os.path.join(parent_dir, "data", "deleted_music_log.txt")
    unfound_file_path = os.path.join(parent_dir, "data", "musiques_introuvables_hq.txt")
    
    if not shutil.which(DEFAULT_FFPROBE_PATH) and not os.path.exists(DEFAULT_FFPROBE_PATH):
        print(f"{Colors.RED}Erreur: FFprobe introuvable.{Colors.RESET}")
        return

    if not shutil.which(DEFAULT_FFMPEG_PATH) and not os.path.exists(DEFAULT_FFMPEG_PATH):
        print(f"{Colors.RED}Erreur: FFmpeg introuvable.{Colors.RESET}")
        return

    print(f"\n{Colors.BLUE}=== Analyse spectrale & Bitrate DJ ==={Colors.RESET}")
    print(f"Cible: {directory}\n")
    
    deleted_count = 0
    scanned_count = 0

    files_to_scan = []
    if os.path.isfile(directory):
        files_to_scan.append(directory)
        directory = os.path.dirname(directory)
    else:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.mp3', '.wav')):
                    files_to_scan.append(os.path.join(root, file))

    for file_path in files_to_scan:
        file = os.path.basename(file_path)
        scanned_count += 1
        
        # Test 0 : Heuristique visuelle du nom de fichier (Sources YouTube identifiables directes)
        file_lower = file.lower()
        if "music video" in file_lower or "4k" in file_lower or "2k" in file_lower or "official video" in file_lower:
            print(f"{Colors.RED}[❌ SUPPRIMÉ - NOM DE FICHIER 'YOUTUBE']{Colors.RESET} {file}")
            try:
                os.remove(file_path)
                deleted_count += 1
                name_without_ext = os.path.splitext(file)[0]
                dir_name = os.path.dirname(os.path.abspath(file_path))
                with open(log_file_path, "a", encoding="utf-8") as log_file:
                    log_file.write(f"{dir_name}|{name_without_ext}\n")
            except Exception as e:
                print(f"    └─ {Colors.RED}Erreur suppression: {e}{Colors.RESET}")
            continue

        audio_info = get_audio_info(file_path, DEFAULT_FFPROBE_PATH)
        bitrate_bps = audio_info["bitrate"]
        codec = audio_info["codec"]
        
        diff_db, is_fake, is_clipping = analyze_frequency_cutoff(file_path, DEFAULT_FFMPEG_PATH)
        
        bitrate_kbps = bitrate_bps / 1000.0 if bitrate_bps is not None else 0
        bitrate_display = f"{bitrate_kbps:.0f} kbps" if bitrate_kbps > 0 else "INCONNU kbps"
        
        should_delete = False
        reason = ""
        
        if is_clipping:
            should_delete = True
            reason = "DANGER CLIPPING MAX 0.0dB"
            
        elif is_fake:
            should_delete = True
            reason = "FAUX 320 / COUPURE HF YOUTUBE"

        else:
            # Vérification via la Matrice stricte de l'utilisateur
            # WAV / AIFF : >= 1400 kbps (PCM) - tolérance -30 kbps, pas de plafond (lossless)
            if "pcm" in codec or codec in ["wav", "aiff"]:
                if bitrate_kbps > 0 and bitrate_kbps < 1370:
                    should_delete = True
                    reason = f"WAV BITRATE TROP FAIBLE ({bitrate_display})"
            # FLAC : ~600+ kbps - pas de plafond (lossless)
            elif codec == "flac":
                if bitrate_kbps > 0 and bitrate_kbps < 570:
                    should_delete = True
                    reason = f"FLAC BITRATE TROP FAIBLE ({bitrate_display})"
            # MP3 : valide entre 290 et 360 kbps (320 ±40 kbps de tolérance)
            # En dessous = mauvaise qualité, au-dessus = probablement upsampleé/transcodé
            elif codec == "mp3":
                if bitrate_kbps > 0 and bitrate_kbps < 290:
                    should_delete = True
                    reason = f"MP3 NON OPTIMAL ({bitrate_display} < 290kbps)"
                elif bitrate_kbps > 360:
                    should_delete = True
                    reason = f"MP3 SUSPECT - UPSAMPLE ({bitrate_display} > 360kbps)"
            # AAC / M4A : valide entre 226 et 286 kbps (256 ±30 kbps de tolérance)
            elif codec in ["aac", "m4a", "alac"]:
                if bitrate_kbps > 0 and bitrate_kbps < 226:
                    should_delete = True
                    reason = f"AAC NON EXCELLENT ({bitrate_display} < 226kbps)"
                elif bitrate_kbps > 286:
                    should_delete = True
                    reason = f"AAC SUSPECT - UPSAMPLE ({bitrate_display} > 286kbps)"
            else:
                # Fichiers sans bitrate lu, on juge sur la fréquence (is_fake deja passé)
                pass

        # Affichage du rapport
        if should_delete:
            print(f"{Colors.RED}[❌ SUPPRIMÉ - {reason}]{Colors.RESET} {file} [{codec.upper()}]")
            if diff_db is not None:
                print(f"    └─ Bitrate: {bitrate_kbps:.0f} kbps | Chute HF: {diff_db:.1f} dB")
                
            shazam_artist, shazam_title, shazam_cover = shazam_identify_sync(file_path)
            shazam_str = ""
            if shazam_title and shazam_artist:
                print(f"    └─ {Colors.GREEN}🎵 Shazam: {shazam_artist} - {shazam_title}{Colors.RESET}")
                shazam_str = f"|{shazam_artist}|{shazam_title}|{shazam_cover}"
            
            try:
                if generate_spectrogram:
                    # Création du dossier Spectrogramme_Analyse s'il n'existe pas
                    spec_dir = os.path.join(os.path.dirname(file_path), "Spectrogramme_Analyse")
                    os.makedirs(spec_dir, exist_ok=True)
                    
                    spec_path = os.path.join(spec_dir, f"SPECTRE_{os.path.splitext(file)[0]}.png")
                    cmd_spec = [
                        DEFAULT_FFMPEG_PATH, '-y', '-i', file_path, 
                        '-lavfi', 'showspectrumpic=s=800x400', spec_path
                    ]
                    subprocess.run(cmd_spec, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                os.remove(file_path)
                deleted_count += 1
                
                name_without_ext = os.path.splitext(file)[0]
                dir_name = os.path.dirname(os.path.abspath(file_path))
                with open(log_file_path, "a", encoding="utf-8") as log_file:
                    log_file.write(f"{dir_name}|{name_without_ext}{shazam_str}\n")
            except Exception as e:
                print(f"    └─ {Colors.RED}Erreur suppression: {e}{Colors.RESET}")
        else:
            diff_text = f"| Chute HF: {diff_db:.1f} dB" if diff_db is not None else ""
            print(f"{Colors.GREEN}[✅ {codec.upper()} VALIDE]{Colors.RESET} {file} ({bitrate_display} {diff_text})")

    print(f"\n{Colors.BLUE}Terminé ! {scanned_count} fichiers analysés, {deleted_count} fichiers supprimés.{Colors.RESET}")
    
    # Etape 2: Télécharger en priorité via SoundCloud pour la qualité (puis failover sur YouTubeHQ)
    if deleted_count > 0:
        print(f"\n{Colors.BLUE}Tentative de retéléchargement HQ pour {deleted_count} fichiers...{Colors.RESET}")
        
        # Initialiser le downloader avec les chemins absolus pour éviter des problèmes de CWD
        from downloader import setup as downloader_setup
        parent_dir = os.path.dirname(script_dir)
        abs_ffmpeg_dir = os.path.join(parent_dir, 'ffmpeg_local')
        abs_downloads_dir = os.path.join(parent_dir, 'downloads')
        downloader_setup(abs_downloads_dir, abs_ffmpeg_dir)
        
        # Créer le dossier HQ dans le répertoire PARENT du dossier analysé
        # Ex: C:\Music\DJ\toutes les musique - Copie1 => C:\Music\DJ\toutes les musique - Copie1 [HQ]
        scanned_dir = directory if os.path.isdir(directory) else os.path.dirname(os.path.abspath(directory))
        parent_dir = os.path.dirname(scanned_dir)
        folder_name = os.path.basename(scanned_dir)
        hq_output_dir = os.path.join(parent_dir, f"{folder_name} [HQ]")
        os.makedirs(hq_output_dir, exist_ok=True)
        print(f"{Colors.BLUE}\n\U0001f4c1 Dossier HQ créé : {hq_output_dir}{Colors.RESET}")
        
        # -- Authentification SoundCloud (optionnel, pour compte Go+) --
        # Exportez vos cookies SoundCloud au format Netscape depuis votre navigateur
        # (ex: avec l'extension "Get cookies.txt LOCALLY") et sauvegardez-les ici :
        sc_cookies_file = os.path.join(parent_dir, 'soundcloud_cookies.txt')
        if os.path.exists(sc_cookies_file):
            print(f"{Colors.GREEN}\U0001f513 Cookies SoundCloud trouvés, accès Go+ activé{Colors.RESET}")
        else:
            sc_cookies_file = None
            print(f"{Colors.YELLOW}\u26a0️  Pas de cookies SoundCloud (prévisualisations 30s seront ignorées){Colors.RESET}")
            print(f"    Pour activer le mode Go+, exportez vos cookies vers : {os.path.join(parent_dir, 'soundcloud_cookies.txt')}")
        
        unfound = []
        with open(log_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Vider le log principal pour les prochaines exécutions
        open(log_file_path, "w", encoding="utf-8").close()
            
        for line in lines:
            line = line.strip()
            if not line: continue
            
            parts = line.split('|')
            s_artist, s_title, s_cover = None, None, None
            
            if len(parts) >= 5:
                original_dir = parts[0]
                track_name = parts[1]
                s_artist = parts[2]
                s_title = parts[3]
                s_cover = parts[4]
            elif len(parts) >= 2:
                original_dir = parts[0]
                track_name = parts[1]
            else:
                track_name = parts[0]
                original_dir = directory if os.path.isdir(directory) else os.path.dirname(os.path.abspath(directory))
            
            # Formater le nom de recherche
            if s_artist and s_title:
                clean_search_name = f"{s_artist} - {s_title}"
            else:
                # Nettoyage auto du nom issu des logs s'il contenait des cochonneries (pour la recherche)
                clean_search_name = track_name
                # Supprimer [Official Video], (4K), HD, etc.
                expressions_to_remove = [
                    r'(?i)\[official\s*(music\s*)?video\]',
                    r'(?i)\(official\s*(music\s*)?video\)',
                    r'(?i)official\s*(music\s*)?video',
                    r'(?i)\(official\)', r'(?i)\[official\]',
                    r'(?i)\[4k\]', r'(?i)\(4k\)', r'(?i)4k resolution',
                    r'(?i)\[2k\]', r'(?i)\(2k\)', 
                    r'(?i)\[1080p\]', r'(?i)\(1080p\)',
                    r'(?i)music\s*video',
                    r'(?i)official\s*audio',
                    r'(?i)lyrics?\s*video'
                ]
                for exp in expressions_to_remove:
                    clean_search_name = re.sub(exp, '', clean_search_name)
                
                # Nettoyer les espaces en double
                clean_search_name = re.sub(r'\s+', ' ', clean_search_name).strip()
                # Nettoyer le tiret de début/fin isolé s'il l'était
                clean_search_name = clean_search_name.strip('- ')

            progress_id = str(uuid.uuid4())
            # Nom propre sans préfixe 'upgrade_' pour que le fichier soit facilement retrouvable
            clean_filename = sanitize_filename(clean_search_name)
            # Sauvegarder dans le dossier HQ parent (et non dans l'original)
            output_path = os.path.join(hq_output_dir, f"{clean_filename}.mp3")
            print(f"\n  📁 Dossier de destination : {hq_output_dir}")
            print(f"  💾 Nom du fichier : {clean_filename}.mp3")
            
            success = False
            final_audio_path = None

            
            # Essai 1: SoundCloud (Meilleur bitrate natif, ou vrai 128 Opus qui bat YouTube)
            print(f"\nRecherche : {clean_search_name} (Source: SoundCloud)")
            sc_preview_detected = False
            try:
                final_path, final_filename = download_soundcloud(
                    f"scsearch1:{clean_search_name}", 
                    output_path, 
                    custom_filename=clean_filename, 
                    progress_id=progress_id, 
                    progress_dict={},
                    sc_cookies_file=sc_cookies_file
                )
                print(f"{Colors.GREEN}[\u2705 RETELECHARGÉ HQ] {final_path}{Colors.RESET}")
                success = True
                final_audio_path = final_path
            except Exception as e:
                err_str = str(e)
                if 'PREVIEW_ONLY' in err_str:
                    print(f"    \u2514\u2500 {Colors.YELLOW}\u23f3 Prévisualisation 30s détectée sur SoundCloud, passage à YouTube...{Colors.RESET}")
                    sc_preview_detected = True
                else:
                    print(f"    └─ Non trouvé/Erreur SC, essai YouTube...")
                # Essai 2: YouTube avec la configuration bestaudio existante de ton app
                try:
                    final_path, final_filename = download_youtube(
                        f"ytsearch1:{clean_search_name} audio", 
                        output_path, 
                        custom_filename=clean_filename, 
                        progress_id=progress_id, 
                        progress_dict={}
                    )
                    print(f"{Colors.GREEN}[✅ RETÉLÉCHARGÉ YT HQ] {final_path}{Colors.RESET}")
                    success = True
                    final_audio_path = final_path
                except Exception as e2:
                    print(f"{Colors.RED}[ERREUR FINAL] Impossible de télécharger '{track_name}'{Colors.RESET}")
            
            if success and final_audio_path and os.path.exists(final_audio_path) and MUTAGEN_AVAILABLE:
                # Appliquer des ID3 Tags propres (Artist - Title.mp3 => Artist tag / Title tag)
                try:
                    audio = EasyID3(final_audio_path)
                except:
                    # Création du header ID3 s'il n'existe pas
                    import mutagen
                    tag_base = mutagen.File(final_audio_path, easy=True)
                    if tag_base is None:
                        # Si ce n'est pas vu comme un medium taggable (ex: mp3 vide), on force un ID3 complet
                        audio = mutagen.id3.ID3()
                        audio.save(final_audio_path)
                        audio = EasyID3(final_audio_path)
                    else:
                        tag_base.add_tags()
                        audio = tag_base
                        
                # Ex: "upgrade_David Guetta - Titanium" => split sur le "-"
                if s_artist and s_title:
                    audio['artist'] = s_artist
                    audio['title'] = s_title
                else:
                    base_track = clean_search_name
                    parts_dash = base_track.split(" - ", 1)
                    if len(parts_dash) == 2:
                        artist = parts_dash[0].strip()
                        title = parts_dash[1].strip()
                        audio['artist'] = artist
                        audio['title'] = title
                    else:
                        audio['title'] = base_track.strip()
                    
                audio.save()
                
                # Injection de la pochette d'album si Shazam l'a trouvée
                if s_cover and s_cover != "None":
                    try:
                        import mutagen.id3
                        audio_tags = mutagen.id3.ID3(final_audio_path)
                        req = urllib.request.Request(s_cover, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req) as response:
                            img_data = response.read()
                        audio_tags.add(mutagen.id3.APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3, desc=u'Cover',
                            data=img_data
                        ))
                        audio_tags.save(v2_version=3)
                        print(f"     └─ {Colors.GREEN}Tags ID3 (Shazam + Cover Art) mis à jour proprement !{Colors.RESET}")
                    except Exception as e:
                        print(f"     └─ {Colors.YELLOW}Tags ID3 ajoutés (erreur cover: {e}){Colors.RESET}")
                else:
                    print(f"     └─ {Colors.GREEN}Tags ID3 mis à jour proprement !{Colors.RESET}")

            if not success:
                unfound.append(track_name)
        
        if unfound:
            with open(unfound_file_path, "a", encoding="utf-8") as ufile:
                for u in unfound:
                    ufile.write(f"{u}\n")
            print(f"\n{Colors.YELLOW}Attention: {len(unfound)} morceaux n'ont pas pu être téléchargés.{Colors.RESET}")
            print(f"Leur nom a été stocké dans: {unfound_file_path}")
            print("Pensez à les chercher sur des plateformes DJ dédiées (Beatport, Bandcamp, Juno, Qobuz).")

if __name__ == "__main__":
    # Correction d'affichage pour les couleurs ANSI sous Windows
    if os.name == 'nt':
        os.system('color')
        
    parser = argparse.ArgumentParser(description="Analyse spectrale DJ: Supprime les faux 320 kbps (rips YouTube) et retélécharge.")
    parser.add_argument("dossier", nargs='?', default=".", help="Dossier ou fichier à analyser")
    parser.add_argument("--min", type=int, default=320, help="Bitrate minimum déclaré en kbps (défaut: 320)")
    parser.add_argument("--spec", action="store_true", help="Génère un spectrogramme visuel (.png) des fichiers supprimés")
    
    args = parser.parse_args()
    
    target_path = os.path.abspath(args.dossier)
    if not os.path.exists(target_path):
        print(f"{Colors.RED}Erreur: Le chemin spécifié n'existe pas : {target_path}{Colors.RESET}")
    else:
        clean_audio_files(target_path, args.min, args.spec)
