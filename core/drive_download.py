"""Download public Drive files through the explicit download endpoint."""
import re
from pathlib import Path

import requests


def download_public_file(file_id, output, *, fallback=None, max_bytes=100 * 1024 * 1024):
    """Stream bounded downloads; leave confirmation pages to the existing client.

    HTTP refusals (including quotas) are not bypassed with another endpoint.
    The caller remains responsible for validating the expected file format.
    """
    if not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
        raise ValueError('Identifiant Drive invalide')
    destination = Path(output)
    destination.unlink(missing_ok=True)
    try:
        with requests.get('https://drive.google.com/uc',
                          params={'id': file_id, 'export': 'download'},
                          stream=True, timeout=(10, 60)) as response:
            if response.status_code in (403, 429):
                raise RuntimeError(f'Drive HTTP {response.status_code} : accès refusé ou téléchargement limité. Réessayez plus tard.')
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                size = 0
                with destination.open('wb') as stream:
                    for chunk in response.iter_content(chunk_size=128 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError('Fichier Drive trop volumineux')
                        stream.write(chunk)
                if not size:
                    raise ValueError('Fichier Drive vide')
                return str(destination)
        if fallback is None:
            raise RuntimeError('Drive a renvoyé une page de confirmation au lieu du fichier')
        return fallback(id=file_id, output=str(destination), quiet=True, use_cookies=False)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
