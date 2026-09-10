"""Deterministic colour vocabulary. Unknown supplier labels require a user choice."""
import re
import unicodedata


def normalized(value):
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', value.replace('-', ' ').replace("'", '').replace('’', '')).strip()


# French output and common French/Italian/English/Spanish/German spellings.
VOCABULARY = {
    'Noir': 'noir|nero|black|negro|schwarz',
    'Blanc': 'blanc|bianco|white|blanco|weiss|weiß',
    'Blanc cassé': 'blanc cassé|off white|broken white|bianco sporco|blanco roto',
    'Écru': 'écru|ecru|unbleached',
    'Ivoire': 'ivoire|ivory|avorio|marfil|elfenbein',
    'Crème': 'crème|cream|crema|creme',
    'Beige': 'beige|beig',
    'Beige clair': 'beige clair|light beige|beige chiaro|beige claro|hellbeige',
    'Sable': 'sable|sand|sabbia|arena|sandfarben',
    'Camel': 'camel|cammello|camello|kamel',
    'Cognac': 'cognac|cuoio',
    'Marron': 'marron|marrone|brown|braun|castaño',
    'Marron foncé': 'marron foncé|dark brown|marrone scuro|moro|dunkelbraun|marrón oscuro',
    'Marron clair': 'marron clair|light brown|marrone chiaro|hellbraun|marrón claro',
    'Fauve': 'fauve|tan|tawny',
    'Chocolat': 'chocolat|chocolate|cioccolato|schokolade',
    'Café': 'café|coffee|caffe|caffè',
    'Taupe': 'taupe|tortora',
    'Gris': 'gris|grigio|grig|grey|gray|grau',
    'Gris clair': 'gris clair|light grey|light gray|grigio chiaro|hellgrau|gris claro',
    'Gris foncé': 'gris foncé|dark grey|dark gray|grigio scuro|dunkelgrau|gris oscuro',
    'Anthracite': 'anthracite|antracite|antrac|charcoal|anthrazit|antracita',
    'Canon de fusil': 'canon de fusil|gunmetal|gun metal|canna di fucile|cannafucile|cannafucil|cannafuc|c.fucile',
    'Argenté': 'argenté|argent|argento|silver|silber|plata|plateado',
    'Doré': 'doré|or|oro|gold|golden|dorado|goldfarben',
    'Or rose': 'or rose|rose gold|pink gold|oro rosa|roségold',
    'Bronze': 'bronze|bronzo|bronce',
    'Cuivré': 'cuivré|cuivre|copper|rame|cobre|kupfer',
    'Titane': 'titane|titanio|titanium|titan',
    'Rouge': 'rouge|rosso|red|rojo|rot',
    'Bordeaux': 'bordeaux|bord|burgundy|wine red|bordo|burdeos|weinrot',
    'Cerise': 'cerise|cherry|ciliegia|cereza|kirschrot',
    'Brique': 'brique|brick|mattone|ladrillo|ziegelrot',
    'Rose': 'rose|pink|rosa|rosado',
    'Rose poudré': 'rose poudré|powder pink|cipria|rosa empolvado|puderrosa',
    'Vieux rose': 'vieux rose|dusty rose|rosa antico|altrosa',
    'Fuchsia': 'fuchsia|fuxia|fucsia|fuchsia pink',
    'Corail': 'corail|coral|corallo|koralle',
    'Orange': 'orange|arancione|arancio|naranja',
    'Jaune': 'jaune|yellow|giallo|amarillo|gelb',
    'Moutarde': 'moutarde|mustard|senape|mostaza|senfgelb',
    'Vert': 'vert|green|verde|grün|gruen',
    'Vert clair': 'vert clair|light green|verde chiaro|hellgrün|verde claro',
    'Vert foncé': 'vert foncé|dark green|verde scuro|dunkelgrün|verde oscuro',
    'Kaki': 'kaki|khaki|militare|verde militare|military green|army green|verde militar|verde m',
    'Olive': 'olive|oliva|olive green|olivgrün',
    'Émeraude': 'émeraude|emerald|smeraldo|esmeralda|smaragdgrün',
    'Menthe': 'menthe|mint|menta|minzgrün',
    'Bleu': 'bleu|blue|blu|azul|blau',
    'Bleu marine': 'bleu marine|navy|navy blue|blu navy|blu marino|azul marino|marineblau',
    'Bleu ciel': 'bleu ciel|sky blue|azzurro|celeste|himmelblau',
    'Bleu clair': 'bleu clair|light blue|hellblau|azul claro',
    'Bleu foncé': 'bleu foncé|dark blue|blu scuro|dunkelblau|azul oscuro',
    'Bleu pétrole': 'bleu pétrole|petrol|petroleum blue|petrolio|azul petroleo',
    'Turquoise': 'turquoise|turquoise blue|turchese|turquesa|türkis',
    'Violet': 'violet|purple|viola|morado|violeta|violett',
    'Lilas': 'lilas|lilac|lilla|lila|flieder',
    'Lavande': 'lavande|lavender|lavanda|lavendel',
    'Prune': 'prune|plum|prugna|ciruela|pflaume',
    'Nude': 'nude|nudo',
    'Naturel': 'naturel|natural|naturale|natur',
    'Multicolore': 'multicolore|multicolor|multicolour|multi color|multi colour|multi|mehrfarbig',
    'Transparent': 'transparent|trasparente|transparente|clear|durchsichtig',
    'Gris glace': 'gris glace|ice grey|ice gray|ghiaccio',
    'Gris pierre': 'gris pierre|stone grey|stone gray|roccia',
}
LOOKUP = {normalized(alias): french for french, aliases in VOCABULARY.items() for alias in [french, *aliases.split('|')]}


def translate_color(value, overrides=None):
    overrides = {normalized(key): translation for key, translation in (overrides or {}).items() if translation}
    def single(text):
        key = normalized(text)
        return overrides.get(key) or LOOKUP.get(key)
    if not str(value).strip():
        return ''
    exact = single(value)
    if exact:
        return exact
    parts = re.split(r'\s*(?:[/+&;]|\band\b|\bet\b|\bund\b|\be\b|\by\b)\s*', str(value), flags=re.I)
    if len(parts) == 1:
        parts = str(value).split('-')
    translated = [single(part) for part in parts]
    if all(translated):
        return ' / '.join(dict.fromkeys(translated))
    return None
