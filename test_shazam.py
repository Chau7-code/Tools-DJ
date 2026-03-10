import asyncio
import sys
from shazamio import Shazam

async def test_shazam():
    shazam = Shazam()
    try:
        out = await shazam.recognize(r"C:\Music\DJ\toutes les musique\yes - miki.mp3")
        import json
        with open("shazam_out.json", "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print("Done. Wrote to shazam_out.json")
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    asyncio.run(test_shazam())
