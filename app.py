from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
import sys
import os
import uuid
import threading
import time
import json
import downloader

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'downloads'
app.config['FFMPEG_FOLDER'] = 'ffmpeg_local'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024  # 16GB max

# Configurer le module downloader
downloader.setup(app.config['UPLOAD_FOLDER'], app.config['FFMPEG_FOLDER'])

# Dictionnaire pour stocker les progressions des téléchargements
download_progress = {}

@app.route('/')
def index():
    """Page d'accueil"""
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_video():
    """Endpoint principal de conversion"""
    data = request.json
    url = data.get('url')
    custom_filename = data.get('filename')
    source_type = data.get('source_type', 'auto')
    
    if not url:
        return jsonify({'error': 'URL manquante'}), 400
    
    # Auto-détection de la source
    if source_type == 'auto':
        if downloader.is_youtube_url(url):
            source_type = 'youtube'
        elif downloader.is_soundcloud_url(url):
            source_type = 'soundcloud'
        elif downloader.is_spotify_url(url):
            source_type = 'spotify'
        elif downloader.is_instagram_url(url):
            source_type = 'instagram'
        else:
            return jsonify({'error': 'Source non reconnue. Veuillez utiliser une URL YouTube, SoundCloud, Spotify ou Instagram.'}), 400
    
    # Générer un ID unique pour suivre la progression
    progress_id = str(uuid.uuid4())
    download_progress[progress_id] = {
        'percent': 0,
        'status': 'starting'
    }
    
    def process_download():
        try:
            # Vérifier si c'est une playlist
            if downloader.is_playlist(url):
                try:
                    zip_path, zip_filename = downloader.process_playlist(url, source_type, progress_id, download_progress)
                    download_progress[progress_id] = {
                        'percent': 100,
                        'status': 'completed',
                        'file_id': os.path.basename(zip_path).replace('.zip', ''),
                        'filename': zip_filename,
                        'is_zip': True
                    }
                except Exception as e:
                    download_progress[progress_id] = {
                        'status': 'error',
                        'message': str(e)
                    }
                return

            # Traitement fichier unique
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{progress_id}.mp3')
            
            if source_type == 'youtube':
                final_path, final_filename = downloader.download_youtube(url, output_path, custom_filename, progress_id, download_progress)
            elif source_type == 'soundcloud':
                final_path, final_filename = downloader.download_soundcloud(url, output_path, custom_filename, progress_id, download_progress)
            elif source_type == 'spotify':
                final_path, final_filename = downloader.download_spotify(url, output_path, custom_filename, progress_id, download_progress)
            elif source_type == 'instagram':
                final_path, final_filename = downloader.download_instagram(url, output_path, custom_filename, progress_id, download_progress)
            else:
                raise Exception("Type de source non supporté")
            
            # Succès
            download_progress[progress_id] = {
                'percent': 100,
                'status': 'completed',
                'file_id': progress_id,
                'filename': final_filename,
                'is_zip': False
            }
            
        except Exception as e:
            print(f"Erreur de conversion: {str(e)}")
            download_progress[progress_id] = {
                'status': 'error',
                'message': str(e)
            }
            # Nettoyage en cas d'erreur
            if 'output_path' in locals() and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass

    # Lancer le téléchargement en arrière-plan
    thread = threading.Thread(target=process_download)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'progress_id': progress_id})

@app.route('/download/<file_id>')
def download_file(file_id):
    """Télécharge le fichier converti"""
    mp3_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}.mp3')
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}.zip')
    
    if os.path.exists(mp3_path):
        file_path = mp3_path
        mimetype = 'audio/mpeg'
    elif os.path.exists(zip_path):
        file_path = zip_path
        mimetype = 'application/zip'
    else:
        return jsonify({'error': 'Fichier non trouvé'}), 404
    
    # Obtenir la taille du fichier pour estimer le temps de téléchargement
    file_size = os.path.getsize(file_path)
    
    # Utiliser le nom du fichier passé en paramètre ou le nom du fichier sur disque
    requested_filename = request.args.get('filename')
    if requested_filename:
        # S'assurer que l'extension est correcte
        if not requested_filename.lower().endswith(('.mp3', '.zip')):
            ext = os.path.splitext(file_path)[1]
            requested_filename += ext
        download_name = requested_filename
    else:
        download_name = os.path.basename(file_path)
    
    # Utiliser un générateur pour streamer le fichier et le supprimer à la fin
    def generate():
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(8192) # 8KB chunks
                    if not chunk:
                        break
                    yield chunk
        finally:
            # Cette partie s'exécute après la fin du stream (ou si le client déconnecte)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Fichier supprimé après téléchargement: {file_path}")
            except Exception as e:
                print(f"Erreur lors du suppression du fichier: {e}")

    response = Response(stream_with_context(generate()), mimetype=mimetype)
    response.headers['Content-Disposition'] = f'attachment; filename="{download_name}"'
    response.headers['Content-Length'] = file_size
    return response

