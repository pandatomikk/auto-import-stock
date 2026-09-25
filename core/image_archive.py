"""Bounded, read-only view of images inside ordinary or nested ZIP archives."""
import copy
import hashlib
import shutil
import tempfile
import zipfile
from contextlib import ExitStack
from pathlib import PurePosixPath


class ImageArchive:
    def __init__(self, path, nested=False, max_depth=3, max_bytes=4 * 1024**3, max_entries=20000):
        self.stack = ExitStack()
        self.entries = []
        self.sources = {}
        self.total = 0
        self.count = 0
        try:
            self._scan(self.stack.enter_context(zipfile.ZipFile(path)), '', nested, 0,
                       max_depth, max_bytes, max_entries)
            if nested:
                self._deduplicate()
        except Exception:
            self.stack.close()
            raise

    def _scan(self, archive, prefix, nested, depth, max_depth, max_bytes, max_entries):
        for original in archive.infolist():
            self.count += 1
            self.total += original.file_size
            if self.count > max_entries or self.total > max_bytes:
                raise ValueError('Archive images trop volumineuse : limites dépassées.')
            name = original.filename.replace('\\', '/')
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Chemin interdit dans le ZIP : ' + name)
            if '__MACOSX' in path.parts or path.name.startswith('._') or original.is_dir():
                continue
            virtual = prefix + name
            if nested and path.suffix.lower() == '.zip':
                if depth >= max_depth:
                    raise ValueError('Trop de niveaux de ZIP imbriqués.')
                temp = self.stack.enter_context(tempfile.TemporaryFile())
                with archive.open(original) as source:
                    shutil.copyfileobj(source, temp)
                temp.seek(0)
                child = self.stack.enter_context(zipfile.ZipFile(temp))
                self._scan(child, virtual + '/', nested, depth + 1, max_depth, max_bytes, max_entries)
            else:
                if virtual in self.sources:
                    raise ValueError('Chemin présent plusieurs fois dans le ZIP : ' + virtual)
                info = copy.copy(original)
                info.filename = virtual
                self.entries.append(info)
                self.sources[virtual] = (archive, original)

    def _deduplicate(self):
        by_name = {}
        kept = []
        def digest(info):
            value = hashlib.sha256()
            with self.open(info) as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    value.update(block)
            return value.digest()
        for info in self.entries:
            name = PurePosixPath(info.filename).name
            previous = by_name.get(name)
            if previous is not None:
                if info.file_size != previous.file_size or digest(info) != digest(previous):
                    raise ValueError('Nom image ambigu, contenus différents dans les ZIP : ' + name)
                continue
            by_name[name] = info
            kept.append(info)
        self.entries = kept

    def infolist(self):
        return list(self.entries)

    def open(self, info):
        archive, original = self.sources[info.filename]
        return archive.open(original)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stack.close()
