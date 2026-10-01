import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from core.image_archive import ImageArchive


class DuplicateEntriesTest(unittest.TestCase):
    def test_duplicate_paths_compare_actual_entries(self):
        for nested in (False, True):
            for second in (b'photo', b'other'):
                with self.subTest(nested=nested, second=second), tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp)/'images.zip'
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        with zipfile.ZipFile(path, 'w') as archive:
                            archive.writestr('photo.jpg', b'photo')
                            archive.writestr('photo.jpg', second)
                    if second == b'photo':
                        with ImageArchive(path, nested=nested) as archive:
                            self.assertEqual(len(archive.infolist()), 1)
                            with archive.open(archive.infolist()[0]) as image:
                                self.assertEqual(image.read(), b'photo')
                        # Deduplication must not bypass archive limits.
                        with self.assertRaises(ValueError):
                            ImageArchive(path, nested=nested, max_entries=1)
                    else:
                        with self.assertRaisesRegex(ValueError, 'contenus différents'):
                            ImageArchive(path, nested=nested)
