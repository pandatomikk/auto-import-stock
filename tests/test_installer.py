import json
from pathlib import Path
import tempfile
import unittest
from installer_windows import copy_application


class InstallerTest(unittest.TestCase):
    def test_private_pack_preserves_mappings_and_updates_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / 'source', Path(folder) / 'dest'
            (source / 'private/profiles').mkdir(parents=True)
            (source / 'private/adapters').mkdir()
            (source / 'private/backups').mkdir()
            (dest / 'configs').mkdir(parents=True)
            template = dict(supplier_name='Example', workflow={'kind':'two_pass'},
                            force_mapping={'sku':'new'}, images={'mode':'zip_pattern'})
            (source / 'private/profiles/example.json').write_text(json.dumps(template))
            (dest / 'configs/example.json').write_text(json.dumps({'force_mapping':{'sku':'custom'}}))
            (source / 'private/adapters/custom.py').write_text('updated = True')
            (source / 'private/backups/history.bundle').write_text('do not install')
            copy_application(source, dest)
            profile = json.loads((dest / 'private/profiles/example.json').read_text())
            self.assertEqual(profile['force_mapping']['sku'], 'custom')
            self.assertEqual(profile['workflow']['kind'], 'two_pass')
            self.assertTrue((dest / 'private/adapters/custom.py').is_file())
            self.assertFalse((dest / 'private/backups').exists())

    def test_public_install_without_private_pack(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / 'source', Path(folder) / 'dest'
            (source / 'profiles').mkdir(parents=True)
            (source / 'profiles/demo.json').write_text('{}')
            (source / 'client.py').write_text('public')
            copy_application(source, dest)
            self.assertTrue((dest / 'profiles/demo.json').exists())
            self.assertTrue((dest / 'private/profiles').is_dir())
            self.assertTrue((dest / 'private/rules').is_dir())
