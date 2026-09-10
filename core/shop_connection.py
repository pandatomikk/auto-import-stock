"""Read-only WordPress/WooCommerce connection checks. Optional local credential persistence, outside the application checkout."""
from dataclasses import dataclass, field
import base64
import json
import os
from pathlib import Path
import tempfile
from core.secret_store import VaultError, save_secrets, load_secrets, store_path
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class ConnectionFailure(ValueError):
    pass


def normalize_url(value):
    value = value.strip()
    if not value.startswith('https://'):
        raise ConnectionFailure('Renseignez une adresse complète en https://.')
    try:
        parts = urlsplit(value)
        _ = parts.port  # Validate malformed ports.
    except ValueError:
        raise ConnectionFailure('Adresse de boutique invalide.') from None
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or any(c.isspace() for c in value):
        raise ConnectionFailure('Utilisez l’adresse HTTPS de la boutique, sans identifiants ni paramètres.')
    path = parts.path.rstrip('/')
    if path.endswith(('/wp-admin', '/wp-json')):
        raise ConnectionFailure('Utilisez l’adresse de la boutique, sans /wp-admin ni /wp-json.')
    return urlunsplit(('https', parts.netloc, path, '', ''))


@dataclass(repr=False)
class Credentials:
    url: str = ''
    username: str = ''
    application_password: str = field(default='', repr=False)
    consumer_key: str = field(default='', repr=False)
    consumer_secret: str = field(default='', repr=False)

    def validated(self):
        url = normalize_url(self.url)
        values = [self.username.strip(), ''.join(self.application_password.split()), self.consumer_key.strip(), self.consumer_secret.strip()]
        if not all(values):
            raise ConnectionFailure('Renseignez les cinq champs pour tester les deux connexions.')
        if ':' in values[0] or any('\n' in v or '\r' in v for v in values):
            raise ConnectionFailure('Identifiants invalides.')
        return Credentials(url, *values)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward credentials, even when a server redirects to another host.
        return None


def get_json(url, username, password):
    token = base64.b64encode(f'{username}:{password}'.encode()).decode('ascii')
    request = Request(url, headers={'Authorization': 'Basic ' + token, 'Accept': 'application/json', 'User-Agent': 'AutoImportStock/0.20'}, method='GET')
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ConnectionFailure('Réponse du site trop volumineuse.')
        return json.loads(raw)
    except HTTPError as exc:
        exc.close()
        messages = {401: 'Identifiants refusés. Vérifiez les clés ou le mot de passe d’application.', 403: 'Accès refusé : vérifiez les droits du compte et les protections du site.', 404: 'API introuvable : vérifiez l’adresse, les permaliens et l’activation de WooCommerce.', 429: 'Trop de requêtes. Réessayez dans quelques instants.'}
        if 300 <= exc.code < 400:
            raise ConnectionFailure('Le site redirige la requête. Renseignez son adresse HTTPS définitive (avec ou sans www).') from None
        raise ConnectionFailure(messages.get(exc.code, f'Le site a renvoyé une erreur HTTP {exc.code}.')) from None
    except (URLError, socket.timeout, TimeoutError, ssl.SSLError, OSError):
        raise ConnectionFailure('Connexion impossible ou délai dépassé : vérifiez le réseau, l’adresse et le certificat HTTPS.') from None
    except (ValueError, UnicodeError):
        raise ConnectionFailure('Réponse inattendue : le site ne renvoie pas une réponse API JSON valide.') from None


def check_connection(credentials, fetch=get_json):
    c = credentials.validated()
    results = {}
    try:
        user = fetch(c.url + '/wp-json/wp/v2/users/me?context=edit', c.username, c.application_password)
        if not isinstance(user, dict) or not isinstance(user.get('id'), int) or user['id'] <= 0:
            raise ConnectionFailure('Réponse WordPress inattendue : utilisateur non reconnu.')
        capabilities = user.get('capabilities', {})
        upload = capabilities.get('upload_files') if isinstance(capabilities, dict) else None
        detail = 'Authentification réussie.'
        detail += ' Droit d’envoyer des médias présent.' if upload is True else (' Droit d’envoyer des médias absent.' if upload is False else ' Droit d’envoyer des médias non confirmé.')
        results['wordpress'] = {'ok': True, 'message': detail}
    except ConnectionFailure as exc:
        results['wordpress'] = {'ok': False, 'message': str(exc)}
    try:
        products = fetch(c.url + '/wp-json/wc/v3/products?per_page=1&_fields=id', c.consumer_key, c.consumer_secret)
        if not isinstance(products, list) or any(not isinstance(p, dict) or not isinstance(p.get('id'), int) for p in products):
            raise ConnectionFailure('Réponse WooCommerce inattendue : catalogue non reconnu.')
        results['woocommerce'] = {'ok': True, 'message': 'Authentification et lecture du catalogue réussies. Les droits d’écriture ne sont pas testés à cette étape.'}
    except ConnectionFailure as exc:
        results['woocommerce'] = {'ok': False, 'message': str(exc)}
    return results


def settings_path():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return base / 'auto-import-stock' / 'shop.json'


def save_settings(credentials, path=None, *, remember_secrets=False):
    path = Path(path) if path else settings_path()
    data = {'url': normalize_url(credentials.url), 'username': credentials.username.strip()}
    if remember_secrets:
        save_secrets(path, {name: getattr(credentials, name) for name in ('application_password', 'consumer_key', 'consumer_secret')})
    else:
        store_path(path).unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates mode 0600 from the outset; replacement is atomic.
    descriptor, name = tempfile.mkstemp(prefix='.shop-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_storage(path=None):
    path = Path(path) if path else settings_path()
    for directory in (path.parent, path.parent / 'secrets'):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.exists():
        from core.secret_store import atomic_write
        atomic_write(path, b'{}')
    return path


def load_settings(path=None):
    path = Path(path) if path else settings_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not data.get('url'):
            return Credentials()
        credentials = Credentials(url=normalize_url(data.get('url', '')), **{name: str(data.get(name, '')) for name in ('username', 'application_password', 'consumer_key', 'consumer_secret')})
    except (OSError, ValueError, AttributeError, TypeError):
        return Credentials()
    if any(name in data for name in ('application_password', 'consumer_key', 'consumer_secret')):
        # Remove plaintext only after encrypted storage and key readback succeed.
        save_settings(credentials, path, remember_secrets=True)
    secrets = load_secrets(path)
    for name in ('application_password', 'consumer_key', 'consumer_secret'):
        setattr(credentials, name, str(secrets.get(name, '')))
    return credentials
