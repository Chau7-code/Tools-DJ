import requests
import time

def search_itunes(artist, title):
    """Search iTunes for a track and return release year + genre."""
    # iTunes API: free, no key needed
    query = f"{artist} {title}".strip()
    url = "https://itunes.apple.com/search"
    params = {
        "term": query,
        "entity": "song",
        "limit": 3,
        "country": "FR"  # French store for better results on French artists
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        if data["resultCount"] > 0:
            track = data["results"][0]
            release_date = track.get("releaseDate", "")  # "2025-01-17T12:00:00Z"
            year = release_date[:4] if release_date else None
            genre = track.get("primaryGenreName", "")
            found_artist = track.get("artistName", "")
            found_title = track.get("trackName", "")
            return {
                "year": year,
                "genre": genre,
                "found_artist": found_artist,
                "found_title": found_title
            }
    except Exception as e:
        print(f"  Error: {e}")
    return None


# Test avec des morceaux connus
test_cases = [
    ("Michael Jackson", "Billie Jean"),
    ("a-ha", "Take On Me"),
    ("Jean-Jacques Goldman", "Quand la musique est bonne"),
    ("Jul", "Alors la zone"),
    ("Ziak", "Akimbo"),
    ("Naps", "6.3"),
    ("The Police", "Every Breath You Take"),
    ("miki", "yes"),
    ("Tame Impala", "The Less I Know the Better"),
    ("Duck Sauce", "Barbra Streisand"),
]

with open("itunes_results.txt", "w", encoding="utf-8") as f:
    for artist, title in test_cases:
        result = search_itunes(artist, title)
        if result:
            line = f"{artist} - {title}  =>  Year: {result['year']}, Genre: {result['genre']}, Match: {result['found_artist']} - {result['found_title']}"
        else:
            line = f"{artist} - {title}  =>  NOT FOUND"
        print(line)
        f.write(line + "\n")
        time.sleep(0.5)  # Gentle rate limiting
