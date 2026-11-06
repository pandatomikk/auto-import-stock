"""Conservative name comparison; every candidate requires a human decision."""
import html
import re
import unicodedata
from difflib import SequenceMatcher
from core.shop_connection import ConnectionFailure

PARTICLES = {'a', 'au', 'aux', 'de', 'des', 'du', 'en', 'et', 'le', 'la', 'les', 'un', 'une', 'd', 'l'}
SYNONYMS = {'sacs': 'sac', 'handbag': 'sac', 'epaule': 'bandouliere'}
DISTINCT = set('noir noire blanc blanche bleu bleue rouge vert verte rose beige marron camel gris grise dore argente marine kaki violet orange jaune petit petite grand grande mini maxi nano medium small large xl xxl xs s m l'.split())


def tokens(name):
    text = ''.join(c for c in unicodedata.normalize('NFKD', html.unescape(name).casefold()) if not unicodedata.combining(c))
    return {SYNONYMS.get(t, t) for t in re.findall(r'[a-z0-9]+', text) if t not in PARTICLES}


def match_reason(left, right):
    a, b = left['payload'], right
    ea, eb = a.get('global_unique_id', ''), b.get('global_unique_id', '')
    if ea and eb:
        return 'Même EAN' if ea == eb else None
    ta, tb = tokens(a.get('name', '')), tokens(b.get('name', ''))
    if not ta or not tb:
        return None
    for field in ('brands',):
        va = {x['id'] for x in a.get(field, []) if 'id' in x}
        vb = {x['id'] for x in b.get(field, []) if 'id' in x}
        if va and vb and va.isdisjoint(vb):
            return None
    # Known colours, sizes and model numbers must not be blurred by fuzzy matching.
    difference = ta ^ tb
    if difference & DISTINCT or any(any(c.isdigit() for c in t) for t in difference):
        return None
    attrs_a = {x.get('name', '').casefold(): set(x.get('options', [])) for x in a.get('attributes', [])}
    attrs_b = {x.get('name', '').casefold(): set(x.get('options', [])) for x in b.get('attributes', [])}
    if any(attrs_a[k] and attrs_b[k] and attrs_a[k].isdisjoint(attrs_b[k]) for k in attrs_a.keys() & attrs_b.keys()):
        return None
    if ta == tb:
        return 'Nom identique après normalisation'
    sa, sb = ' '.join(sorted(ta)), ' '.join(sorted(tb))
    if len(ta & tb) >= 2 and SequenceMatcher(None, sa, sb).ratio() >= .88:
        return 'Nom proche : vérifier le modèle, la couleur et la taille'
    return None


def detect_duplicates(plan, catalogue):
    previous = []
    for item in plan['items']:
        if item['state'] != 'new':
            continue
        candidates = []
        for product in catalogue + previous:
            reason = match_reason(item, product)
            if reason:
                candidates.append({'id': product.get('id'), 'line': product.get('_line'), 'name': product.get('name', ''), 'sku': product.get('sku', ''), 'reason': reason})
        if candidates:
            item['duplicate_candidates'] = candidates
        previous.append(dict(item['payload'], _line=item['line']))
    return plan


def require_duplicate_decisions(plan):
    if any(i.get('duplicate_candidates') and i.get('duplicate_decision') not in ('create', 'skip') for i in plan['items']):
        raise ConnectionFailure('Doublons possibles : choisissez Ignorer ou Créer quand même avant l’envoi.')
