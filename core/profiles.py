"""Discovery of public examples and optional local profiles/adapters."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import sys
import types

APP_DIR = Path(__file__).resolve().parent.parent


def private_directory():
    return Path(os.environ.get('AUTO_IMPORT_PRIVATE_DIR', APP_DIR / 'private')).expanduser().resolve()


def read_profile(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Le profil doit contenir un objet JSON.')
    return data


def discover_profiles():
    profiles = {}
    for directory in (APP_DIR / 'profiles', private_directory() / 'profiles'):
        for path in sorted(directory.glob('*.json')):
            if not path.name.startswith('_') and not path.name.endswith('_rules.json'):
                profiles[path.stem] = path
    real = {key: path for key, path in profiles.items() if not read_profile(path).get('demo')}
    selected = real or profiles
    return sorted(selected.values(), key=lambda path: str(read_profile(path).get('supplier_name', path.stem)).casefold())


def resolve_profile(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
        raise ValueError('Identifiant de profil invalide.')
    for directory in (private_directory() / 'profiles', APP_DIR / 'profiles'):
        path = directory / (identifier + '.json')
        if path.is_file():
            return path
    raise ValueError('Profil introuvable : ' + identifier + '. Installer son pack privé ou sélectionner un profil disponible.')


def workflow_kind(config):
    return config.get('workflow', {}).get('kind', 'catalogue')


def load_adapter(name):
    """Load trusted local Python extensions; never download or execute remote code."""
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
        raise ValueError('Nom d’adaptateur invalide.')
    directory = private_directory() / 'adapters'
    if not (directory / (name + '.py')).is_file():
        raise ValueError('Adaptateur local absent : ' + name + '. Installer le pack privé correspondant.')
    # A distinct package per directory supports sibling relative imports without
    # sharing modules across separately configured private packs.
    import hashlib
    package_name = '_auto_import_private_' + hashlib.sha256(str(directory).encode()).hexdigest()[:12]
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(directory)]
        sys.modules[package_name] = package
    return importlib.import_module(package_name + '.' + name)
