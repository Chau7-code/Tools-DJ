from mutagen.easyid3 import EasyID3
try:
    audio = EasyID3(r"C:\Music\DJ\toutes les musique\Akimbo - Ziak.mp3")
    print(audio.keys())
    print("Artist:", audio.get("artist"))
    print("Date:", audio.get("date"))
    print("Original Date:", audio.get("originaldate"))
except Exception as e:
    print(f"Error reading file: {e}")
