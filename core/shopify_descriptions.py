"""Description lookup in a configured public Shopify catalogue, by exact SKU."""
import json
import re
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .version import USER_AGENT


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'iframe'}:
            self.blocked += 1
        if tag in {'p', 'div', 'br', 'li'} and not self.blocked:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'iframe'}:
            self.blocked = max(0, self.blocked - 1)
        if tag in {'p', 'div', 'li'} and not self.blocked:
            self.parts.append('\n')

    def handle_data(self, text):
        if not self.blocked:
            self.parts.append(text)


def clean_text(raw):
    parser = TextOnly()
    parser.feed(str(raw or ''))
    return '\n'.join(re.sub(r'\s+', ' ', line).strip()
                     for line in ''.join(parser.parts).splitlines() if line.strip())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirection du catalogue fournisseur : adresse à vérifier')


class SupplierDescriptions:
    def __init__(self, settings):
        self.settings = settings
        self.records = []
        self.index = None
        self.error = None
        self.base = str(settings.get('base_url', '')).rstrip('/')
        url = urlsplit(self.base)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.port not in (None, 443) or url.query or url.fragment or url.path):
            raise ValueError('Adresse HTTPS du catalogue fournisseur invalide')

    def normalize(self, value):
        value = str(value or '').strip().upper()
        for char in self.settings.get('reference_remove_chars', ''):
            value = value.replace(char, '')
        return value

    def fetch(self, page):
        url = self.base + '/products.json?' + urlencode({'limit': 250, 'page': page})
        request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Language': 'fr-FR'})
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            data = response.read(16_000_001)
            if len(data) > 16_000_000:
                raise ValueError('Catalogue fournisseur trop volumineux')
        products = json.loads(data)['products']
        if not isinstance(products, list):
            raise ValueError('Catalogue fournisseur invalide')
        return products

    def load(self):
        index = {}
        seen = set()
        for page in range(1, int(self.settings.get('max_pages', 20)) + 1):
            if page > 1:
                time.sleep(float(self.settings.get('delay_seconds', .4)))
            products = self.fetch(page)
            print(f'Descriptions fournisseur : page {page}, {len(products)} fiches.', flush=True)
            for product in products:
                key = product['id']
                if key in seen:
                    raise ValueError('Pagination du catalogue répétée : recherche interrompue')
                seen.add(key)
                for variant in product.get('variants', []):
                    reference = self.normalize(variant.get('sku'))
                    if reference:
                        index.setdefault(reference, []).append((product, variant))
            if len(products) < 250:
                self.index = index
                return
        raise ValueError('Catalogue incomplet : limite de pages atteinte')

    def get(self, values):
        record = {'sku': str(values.get('sku') or ''), 'status': 'fallback'}
        try:
            if self.index is None and self.error is None:
                try:
                    self.load()
                except Exception as exc:
                    self.error = str(exc)
            if self.error:
                raise ValueError(self.error)
            reference = self.normalize(values.get(self.settings.get('reference_field', 'model')))
            record['reference'] = reference
            candidates = self.index.get(reference, [])
            if len(candidates) != 1:
                raise ValueError('Référence absente ou ambiguë dans le catalogue fournisseur')
            product, variant = candidates[0]
            ean, barcode = str(values.get('ean') or '').strip(), str(variant.get('barcode') or '').strip()
            if ean and barcode and ean != barcode:
                raise ValueError('EAN différent de la fiche fournisseur')
            text = clean_text(product.get('body_html'))
            if not text:
                raise ValueError('Description fournisseur vide')
            record.update(status='retrieved', url=self.base + '/products/' + product['handle'],
                          variant_id=str(variant['id']))
            return text
        except Exception as exc:
            record['reason'] = str(exc)
            return None
        finally:
            self.records.append(record)
