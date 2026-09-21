"""Opt-in updates for managed installations; never replace local business data.

Also runnable as a detached helper copied outside the installation being updated.
"""
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from urllib.request import Request, urlopen
import zipfile

REPOSITORY = 'pandatomikk/auto-import-stock'
BRANCH = 'main'
STATE = 'update_state.json'
RUNTIME = 'active_runtime.json'
ROOT_FILES = {'client.py', 'lancer.py', 'convertisseur.py', 'requirements.txt', 'README.md', 'LICENSE',
              'installer_windows.py', 'Installer-Windows.cmd', 'Ouvrir-Windows.bat',
              'Ouvrir-Windows.vbs', 'Ouvrir-Linux.sh', 'Ouvrir-macOS.command'}
REQUIRED = {'client.py', 'lancer.py', 'requirements.txt', 'core/__init__.py',
            'core/updater.py', 'assets/app.png', 'assets/app.ico'}


class UpdateError(ValueError):
    pass


def write_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def managed(name):
    p = PurePosixPath(name)
    if not p.parts or any(part in {'..', '.', ''} or ':' in part or '\\' in part for part in p.parts):
        return False
    return (name in ROOT_FILES or name == 'profiles/demo.json' or
            (len(p.parts) > 1 and p.parts[0] in {'core', 'schemas', 'assets'} and '__pycache__' not in p.parts))


def installed_state(root):
    root = Path(root)
    if (root / '.git').exists():
        return None  # Development checkouts are updated with Git, never in-place.
    try:
        state = json.loads((root / STATE).read_text(encoding='utf-8'))
        return state if state.get('managed') is True and state.get('repository') == REPOSITORY else None
    except (OSError, ValueError, AttributeError):
        return None


def fetch_bytes(url, limit):
    req = Request(url, headers={'User-Agent': 'AutoImportStock-Updater', 'Accept': 'application/vnd.github+json'})
    with urlopen(req, timeout=20) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise UpdateError('Téléchargement trop volumineux.')
    return raw


def check_update(root, fetch=fetch_bytes):
    state = installed_state(root)
    if state is None:
        return None
    data = json.loads(fetch(f'https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}', 2_000_000))
    sha = data.get('sha', '')
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise UpdateError('Version GitHub invalide.')
    if sha == state.get('revision'):
        return None
    return {'revision': sha, 'message': str(data.get('commit', {}).get('message', '')).split('\n')[0][:160]}


def extract_archive(archive, destination):
    destination = Path(destination)
    selected = {}
    total = 0
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            parts = PurePosixPath(item.filename).parts
            if item.is_dir():
                continue
            if len(parts) < 2 or PurePosixPath(item.filename).is_absolute() or any(x in {'..', '.'} or ':' in x or '\\' in x for x in parts):
                raise UpdateError('Chemin non autorisé dans la mise à jour.')
            name = '/'.join(parts[1:])
            if not managed(name):
                continue
            if stat.S_ISLNK(item.external_attr >> 16) or name.casefold() in selected:
                raise UpdateError('Archive ambiguë ou contenant un lien symbolique.')
            total += item.file_size
            if total > 100_000_000 or len(selected) >= 5000:
                raise UpdateError('Archive trop volumineuse.')
            selected[name.casefold()] = name
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if target.suffix == '.py':
                compile(target.read_bytes(), name, 'exec')
    names = set(selected.values())
    if not REQUIRED.issubset(names):
        raise UpdateError('Cette version ne contient pas tous les fichiers nécessaires à une mise à jour.')
    return sorted(names)


def prepare_update(root, update, fetch=fetch_bytes):
    root = Path(root).resolve()
    if installed_state(root) is None:
        raise UpdateError('Mise à jour réservée aux installations gérées.')
    sha = update['revision']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise UpdateError('Version invalide.')
    staging = root / '.updates' / uuid.uuid4().hex
    staging.mkdir(parents=True)
    try:
        archive = staging / 'release.zip'
        archive.write_bytes(fetch(f'https://codeload.github.com/{REPOSITORY}/zip/{sha}', 30_000_000))
        names = extract_archive(archive, staging / 'new')
        write_json(staging / 'plan.json', {'revision': sha, 'files': names})
        return staging
    except Exception:
        shutil.rmtree(staging)
        raise


