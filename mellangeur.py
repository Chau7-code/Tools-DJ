import spotipy
from spotipy.oauth2 import SpotifyOAuth
import random
import os
import sys

def get_playlist_id(url):
    """Extracts playlist ID from a Spotify URL."""
    if "spotify.com" in url:
        parts = url.split("/")
        # format: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
        for i, part in enumerate(parts):
            if part == "playlist":
                return parts[i+1].split("?")[0]
    return url # Return as is if it looks like an ID

def process_playlists(client_id, client_secret, playlist_urls, redirect_uri="http://127.0.0.1:8888/callback"):
    """
    Main logic to process playlists.
    Returns the new playlist URL or raises an exception.
    """
    scope = "playlist-modify-public playlist-modify-private"

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        open_browser=True
    ))

    user_id = sp.current_user()['id']
    all_track_uris = []
    
    print("\n--- Récupération des morceaux ---")
    
    for url in playlist_urls:
        if not url.strip(): continue
        try:
            playlist_id = get_playlist_id(url)
            # Get playlist name for better logs
            pl_details = sp.playlist(playlist_id, fields="name")
            print(f"Traitement de : {pl_details['name']}...")
            
            # Get playlist tracks (handle pagination)
            try:
                results = sp.playlist_items(playlist_id)
                tracks = results['items']
                while results['next']:
                    results = sp.next(results)
                    tracks.extend(results['items'])
            except Exception as e:
                if "404" in str(e):
                    if 'pt=' in url:
                        raise Exception(f"La playlist '{url}' est privée et utilise un lien spécial (pt=...). Veuillez d'abord la rendre publique dans Spotify pour la mélanger.")
                    else:
                        raise Exception(f"La playlist '{url}' est introuvable ou privée (Erreur 404). Vérifiez le lien ou rendez-la publique.")
                raise e
            
            count_before = len(all_track_uris)
            for item in tracks:
                if item.get('track') and item['track'].get('uri'):
                    all_track_uris.append(item['track']['uri'])
            
            print(f"  -> +{len(all_track_uris) - count_before} morceaux ajoutés.")
            
        except Exception as e:
            print(f"  Erreur lors de la lecture de {url}: {e}")
            # We continue even if one fails
            continue

    if not all_track_uris:
        raise Exception("Aucune piste valide trouvée dans les playlists fournies.")
        
    print(f"\nTotal: {len(all_track_uris)} morceaux récupérés.")

    # Shuffle
    print("Mélange global des morceaux...")
    random.shuffle(all_track_uris)
    
    # New playlist name
    new_name = f"Mélange de {len(playlist_urls)} playlists"
    
    # Create new playlist
    print(f"Création de la nouvelle playlist '{new_name}'...")
    new_playlist = sp.user_playlist_create(user_id, new_name, public=True)
    new_playlist_id = new_playlist['id']
    
    # Add tracks in batches of 100 (Spotify API limit)
    print("Ajout des morceaux dans la nouvelle playlist...")
    
    for i in range(0, len(all_track_uris), 100):
        batch = all_track_uris[i:i+100]
        sp.playlist_add_items(new_playlist_id, batch)
        print(f"  Progression : {min(i+100, len(all_track_uris))}/{len(all_track_uris)}")
        
    return new_playlist['external_urls']['spotify']

def main():
    print("--- Mélangeur de Playlist Spotify (Multi-Sources) ---")
    
    # Check for credentials
    client_id = os.getenv("SPOTIPY_CLIENT_ID", "3c4217ec0e04475790086e67b7161527")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "70f352025190408a9218c901388b4f65")
    
    if not client_id or not client_secret:
        print("\nATTENTION: Identifiants Spotify manquants.")
        print("Veuillez définir les variables d'environnement SPOTIPY_CLIENT_ID et SPOTIPY_CLIENT_SECRET.")
        print("Ou entrez-les ici (ils ne seront pas sauvegardés) :")
        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()
        if not client_id or not client_secret:
            print("Erreur: Identifiants requis.")
            return

    # Input loop for multiple playlists
    playlist_urls = []
    print("\nEntrez les URL des playlists Spotify à mélanger.")
    print("Appuyez sur Entrée sur une ligne vide pour terminer.")
    while True:
        url = input(f"URL de la playlist #{len(playlist_urls) + 1}: ").strip()
        if not url:
            break
        playlist_urls.append(url)
    
    if not playlist_urls:
        print("Aucune URL fournie.")
        return

    try:
        new_url = process_playlists(client_id, client_secret, playlist_urls)
        print("\nSuccès ! Votre méga-playlist mélangée est prête.")
        print(f"Nouvelle URL: {new_url}")
        
    except Exception as e:
        print(f"Une erreur est survenue: {e}")

if __name__ == "__main__":
    main()