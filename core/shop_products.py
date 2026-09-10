"""CSV preview and create-only WooCommerce imports. No update endpoint exists here."""
import base64
import csv
from decimal import Decimal, InvalidOperation
import html
import io
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, build_opener
from core.shop_connection import ConnectionFailure, NoRedirect, normalize_url
from core.secret_store import atomic_write


class ProductAPI:
    def __init__(self, credentials):
        self.credentials = credentials
        self.url = normalize_url(credentials.url)
        if not credentials.consumer_key.strip() or not credentials.consumer_secret.strip():
            raise ConnectionFailure('Renseignez les clés WooCommerce.')

    def request(self, route, query=None, payload=None):
        c = self.credentials
        wordpress = route.startswith('wp/v2/')
        user, password = (c.username.strip(), ''.join(c.application_password.split())) if wordpress else (c.consumer_key.strip(), c.consumer_secret.strip())
        if not user or not password:
            raise ConnectionFailure('Les accès WordPress sont nécessaires pour retrouver les images de la médiathèque.')
        # Restrict every write to product creation, never updates or deletions.
        if payload is not None and route not in ('wc/v3/products', 'wc/v3/products/categories'):
            raise ConnectionFailure('Seule la création de produits ou de catégories est autorisée.')
        address = self.url + '/wp-json/' + route + ('?' + urlencode(query) if query else '')
        token = base64.b64encode(f'{user}:{password}'.encode()).decode('ascii')
        request = Request(address, data=None if payload is None else json.dumps(payload).encode(), method='GET' if payload is None else 'POST', headers={'Authorization': 'Basic ' + token, 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'AutoImportStock/0.20'})
        try:
            with build_opener(NoRedirect()).open(request, timeout=60) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                self.last_total_pages = int(response.headers.get('X-WP-TotalPages', '0'))
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError()
            return json.loads(raw)
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise ConnectionFailure(f'API : erreur HTTP {code}. Vérifiez les accès et les droits du site.' + (' Création non confirmée : vérifiez la boutique avant de relancer.' if payload is not None else '')) from None
        except (OSError, URLError, ValueError):
            raise ConnectionFailure('Réponse API absente ou invalide.' + (' Création non confirmée : vérifiez la boutique avant de relancer.' if payload is not None else '')) from None

    def listing(self, route):
        items = []
        for page in range(1, 1001):
            batch = self.request(route, {'per_page': 100, 'page': page})
            if not isinstance(batch, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), int) for x in batch):
                raise ConnectionFailure('Liste API invalide : contrôle interrompu.')
            items.extend(batch)
            if len(batch) < 100 or (getattr(self, 'last_total_pages', 0) and page >= self.last_total_pages):
                return items
        raise ConnectionFailure('Catalogue trop volumineux pour ce test ; contrôle interrompu.')

    def existing(self, sku):
        result = self.request('wc/v3/products', {'sku': sku, 'status': 'any', 'per_page': 100})
        if not isinstance(result, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), int) for x in result):
            raise ConnectionFailure('Recherche de référence invalide : contrôle interrompu.')
        # A comma in a SKU acts as a list in WooCommerce; CSV validation rejects it.
        return result

    def create_category(self, name):
        name = name.strip()
        if not name or '>' in name:
            raise ConnectionFailure('Renseignez un nom de catégorie simple. Pour une hiérarchie, créez-la dans WordPress.')
        existing = [term for term in self.listing('wc/v3/products/categories') if html.unescape(term.get('name', '')).casefold() == name.casefold() and not term.get('parent')]
        if len(existing) == 1:
            return existing[0]
        if existing:
            raise ConnectionFailure('Plusieurs catégories correspondent : choisissez dans la liste.')
        result = self.request('wc/v3/products/categories', payload={'name': name, 'parent': 0})
        if not isinstance(result, dict) or type(result.get('id')) is not int or not result.get('name'):
            raise ConnectionFailure('Création de catégorie non confirmée. Rechargez les correspondances avant de réessayer.')
        return result

    def create(self, payload):
        return self.request('wc/v3/products', payload=payload)


