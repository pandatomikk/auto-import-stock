"""Optional client-specific presentation settings kept in the private pack."""
import json
import re
from pathlib import Path
from .profiles import private_directory


def image_filename(name):
    path = private_directory() / 'client.json'
    if not path.exists():
        return name
    settings = json.loads(path.read_text(encoding='utf-8'))
    suffix = settings.get('image_filename_suffix', '')
    if not isinstance(suffix, str) or (suffix and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,99}', suffix)):
        raise ValueError('Suffixe des images invalide dans private/client.json.')
    if not suffix:
        return name
    image = Path(name)
    if image.stem.endswith('-' + suffix):
        return name
    return str(image.with_name(image.stem + '-' + suffix + image.suffix))
