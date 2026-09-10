"""Shared validation and atomic JSON output, independent of supplier profiles."""
import json
from pathlib import Path
import re


def ean_valid(value):
    return bool(re.fullmatch(r'\d{13}', value)) and sum(
        int(char) * (1 if index % 2 == 0 else 3)
        for index, char in enumerate(value)) % 10 == 0


def image_ok(path):
    from PIL import Image
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def save_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
