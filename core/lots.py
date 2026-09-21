"""Local, self-contained preparation folders; supplier originals are copied."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import uuid


def lots_directory():
    return Path(os.environ.get('AUTO_IMPORT_LOTS_DIR', str(Path.home() / 'auto-import-stock-lots'))).expanduser()


def copy_source(source, folder):
    source = Path(source).expanduser().resolve()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / source.name
    if destination.resolve() == source:
        return source
    if destination.exists():
        destination = folder / (source.stem + '_' + uuid.uuid4().hex[:8] + source.suffix)
    temporary = destination.with_name('.' + destination.name + '.copy')
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def create_lot(source, supplier, images=None, drive_url=None, root=None):
    root = Path(root) if root is not None else lots_directory()
    root.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[^\w-]+', '_', supplier).strip('_')[:60] or 'Catalogue'
    name += '_' + datetime.now().strftime('%d%m%y_%H%M%S')
    folder = root / name
    try:
        folder.mkdir()
    except FileExistsError:
        folder = root / (name + '_' + uuid.uuid4().hex[:8]); folder.mkdir()
    (folder / 'resultats').mkdir()
    metadata = {'version': 1, 'supplier': supplier, 'created': datetime.now().isoformat()}
    (folder / 'lot.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    source = copy_source(source, folder / 'sources')
    archive = copy_source(images, folder / 'sources') if images else None
    if drive_url:
        (folder / 'sources' / 'source_images.txt').write_text(drive_url + '\n', encoding='utf-8')
    return folder, source, archive


def prepare_lot(source, supplier, images=None, drive_url=None, root=None):
    source = Path(source).expanduser().resolve()
    folder = source.parent.parent
    metadata = folder / 'lot.json'
    if source.parent.name == 'sources' and metadata.is_file():
        data = json.loads(metadata.read_text(encoding='utf-8'))
        if data.get('version') == 1 and data.get('supplier') == supplier:
            (folder / 'resultats').mkdir(exist_ok=True)
            archive = copy_source(images, folder / 'sources') if images else None
            if drive_url:
                (folder / 'sources' / 'source_images.txt').write_text(drive_url + '\n', encoding='utf-8')
            return folder, source, archive
    return create_lot(source, supplier, images, drive_url, root)


def attach_archive(session, archive):
    folder = Path(session).resolve().parent.parent
    return copy_source(archive, folder / 'sources') if (folder / 'lot.json').is_file() else Path(archive)


def emit_lot(folder, source):
    print('ZPSI_LOT ' + json.dumps({'folder': str(folder), 'source': str(source)}, ensure_ascii=False), flush=True)
