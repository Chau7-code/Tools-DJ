from fastapi import FastAPI, Request, BackgroundTasks, Form, Body, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import sys
import os
import uuid
import asyncio
import time
import json
from contextlib import asynccontextmanager
import downloader
import mellangeur
from dotenv import load_dotenv

load_dotenv()

async def periodic_cleanup():
    """Tâche de fond tournant toutes les heures pour nettoyer les fichiers vieux de plus de 2 heures (7200s)."""
    while True:
        try:
            await asyncio.to_thread(downloader.clean_old_files, UPLOAD_FOLDER, 7200)
            await asyncio.to_thread(downloader.clean_old_files, 'downloads_bot', 7200)
        except Exception as e:
            print(f"Erreur dans la tâche de nettoyage automatique: {e}")
        await asyncio.sleep(3600)  # Attendre 1 heure

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage de l'application: lance la tâche de nettoyage arrière-plan
    cleanup_task = asyncio.create_task(periodic_cleanup())
    yield
    # Extinction de l'application: annule la tâche
    cleanup_task.cancel()

app = FastAPI(title="Conversion Musique API", description="API de conversion de musique asynchrone", lifespan=lifespan)

UPLOAD_FOLDER = 'downloads'
FFMPEG_FOLDER = 'ffmpeg_local'

downloader.setup(UPLOAD_FOLDER, FFMPEG_FOLDER)

download_progress = {}

# Make sure templates folder exists
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Page d'accueil"""
    default_client_id = os.getenv("SPOTIPY_CLIENT_ID", "")
    default_client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "client_id": default_client_id,
        "client_secret": default_client_secret
    })

@app.post("/convert")
async def convert_video(background_tasks: BackgroundTasks, data: dict = Body(...)):
    """Endpoint principal de conversion"""
    url = data.get('url')
    custom_filename = data.get('filename')
    source_type = data.get('source_type', 'auto')
    
    if not url:
        return JSONResponse(status_code=400, content={'error': 'URL manquante'})
    
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
            return JSONResponse(status_code=400, content={'error': 'Source non reconnue. Veuillez utiliser une URL YouTube, SoundCloud, Spotify ou Instagram.'})
    
    progress_id = str(uuid.uuid4())
    download_progress[progress_id] = {
        'percent': 0,
        'status': 'starting'
    }
    
    def process_download_sync():
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
            output_path = os.path.join(UPLOAD_FOLDER, f'{progress_id}.mp3')
            
            if source_type == 'youtube':
                final_path, final_filename = downloader.download_youtube(url, output_path, custom_filename, progress_id, download_progress)
            elif source_type == 'soundcloud':
                final_path, final_filename = downloader.download_soundcloud(url, output_path, custom_filename, progress_id, download_progress)
            elif source_type == 'spotify':
                # Use fallback if spotdl isn't strictly necessary or used previously
                final_path, final_filename = downloader.download_spotify_fallback(url, output_path, custom_filename, progress_id, download_progress)
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

    async def run_process():
        await asyncio.to_thread(process_download_sync)

    background_tasks.add_task(run_process)
    
    return {'success': True, 'progress_id': progress_id}

@app.get("/download/{file_id}")
async def download_file(file_id: str, background_tasks: BackgroundTasks, filename: str = Query(None)):
    """Télécharge le fichier converti"""
    mp3_path = os.path.join(UPLOAD_FOLDER, f'{file_id}.mp3')
    zip_path = os.path.join(UPLOAD_FOLDER, f'{file_id}.zip')
    
    if os.path.exists(mp3_path):
        file_path = mp3_path
        media_type = 'audio/mpeg'
    elif os.path.exists(zip_path):
        file_path = zip_path
        media_type = 'application/zip'
    else:
        return JSONResponse(status_code=404, content={'error': 'Fichier non trouvé'})
        
    requested_filename = filename
    if requested_filename:
        if not requested_filename.lower().endswith(('.mp3', '.zip')):
            ext = os.path.splitext(file_path)[1]
            requested_filename += ext
        download_name = requested_filename
    else:
        download_name = os.path.basename(file_path)

    # background_tasks is cleaner than a stream_with_context block for file cleanup
    # FileResponse manages streaming natively, the task runs when the response completes
    def cleanup_file():
        try:
            # Let the file finish transferring before removing (Windows locks handling)
            time.sleep(1) 
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Fichier supprimé après téléchargement: {file_path}")
        except Exception as e:
            print(f"Erreur lors de la suppression du fichier: {e}")

    background_tasks.add_task(cleanup_file)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'}
    )

@app.post("/delete/{file_id}")
async def delete_file(file_id: str):
    """Supprime un fichier du serveur"""
    mp3_path = os.path.join(UPLOAD_FOLDER, f'{file_id}.mp3')
    zip_path = os.path.join(UPLOAD_FOLDER, f'{file_id}.zip')
    
    try:
        deleted = False
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
            deleted = True
        
        if os.path.exists(zip_path):
            os.remove(zip_path)
            deleted = True
            
        if deleted:
            return {'success': True, 'message': 'Fichier supprimé'}
        else:
            return JSONResponse(status_code=404, content={'error': 'Fichier non trouvé'})
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.get("/check-progress/{progress_id}")
async def check_progress(progress_id: str):
    """Endpoint simple pour vérifier le statut d'une conversion"""
    data = download_progress.get(progress_id)
    if data:
        return data
    else:
        return JSONResponse(status_code=404, content={'status': 'not_found'})

