import os
import sys

def setup_spotify():
    print("=== Configuration Spotify API ===")
    print("Pour permettre au bot de lancer la musique sur votre PC ou de fournir des liens directs,")
    print("nous avons besoin de vos identifiants Spotify API.")
    print("\n1. Allez sur https://developer.spotify.com/dashboard")
    print("2. Connectez-vous et cliquez sur 'Create App'")
    print("3. Donnez un nom (ex: 'MusicBot') et une description")
    print("4. Dans les paramètres de l'app, trouvez le 'Client ID' et 'Client Secret'")
    print("5. Ajoutez 'http://localhost:8888/callback' dans 'Redirect URIs' (pour l'authentification future)")
    print("\nEntrez vos identifiants ci-dessous :")
    
    client_id = input("Client ID : ").strip()
    client_secret = input("Client Secret : ").strip()
    
    if not client_id or not client_secret:
        print("Erreur : Identifiants manquants.")
        return
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    env_path = os.path.join(parent_dir, '.env')
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    
    # Remove existing keys
    lines = [l for l in lines if not l.startswith('SPOTIFY_CLIENT_ID=') and not l.startswith('SPOTIFY_CLIENT_SECRET=')]
    
    # Add new keys
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
        
    lines.append(f"SPOTIFY_CLIENT_ID={client_id}\n")
    lines.append(f"SPOTIFY_CLIENT_SECRET={client_secret}\n")
    
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
    print(f"\n✅ Identifiants sauvegardés dans {env_path}")
    print("Vous pouvez maintenant relancer le bot !")

if __name__ == "__main__":
    setup_spotify()
