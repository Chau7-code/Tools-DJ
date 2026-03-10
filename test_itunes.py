import requests
import json

def test_itunes(query):
    print(f"Testing: {query}")
    url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=1"
    try:
        response = requests.get(url).json()
        if response['resultCount'] > 0:
            track = response['results'][0]
            print("  Title:", track.get('trackName'))
            print("  Artist:", track.get('artistName'))
            print("  Release Date:", track.get('releaseDate'))
            print("  Genre:", track.get('primaryGenreName'))
        else:
            print("  No results")
    except Exception as e:
        print("  Error:", e)

test_itunes("Michael Jackson Billie Jean")
test_itunes("A-ha Take On Me")
test_itunes("Jul Alors la zone")
test_itunes("Ziak Akimbo")