@app.get("/progress/{progress_id}")
async def progress(progress_id: str, request: Request):
    """
    Flux SSE pour suivre la progression d'un téléchargement / conversion.
    """
    async def event_generator():
        last_state = None
        # Max wait: ~5 minutes -> 600 * 0.5s
        max_wait = 600
        wait_count = 0

        while wait_count < max_wait:
            if await request.is_disconnected():
                print(f"Client disconnected SSE for {progress_id}")
                break

            data = download_progress.get(progress_id)

            if not data:
                wait_count += 1
                await asyncio.sleep(0.5)
                continue

            current_state_key = json.dumps(data, sort_keys=True)
            last_state_key = json.dumps(last_state, sort_keys=True) if last_state else None

            if current_state_key != last_state_key:
                yield f"data: {json.dumps(data)}\n\n"
                last_state = data.copy() if isinstance(data, dict) else data

            if data.get('status') in ('completed', 'error'):
                yield f"data: {json.dumps(data)}\n\n"
                break

            await asyncio.sleep(0.5)
            wait_count += 1

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream", 
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/find")
async def find_music(background_tasks: BackgroundTasks, data: dict = Body(...)):
    """Endpoint de reconnaissance musicale"""
    url = data.get('url')
    timecodes_str = data.get('timecodes')
    do_download = data.get('download', False)
    
    if not url:
        return JSONResponse(status_code=400, content={'error': 'URL manquante'})
        
    timecodes = None
    if timecodes_str:
        try:
            parts = timecodes_str.replace(',', ';').split(';')
            timecodes = [downloader.parse_timecode(tc.strip()) for tc in parts if tc.strip()]
        except Exception as e:
            return JSONResponse(status_code=400, content={'error': f'Format de timecode invalide: {str(e)}'})
            
    progress_id = str(uuid.uuid4())
    download_progress[progress_id] = {
        'status': 'starting',
        'percent': 0,
        'message': 'Démarrage de l\'analyse...'
    }
    
    def process_identification_sync():
        try:
            download_progress[progress_id]['status'] = 'analyzing'
            download_progress[progress_id]['message'] = 'Téléchargement et analyse en cours...'
            
            result = downloader.recognize_music_from_url_sync(
                url, 
                timecodes=timecodes,
                progress_id=progress_id,
                progress_dict=download_progress
            )
            
            if not result['found']:
                download_progress[progress_id] = {
                    'status': 'completed_find',
                    'found': False,
                    'message': result.get('message', 'Aucune musique trouvée')
                }
                return

            if do_download:
                download_progress[progress_id]['message'] = 'Musique trouvée ! Téléchargement en cours...'
                download_progress[progress_id]['found_results'] = result.get('results', [])
                
                results_to_download = result.get('results', [])
                if not results_to_download:
                    results_to_download = [result]
                
                downloaded_files = []
                
                for i, res in enumerate(results_to_download):
                    track_name = f"{res['artist']} - {res['title']}"
                    download_progress[progress_id]['message'] = f"Téléchargement de : {track_name}"
                    
                    search_query = f"ytsearch1:{track_name} audio"
                    output_path = os.path.join(UPLOAD_FOLDER, f'{progress_id}_{i}.mp3')
                    
                    try:
                        final_path, final_filename = downloader.download_youtube(
                            search_query, 
                            output_path, 
                            custom_filename=track_name,
                            progress_id=None,
                            progress_dict=None
                        )
                        downloaded_files.append((final_path, final_filename))
                    except Exception as e:
                        print(f"Erreur téléchargement {track_name}: {e}")
                
                if not downloaded_files:
                    raise Exception("Impossible de télécharger la musique trouvée.")
                
                if len(downloaded_files) == 1:
                    final_path, final_filename = downloaded_files[0]
                    clean_path = os.path.join(UPLOAD_FOLDER, f'{progress_id}.mp3')
                    if os.path.exists(clean_path): os.remove(clean_path)
                    os.rename(final_path, clean_path)
                    
                    download_progress[progress_id] = {
                        'status': 'completed',
                        'percent': 100,
                        'file_id': progress_id,
                        'filename': final_filename + ".mp3",
                        'is_zip': False,
                        'found_info': result
                    }
                else:
                    import zipfile
                    zip_filename = f"musiques_trouvees_{progress_id}.zip"
                    zip_path = os.path.join(UPLOAD_FOLDER, f'{progress_id}.zip')
                    
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for fpath, fname in downloaded_files:
                            zipf.write(fpath, fname + ".mp3")
                            try:
                                os.remove(fpath)
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

    async def run_identification():
        await asyncio.to_thread(process_identification_sync)

    background_tasks.add_task(run_identification)
    
    return {'success': True, 'progress_id': progress_id}


@app.post("/mix-playlists")
async def mix_playlists_route(data: dict = Body(...)):
    client_id = data.get('client_id')
    client_secret = data.get('client_secret')
    playlist_urls = data.get('playlist_urls', [])
    
    playlist_urls = [url for url in playlist_urls if url.strip()]

    if not client_id or not client_secret:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Identifiants manquants'})
        
    if not playlist_urls:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Aucune playlist fournie'})

    try:
        new_url = await asyncio.to_thread(mellangeur.process_playlists, client_id, client_secret, playlist_urls)
        return {'success': True, 'new_url': new_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)