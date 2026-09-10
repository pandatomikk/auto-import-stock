"""Encrypted local vault; encryption key belongs to the OS credential store."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class VaultError(ValueError):
    pass


def system_vault():
    try:
        import keyring
        backend = keyring.get_keyring()
        allowed = {'keyring.backends.Windows', 'keyring.backends.macOS', 'keyring.backends.SecretService', 'keyring.backends.kwallet'}
        candidates = getattr(backend, 'backends', [backend])
        for candidate in candidates:
            if type(candidate).__module__ in allowed:
                return candidate
    except Exception:
        pass
    raise VaultError('Coffre système indisponible. Installez les dépendances et déverrouillez votre trousseau de session ; aucun secret ne sera enregistré en clair.')


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.vault-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def store_path(settings):
    return Path(settings).parent / 'secrets' / 'shop.enc'


def cipher(path, create=False):
    try:
        from cryptography.fernet import Fernet
        vault = system_vault()
        account = hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()
        key = vault.get_password('auto-import-stock', account)
        if key is None and create:
            key = Fernet.generate_key().decode('ascii')
            vault.set_password('auto-import-stock', account, key)
            if vault.get_password('auto-import-stock', account) != key:
                raise ValueError()
        if key is None:
            raise ValueError()
        return Fernet(key.encode('ascii'))
    except VaultError:
        raise
    except Exception:
        raise VaultError('Clé de chiffrement inaccessible. Déverrouillez le coffre système de ce compte utilisateur.') from None


def save_secrets(settings, data):
    path = store_path(settings)
    atomic_write(path, cipher(path, create=True).encrypt(json.dumps(data).encode()))


def load_secrets(settings):
    path = store_path(settings)
    if not path.exists():
        return {}
    try:
        return json.loads(cipher(path).decrypt(path.read_bytes()))
    except VaultError:
        raise
    except Exception:
        raise VaultError('Le fichier de secrets ne peut pas être déchiffré avec ce compte système.') from None