def number(value, integer=False):
    try:
        amount = Decimal(value.replace(',', '.'))
        if not amount.is_finite() or amount < 0 or (integer and amount != amount.to_integral_value()):
            raise ValueError()
        return int(amount) if integer else format(amount, 'f')
    except (InvalidOperation, ValueError):
        raise ConnectionFailure('Nombre invalide ou négatif : ' + value) from None


def boolean(value):
    if value not in ('0', '1'):
        raise ConnectionFailure('Valeur booléenne attendue : 0 ou 1.')
    return value == '1'


def split_values(value):
    return [x.strip() for x in re.split(r'(?<!\\),', value) if x.strip()]


def read_products_csv(path):
    try:
        if Path(path).stat().st_size > 10 * 1024 * 1024:
            raise ConnectionFailure('CSV trop volumineux pour ce test (maximum 10 Mo).')
        text = Path(path).read_text(encoding='utf-8-sig')
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=',;\t')
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        headers = [x.strip().replace('\xa0', ' ') for x in (reader.fieldnames or [])]
        if len(set(headers)) != len(headers) or not {'UGS', 'Nom'}.issubset(headers):
            raise ConnectionFailure('CSV WooCommerce attendu : colonnes UGS et Nom obligatoires, sans doublons.')
        result = []
        for index, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ConnectionFailure(f'Ligne {index} : nombre de colonnes incorrect.')
            clean = {k.strip().replace('\xa0', ' '): v.strip() for k, v in row.items()}
            if any(clean.values()):
                result.append((index, clean))
        if not result:
            raise ConnectionFailure('Le CSV ne contient aucun article.')
        return result
    except (OSError, UnicodeError, csv.Error):
        raise ConnectionFailure('CSV illisible : utilisez le CSV WooCommerce UTF-8 généré par l’outil.') from None


class Resolver:
    def __init__(self, api, mappings=None):
        self.api = api
        self.cache = {}
        self.mappings = mappings or {}
        self.used_mappings = []

    def all(self, route):
        if route not in self.cache:
            self.cache[route] = self.api.listing(route)
        return self.cache[route]

    def terms(self, kind, value):
        terms = self.all('wc/v3/products/' + kind)
        ids = []
        for name in split_values(value):
            from core.shop_mappings import source_key, term_labels
            selected = self.mappings.get(kind, {}).get(source_key(name.replace('\\,', ',')))
            if selected is not None:
                if selected not in {term['id'] for term in terms}:
                    raise ConnectionFailure(f'Correspondance {kind} périmée : {name}. Choisissez une autre destination.')
                ids.append({'id': selected})
                self.used_mappings.append({'kind': kind, 'source': name, 'id': selected, 'destination': term_labels(kind, terms)[selected]})
                continue
            parent = 0
            for component in (name.split('>') if kind == 'categories' else [name]):
                matches = [t for t in terms if html.unescape(t.get('name', '')).casefold() == component.strip().replace('\\,', ',').casefold() and (kind != 'categories' or t.get('parent', 0) == parent)]
                if len(matches) != 1:
                    raise ConnectionFailure(f'{kind} : « {name} » absent ou ambigu dans la boutique. Créez-le avant ce test.')
                parent = matches[0]['id']
            ids.append({'id': parent})
        return ids

    def images(self, value):
        media = self.all('wp/v2/media')
        result = []
        for location in split_values(value):
            location = location.replace('\\,', ',')
            matches = []
            for image in media:
                sources = [image.get('source_url', '')]
                sources += [s.get('source_url', '') for s in image.get('media_details', {}).get('sizes', {}).values()]
                if '://' in location:
                    found = any(unquote(s) == unquote(location) for s in sources)
                else:
                    found = any(unquote(urlsplit(s).path).rsplit('/', 1)[-1] == location for s in sources)
                if found:
                    matches.append(image)
            if len(matches) != 1:
                raise ConnectionFailure(f'Image absente ou ambiguë dans WordPress : {location}. Envoyez-la d’abord ou utilisez son URL exacte.')
            result.append({'id': matches[0]['id']})
        return result