def python_at(environment):
    return Path(environment) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def build_runtime(root, staging):
    """Prepare dependencies separately: a failed install leaves the old runtime intact."""
    runtime = root / '.runtimes' / uuid.uuid4().hex
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    log = staging / 'installation.log'
    try:
        with log.open('w', encoding='utf-8') as stream:
            subprocess.run([sys._base_executable, '-m', 'venv', str(runtime)], check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=180, **flags)
            python = python_at(runtime)
            subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(staging / 'new/requirements.txt')], check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=600, **flags)
            subprocess.run([str(python), '-c', 'import tkinter, openpyxl, gdown, keyring, cryptography; from PIL import features; assert features.check("webp"); import client; import core.shop_publication'], cwd=staging / 'new', check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=60, **flags)
        return runtime
    except Exception:
        shutil.rmtree(runtime, ignore_errors=True)
        raise UpdateError('Préparation de la mise à jour impossible. Ancienne version conservée. Journal : ' + str(log)) from None


def apply_update(root, staging, runtime_builder=build_runtime):
    root, staging = Path(root).resolve(), Path(staging).resolve()
    if installed_state(root) is None or not staging.is_relative_to(root / '.updates'):
        raise UpdateError('Installation ou dossier de mise à jour invalide.')
    plan = json.loads((staging / 'plan.json').read_text(encoding='utf-8'))
    names = plan['files']
    if not re.fullmatch('[0-9a-f]{40}', plan['revision']) or not REQUIRED.issubset(names) or any(not managed(name) for name in names):
        raise UpdateError('Plan de mise à jour invalide.')
    # Block launch while application files are being changed.
    lock = root / '.update.lock'
    try:
        lock.open('x').close()
    except FileExistsError:
        raise UpdateError('Une mise à jour est déjà en cours.') from None
    originals, changed = {}, []
    runtime = None
    try:
        old_names = {p.relative_to(root).as_posix() for directory in ('core', 'schemas', 'assets') for p in (root / directory).rglob('*') if p.is_file() and managed(p.relative_to(root).as_posix())}
        affected = sorted(set(names) | old_names | {STATE, RUNTIME})
        for name in affected:
            target = root / name
            if not target.resolve().is_relative_to(root) or target.is_symlink():
                raise UpdateError('Destination de mise à jour invalide.')
            backup = staging / 'backup' / name
            originals[name] = target.exists()
            if target.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
        if plan.get('runtime'):
            runtime = (root / plan['runtime']).resolve()
            if not runtime.is_relative_to(root / '.runtimes') or not python_at(runtime).is_file():
                raise UpdateError('Environnement préparé invalide.')
        else:
            runtime = runtime_builder(root, staging)
        for name in affected:
            if name in {STATE, RUNTIME}:
                continue
            target = root / name
            changed.append(name)
            if name in names:
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + '.update-tmp')
                shutil.copy2(staging / 'new' / name, temp)
                temp.replace(target)
            else:
                target.unlink(missing_ok=True)
        changed.append(RUNTIME)
        write_json(root / RUNTIME, {'directory': str(runtime.relative_to(root))})
        changed.append(STATE)
        write_json(root / STATE, {'managed': True, 'repository': REPOSITORY, 'revision': plan['revision']})
    except Exception:
        for name in reversed(changed):
            target = root / name
            if originals[name]:
                shutil.copy2(staging / 'backup' / name, target)
            else:
                target.unlink(missing_ok=True)
        if runtime is not None and runtime.is_relative_to(root / '.runtimes'):
            shutil.rmtree(runtime, ignore_errors=True)
        raise
    finally:
        lock.unlink(missing_ok=True)


def wait_for_parent(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle and ctypes.get_last_error() != 87:
            raise UpdateError('Impossible de vérifier la fermeture de l’application.')
        if handle:
            try:
                if kernel.WaitForSingleObject(handle, 60000) != 0:
                    raise UpdateError('L’application ne s’est pas fermée : mise à jour annulée.')
            finally:
                kernel.CloseHandle(handle)
    else:
        for _ in range(120):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.5)
        raise UpdateError('L’application ne s’est pas fermée : mise à jour annulée.')


def launch_helper(root, staging):
    helper = Path(staging) / 'apply_update.py'
    shutil.copy2(__file__, helper)
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    log = (Path(staging) / 'helper.log').open('w', encoding='utf-8')
    try:
        subprocess.Popen([str(python_at(Path(sys.prefix))), str(helper), str(root), str(staging), str(os.getpid())], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **flags)
    finally:
        log.close()


def helper_main():
    root, staging, pid = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    try:
        wait_for_parent(pid)
        apply_update(root, staging)
        result = {'ok': True, 'message': 'Mise à jour installée.'}
    except Exception as exc:
        result = {'ok': False, 'message': 'Mise à jour non installée : ' + str(exc)}
    write_json(root / 'update_result.json', result)
    python = python_at(root / '.venv')
    if os.name == 'nt':
        python = python.with_name('pythonw.exe')
    subprocess.Popen([str(python), str(root / 'lancer.py'), '--client'], cwd=root)


if __name__ == '__main__':
    helper_main()
