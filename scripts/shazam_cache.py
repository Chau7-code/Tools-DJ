"""
shazam_cache.py
---------------
Cache JSON pour les résultats Shazam / iTunes / Spotify.
Évite de ré-identifier un fichier déjà scanné entre l'étape 1 (qualité)
et l'étape 2 (renommage).

Le cache est indexé par le nom de fichier normalisé (sans préfixe upgrade_,
sans extension, minuscules, sans accents).

Fichier de cache : data/shazam_cache.json
"""

import os
import json
import re
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
CACHE_FILE = os.path.join(PARENT_DIR, 'data', 'shazam_cache.json')


def _make_key(filepath):
    """Crée une clé de cache à partir du chemin du fichier."""
    base = os.path.splitext(os.path.basename(filepath))[0]
    # Retirer préfixes courants
    base = re.sub(r'^upgrade_', '', base, flags=re.IGNORECASE)
    # Normaliser
    base = unicodedata.normalize('NFKD', base).encode('ascii', 'ignore').decode('ascii')
    base = base.lower()
    base = re.sub(r'[^a-z0-9 ]', '', base)
    base = re.sub(r'\s+', ' ', base).strip()
    return base


def _load_cache():
    """Charge le cache depuis le fichier JSON."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(cache):
    """Sauvegarde le cache dans le fichier JSON."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cache_get(filepath):
    """
    Récupère un résultat en cache pour un fichier donné.
    Retourne un dict {'artist', 'title', 'genre', 'year', 'source'} ou None.
    """
    key = _make_key(filepath)
    if not key:
        return None
    cache = _load_cache()
    return cache.get(key)


def cache_save(filepath, result, source='Shazam'):
    """
    Sauvegarde un résultat d'identification dans le cache.
    
    Args:
        filepath: Chemin du fichier audio
        result: dict avec 'artist', 'title', 'genre', 'year'
        source: Source d'identification ('Shazam', 'iTunes', 'Spotify')
    """
    key = _make_key(filepath)
    if not key or not result:
        return
    
    cache = _load_cache()
    cache[key] = {
        'artist': result.get('artist', ''),
        'title': result.get('title', ''),
        'genre': result.get('genre', ''),
        'year': result.get('year'),
        'source': source,
    }
    _save_cache(cache)


def cache_clear():
    """Vide le cache."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