def row_payload(row, resolver):
    used = {'ID', 'Type', 'UGS', 'Nom', 'Publié'}
    if row.get('ID') or row.get('Type', 'simple') not in ('', 'simple'):
        raise ConnectionFailure('Création uniquement : ID vide et type simple requis.')
    if not row.get('UGS') or not row.get('Nom') or ',' in row['UGS']:
        raise ConnectionFailure('Nom et UGS obligatoires ; l’UGS ne doit pas contenir de virgule.')
    if row.get('Publié', '1') not in ('', '1'):
        raise ConnectionFailure('Ce test crée des produits publiés : la colonne Publié doit valoir 1.')
    payload = {'type': 'simple', 'status': 'publish', 'sku': row['UGS'], 'name': row['Nom']}
    texts = {'Description': 'description', 'Description courte': 'short_description', 'GTIN, UPC, EAN ou ISBN': 'global_unique_id', 'Note de commande': 'purchase_note', 'Classe de TVA': 'tax_class', 'Classe d’expédition': 'shipping_class', 'Date de début de promo': 'date_on_sale_from', 'Date de fin de promo': 'date_on_sale_to'}
    for column, field in texts.items():
        used.add(column)
        if row.get(column):
            payload[field] = row[column]
    for column, field in {'Tarif régulier': 'regular_price', 'Tarif promo': 'sale_price', 'Poids (kg)': 'weight'}.items():
        used.add(column)
        if row.get(column):
            payload[field] = number(row[column])
    for column, field in {'Longueur (cm)': 'length', 'Largeur (cm)': 'width', 'Hauteur (cm)': 'height'}.items():
        used.add(column)
        if row.get(column):
            payload.setdefault('dimensions', {})[field] = number(row[column])
    for column, field in {'Mis en avant ?': 'featured', 'Vendre individuellement ?': 'sold_individually', 'Autoriser les avis clients ?': 'reviews_allowed'}.items():
        used.add(column)
        if row.get(column):
            payload[field] = boolean(row[column])
    for column, field, choices in [('Visibilité dans le catalogue', 'catalog_visibility', ('visible', 'catalog', 'search', 'hidden')), ('État de la TVA', 'tax_status', ('taxable', 'shipping', 'none'))]:
        used.add(column)
        if row.get(column):
            if row[column] not in choices:
                raise ConnectionFailure('Valeur non reconnue : ' + column)
            payload[field] = row[column]
    used.update(('Stock', 'En stock ?', 'Montant de stock faible', 'Position', 'Autoriser les commandes de produits en rupture ?'))
    if row.get('Stock'):
        payload.update(manage_stock=True, stock_quantity=number(row['Stock'], integer=True))
    if row.get('En stock ?'):
        payload['stock_status'] = 'instock' if boolean(row['En stock ?']) else 'outofstock'
    for column, field in [('Position', 'menu_order'), ('Montant de stock faible', 'low_stock_amount')]:
        if row.get(column):
            payload[field] = number(row[column], integer=True)
    if row.get('Autoriser les commandes de produits en rupture ?'):
        value = row['Autoriser les commandes de produits en rupture ?']
        if value not in ('0', '1', 'notify'):
            raise ConnectionFailure('Valeur de commandes en rupture non reconnue.')
        payload['backorders'] = {'0': 'no', '1': 'yes', 'notify': 'notify'}[value]
    for column, kind in [('Catégories', 'categories'), ('Étiquettes', 'tags'), ('Marques', 'brands')]:
        used.add(column)
        if row.get(column):
            payload[kind] = resolver.terms(kind, row[column])
    used.add('Images')
    if row.get('Images'):
        payload['images'] = resolver.images(row['Images'])
    for index in range(1, 101):
        name, values, visible, global_ = f'Nom de l’attribut {index}', f'Valeur(s) de l’attribut {index}', f'Attribut {index} visible', f'Attribut {index} global'
        used.update((name, values, visible, global_))
        if row.get(name):
            attribute = {'name': row[name], 'options': [x.replace('\\,', ',') for x in split_values(row.get(values, ''))], 'visible': boolean(row.get(visible) or '1'), 'variation': False}
            if row.get(global_) and boolean(row[global_]):
                matches = [a for a in resolver.all('wc/v3/products/attributes') if html.unescape(a.get('name', '')).casefold() == row[name].casefold()]
                if len(matches) != 1:
                    raise ConnectionFailure('Attribut global absent ou ambigu : ' + row[name])
                attribute.pop('name'); attribute['id'] = matches[0]['id']
                terms = resolver.all(f"wc/v3/products/attributes/{attribute['id']}/terms")
                known = {html.unescape(t['name']).casefold() for t in terms}
                if any(option.casefold() not in known for option in attribute['options']):
                    raise ConnectionFailure('Valeur d’attribut global absente : ' + row[name])
            payload.setdefault('attributes', []).append(attribute)
        elif row.get(values):
            raise ConnectionFailure('Valeurs d’attribut sans nom.')
    unsupported = [key for key, value in row.items() if value and key not in used]
    if unsupported:
        raise ConnectionFailure('Colonnes renseignées non prises en charge : ' + ', '.join(unsupported))
    return payload


