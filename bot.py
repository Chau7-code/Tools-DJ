import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import downloader
import asyncio
import uuid
import random
import string
import requests
import sys
import subprocess

def upload_to_transfer_api(file_path, title="Fichiers partagés"):
    """
    Uploads a file to GoFile API if it exceeds the Discord size limit.
    Returns the download URL if successful, or None if failed.
    """
    try:
        # Step 1: Get the best server available
        server_req = requests.get("https://api.gofile.io/servers")
        server_req.raise_for_status()
        server_data = server_req.json()
        
        if server_data.get('status') != 'ok':
            print(f"[ERROR] GoFile server request failed: {server_data}")
            return None
            
        server = server_data['data']['servers'][0]['name']
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"
        
        # Step 2: Upload the file
        print(f"[GoFile] Uploading to {server}...")
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            response = requests.post(upload_url, files=files)
            response.raise_for_status()
            
            result = response.json()
            if result.get('status') == 'ok':
                return result['data']['downloadPage']
            else:
                print(f"[ERROR] GoFile upload failed: {result}")
                return None
            
    except Exception as e:
        print(f"[ERROR] Upload to GoFile API failed: {e}")
        return None

# Charger les variables d'environnement
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configuration
UPLOAD_FOLDER = 'downloads_bot'
INSTALL_FOLDER = os.path.join(UPLOAD_FOLDER, 'musique_find')
FFMPEG_FOLDER = 'ffmpeg_local'
downloader.setup(UPLOAD_FOLDER, FFMPEG_FOLDER)
os.makedirs(INSTALL_FOLDER, exist_ok=True)

# Stockage en mémoire des résultats de recherche
FIND_HISTORY = {}


# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté à Discord!')

