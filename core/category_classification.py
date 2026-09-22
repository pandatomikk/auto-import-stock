"""Supplier-configured category proposals, reviewed against shop destinations."""
import re

REVIEW_PREFIX = 'À classer : '


def classify(values, settings):
    for rule in settings.get('rules', []):
        value = str(values.get(rule.get('source', 'name'), '') or '').strip()
        if ('equals' in rule and value.casefold() == str(rule['equals']).casefold()) or ('regex' in rule and re.search(rule['regex'], value)):
            if rule.get('review'):
                return REVIEW_PREFIX + rule.get('label', value or 'Type inconnu'), 'À vérifier'
            return rule['category'], 'Classé'
    value = str(values.get(settings.get('fallback_field', 'name'), '') or '').strip()
    return REVIEW_PREFIX + (value or 'Type inconnu'), 'À vérifier'
