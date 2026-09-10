"""Per-shop taxonomy mappings and suggestions; no supplier rules in public code."""
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata
from core.shop_connection import ConnectionFailure, normalize_url, settings_path
from core.secret_store import atomic_write

KINDS = {'brands': 'Marques', 'categories': 'Catégories'}


def source_key(value):
    return ' '.join(html.unescape(value).strip().casefold().split())


def comparable(value):
    value = unicodedata.normalize('NFKD', source_key(value))
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


def mapping_path(site):
    digest = hashlib.sha256(normalize_url(site).encode()).hexdigest()[:24]
    return settings_path().parent / 'correspondances' / (digest + '.json')


def load_mappings(site, path=None):
    path = Path(path) if path else mapping_path(site)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['site'] != normalize_url(site) or not isinstance(data['mappings'], dict):
            raise ValueError()
        for kind, entries in data['mappings'].items():
            if kind not in KINDS or not isinstance(entries, dict) or any(not isinstance(k, str) or type(v) is not int or v <= 0 for k, v in entries.items()):
                raise ValueError()
        return data['mappings']
    except (OSError, ValueError, KeyError, TypeError):
        raise ConnectionFailure('Fichier de correspondances illisible ou associé à une autre boutique.') from None


def save_mappings(site, choices, path=None):
    target = Path(path) if path else mapping_path(site)
    existing = load_mappings(site, target)
    for kind, entries in choices.items():
        existing.setdefault(kind, {}).update(entries)
    atomic_write(target, json.dumps({'site': normalize_url(site), 'mappings': existing}, ensure_ascii=False, indent=2).encode())


def term_labels(kind, terms):
    by_id = {t['id']: t for t in terms}
    labels = {}
    for term in terms:
        chain = []
        current = term
        seen = set()
        while current:
            if current['id'] in seen:
                raise ConnectionFailure('Hiérarchie de catégories invalide dans la boutique.')
            seen.add(current['id'])
            chain.append(html.unescape(current.get('name', '')))
            current = by_id.get(current.get('parent')) if kind == 'categories' else None
        labels[term['id']] = ' > '.join(reversed(chain))
    return labels


def prepare_mappings(filename, api, progress=lambda text: None):
    from core.shop_products import read_products_csv, split_values
    rows = read_products_csv(filename)
    stored = load_mappings(api.url)
    review = {'site': api.url, 'source': str(filename), 'rows': [], 'options': {}}
    for kind, column in KINDS.items():
        sources = sorted({name.replace('\\,', ',') for _, row in rows for name in split_values(row.get(column, ''))})
        if not sources:
            continue
        progress('Chargement des ' + column.lower() + ' de la boutique…')
        terms = api.listing('wc/v3/products/' + kind)
        labels = term_labels(kind, terms)
        review['options'][kind] = labels
        for source in sources:
            key = source_key(source)
            chosen = stored.get(kind, {}).get(key)
            state = 'Mémorisé'
            if chosen not in labels:
                stale = chosen is not None
                exact = [t['id'] for t in terms if comparable(source) == comparable(labels[t['id']])]
                if not exact and kind == 'categories' and '>' not in source:
                    exact = [t['id'] for t in terms if comparable(source) == comparable(t.get('name', ''))]
                chosen = exact[0] if len(exact) == 1 and not stale else None
                state = 'Exact' if chosen else ('Ancienne destination absente : choisir' if stale else 'À choisir')
                if chosen is None and not stale:
                    ranked = sorted(((SequenceMatcher(None, comparable(source), comparable(label)).ratio() + (0.3 if comparable(source) and comparable(source) in comparable(label) else 0), id_) for id_, label in labels.items()), reverse=True)
                    if ranked and ranked[0][0] >= 0.5 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] > 0.05):
                        chosen = ranked[0][1]
                        state = 'Suggestion à valider'
            review['rows'].append({'kind': kind, 'source': source, 'id': chosen, 'state': state})
    return review
