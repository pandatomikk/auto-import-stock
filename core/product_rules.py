"""Local supplier/shop presentation rules; source identifiers stay untouched."""
import hashlib
import json
import re
from pathlib import Path
from core.shop_connection import settings_path
from core.secret_store import atomic_write


def rule_key(value):
    return ' '.join(str(value or '').strip().upper().split())


def current_site():
    try:
        return json.loads(settings_path().read_text(encoding='utf-8')).get('url', '')
    except (OSError, ValueError, AttributeError):
        return ''


def rules_path(supplier, site=None):
    site = current_site() if site is None else site
    digest = hashlib.sha256((supplier + '\n' + site).encode()).hexdigest()[:24]
    return settings_path().parent / 'regles-produits' / (digest + '.json')


def load_rules(config, path=None):
    rules = dict(config.get('product_rules', {}))
    rules['colors'] = dict(rules.get('colors', {}))
    rules['models'] = dict(rules.get('models', {}))
    if path and Path(path).exists():
        saved = json.loads(Path(path).read_text(encoding='utf-8'))
        rules.update({k: v for k, v in saved.items() if k not in ('colors', 'models')})
        for name in ('colors', 'models'):
            rules[name].update(saved.get(name, {}))
    return rules


def save_rules(path, rules):
    atomic_write(path, json.dumps(rules, ensure_ascii=False, indent=2).encode())


def logical_values(row, mapping):
    return {key: str(row.get(info['source'], '') or '').strip() for key, info in mapping.items()}


def display_values(values, rules):
    raw_model = values.get(rules.get('model_field', 'name'), '')
    model = re.sub(rules.get('model_remove_pattern') or r'(?!)', '', raw_model).strip().title()
    override = rules.get('models', {}).get(rule_key(raw_model), {})
    model = override.get('name') or model
    raw_color = values.get('color', '')
    colors = rules.get('colors', {})
    from core.color_translations import translate_color
    color = translate_color(raw_color, colors)
    if raw_color and not color:
        raise ValueError('Couleur non traduite : ' + raw_color + '. Ouvrez Règles produits pour la renseigner.')
    if not model:
        raise ValueError('Modèle commercial absent : vérifiez le champ modèle dans Règles produits.')
    color = color or ''
    category = override.get('category') or rules.get('category_template', '{model}').format(model=model)
    color_parts = [part.strip() for part in color.split('/')]
    compact_color = '/'.join(color_parts)
    compact_initial_lower = '/'.join([color_parts[0].lower(), *color_parts[1:]])
    title = rules.get('name_template', '{model} — {color}').format(model=model, model_upper=model.upper(), color=color, color_compact=compact_color, color_compact_initial_lower=compact_initial_lower).strip(' —-')
    return {'model': model, 'color': color, 'category': category, 'title': title, 'raw_model': raw_model, 'raw_color': raw_color}