@app.route('/delete/<file_id>', methods=['POST'])
def delete_file(file_id):
    """Supprime un fichier du serveur"""
    mp3_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}.mp3')
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}.zip')
    
    try:
        deleted = False
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
            deleted = True
        
        if os.path.exists(zip_path):
            os.remove(zip_path)
            deleted = True
            
        if deleted:
            return jsonify({'success': True, 'message': 'Fichier supprimé'})
        else:
            return jsonify({'error': 'Fichier non trouvé'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check-progress/<progress_id>')
def check_progress(progress_id):
    """Endpoint simple pour vérifier le statut d'une conversion"""
    data = download_progress.get(progress_id)
    if data:
        return jsonify(data)
    else:
        return jsonify({'status': 'not_found'}), 404

@app.route('/progress/<progress_id>')
def progress(progress_id):
    """
    Flux SSE pour suivre la progression d'un téléchargement / conversion.
    """
    def generate():
        last_state = None
        max_wait = 300  # Maximum 5 minutes d'attente (300 * 0.5s)
        wait_count = 0

        while wait_count < max_wait:
            data = download_progress.get(progress_id)

            if not data:
                wait_count += 1
                time.sleep(0.5)
                continue

            # Comparer les états de manière plus fiable
            current_state_key = json.dumps(data, sort_keys=True)
            last_state_key = json.dumps(last_state, sort_keys=True) if last_state else None

            if current_state_key != last_state_key:
                # on envoie les données au client
                yield f"data: {json.dumps(data)}\n\n"
                last_state = data.copy() if isinstance(data, dict) else data

            # si terminé ou erreur, on envoie un dernier message et on sort
            if data.get('status') in ('completed', 'error'):
                # S'assurer que le dernier message est bien envoyé
                yield f"data: {json.dumps(data)}\n\n"
                break

            time.sleep(0.5)
            wait_count += 1

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/find', methods=['POST'])
def find_music():
    """Endpoint de reconnaissance musicale"""
    data = request.json
    url = data.get('url')
    timecodes_str = data.get('timecodes')
    do_download = data.get('download', False)
    
    if not url:
        return jsonify({'error': 'URL manquante'}), 400
        
    # Parser les timecodes
    timecodes = None
    if timecodes_str:
        try:
            # Supporte "10;20;30" ou "10,20,30"
            parts = timecodes_str.replace(',', ';').split(';')
            timecodes = [downloader.parse_timecode(tc.strip()) for tc in parts if tc.strip()]
        except Exception as e:
            return jsonify({'error': f'Format de timecode invalide: {str(e)}'}), 400
            
    progress_id = str(uuid.uuid4())
    download_progress[progress_id] = {
        'status': 'starting',
        'percent': 0,
        'message': 'Démarrage de l\'analyse...'
    }
    
    def process_identification():
        try:
            download_progress[progress_id]['status'] = 'analyzing'
            download_progress[progress_id]['message'] = 'Téléchargement et analyse en cours...'
            
            # Reconnaissance
            result = downloader.recognize_music_from_url_sync(
                url, 
                timecodes=timecodes,
                progress_id=progress_id,
                progress_dict=download_progress
            )
            
            if not result['found']:
                download_progress[progress_id] = {
                    'status': 'completed_find', # Statut spécial pour fin de recherche sans téléchargement
                    'found': False,
                    'message': result.get('message', 'Aucune musique trouvée')
                }
                return

            # Si on doit télécharger
            if do_download:
                download_progress[progress_id]['message'] = 'Musique trouvée ! Téléchargement en cours...'
                download_progress[progress_id]['found_results'] = result.get('results', [])
                
                results_to_download = result.get('results', [])
                # Si pas de liste results (vieux format), on utilise les champs top level
                if not results_to_download:
                    results_to_download = [result]
                
                downloaded_files = []
                
                for i, res in enumerate(results_to_download):
                    track_name = f"{res['artist']} - {res['title']}"
                    download_progress[progress_id]['message'] = f"Téléchargement de : {track_name}"
                    
                    # Recherche et téléchargement via YouTube
                    search_query = f"ytsearch1:{track_name} audio"
                    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{progress_id}_{i}.mp3')
                    
                    try:
                        final_path, final_filename = downloader.download_youtube(
                            search_query, 
                            output_path, 
                            custom_filename=track_name,
                            progress_id=None, # On ne met pas à jour la barre de progression globale pour chaque sous-téléchargement pour l'instant
                            progress_dict=None
                        )
                        downloaded_files.append((final_path, final_filename))
                    except Exception as e:
                        print(f"Erreur téléchargement {track_name}: {e}")
                
                if not downloaded_files:
                    raise Exception("Impossible de télécharger la musique trouvée.")
                
                # Si un seul fichier
                if len(downloaded_files) == 1:
                    final_path, final_filename = downloaded_files[0]
                    # Renommer pour avoir l'ID propre
                    clean_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{progress_id}.mp3')
                    if os.path.exists(clean_path): os.remove(clean_path)
                    os.rename(final_path, clean_path)
                    
                    download_progress[progress_id] = {
                        'status': 'completed', # Déclenche le téléchargement standard
                        'percent': 100,
                        'file_id': progress_id,
                        'filename': final_filename + ".mp3",
                        'is_zip': False,
                        'found_info': result # Pour afficher les infos
                    }
                else:
                    # Plusieures fichiers -> ZIP
                    import zipfile
                    zip_filename = f"musiques_trouvees_{progress_id}.zip"
                    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{progress_id}.zip')
                    
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for fpath, fname in downloaded_files:
                            zipf.write(fpath, fname + ".mp3")
                            try:
                                os.remove(fpath) # Nettoyage
                            except: pass
                            
                    download_progress[progress_id] = {
                        'status': 'completed',
                        'percent': 100,
                        'file_id': progress_id,
                        'filename': zip_filename,
                        'is_zip': True,
                        'found_info': result
                    }
            else:
                # Pas de téléchargement demandé, on renvoie juste les infos
                download_progress[progress_id] = {
                    'status': 'completed_find',
                    'found': True,
                    'results': result.get('results', []),
                    'message': 'Analyse terminée'
                }
                
        except Exception as e:
            print(f"Erreur find: {e}")
            download_progress[progress_id] = {
                'status': 'error',
                'message': str(e)
            }

    thread = threading.Thread(target=process_identification)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'progress_id': progress_id})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)