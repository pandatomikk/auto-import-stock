"""Explicit single-image upload for the first WordPress media trial."""
import base64
import io
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from PIL import Image
from core.shop_connection import ConnectionFailure, NoRedirect, normalize_url

MAX_BYTES = 20 * 1024 * 1024


def upload_image(credentials, filename):
    url = normalize_url(credentials.url)
    username = credentials.username.strip()
    password = ''.join(credentials.application_password.split())
    if not username or not password or ':' in username:
        raise ConnectionFailure('Renseignez l’identifiant et le mot de passe d’application WordPress.')
    try:
        with Path(filename).open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ConnectionFailure('Choisissez une image de 20 Mo maximum pour ce test.')
        with Image.open(io.BytesIO(data)) as picture:
            kind = picture.format
            picture.verify()
        formats = {'JPEG': ('image/jpeg', '.jpg'), 'PNG': ('image/png', '.png'), 'WEBP': ('image/webp', '.webp')}
        if kind not in formats:
            raise ConnectionFailure('Formats acceptés : JPEG, PNG et WebP.')
    except ConnectionFailure:
        raise
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ConnectionFailure('Image illisible ou invalide. Sélectionnez un fichier JPEG, PNG ou WebP valide.') from None
    mime, extension = formats[kind]
    name = re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(filename).stem)[:120] or 'image'
    token = base64.b64encode(f'{username}:{password}'.encode()).decode('ascii')
    request = Request(url + '/wp-json/wp/v2/media', data=data, method='POST', headers={
        'Authorization': 'Basic ' + token,
        'Content-Type': mime,
        'Content-Disposition': f'attachment; filename="{name}{extension}"',
        'Accept': 'application/json',
        'User-Agent': 'AutoImportStock/0.20',
    })
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            result = json.loads(response.read(1024 * 1024 + 1))
        if not isinstance(result, dict) or not isinstance(result.get('id'), int) or result['id'] <= 0 or not isinstance(result.get('source_url'), str):
            raise ValueError()
        return {'id': result['id'], 'url': result['source_url'], 'filename': name + extension}
    except HTTPError as exc:
        exc.close()
        messages = {401: 'Identifiants WordPress refusés.', 403: 'Envoi refusé : vérifiez le droit de téléverser des fichiers.', 413: 'Le serveur refuse cette taille d’image.', 415: 'Le serveur refuse ce format d’image.'}
        message = messages.get(exc.code, f'Envoi non confirmé (HTTP {exc.code}).')
        raise ConnectionFailure(message + ' Vérifiez la médiathèque avant de réessayer pour éviter un doublon.') from None
    except (OSError, URLError, ValueError):
        raise ConnectionFailure('Envoi non confirmé : connexion interrompue ou réponse inattendue. Vérifiez la médiathèque avant de réessayer ; l’image a peut-être été créée.') from None
