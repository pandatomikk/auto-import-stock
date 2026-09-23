"""Read-only GitHub delivery of private packs; local changes are never overwritten."""
import base64
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from .secret_store import atomic_write

STATE = '.sync-state.json'


def allowed(name):
    if not isinstance(name, str) or '\\' in name:
        return False
    parts = name.split('/')
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) or p in ('.', '..') for p in parts):
        return False
    return name == 'client.json' or (len(parts) == 2 and ((parts[0] in ('profiles', 'rules') and name.endswith('.json')) or (parts[0] == 'adapters' and name.endswith('.py'))))


def digest(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_pack(repository, branch, token):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not re.fullmatch(r'[A-Za-z0-9_-]+', branch):
        raise ValueError('Dépôt ou branche invalide.')
    opener = build_opener(NoRedirect())
    def get(path):
        req = Request('https://api.github.com/repos/' + repository + path, headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'User-Agent': 'ZPSI-Private-Pack'})
        try:
            with opener.open(req, timeout=30) as response:
                raw = response.read(4_000_001)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(65536)).get('message', '')
                detail = ' '.join(str(detail).split())
                from urllib.parse import quote
                for secret in (token, quote(token, safe='')):
                    if secret: detail = detail.replace(secret, '[masqué]')
                detail = detail[:500]
                limited = exc.headers.get('X-RateLimit-Remaining') == '0' or 'rate limit' in detail.lower()
                hint = ('Limite de requêtes GitHub atteinte ; réessayez plus tard.' if limited else
                        'Vérifiez le jeton enregistré et les droits du dépôt.')
            except (ValueError, AttributeError, OSError):
                detail, hint = '', 'Vérifiez le jeton enregistré et les droits du dépôt.'
            finally:
                exc.close()
            raise ValueError(f'GitHub HTTP {exc.code} ({path}) : {detail or "refus sans détail"}. {hint}') from None
        if len(raw) > 4_000_000:
            raise ValueError('Réponse GitHub trop volumineuse.')
        return json.loads(raw)
    def listing(path):
        entries = get('/contents' + path + '?ref=' + branch)
        if not isinstance(entries, list) or len(entries) >= 1000:
            raise ValueError('Arborescence GitHub invalide ou trop volumineuse.')
        return entries

    roots = listing('')
    def manifest(entries):
        selected = {}
        for entry in entries:
            name = entry.get('path', '')
            if name not in {'client.json', 'profiles', 'rules', 'adapters'}:
                continue
            expected_type = 'file' if name == 'client.json' else 'dir'
            if entry.get('type') != expected_type or not re.fullmatch(r'[a-f0-9]{40}', entry.get('sha', '')) or name in selected:
                raise ValueError('Arborescence du pack invalide.')
            selected[name] = entry['sha']
        return selected
    before = manifest(roots)
    entries = [e for e in roots if e.get('path') == 'client.json']
    for directory in ('profiles', 'rules', 'adapters'):
        if directory in before:
            children = listing('/' + directory)
            if any(not str(e.get('path', '')).startswith(directory + '/') for e in children):
                raise ValueError('Chemin GitHub incohérent.')
            entries.extend(children)
    files = {}
    for entry in entries:
        name = entry.get('path', '')
        if not allowed(name):
            continue
        sha = entry.get('sha', '')
        if entry.get('type') != 'file' or not re.fullmatch(r'[a-f0-9]{40}', sha) or name in files:
            raise ValueError('Type de fichier interdit dans le pack.')
        if entry.get('size', 0) > 1_000_000 or len(files) >= 200:
            raise ValueError('Pack trop volumineux.')
        blob = get('/contents/' + name + '?ref=' + branch)
        if blob.get('encoding') != 'base64' or blob.get('type') != 'file' or blob.get('sha') != sha:
            raise ValueError('Le pack a changé ou son contenu est invalide ; réessayez.')
        content = base64.b64decode(''.join(blob['content'].split()), validate=True)
        actual = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
        if actual != sha or len(content) > 1_000_000:
            raise ValueError('Intégrité du fichier invalide.')
        files[name] = content
    if not files or sum(map(len, files.values())) > 10_000_000:
        raise ValueError('Pack vide ou trop volumineux.')
    if manifest(listing('')) != before:
        raise ValueError('Le pack a changé pendant le téléchargement ; réessayez.')
    # Content fingerprint, not a commit SHA: Contents access alone is sufficient.
    revision = hashlib.sha1(json.dumps(before, sort_keys=True).encode()).hexdigest()
    return revision, files


def apply_pack(root, repository, revision, files):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not files or any(not allowed(name) for name in files):
        raise ValueError('Contenu de pack invalide.')
    for name, content in files.items():
        text = content.decode('utf-8')
        if name.endswith('.json'):
            if not isinstance(json.loads(text), dict):
                raise ValueError('Configuration JSON invalide : ' + name)
        else:
            compile(text, name, 'exec')
    lock = root / '.sync-lock'
    with lock.open('x'):
        pass
    try:
        state_path = root / STATE
        if state_path.is_symlink():
            raise ValueError('Lien symbolique interdit pour l’historique du pack.')
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
        if state and state.get('repository') != repository:
            raise ValueError('Ce pack est déjà associé à un autre dépôt.')
        old = state.get('files', {})
        if any(not allowed(name) for name in old):
            raise ValueError('Historique du pack invalide.')
        changes = {}
        conflicts = []
        for name in set(files) | set(old):
            target = root / name
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root and root in p.parents):
                raise ValueError('Lien symbolique interdit dans le pack.')
            current = target.read_bytes() if target.exists() else None
            incoming = files.get(name)
            if current == incoming:
                continue
            if name in old and incoming is not None and digest(incoming) == old[name]:
                continue  # Upstream unchanged: keep local customization.
            if current is not None and (name not in old or digest(current) != old[name]):
                conflicts.append(name)
            elif current is None and name in old:
                conflicts.append(name)  # Local deletion is also a local change.
            else:
                changes[name] = incoming
        if conflicts:
            raise ValueError('Réglages locaux différents, aucun fichier remplacé : ' + ', '.join(sorted(conflicts)))
        before = {name: (root/name).read_bytes() if (root/name).exists() else None for name in changes}
        state_before = state_path.read_bytes() if state_path.exists() else None
        try:
            for name, content in changes.items():
                path = root / name
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, content)
            atomic_write(state_path, json.dumps({'repository': repository, 'revision': revision, 'files': {n: digest(v) for n, v in files.items()}}, indent=2).encode())
        except Exception:
            for name, content in before.items():
                if content is None:
                    (root/name).unlink(missing_ok=True)
                else:
                    atomic_write(root/name, content)
            if state_before is None:
                state_path.unlink(missing_ok=True)
            else:
                atomic_write(state_path, state_before)
            raise
        return len(changes)
    finally:
        lock.unlink(missing_ok=True)
