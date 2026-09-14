"""Review a batch before uploading local photos and creating simple products."""
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from PIL import Image
from core.shop_connection import ConnectionFailure
from core.shop_products import read_products_csv, split_values, prepare_csv, import_plan
from core.shop_media import upload_image, MAX_BYTES
from core.io import write_csv


def digest(path):
    with Path(path).open('rb') as stream:
        value = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
        return value.hexdigest()


def prepare_publication(path, api, progress=lambda text: None, mappings=None):
    path = Path(path).resolve()
    if path.stem.endswith('_preparation'):
        raise ConnectionFailure('Sélectionnez le CSV final : cette préparation attend encore ses images.')
    rows = read_products_csv(path)
    # Only photos alongside this result, never unrelated supplier archives.
    index = {}
    for file in path.parent.rglob('*'):
        if file.is_file() and file.resolve().is_relative_to(path.parent) and file.suffix.lower() in {'.webp', '.jpg', '.jpeg', '.png'} and not any(p.startswith('sauvegarde') for p in file.relative_to(path.parent).parts):
            index.setdefault(file.name, []).append(file)
    overrides = {}
    for _, row in rows:
        for location in split_values(row.get('Images', '')):
            location = location.replace('\\,', ',')
            name = unquote(urlsplit(location).path).rsplit('/', 1)[-1]
            matches = index.get(name, [])
            if len(matches) > 1:
                raise ConnectionFailure('Plusieurs images locales portent ce nom : ' + name)
            if matches:
                overrides[location] = {'_local_path': str(matches[0])}
    plan = prepare_csv(path, api, progress, mappings, image_overrides=overrides)
    files = {}
    for item in plan['items']:
        for image in item.get('payload', {}).get('images', []):
            if '_local_path' in image:
                filename = image['_local_path']
                if filename in files:
                    continue
                progress('Vérification de l’image : ' + Path(filename).name)
                try:
                    if Path(filename).stat().st_size > MAX_BYTES:
                        raise ValueError('Image supérieure à 20 Mo')
                    with Image.open(filename) as picture:
                        if picture.format not in {'WEBP', 'PNG', 'JPEG'}:
                            raise ValueError('Format invalide')
                        picture.verify()
                    files[filename] = digest(filename)
                except (OSError, ValueError, Image.DecompressionBombError):
                    raise ConnectionFailure('Image invalide ou trop volumineuse : ' + Path(filename).name) from None
    plan['local_files'] = files
    plan['source_hash'] = digest(path)
    return plan


def publish_plan(plan, api, report_path, progress=lambda text: None, uploader=upload_image):
    if plan['errors'] or plan['site'] != api.url:
        raise ConnectionFailure('Contrôle invalide : sélectionnez à nouveau le CSV.')
    source = Path(plan['source'])
    if digest(source) != plan['source_hash']:
        raise ConnectionFailure('Le CSV a changé depuis le contrôle. Sélectionnez-le à nouveau.')
    for filename, expected in plan['local_files'].items():
        if digest(filename) != expected:
            raise ConnectionFailure('Une image a changé depuis le contrôle : ' + Path(filename).name)
    site_key = hashlib.sha256(api.url.encode()).hexdigest()[:16]
    journal_path = source.parent / ('publication_images_' + site_key + '.json')
    lock = journal_path.with_suffix('.lock')
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise ConnectionFailure('Une publication est déjà en cours, ou a été interrompue. Vérifiez la boutique et le fichier ' + lock.name + ' avant de reprendre.') from None
    try:
        handle.close()
        journal = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {'site': api.url, 'images': {}}
        if journal.get('site') != api.url:
            raise ConnectionFailure('Journal associé à une autre boutique.')
        def save():
            temporary = journal_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(journal_path)
        prepared = copy.deepcopy(plan)
        # Recheck before media uploads: existing articles need no new photos.
        needed = set()
        for item in prepared['items']:
            if item['state'] == 'new' and api.existing(item['sku']):
                item['state'] = 'existing'; item.pop('payload', None)
            needed.update(image['_local_path'] for image in item.get('payload', {}).get('images', []) if '_local_path' in image)
        for filename in needed:
            previous = journal['images'].get(plan['local_files'][filename])
            if previous and previous.get('state') != 'uploaded':
                raise ConnectionFailure('Envoi précédent non confirmé : ' + Path(filename).name + '. Vérifiez la médiathèque et le journal ' + journal_path.name + ' avant de reprendre ; aucun nouvel envoi automatique.')
        uploaded = {}
        for number, filename in enumerate(sorted(needed), 1):
            key = plan['local_files'][filename]
            previous = journal['images'].get(key)
            progress(f'Images {number}/{len(needed)} : ' + Path(filename).name)
            if not previous:
                journal['images'][key] = {'state': 'unconfirmed', 'filename': Path(filename).name}
                save()  # Persist BEFORE the network write.
                try:
                    result = uploader(api.credentials, filename)
                except ConnectionFailure as exc:
                    raise ConnectionFailure(str(exc) + ' Journal : ' + str(journal_path)) from None
                previous = {'state': 'uploaded', **result}
                journal['images'][key] = previous
                save()
            uploaded[filename] = previous
        locations = {}
        for item in prepared['items']:
            for image in item.get('payload', {}).get('images', []):
                if '_local_path' in image:
                    filename = image.pop('_local_path')
                    image['id'] = uploaded[filename]['id']
                    locations[Path(filename).name] = uploaded[filename]['url']
        rows = [row for _, row in read_products_csv(source)]
        for row in rows:
            values = []
            for value in split_values(row.get('Images', '')):
                name = unquote(urlsplit(value.replace('\\,', ',')).path).rsplit('/', 1)[-1]
                values.append(locations.get(name, value))
            if 'Images' in row:
                row['Images'] = ', '.join(values)
        online = source.with_name(source.stem + '_en_ligne.csv')
        temporary = online.with_suffix('.tmp')
        write_csv(temporary, list(rows[0]), rows)
        temporary.replace(online)
        progress('Images prêtes. Création des nouveaux produits…')
        return import_plan(prepared, api, report_path, progress)
    finally:
        lock.unlink(missing_ok=True)
