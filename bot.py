import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import downloader
import asyncio
import shutil

# Charger les variables d'environnement
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configuration
UPLOAD_FOLDER = 'downloads_bot'
FFMPEG_FOLDER = 'ffmpeg_local'
downloader.setup(UPLOAD_FOLDER, FFMPEG_FOLDER)

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté à Discord!')

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
        
        limit_bytes = 25 * 1024 * 1024 # 25 MB
        
        if file_size > limit_bytes:
            await status_msg.edit(content=f"Le fichier est trop volumineux ({file_size / (1024*1024):.2f} MB) pour être envoyé sur Discord.")
            # Ne pas supprimer le fichier ici, laisser l'utilisateur décider
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
                "`!find <url> -no_delete` - Garde le fichier téléchargé après analyse"
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
        
        if not result['found']:
            await status_msg.edit(content=f"❌ {result['message']}")
            return
        
        # Vérifier si on a plusieurs résultats
        if 'results' in result and len(result['results']) > 1:
            embed = discord.Embed(
                title=f"🎵 {len(result['results'])} Musiques Identifiées !",
                description=f"Voici les musiques trouvées aux différents timecodes :",
                color=discord.Color.green()
            )
            
            for res in result['results']:
                links_txt = ""
                if 'links' in res:
                    if 'youtube' in res['links']: links_txt += f"🎥 [YouTube]({res['links']['youtube']}) "
                    if 'spotify' in res['links']: links_txt += f"🎧 [Spotify]({res['links']['spotify']}) "
                    if 'soundcloud' in res['links']: links_txt += f"☁️ [SoundCloud]({res['links']['soundcloud']}) "
                if res.get('shazam_url'): links_txt += f"🔵 [Shazam]({res['shazam_url']})"
                
                embed.add_field(
                    name=f"⏱️ {res.get('formatted_timecode', f'{res['timecode']}s')}",
                    value=f"**{res['title']}**\n{res['artist']}\n{links_txt}",
                    inline=False
                )
        else:
            # Cas normal (un seul résultat)
            embed = discord.Embed(
                title="🎵 Musique Identifiée !",
                description=f"**{result['title']}**\npar {result['artist']}",
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

if __name__ == '__main__':
    if not TOKEN:
        print("Erreur: Le token Discord n'est pas défini dans le fichier .env")
    else:
        bot.run(TOKEN)
