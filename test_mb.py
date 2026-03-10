import musicbrainzngs
import time

# MusicBrainz requires a useragent setup
musicbrainzngs.set_useragent("MusicOrganizer", "1.0", "https://github.com/myuser/myproject")

def test_mb(artist, title):
    print(f"Testing: {artist} - {title}")
    try:
        # Search for recordings matching artist and title
        time.sleep(1) # MusicBrainz rate limits to 1 req per sec
        result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=5)
        recordings = result.get("recording-list", [])
        
        earliest_year = None
        genres = set()
        
        if recordings:
            for rec in recordings:
                # Get releases associated with this recording
                for release in rec.get("release-list", []):
                    date = release.get("date", "")
                    if date:
                        year = int(date.split('-')[0])
                        if not earliest_year or year < earliest_year:
                            earliest_year = year
                
                # Check for tags/genres if available
                for tag in rec.get("tag-list", []):
                    genres.add(tag['name'])

            print(f"  FOUND! Earliest Year: {earliest_year}, Genres/Tags: {list(genres)[:5]}")
        else:
            print("  Not found in MusicBrainz database.")
    except Exception as e:
        print(f"  Error: {e}")

test_mb("A-ha", "Take On Me")
test_mb("Michael Jackson", "Billie Jean")
test_mb("Ziak", "Akimbo")
test_mb("Goldman", "Quand la musique est bonne")
