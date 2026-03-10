import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
import json

load_dotenv('.env')

client_id = os.getenv('SPOTIPY_CLIENT_ID')
client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=client_id,
    client_secret=client_secret
))

def test_query(q):
    print(f"\n--- Testing Query: '{q}' ---")
    try:
        results = sp.search(q=q, type='track', limit=1)
        items = results.get('tracks', {}).get('items', [])
        if items:
            track = items[0]
            artists = ", ".join([a['name'] for a in track['artists']])
            print(f"FOUND: {track['name']} by {artists}")
        else:
            print("NOT FOUND")
    except Exception as e:
        print("ERROR:", e)

test_query("yes miki")
test_query("track:yes artist:miki")
test_query("Akimbo Ziak")
test_query("track:Akimbo artist:Ziak")
test_query("Air Max Rim_K Ninho")
test_query("Air Max Rim'K Ninho")
test_query("Vald Vladimir Cauchemar Todiefor QUE DES PROBLEMES RELOADED")
