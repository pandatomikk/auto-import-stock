"""Préparation persistante en deux étapes, pilotée par le profil fournisseur."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import unicodedata
import zipfile

from .converter import convert_catalogue, validate
from .io import write_csv
from .profiles import read_profile, resolve_profile, workflow_kind

EAN_COLUMN = 'GTIN, UPC, EAN ou ISBN'
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff'}


def save_session(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def session_path_for(source, output=None):
    source = Path(source).expanduser().resolve()
    final = Path(output).expanduser().resolve() if output else source.with_name(source.stem + '_woocommerce.csv')
    return final.with_name(final.stem + '_session.json')


def load_session(path):
    path = Path(path).expanduser().resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or not isinstance(data.get('supplier'), str)
            or data.get('version') != 1 or data.get('status') not in {'waiting_images', 'complete'}):
        raise ValueError('Sélectionner une préparation (*_session.json).')
    if (not isinstance(data.get('source'), str) or not data['source']
            or type(data.get('products')) is not int or data['products'] < 1):
        raise ValueError('Préparation incomplète : source ou nombre de produits absent.')
    if data.get('workflow') != 'two_pass':
        config = read_profile(resolve_profile(data['supplier']))
        if workflow_kind(config) != 'two_pass':
            raise ValueError('Cette session ne correspond pas à un traitement en deux étapes.')
        data.update(workflow='two_pass', supplier_name=config.get('supplier_name', data['supplier']),
                    image_settings=config.get('images', {}))
    # Relative artifact names let the whole preparation folder be moved together.
    for key in ('prepared_csv', 'ean_text', 'preparation_report', 'final_csv', 'final_report'):
        name = data.get(key)
        if not isinstance(name, str) or not name or Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Chemin de préparation invalide : ' + key)
    identities = data.get('image_identifiers', [])
    if not isinstance(identities, list) or any(
            not isinstance(item, dict) or any(not isinstance(item.get(key), str)
                                             for key in ('ean', 'article', 'color_code', 'color'))
            for item in identities):
        raise ValueError('Identifiants images invalides dans la préparation.')
    return data


def workflow_event(path, data):
    path = Path(path).resolve()
    return dict(status=data['status'], session=str(path),
                prepared_csv=str(path.parent / data['prepared_csv']),
                ean_text=str(path.parent / data['ean_text']),
                final_csv=str(path.parent / data['final_csv']),
                products=data['products'], missing_images=data.get('missing_images', []),
                service_label=data.get('image_settings', {}).get('service_label', 'la plateforme fournisseur'),
                images_directory=str(path.parent / data.get('image_settings', {}).get('directory', 'images_produits')))


def prepare_catalogue(source, config, schema, output=None, rules_path=None, rebuild=False):
    source = Path(source).expanduser().resolve()
    config_path = Path(config)
    profile = read_profile(config_path)
    session_path = session_path_for(source, output)
    if session_path.exists():
        previous = load_session(session_path)
        if previous['status'] == 'waiting_images' and not rebuild:
            if previous.get('source') != str(source) or previous.get('supplier') != config_path.stem:
                raise ValueError('Une autre préparation utilise cette sortie. Choisir un autre nom de CSV.')
            if not (session_path.parent / previous['prepared_csv']).is_file():
                raise ValueError('CSV de préparation introuvable. Restaurer le fichier avant de reprendre.')
            return session_path, previous
    final = Path(output).expanduser().resolve() if output else source.with_name(source.stem + '_woocommerce.csv')
    prepared = final.with_name(final.stem + '_preparation.csv')
    if final.suffix.lower() != '.csv' or source in {final, prepared}:
        raise ValueError('Choisir une sortie .csv distincte du catalogue source.')
    final.parent.mkdir(parents=True, exist_ok=True)
    # Keep an existing preparation intact if the new catalogue fails validation.
    with tempfile.TemporaryDirectory(dir=final.parent, prefix='.preparation-') as tmp:
        staged = Path(tmp) / prepared.name
        result = convert_catalogue(source, Path(config), Path(schema), staged, web_descriptions=False, product_rules_path=rules_path)
        if not result.row_count:
            raise ValueError('Aucun produit commandé à préparer. Vérifier les quantités et les codes-barres.')
        report = json.loads(result.report_path.read_text(encoding='utf-8'))
        if not report.get('ean_text'):
            raise ValueError('Le profil doit activer export_ean_text.')
        ean_path = prepared.with_name(prepared.stem + '_ean.txt')
        staged_ean = Path(report['ean_text']['path'])
        report['ean_text']['path'] = str(ean_path)
        report['workflow_status'] = 'waiting_images'
        result.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if rebuild and session_path.exists():
            import shutil, uuid
            backup = final.parent / ('sauvegarde_preparation_' + uuid.uuid4().hex[:12])
            backup.mkdir()
            old = load_session(session_path)
            for file in [session_path, *(final.parent / old[key] for key in ('prepared_csv', 'ean_text', 'preparation_report'))]:
                if file.exists(): shutil.copy2(file, backup / file.name)
        staged.replace(prepared)
        staged_ean.replace(ean_path)
        preparation_report = prepared.with_name(prepared.stem + '_rapport.json')
        result.report_path.replace(preparation_report)
    data = dict(version=1, workflow='two_pass', supplier=config_path.stem,
                supplier_name=profile.get('supplier_name', config_path.stem),
                image_settings=profile.get('images', {}), status='waiting_images', source=str(source),
                prepared_csv=prepared.name, ean_text=ean_path.name,
                preparation_report=preparation_report.name, final_csv=final.name,
                final_report=final.stem + '_rapport.json', products=result.row_count,
                image_identifiers=report['image_identifiers'])
    save_session(session_path, data)
    return session_path, data


def normalize_color(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().upper()
    text = re.sub(r'[^A-Z0-9]', '', text)
    return str(int(text)) if text.isdigit() else text


def select_zip_images(archive, references, identities=(), settings=None):
    """Match a configured article/color pattern, or an exact EAN."""
    selected = {ref: [] for ref in references}
    by_article_color = {}
    for product in identities:
        ref = product['ean']
        article = str(product['article']).strip().upper()
        if ref not in references or not article:
            continue
        for value in (product['color_code'], product['color']):
            color = normalize_color(value)
            if color:
                by_article_color.setdefault((article, color), set()).add(ref)
    pattern = (settings or {}).get('filename_pattern')
    filename_pattern = re.compile(pattern or r'(?!)', re.I)
    if pattern and not {'article', 'color'}.issubset(filename_pattern.groupindex):
        raise ValueError('Le motif image doit définir les groupes article et color.')
    ignored = []
    ambiguous = []
    seen_paths = set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace('\\', '/'))
        if info.is_dir() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if '__MACOSX' in path.parts or path.name.startswith('._'):
            continue
        matched = filename_pattern.fullmatch(path.stem)
        if matched:
            color, article = matched['color'], matched['article']
            matches = by_article_color.get((article.upper(), normalize_color(color)), set())
        else:
            # Ignore a batch directory/date; only a filename or a directory named
            # exactly after a barcode can provide the fallback identity.
            codes = set(re.findall(r'(?<!\d)\d{8,14}(?!\d)', path.stem))
            codes.update(part for part in path.parts[:-1] if part in references)
            matches = codes & references
            if len(codes) > 1 and matches:
                ambiguous.append(info.filename)
                continue
        if len(matches) > 1:
            ambiguous.append(info.filename)
            continue
        if len(matches) != 1:
            ignored.append(info.filename)
            continue
        if info.filename in seen_paths:
            raise ValueError('Chemin image présent plusieurs fois dans le ZIP : ' + info.filename)
        seen_paths.add(info.filename)
        selected[next(iter(matches))].append(info)
    if ambiguous:
        raise ValueError('Association image ambiguë (plusieurs produits possibles) : ' + ', '.join(ambiguous[:5]))
    # Natural sort preserves gallery order for 1, 2, 10 (also with nested folders).
    def order(info):
        path = PurePosixPath(info.filename.replace('\\', '/'))
        matched = filename_pattern.fullmatch(path.stem)
        photo = int(matched.groupdict().get('order') or 1) if matched else 0
        return (photo, [part.zfill(24) if part.isdigit() else part.casefold()
                        for part in re.split(r'(\d+)', info.filename)])
    for entries in selected.values():
        entries.sort(key=order)
    return selected, ignored


def finalize_catalogue(session_path, images_zip):
    from .image_webp import optimize_webp
    from .shared import image_ok
    import shutil
    import unicodedata

    session_path = Path(session_path).expanduser().resolve()
    data = load_session(session_path)
    root = session_path.parent
    prepared = root / data['prepared_csv']
    output = root / data['final_csv']
    images_zip = Path(images_zip).expanduser().resolve()
    if output in {prepared, images_zip, Path(data['source']).resolve()}:
        raise ValueError('La sortie finale doit être distincte des fichiers source.')
    with prepared.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        if not {'UGS', EAN_COLUMN, 'Nom', 'Images', 'Publié'}.issubset(columns):
            raise ValueError('Colonnes manquantes dans le CSV de préparation.')
        rows = list(reader)
    if not rows:
        raise ValueError('Le CSV de préparation ne contient aucun produit.')
    references = {row[EAN_COLUMN].strip() for row in rows}
    if any(not re.fullmatch(r'\d{8,14}', ref) for ref in references):
        raise ValueError('Code-barres absent ou invalide dans le CSV de préparation.')
    image_settings = data.get('image_settings', {})
    image_directory = image_settings.get('directory', 'images_produits')
    if not re.fullmatch(r'images_[A-Za-z0-9_-]+', image_directory):
        raise ValueError('Nom du dossier images invalide dans la session.')
    images_root = root / image_directory / 'fichiers_webp'
    records = []
    with zipfile.ZipFile(images_zip) as archive:
        selected, ignored = select_zip_images(archive, references, data.get('image_identifiers', []), image_settings)
        if not any(selected.values()):
            raise ValueError('Aucune image ne correspond aux produits. Vérifier le format de nom configuré dans le profil, ou utiliser des noms contenant les EAN exacts. La préparation reste disponible ; sélectionner un autre ZIP.')
        total = sum(len(entries) for entries in selected.values())
        names_by_ref = {}
        for row in rows:
            ref = row[EAN_COLUMN].strip()
            if ref in names_by_ref:
                continue
            names = names_by_ref[ref] = []
            slug = unicodedata.normalize('NFKD', row['Nom']).encode('ascii', 'ignore').decode().lower()
            slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')[:100] or ref
            for number, info in enumerate(selected[ref], 1):
                digest = hashlib.sha256((info.filename + ':' + str(info.CRC)).encode()).hexdigest()[:12]
                target = images_root / f'{slug}-{number:02d}__{digest}.webp'
                existing = image_ok(target)
                if not existing:
                    with tempfile.TemporaryDirectory(prefix='product-image-') as tmp:
                        source = Path(tmp) / 'source'
                        with archive.open(info) as src, source.open('wb') as dst:
                            shutil.copyfileobj(src, dst)
                        optimize_webp(source, target)
                names.append(target.name)
                records.append(dict(ean=ref, archive_path=info.filename, filename=target.name,
                                    status='existing' if existing else 'converted'))
                print('ZPSI_LOCAL_IMAGES ' + json.dumps(dict(done=len(records), total=total)), flush=True)
        for row in rows:
            row['Publié'] = '1'
            row['Images'] = ', '.join(names_by_ref[row[EAN_COLUMN].strip()])
    missing = sorted(ref for ref, names in names_by_ref.items() if not names)
    report = dict(supplier=data.get('supplier_name', data['supplier']), workflow_status='complete', published=1,
                  prepared_csv=str(prepared), images_zip=str(images_zip), output_products=len(rows),
                  products_with_images=sum(bool(row['Images']) for row in rows),
                  missing_images=missing, ignored_images=ignored, images=records, warnings=validate(rows),
                  missing_image_products=[dict(ean=row[EAN_COLUMN], name=row['Nom'],
                                               reference=row.get('Description courte', ''))
                                          for row in rows if not row['Images']],
                  preparation_report=data['preparation_report'])
    # Never leave a half-written final CSV when ZIP validation or conversion fails.
    with tempfile.TemporaryDirectory(dir=root, prefix='.media-final-') as tmp:
        staged = Path(tmp) / output.name
        write_csv(staged, columns, rows)
        save_session(root / data['final_report'], report)
        staged.replace(output)
    data.update(status='complete', products=len(rows), missing_images=missing)
    save_session(session_path, data)
    return data