@bot.command(name='help')
async def help_command(ctx):
    """Affiche la liste des commandes disponibles."""
    embed = discord.Embed(
        title="🤖 Guide du Bot Musique",
        description="Voici la liste de toutes les commandes disponibles :",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📥 Convertir & Télécharger",
        value=(
            "`!convert <url>` - Convertit un lien en MP3 (Youtube, Spotify, Soundcloud, Instagram)\n"
            "`!convert <url> -debut X -fin Y` - Télécharge un extrait spécifique\n"
            "`!convert <url>` (avec une playlist) - Télécharge toute la playlist en ZIP"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔍 Rechercher (Shazam)",
        value=(
            "`!find <url>` - Identifie la musique dans une vidéo/audio\n"
            "`!find <url> -t <timecodes>` - Analyse à un moment précis (ex: `1.30`)\n"
            "`!install -u <uid> <numero>` - Installe une musique trouvée par `!find`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎙️ Lecture Vocale",
        value=(
            "`!play <url>` - Joue une musique dans le salon vocal\n"
            "`!play -u <uid> <numero>` - Joue une musique trouvée par `!find`\n"
            "`!stop` - Arrête la musique en cours\n"
            "`!exit` - Déconnecte le bot du salon"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Autres",
        value=(
            "`!help` - Affiche ce message d'aide\n"
            "`!reboot` - Redémarre le bot et l'interface web"
        ),
        inline=False
    )
    
    embed.set_footer(text="Profitez de votre musique ! 🎵")
    await ctx.send(embed=embed)

@bot.command(name='convert')
async def convert(ctx, url: str, *args):
    # Vérifier si l'utilisateur demande de l'aide
    if url in ['-h', '-help', '--help']:
        embed = discord.Embed(
            title="🤖 Présentation du Bot Musique",
            description="Ce bot vous permet de télécharger et convertir des musiques depuis plusieurs plateformes directement sur Discord.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🛠️ Fonctionnalités",
            value=(
                "• **Téléchargement direct** : Convertit les liens en fichiers MP3.\n"
                "• **Support Playlists** : Télécharge les playlists complètes et les envoie sous forme de fichier ZIP.\n"
                "• **Organisation** : Envoie automatiquement les fichiers dans le salon `#musique`.\n"
                "• **Découpage** : Utilisez `-debut` et `-fin` pour couper l'audio."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🌍 Plateformes Supportées",
            value=(
                "• **YouTube** (Vidéos & Playlists)\n"
                "• **SoundCloud** (Tracks & Sets)\n"
                "• **Spotify** (Tracks & Playlists)\n"
                "• **Instagram** (Reels)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📝 Utilisation",
            value=(
                "`!convert <url>`\n"
                "`!convert <url> -debut 1.30 -fin 2.45` (Coupe de 1m30 à 2m45)\n"
                "`!convert <url> -debut 10` (Commence à 10 min)"
            ),
            inline=False
        )
        
        embed.set_footer(text="Profitez de votre musique ! 🎵")
        await ctx.send(embed=embed)
        return

    # Parser les arguments de découpage
    start_time = None
    end_time = None
    
    if args:
        for i, arg in enumerate(args):
            if arg in ['-debut', '--start'] and i + 1 < len(args):
                try:
                    # default_to_minutes=True car l'utilisateur veut que "10" soit 10 minutes
                    start_time = downloader.parse_timecode(args[i+1], default_to_minutes=True)
                except Exception as e:
                    await ctx.send(f"❌ Format de temps invalide pour -debut: {e}")
                    return
            elif arg in ['-fin', '--end'] and i + 1 < len(args):
                try:
                    end_time = downloader.parse_timecode(args[i+1], default_to_minutes=True)
                except Exception as e:
                    await ctx.send(f"❌ Format de temps invalide pour -fin: {e}")
                    return

    # Vérifier si on est dans le bon channel ou rediriger
    target_channel_name = "musique"
    target_channel = discord.utils.get(ctx.guild.channels, name=target_channel_name)
    
    if not target_channel:
        await ctx.send(f"Le salon '{target_channel_name}' n'existe pas. Veuillez le créer.")
        return

    # Message de confirmation
    status_msg = await ctx.send(f"Traitement de l'URL : {url} ...")

    # Dictionnaire de progression (non utilisé pour l'affichage temps réel ici pour simplifier)
    progress_dict = {}
    progress_id = "bot_task"

    try:
        # Exécuter le téléchargement dans un thread séparé pour ne pas bloquer le bot
        loop = asyncio.get_event_loop()
        
        # Déterminer la source
        source_type = 'auto'
        if downloader.is_youtube_url(url):
            source_type = 'youtube'
        elif downloader.is_soundcloud_url(url):
            source_type = 'soundcloud'
        elif downloader.is_spotify_url(url):
            source_type = 'spotify'
        elif downloader.is_instagram_url(url):
            source_type = 'instagram'
        else:
            await status_msg.edit(content="URL non supportée.")
            return

        await status_msg.edit(content=f"Téléchargement en cours ({source_type})...")

        if downloader.is_playlist(url):
            if start_time is not None or end_time is not None:
                await status_msg.edit(content="❌ Le découpage n'est pas supporté pour les playlists.")
                return
                
            # Playlist
            zip_path, zip_filename = await loop.run_in_executor(
                None, 
                lambda: downloader.process_playlist(url, source_type, progress_id, progress_dict)
            )
            file_path = zip_path
            filename = zip_filename + ".zip"
        else:
            # Fichier unique
            output_path = os.path.join(UPLOAD_FOLDER, f"{progress_id}.mp3")
            
            if source_type == 'youtube':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_youtube(url, output_path, None, progress_id, progress_dict))
            elif source_type == 'soundcloud':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_soundcloud(url, output_path, None, progress_id, progress_dict))
            elif source_type == 'spotify':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_spotify(url, output_path, None, progress_id, progress_dict))
            elif source_type == 'instagram':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_instagram(url, output_path, None, progress_id, progress_dict))
            
            file_path = final_path
            filename = final_filename + ".mp3"
            
            # Appliquer le découpage si demandé
            if start_time is not None or end_time is not None:
                await status_msg.edit(content="✂️ Découpage du fichier audio...")
                trimmed_path = os.path.join(UPLOAD_FOLDER, f"{progress_id}_trimmed.mp3")
                try:
                    await loop.run_in_executor(None, lambda: downloader.trim_audio(file_path, trimmed_path, start_time, end_time))
                    
                    # Remplacer le fichier original par le fichier coupé
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    file_path = trimmed_path
                    
                except Exception as e:
                    await status_msg.edit(content=f"❌ Erreur lors du découpage: {e}")
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return

        # Vérifier que le fichier existe
        if not os.path.exists(file_path):
            await status_msg.edit(content=f"Erreur: Le fichier téléchargé n'a pas été trouvé: {file_path}")
            return
        
        print(f"[DEBUG] Fichier trouvé: {file_path}")
        
        # Vérifier la taille du fichier (limite Discord ~8MB sans nitro, on met une limite safe à 25MB pour les serveurs boostés ou on prévient)
        try:
            file_size = os.path.getsize(file_path)
            print(f"[DEBUG] Taille du fichier: {file_size / (1024*1024):.2f} MB")
        except OSError as e:
            await status_msg.edit(content=f"Erreur lors de la lecture du fichier: {str(e)}")
            if os.path.exists(file_path):
                os.remove(file_path)
            return
        
        # Vérifier la taille du fichier (Discord limite à 25MB gratuit, on met une limite safe à 24MB)
        limit_bytes = 24 * 1024 * 1024 # 24 MB
        
        if file_size > limit_bytes:
            await status_msg.edit(content=f"Le fichier est très volumineux ({file_size / (1024*1024):.2f} MB). Upload vers GoFile en cours... ⏳")
            
            # Utiliser la fonction d'upload API
            try:
                download_url = await loop.run_in_executor(None, lambda: upload_to_transfer_api(file_path, title=f"Conversion: {filename}"))
                
                if download_url:
                    await target_channel.send(
                        f"🎶 **Conversion demandée par {ctx.author.mention}**\n\n"
                        f"⚠️ Le fichier dépasse la limite Discord ({file_size / (1024*1024):.2f} MB).\n"
                        f"📁 Voici le lien sécurisé pour le télécharger (via GoFile) :\n"
                        f"🔗 {download_url}"
                    )
                    await status_msg.edit(content="✅ Fichier envoyé via lien de transfert !")
                else:
                    await status_msg.edit(content=f"❌ Le fichier est trop volumineux ({file_size / (1024*1024):.2f} MB) et l'envoi vers le service de transfert a échoué.")
            except Exception as e:
                print(f"[ERROR] Exception during transfer upload: {e}")
                await status_msg.edit(content=f"❌ Erreur lors de l'envoi vers le service de transfert: {e}")

        else:
            await status_msg.edit(content="Envoi du fichier dans le salon musique...")
            print(f"[DEBUG] Envoi vers le salon: {target_channel.name}")
            print(f"[DEBUG] Nom du fichier: {filename}")
            print(f"[DEBUG] Demandé par: {ctx.author.mention}")
            
            try:
                # Envoyer le fichier
                sent_message = await target_channel.send(
                    f"Conversion demandée par {ctx.author.mention}", 
                    file=discord.File(file_path, filename=filename)
                )
                print(f"[DEBUG] Message envoyé avec succès! ID: {sent_message.id}")
                await status_msg.edit(content="Fichier envoyé avec succès !")
            except discord.errors.HTTPException as http_error:
                error_msg = f"Erreur HTTP lors de l'envoi: {http_error.status} - {http_error.text}"
                print(f"[ERROR] {error_msg}")
                await status_msg.edit(content=error_msg)
            except discord.errors.Forbidden as forbidden_error:
                error_msg = f"Permission refusée: Le bot n'a pas les permissions pour envoyer des fichiers dans #{target_channel.name}"
                print(f"[ERROR] {error_msg}")
                await status_msg.edit(content=error_msg)
            except Exception as send_error:
                error_msg = f"Erreur lors de l'envoi du fichier: {str(send_error)}"
                print(f"[ERROR] {error_msg}")
                await status_msg.edit(content=error_msg)

        # Nettoyage
        if os.path.exists(file_path):
            print(f"[DEBUG] Nettoyage du fichier: {file_path}")
            os.remove(file_path)

    except Exception as e:
        print(f"[ERROR] Exception globale: {str(e)}")
        import traceback
        traceback.print_exc()
        await status_msg.edit(content=f"Erreur lors de la conversion : {str(e)}")
        # Nettoyage en cas d'erreur
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

@bot.command(name='find')
async def find_music(ctx, url: str = None, *args):
    """Identifie une musique depuis une URL en utilisant Shazam"""
    
    # Vérifier si l'utilisateur demande de l'aide
    if url in ['-h', '-help', '--help', None]:
        embed = discord.Embed(
            title="🎵 Reconnaissance Musicale",
            description="Identifie une musique depuis une URL en utilisant Shazam et renvoie les liens vers différentes plateformes.",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="🌍 Plateformes Supportées",
            value=(
                "• **YouTube**\n"
                "• **SoundCloud**\n"
                "• **Spotify**\n"
                "• **Instagram**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📝 Utilisation",
            value=(
                "`!find <url>` - Analyse aux positions par défaut (30s, 60s, 90s)\n"
                "`!find <url> -t <timecodes>` - Analyse aux timecodes spécifiés\n"
                "`!find <url> -t <timecodes>` - Analyse aux timecodes spécifiés\n"
                "`!find <url> -no_delete` - Garde le fichier téléchargé après analyse\n"
                "`!install -u <uid> <numero>` - Installe une musique trouvée"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⏱️ Format des Timecodes",
            value=(
                "• Secondes: `90`\n"
                "• MM.SS: `19.30` (19 min 30 sec)\n"
                "• HH.MM.SS: `1.00.00` (1 heure)\n"
                "• Heures: `1h`, `1h07`, `2H30`\n"
                "• Heures + MM.SS: `1h11.30`\n"
                "• HH:MM:SS: `1:30:45`\n"
                "• Multiples: `19.30;1.00.00;1h11.30`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📌 Exemples",
            value=(
                "`!find https://youtube.com/watch?v=...`\n"
                "`!find https://instagram.com/reel/... -t 15`\n"
                "`!find <url> -t 19.30;1.00.00;1h11.30`"
            ),
            inline=False
        )
        
        embed.set_footer(text="Trouvez vos musiques préférées ! 🎶")
        await ctx.send(embed=embed)
        return
    
    # Parser les arguments pour extraire les timecodes et l'option no_delete
    timecodes = None
    keep_file = False
    
    if args:
        # Chercher l'option -no_delete
        if '-no_delete' in args or '--no-delete' in args:
            keep_file = True
        
        # Chercher l'option -t ou --time
        for i, arg in enumerate(args):
            if arg in ['-t', '--time'] and i + 1 < len(args):
                timecode_str = args[i + 1]
                try:
                    # Parser les timecodes séparés par des points-virgules
                    timecode_parts = timecode_str.split(';')
                    timecodes = [downloader.parse_timecode(tc.strip()) for tc in timecode_parts]
                except Exception as e:
                    await ctx.send(f"❌ Erreur de format des timecodes: {str(e)}")
                    return
                break
    
    # Vérifier si le salon #musique existe
    target_channel_name = "musique"
    target_channel = discord.utils.get(ctx.guild.channels, name=target_channel_name)
    
    if not target_channel:
        await ctx.send(f"Le salon '{target_channel_name}' n'existe pas. Veuillez le créer.")
        return
    
    # Message de confirmation
    status_msg = await ctx.send(f"🔍 Analyse de l'URL : {url} ...")
    
    try:
        # Exécuter la reconnaissance dans un thread séparé pour ne pas bloquer Discord
        loop = asyncio.get_event_loop()
        
        await status_msg.edit(content="⬇️ Téléchargement de l'audio complet...")
        
        # Appeler la fonction de reconnaissance dans un executor pour éviter de bloquer
        result = await loop.run_in_executor(
            None,
            lambda: downloader.recognize_music_from_url_sync(url, timecodes, keep_file=keep_file)
        )
        
        # Générer un UID pour cette recherche
        search_uid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        
        if not result['found']:
            await status_msg.edit(content=f"❌ {result['message']}")
            return
        
        # Stocker les résultats
        results_list = result.get('results', [result])
        FIND_HISTORY[search_uid] = results_list
        
        # Vérifier si on a plusieurs résultats
        if 'results' in result and len(result['results']) > 1:
            embed = discord.Embed(
                title=f"🎵 {len(result['results'])} Musiques Identifiées ! (UID: {search_uid})",
                description=f"Utilisez `!install -u {search_uid} <numero>` pour télécharger.",
                color=discord.Color.green()
            )
            
            for i, res in enumerate(result['results']):
                links_txt = ""
                if 'links' in res:
                    if 'youtube' in res['links']: links_txt += f"🎥 [YouTube]({res['links']['youtube']}) "
                    if 'spotify' in res['links']: links_txt += f"🎧 [Spotify]({res['links']['spotify']}) "
                    if 'soundcloud' in res['links']: links_txt += f"☁️ [SoundCloud]({res['links']['soundcloud']}) "
                if res.get('shazam_url'): links_txt += f"🔵 [Shazam]({res['shazam_url']})"
                
                embed.add_field(
                    name=f"#{i+1} - ⏱️ {res.get('formatted_timecode', f'{res['timecode']}s')}",
                    value=f"**{res['title']}**\n{res['artist']}\n{links_txt}",
                    inline=False
                )
        else:
            # Cas normal (un seul résultat)
            embed = discord.Embed(
                title=f"🎵 Musique Identifiée ! (UID: {search_uid})",
                description=f"**{result['title']}**\npar {result['artist']}\n\nUtilisez `!install -u {search_uid} 1` pour télécharger.",
                color=discord.Color.green()
            )
            
            # Ajouter l'image de couverture si disponible
            if result.get('cover_art'):
                embed.set_thumbnail(url=result['cover_art'])
            
            # Ajouter les liens trouvés
            links_text = ""
            if 'links' in result and result['links']:
                if 'youtube' in result['links']:
                    links_text += f"🎥 [YouTube]({result['links']['youtube']})\n"
                if 'spotify' in result['links']:
                    links_text += f"🎧 [Spotify]({result['links']['spotify']})\n"
                if 'soundcloud' in result['links']:
                    links_text += f"☁️ [SoundCloud]({result['links']['soundcloud']})\n"
                if result.get('shazam_url'):
                    links_text += f"🔵 [Shazam]({result['shazam_url']})\n"
                
                # Tenter de lancer sur Spotify localement
                if 'spotify_uri' in result['links']:
                    try:
                        # On lance dans un thread séparé pour ne pas bloquer
                        await loop.run_in_executor(None, lambda: downloader.play_spotify_uri(result['links']['spotify_uri']))
                        embed.set_footer(text=f"Demandé par {ctx.author.name} • 🚀 Lancé sur Spotify !")
                    except Exception as e:
                        print(f"Erreur lancement Spotify: {e}")
                        embed.set_footer(text=f"Demandé par {ctx.author.name}")
                else:
                    embed.set_footer(text=f"Demandé par {ctx.author.name}")
            else:
                embed.set_footer(text=f"Demandé par {ctx.author.name}")
            
            if links_text:
                embed.add_field(
                    name="🔗 Liens",
                    value=links_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="🔗 Liens",
                    value="Aucun lien trouvé",
                    inline=False
                )
            
            # Ajouter le timecode où la musique a été trouvée
            embed.add_field(
                name="⏱️ Trouvé à",
                value=f"{result.get('formatted_timecode', f'{result['timecode']}s')}",
                inline=True
            )
        
        await status_msg.delete()
        await target_channel.send(f"Reconnaissance demandée par {ctx.author.mention}", embed=embed)
        
    except Exception as e:
        await status_msg.edit(content=f"❌ Erreur lors de la reconnaissance : {str(e)}")

# ===== COMMANDES MUSIQUE VOCAL =====

@bot.command(name='play')
async def play(ctx, *args):
    """Joue de la musique depuis une URL dans le salon vocal"""
    
    # Gestion de l'aide
    if args and args[0] in ['-h', '-help', '--help']:
        embed = discord.Embed(
            title="🎵 Aide Commande Play",
            description="Joue de la musique depuis une URL directement dans votre salon vocal.",
            color=discord.Color.green()
        )
        embed.add_field(
            name="🌍 Plateformes Supportées",
            value="• **YouTube**\n• **SoundCloud**\n• **Spotify**\n• **Instagram**",
            inline=False
        )
        embed.add_field(
            name="📝 Utilisation",
            value=(
                "`!play <url>` - Joue la musique de l'URL\n"
                "`!play -u <uid>` - Joue toute la liste des résultats trouvés\n"
                "`!play -u <uid> <numero>` - Joue une musique spécifique de la liste\n"
                "`!stop` - Arrête la musique\n"
                "`!exit` - Déconnecte le bot"
            ),
            inline=False
        )
        embed.set_footer(text="Ambiancez votre salon vocal ! 🎤")
        await ctx.send(embed=embed)
        return

    # Vérifier si l'utilisateur est dans un salon vocal
    if not ctx.author.voice:
        await ctx.send("❌ Vous devez être connecté à un salon vocal pour utiliser cette commande.")
        return

    channel = ctx.author.voice.channel
    
    # Se connecter au salon vocal si nécessaire
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)
        
    voice_client = ctx.voice_client
    
    # Si déjà en train de jouer, arrêter
    if voice_client.is_playing():
        voice_client.stop()

    # Analyse des arguments
    url = None
    tracks_to_play = []
    
    if '-u' in args:
        try:
            u_index = args.index('-u')
            if u_index + 1 < len(args):
                uid = args[u_index + 1]
                
                if uid not in FIND_HISTORY:
                    await ctx.send(f"❌ UID '{uid}' introuvable ou expiré.")
                    return
                
                results = FIND_HISTORY[uid]
                
                # Vérifier si un index spécifique est demandé
                track_index = None
                if u_index + 2 < len(args) and args[u_index + 2].isdigit():
                    track_index = int(args[u_index + 2])
                
                if track_index is not None:
                    # Jouer une seule piste
                    if 1 <= track_index <= len(results):
                        tracks_to_play = [results[track_index - 1]]
                    else:
                        await ctx.send(f"❌ Numéro de piste invalide. Choisissez entre 1 et {len(results)}.")
                        return
                else:
                    # Jouer toute la liste (playlist)
                    tracks_to_play = results
                    
        except Exception as e:
            await ctx.send(f"❌ Erreur d'analyse des arguments: {e}")
            return
    elif args:
        # Cas classique : URL directe
        url = args[0]
        # On crée un objet "track" fictif pour uniformiser le traitement
        tracks_to_play = [{'url': url, 'title': 'Musique', 'artist': 'Inconnu'}]
    else:
        await ctx.send("❌ Veuillez spécifier une URL ou un UID.")
        return

    if not tracks_to_play:
        await ctx.send("❌ Aucune musique à jouer.")
        return

    # Fonction récursive pour jouer la liste
    async def play_next_track(track_list, index):
        if index >= len(track_list):
            await ctx.send("✅ Playlist terminée.")
            return
            
        track = track_list[index]
        
        # Déterminer l'URL
        play_url = track.get('url') # Cas URL directe
        
        # Cas résultat !find
        if not play_url:
            if 'links' in track and track['links']:
                if 'youtube' in track['links']: play_url = track['links']['youtube']
                elif 'soundcloud' in track['links']: play_url = track['links']['soundcloud']
                elif 'spotify' in track['links']: play_url = track['links']['spotify']
            
            if not play_url:
                # Fallback recherche
                search_query = f"{track.get('artist', '')} - {track.get('title', '')}"
                play_url = f"ytsearch1:{search_query}"

        status_msg = await ctx.send(f"⬇️ Préparation de : **{track.get('title', 'Musique')}** ({index+1}/{len(track_list)})...")
        
        try:
            loop = asyncio.get_event_loop()
            
            # ID unique pour ce téléchargement
            play_id = str(uuid.uuid4())
            output_path = os.path.join(UPLOAD_FOLDER, f"play_{play_id}.mp3")
            
            # Téléchargement
            final_path = None
            final_filename = track.get('title', 'Musique')
            
            # Détection source (simple)
            source_type = 'auto'
            if downloader.is_youtube_url(play_url): source_type = 'youtube'
            elif downloader.is_soundcloud_url(play_url): source_type = 'soundcloud'
            elif downloader.is_spotify_url(play_url): source_type = 'spotify'
            elif downloader.is_instagram_url(play_url): source_type = 'instagram'
            
            # Exécution téléchargement
            if source_type == 'youtube':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_youtube(play_url, output_path))
            elif source_type == 'soundcloud':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_soundcloud(play_url, output_path))
            elif source_type == 'spotify':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_spotify(play_url, output_path))
            elif source_type == 'instagram':
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_instagram(play_url, output_path))
            else:
                # Fallback YouTube search
                final_path, final_filename = await loop.run_in_executor(None, lambda: downloader.download_youtube(play_url, output_path))

            if not final_path or not os.path.exists(final_path):
                await status_msg.edit(content="❌ Erreur: Fichier audio non trouvé.")
                # Passer au suivant
                await play_next_track(track_list, index + 1)
                return
                
            # Jouer le fichier
            ffmpeg_path = downloader.get_ffmpeg_exe_path()
            
            def after_playing(error):
                if error:
                    print(f"Erreur de lecture: {error}")
                
                # Nettoyage
                try:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                except:
                    pass
                
                # Jouer le suivant
                if index + 1 < len(track_list):
                    future = asyncio.run_coroutine_threadsafe(play_next_track(track_list, index + 1), loop)
                    try:
                        future.result()
                    except:
                        pass
                    
            source = discord.FFmpegPCMAudio(final_path, executable=ffmpeg_path)
            voice_client.play(source, after=after_playing)
            
            await status_msg.edit(content=f"▶️ En train de jouer : **{final_filename}**")
            
        except Exception as e:
            await status_msg.edit(content=f"❌ Erreur : {str(e)}")
            # Essayer le suivant
            await play_next_track(track_list, index + 1)

    # Lancer la lecture de la première piste
    await play_next_track(tracks_to_play, 0)

