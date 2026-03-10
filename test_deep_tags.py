from mutagen.id3 import ID3, TDRC, TYER, TDAT, TORY

filepath = r"C:\Music\DJ\toutes les musique\Akimbo - Ziak.mp3"
try:
    audio = ID3(filepath)
    
    # Try different date formats that DJ software uses
    audio.add(TYER(encoding=3, text='2021')) # ID3v2.3 Year
    audio.add(TDAT(encoding=3, text='0101')) # ID3v2.3 Date
    audio.add(TORY(encoding=3, text='2021')) # ID3v2.3 Original release year
    audio.add(TDRC(encoding=3, text='2021')) # ID3v2.4 Recording time
    
    audio.save()
    print("Tags force written with ID3!")
except Exception as e:
    print(e)
