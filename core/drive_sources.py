"""Validate and deduplicate public Google Drive folder sources."""
import re
from urllib.parse import urlsplit


def parse_drive_sources(value):
    values = re.split(r'[\s;,]+', value.strip()) if isinstance(value, str) else value
    sources = []
    for raw in values:
        if not raw:
            continue
        u = urlsplit(raw)
        match = re.fullmatch(r'/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/*', u.path)
        if u.scheme != 'https' or u.hostname != 'drive.google.com' or u.username or u.password or u.port or not match:
            raise ValueError('Indiquer des liens de dossiers Google Drive valides, un par ligne.')
        url = 'https://drive.google.com/drive/folders/' + match[1]
        if url not in sources:
            sources.append(url)
    if not sources:
        raise ValueError('Indiquer au moins un dossier Google Drive.')
    return sources
