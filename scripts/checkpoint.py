"""
checkpoint.py
--------------
Module utilitaire partage pour tous les scripts :
  - Pause/Reprise avec la touche 'p' (detection non-bloquante)
  - Checkpoint automatique : sauvegarde la progression dans .checkpoint.json
  - Reprise automatique : si un checkpoint existe, reprend la ou le script s'est arrete

Usage dans un script :
    from checkpoint import CheckpointManager

    mgr = CheckpointManager("nom_script", directory)
    mgr.start()  # lance l'ecoute clavier

    files = mgr.get_remaining_files(all_files)  # reprend au bon endroit

    for filepath in files:
        await mgr.wait_if_paused()  # pause si 'p' appuye
        # ... traitement ...
        mgr.save_progress(filepath)  # sauvegarde apres chaque fichier

    mgr.finish()  # supprime le checkpoint a la fin
"""

import os
import sys
import json
import threading
from datetime import datetime


# ─── Detection clavier non-bloquante ─────────────────────────────
if os.name == 'nt':
    import msvcrt

    def _check_key():
        """Verifie si une touche est pressee (Windows)."""
        if msvcrt.kbhit():
            key = msvcrt.getch()
            try:
                return key.decode('utf-8', errors='ignore').lower()
            except Exception:
                return ''
        return ''
else:
    import select

    def _check_key():
        """Verifie si une touche est pressee (Linux/Mac)."""
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower()
        return ''


# ─── Couleurs ────────────────────────────────────────────────────
class _C:
    Y = '\033[93m'; B = '\033[94m'; M = '\033[95m'
    G = '\033[92m'; X = '\033[0m'


class CheckpointManager:
    """
    Gestionnaire de checkpoint et pause/reprise pour les scripts de traitement.

    Fonctionnalites :
      - Touche 'p' : bascule pause/reprise
      - Sauvegarde automatique de la progression dans .checkpoint.json
      - Reprise automatique depuis le dernier checkpoint
    """

    def __init__(self, script_name, directory):
        self.script_name = script_name
        self.directory = os.path.abspath(directory)
        self.checkpoint_file = os.path.join(self.directory, ".checkpoint.json")
        self._paused = False
        self._running = False
        self._lock = threading.Lock()
        self._listener_thread = None
        self._processed_files = set()

    def start(self):
        """Demarre l'ecoute clavier pour la pause."""
        self._running = True
        self._listener_thread = threading.Thread(target=self._key_listener, daemon=True)
        self._listener_thread.start()
        print(f"{_C.M}💡 Appuyez sur 'p' à tout moment pour mettre en pause / reprendre{_C.X}")

        # Verifier si un checkpoint existe
        cp = self._load_checkpoint()
        if cp and cp.get('script') == self.script_name:
            count = len(cp.get('processed', []))
            print(f"{_C.B}📌 Checkpoint trouvé : {count} fichier(s) déjà traités, reprise en cours...{_C.X}")

    def stop(self):
        """Arrete l'ecoute clavier."""
        self._running = False

    def finish(self):
        """Termine le traitement : supprime le checkpoint."""
        self.stop()
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print(f"{_C.G}✅ Checkpoint supprimé (traitement terminé){_C.X}")

    def _key_listener(self):
        """Thread d'ecoute clavier en arriere-plan."""
        while self._running:
            try:
                key = _check_key()
                if key == 'p':
                    with self._lock:
                        self._paused = not self._paused
                    if self._paused:
                        print(f"\n{_C.Y}⏸️  PAUSE — Appuyez sur 'p' pour reprendre...{_C.X}")
                    else:
                        print(f"\n{_C.G}▶️  REPRISE du traitement...{_C.X}")
            except Exception:
                pass
            # Petit delai pour ne pas surcharger le CPU
            threading.Event().wait(0.15)

    @property
    def is_paused(self):
        with self._lock:
            return self._paused

    async def wait_if_paused(self):
        """Attend tant que le script est en pause (compatible asyncio)."""
        import asyncio
        while self.is_paused:
            await asyncio.sleep(0.3)

    def _load_checkpoint(self):
        """Charge le checkpoint depuis le fichier JSON."""
        try:
            if os.path.exists(self.checkpoint_file):
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_checkpoint(self):
        """Sauvegarde le checkpoint."""
        data = {
            'script': self.script_name,
            'directory': self.directory,
            'processed': list(self._processed_files),
            'timestamp': datetime.now().isoformat()
        }
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_progress(self, filepath):
        """Marque un fichier comme traite et sauvegarde le checkpoint."""
        self._processed_files.add(os.path.basename(filepath))
        self._save_checkpoint()

    def get_remaining_files(self, all_files):
        """
        Retourne la liste des fichiers restants a traiter.
        Si un checkpoint existe, filtre les fichiers deja traites.
        """
        cp = self._load_checkpoint()
        if cp and cp.get('script') == self.script_name:
            already_done = set(cp.get('processed', []))
            self._processed_files = already_done
            remaining = [f for f in all_files if os.path.basename(f) not in already_done]
            skipped = len(all_files) - len(remaining)
            if skipped > 0:
                print(f"{_C.B}⏭️  {skipped} fichier(s) déjà traités (checkpoint), {len(remaining)} restant(s){_C.X}")
            return remaining
        return all_files