@bot.command(name='stop')
async def stop(ctx):
    """Arrête la musique en cours"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏹️ Musique arrêtée.")
    else:
        await ctx.send("Aucune musique n'est en cours de lecture.")

@bot.command(name='exit')
async def exit_voice(ctx):
    """Déconnecte le bot du salon vocal"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Déconnexion du salon vocal.")
    else:
        await ctx.send("Le bot n'est pas connecté à un salon vocal.")

@bot.command(name='install')
async def install(ctx, *args):
    """Installe une musique trouvée avec !find"""
    
    # Vérifier si l'utilisateur demande de l'aide
    if args and args[0] in ['-h', '-help', '--help']:
        embed = discord.Embed(
            title="⬇️ Aide Commande Install",
            description="Télécharge et installe une musique trouvée précédemment avec la commande `!find`.",
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="📝 Utilisation",
            value=(
                "`!install -u <uid> <numero>`\n"
                "Exemple: `!install -u ABCD 1`"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔍 Comment obtenir l'UID ?",
            value="L'UID est affiché dans le titre des résultats de la commande `!find` (ex: `UID: ABCD`).",
            inline=False
        )
        
        embed.set_footer(text="Constituez votre bibliothèque musicale ! 💾")
        await ctx.send(embed=embed)
        return
    
    # Parser les arguments
    uid = None
    track_index = 1
    
    if '-u' in args:
        try:
            u_index = args.index('-u')
            if u_index + 1 < len(args):
                uid = args[u_index + 1]
                
                # Chercher l'index de la piste (le prochain argument qui est un nombre)
                if u_index + 2 < len(args) and args[u_index + 2].isdigit():
                    track_index = int(args[u_index + 2])
        except:
            pass
            
    if not uid:
        await ctx.send("❌ Vous devez spécifier un UID avec `-u <uid>`. Utilisez `!find` d'abord.")
        return
        
    if uid not in FIND_HISTORY:
        await ctx.send(f"❌ UID '{uid}' introuvable ou expiré.")
        return
        
    results = FIND_HISTORY[uid]
    
    if track_index < 1 or track_index > len(results):
        await ctx.send(f"❌ Numéro de piste invalide. Choisissez entre 1 et {len(results)}.")
        return
        
    track = results[track_index - 1]
    
    # Trouver la meilleure URL de téléchargement
    download_url = None
    source_type = 'auto'
    
    if 'links' in track and track['links']:
        if 'youtube' in track['links']:
            download_url = track['links']['youtube']
            source_type = 'youtube'
        elif 'soundcloud' in track['links']:
            download_url = track['links']['soundcloud']
            source_type = 'soundcloud'
        elif 'spotify' in track['links']:
            download_url = track['links']['spotify']
            source_type = 'spotify'
            
    if not download_url:
        # Fallback: Recherche YouTube avec titre et artiste
        search_query = f"{track['artist']} - {track['title']}"
        download_url = f"ytsearch1:{search_query}"
        source_type = 'youtube'
        
    status_msg = await ctx.send(f"⬇️ Installation de **{track['title']}** ...")
    
    try:
        loop = asyncio.get_event_loop()
        
        # Vérifier l'espace disque (10 GB limit)
        limit_bytes = 10 * 1024 * 1024 * 1024 # 10 GB
        downloader.check_and_clean_folder(INSTALL_FOLDER, limit_bytes)
        
        # Nom du fichier
        safe_title = downloader.sanitize_filename(f"{track['artist']} - {track['title']}")
        output_filename = f"{safe_title}.mp3"
        output_path = os.path.join(INSTALL_FOLDER, output_filename)
        
        # Vérifier si déjà téléchargé
        if os.path.exists(output_path):
             await status_msg.edit(content=f"✅ Fichier déjà installé : **{output_filename}**")
             await ctx.send(file=discord.File(output_path))
             return

        # Téléchargement
        final_path = None
        
        if source_type == 'youtube':
            final_path, _ = await loop.run_in_executor(None, lambda: downloader.download_youtube(download_url, output_path))
        elif source_type == 'soundcloud':
            final_path, _ = await loop.run_in_executor(None, lambda: downloader.download_soundcloud(download_url, output_path))
        elif source_type == 'spotify':
            final_path, _ = await loop.run_in_executor(None, lambda: downloader.download_spotify(download_url, output_path))
            
        if final_path and os.path.exists(final_path):
            await status_msg.edit(content=f"✅ Installation terminée : **{output_filename}**")
            
            # Envoyer le fichier
            try:
                await ctx.send(file=discord.File(final_path))
            except Exception as e:
                await ctx.send(f"⚠️ Fichier installé mais trop gros pour Discord ({os.path.getsize(final_path)/(1024*1024):.2f} MB).")
        else:
            await status_msg.edit(content="❌ Erreur lors du téléchargement.")
            
    except Exception as e:
        await status_msg.edit(content=f"❌ Erreur : {str(e)}")


@bot.command(name='reboot')
async def reboot(ctx):
    """Redémarre le bot et l'interface web"""
    
    await ctx.send("🔄 Redémarrage en cours... (Le bot sera indisponible quelques instants)")
    
    try:
        # 1. Tuer le processus app.py existant (Flask)
        # On utilise wmic pour trouver et tuer le processus par ligne de commande
        # car on veut éviter d'installer psutil juste pour ça
        subprocess.run('wmic process where "CommandLine like \'%app.py%\'" call terminate', shell=True)
        
        # 2. Relancer app.py dans une nouvelle fenêtre
        subprocess.Popen(f'start {sys.executable} app.py', shell=True)
        
        # 3. Relancer bot.py (ce script) dans une nouvelle fenêtre
        subprocess.Popen(f'start {sys.executable} bot.py', shell=True)
        
        # 4. Quitter le processus actuel
        await bot.close()
        sys.exit(0)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur lors du redémarrage: {str(e)}")

if __name__ == '__main__':
    if not TOKEN:
        print("Erreur: Le token Discord n'est pas défini dans le fichier .env")
    else:
        bot.run(TOKEN)
