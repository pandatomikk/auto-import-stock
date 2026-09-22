import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core.client_settings import image_filename
from installer_windows import copy_application

class ClientSettingsTests(unittest.TestCase):
    def test_optional_safe_idempotent_suffix(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'AUTO_IMPORT_PRIVATE_DIR': temp}):
            p=Path(temp)/'client.json'
            self.assertEqual(image_filename('sac.webp'),'sac.webp')
            p.write_text(json.dumps({'image_filename_suffix':'www.example.fr'}))
            self.assertEqual(image_filename('sac.webp'),'sac-www.example.fr.webp')
            self.assertEqual(image_filename('sac-www.example.fr.webp'),'sac-www.example.fr.webp')
            p.write_text(json.dumps({'image_filename_suffix':'../escape'}))
            with self.assertRaises(ValueError): image_filename('sac.webp')

    def test_installer_preserves_client_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source'; dest=Path(temp)/'dest'
            (source/'private').mkdir(parents=True)
            settings=source/'private/client.json';settings.write_text('{"image_filename_suffix":"first"}')
            copy_application(source,dest)
            settings.write_text('{"image_filename_suffix":"new"}')
            copy_application(source,dest)
            self.assertIn('first',(dest/'private/client.json').read_text())

    def test_actual_zip_output_and_cache_use_suffixed_name(self):
        import zipfile
        from PIL import Image
        from core.images import prepare_local_zip_images
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'AUTO_IMPORT_PRIVATE_DIR':temp}):
            root=Path(temp)
            (root/'client.json').write_text('{"image_filename_suffix":"www.example.fr"}')
            Image.new('RGB',(10,10)).save(root/'photo.png')
            with zipfile.ZipFile(root/'images.zip','w') as z:z.write(root/'photo.png','photo.png')
            args=(root/'images.zip',['photo.png'],root,'Example','Sac bleu')
            names=prepare_local_zip_images(*args)
            self.assertTrue(names[0].endswith('-www.example.fr.webp'))
            path=root/'images_example/fichiers_webp'/names[0]
            self.assertTrue(path.exists())
            before=path.stat().st_mtime_ns
            self.assertEqual(prepare_local_zip_images(*args),names)
            self.assertEqual(path.stat().st_mtime_ns,before)
