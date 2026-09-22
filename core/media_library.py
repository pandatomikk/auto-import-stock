"""Resolve existing WordPress images by exact original filenames or saved IDs."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from .shop_connection import ConnectionFailure


def upload_name(filename, limit=220):
    path = Path(filename)
    stem = re.sub(r'[^a-zA-Z0-9_.-]', '_', path.stem)[:limit] or 'image'
    extension = '.jpg' if path.suffix.lower() in ('.jpg', '.jpeg') else path.suffix.lower()
    return stem + extension


def normalized_name(name):
    # WordPress collapses dashes/dots and may protect intermediate extensions
    # (e.g. a domain's .fr becomes .fr_ before the final .webp extension).
    name = re.sub(r'-+', '-', re.sub(r'\.{2,}', '.', name)).strip('.-_')
    parts = name.split('.')
    for i in range(1, len(parts)-1):
        if re.fullmatch(r'[A-Za-z]{2,5}[0-9]?_', parts[i]):
            parts[i] = parts[i][:-1]
    return '.'.join(parts)


class MediaLibrary:
    def __init__(self, api):
        self.by_id = {}
        self.by_name = {}
        for item in api.listing('wp/v2/media'):
            if item.get('media_type', 'image') != 'image':
                continue
            url = item.get('source_url')
            if type(item.get('id')) is not int or item['id'] <= 0 or not isinstance(url, str) or urlsplit(url).scheme not in ('https', 'http'):
                raise ConnectionFailure('Réponse médiathèque invalide : aucun nouvel envoi.')
            details = item.get('media_details') or {}
            if not isinstance(details, dict):
                raise ConnectionFailure('Détails de la médiathèque invalides.')
            names = {unquote(urlsplit(url).path).rsplit('/', 1)[-1]}
            for field in ('file', 'original_image'):
                if isinstance(details.get(field), str):
                    names.add(details[field].replace('\\', '/').rsplit('/', 1)[-1])
            record = {'id': item['id'], 'url': url, 'filename': unquote(urlsplit(url).path).rsplit('/', 1)[-1]}
            self.by_id[item['id']] = record
            for name in names:
                self.by_name.setdefault(normalized_name(name), {})[item['id']] = record

    def find(self, filename, previous=None):
        if previous and previous.get('state') == 'uploaded':
            known = self.by_id.get(previous.get('id'))
            if known:
                return known
        names = {Path(filename).name, upload_name(filename), upload_name(filename, 120)}
        if previous and previous.get('state') == 'uploaded' and previous.get('filename'):
            names.add(previous['filename'])
        matches = {}
        for name in names:
            matches.update(self.by_name.get(normalized_name(name), {}))
        if len(matches) > 1:
            raise ConnectionFailure('Plusieurs images existantes correspondent à ' + Path(filename).name + ' : vérifiez la médiathèque avant de reprendre.')
        return next(iter(matches.values()), None)
