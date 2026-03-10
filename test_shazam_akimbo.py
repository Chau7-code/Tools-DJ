import asyncio
import sys
from shazamio import Shazam
import traceback

async def test_shazam():
    shazam = Shazam()
    target_file = r"C:\Music\DJ\toutes les musique\Akimbo - Ziak.mp3"
    print(f"Testing Shazamio on: {target_file}")
    try:
        out = await asyncio.wait_for(shazam.recognize(target_file), timeout=15.0)
        import json
        print("Success! Response keys:", out.keys())
        if 'track' in out:
            print("Track found:", out['track'].get('title'), "-", out['track'].get('subtitle'))
        else:
            print("Track not found")
    except asyncio.TimeoutError:
        print("Error: Shazamio timed out after 15 seconds.")
    except Exception as e:
        print(f"Erreur: {repr(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_shazam())
