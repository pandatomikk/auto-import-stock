"""Optional, client-configured delivery of diagnostic bundles to a public share."""
import hashlib
import io
import json
import re
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests
from .profiles import private_directory
from .version import VERSION

_LOCK = threading.Lock()
_SECRET = re.compile(r'password|passwd|secret|token|authorization|consumer_key|api_key|application_password', re.I)


def scrub(value):
    if isinstance(value, dict):
        return {k: '[masqué]' if _SECRET.search(k) else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'(?i)\b(?:gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|c[ks]_[a-f0-9]{20,})\b', '[masqué]', value)
    value = re.sub(r'(?i)(https?://)[^\s/@]+:[^\s/@]+@', r'\1[masqué]@', value)
    value = re.sub(r'(?i)(authorization\s*[:=]\s*).*', r'\1[masqué]', value)
    value = re.sub(r'(?i)((?:password|passwd|secret|token|consumer_key|api_key|mot de passe)[\w -]*["\']?\s*[:=]\s*)[^\r\n&,]+', r'\1[masqué]', value)
    return value


def settings():
    path = private_directory() / 'client.json'
    data = json.loads(path.read_text(encoding='utf-8')).get('diagnostic_cloud', {}) if path.exists() else {}
    if not data.get('enabled'):
        return None
    url = urlsplit(data.get('share_url', ''))
    match = re.fullmatch(r'/(?:index.php/)?s/([A-Za-z0-9]+)', url.path)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or not match:
        raise ValueError('Adresse du partage de diagnostics invalide')
    return f'https://{url.netloc}/public.php/webdav/', match[1]


def bundle(root, phase, outcome):
    """Allowlist diagnostics only: never sources, product CSVs, settings or images."""
    data = io.BytesIO()
    size = 0
    skipped = []
    with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            relative = path.relative_to(root)
            if any(part.startswith('.') for part in relative.parts):
                continue
            name = path.name
            allowed = ((path.suffix == '.json' and (name.startswith(('rapport_', 'publication_images_')) or name.endswith('_rapport.json')))
                       or (name.startswith('diagnostic_') and path.suffix == '.txt'))
            if not allowed:
                continue
            if path.stat().st_size > 8_000_000 or size + path.stat().st_size > 24_000_000:
                skipped.append(str(relative)); continue
            text = path.read_text(encoding='utf-8-sig', errors='replace')
            size += len(text.encode())
            if path.suffix == '.json':
                try: text = json.dumps(scrub(json.loads(text)), ensure_ascii=False, indent=2)
                except ValueError: text = scrub(text)
            else:
                text = scrub(text)
            archive.writestr(str(relative).replace('\\', '/'), text)
        archive.writestr('execution.json', json.dumps({'version': VERSION, 'phase': phase,
            'outcome': scrub(outcome), 'date_utc': datetime.now(timezone.utc).isoformat(),
            'omitted_oversize_files': skipped}, ensure_ascii=False))
    return data.getvalue()


def send_pending(root, endpoint, token):
    with _LOCK:
        queue = root / '.diagnostics_cloud' / hashlib.sha256(endpoint.encode()+token.encode()).hexdigest()[:16]
        queue.mkdir(parents=True, exist_ok=True)
        for path in sorted(queue.glob('*.zip'))[:10]:
            try:
                with path.open('rb') as stream:
                    response = requests.put(endpoint + path.name, data=stream, auth=(token, ''),
                        headers={'Content-Type': 'application/zip'}, timeout=(10, 45), allow_redirects=False)
                if response.status_code not in (200, 201, 204):
                    raise RuntimeError(f'Cloud HTTP {response.status_code}')
                path.rename(path.with_suffix('.sent'))
                status = {'status': 'sent', 'file': path.name}
            except Exception as exc:
                status = {'status': 'pending', 'file': path.name, 'error': scrub(str(exc))}
            (root / 'diagnostic_cloud_status.json').write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
            if status['status'] == 'pending':
                break


def submit(root, phase, outcome):
    """Snapshot now; network never blocks Tk or changes operation success."""
    try:
        destination = settings()
        if not destination:
            return
        root = Path(root).resolve()
        endpoint, token = destination
        queue = root / '.diagnostics_cloud' / hashlib.sha256(endpoint.encode()+token.encode()).hexdigest()[:16]
        queue.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + phase + '_' + uuid.uuid4().hex[:10] + '.zip'
        payload = bundle(root, phase, outcome)
        path = queue/name
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(payload)
        temporary.replace(path)
        threading.Thread(target=send_pending, args=(root, endpoint, token), daemon=True).start()
    except Exception as exc:
        try:
            (Path(root)/'diagnostic_cloud_status.json').write_text(json.dumps({'status': 'error', 'error': scrub(str(exc))}), encoding='utf-8')
        except OSError:
            pass