def prepare_csv(path, api, progress=lambda text: None, mappings=None):
    rows = read_products_csv(path)
    resolver = Resolver(api, mappings)
    plan = {'site': api.url, 'source': str(Path(path).resolve()), 'items': [], 'errors': []}
    seen = set()
    for index, row in rows:
        sku = row.get('UGS', '')
        progress(f'Contrôle de la ligne {index} : {sku}')
        try:
            if not sku or ',' in sku:
                raise ConnectionFailure('UGS obligatoire, sans virgule.')
            if sku.casefold() in seen:
                raise ConnectionFailure('UGS présente plusieurs fois dans le CSV.')
            seen.add(sku.casefold())
            if api.existing(sku):
                plan['items'].append({'line': index, 'sku': sku, 'name': row.get('Nom', ''), 'state': 'existing'})
                continue
            payload = row_payload(row, resolver)
            plan['items'].append({'line': index, 'sku': sku, 'name': row['Nom'], 'state': 'new', 'payload': payload})
        except ConnectionFailure as exc:
            plan['errors'].append(f'Ligne {index} ({sku}) : {exc}')
    plan['correspondences'] = resolver.used_mappings
    return plan


def import_plan(plan, api, report_path, progress=lambda text: None):
    if plan['errors'] or plan['site'] != api.url:
        raise ConnectionFailure('Aperçu invalide ou boutique différente : recommencez le contrôle.')
    report = {'site': api.url, 'source': plan['source'], 'total': len(plan['items']), 'correspondences': plan.get('correspondences', []), 'results': []}
    def save():
        atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2).encode())
    save()  # Verify report storage before any product is created.
    for item in plan['items']:
        record = {k: item[k] for k in ('line', 'sku', 'name')}
        if item['state'] == 'existing':
            record['state'] = 'skipped'
            report['results'].append(record); save()
            continue
        progress('Création : ' + item['sku'])
        # Recheck immediately before POST, including when resuming after an interruption.
        if api.existing(item['sku']):
            record['state'] = 'skipped'
            report['results'].append(record); save()
            continue
        record['state'] = 'unconfirmed'
        report['results'].append(record); save()
        try:
            result = api.create(item['payload'])
            if not isinstance(result, dict) or not isinstance(result.get('id'), int) or result['id'] <= 0 or result.get('sku') != item['sku']:
                raise ConnectionFailure('Création non confirmée : vérifiez la boutique avant de relancer.')
            record.update(state='created', id=result['id'], url=result.get('permalink', ''))
        except ConnectionFailure as exc:
            record['message'] = str(exc)
            save()
            break  # No automatic retry of a possibly successful write.
        save()
    return report
