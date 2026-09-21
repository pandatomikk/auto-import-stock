import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from core import updater
from core.lots import prepare_lot

SHA = 'a' * 40


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        updater.write_json(self.root / updater.STATE, {'managed': True, 'repository': updater.REPOSITORY, 'revision': 'b' * 40})

    def archive(self, extras=None):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            for name in sorted(updater.REQUIRED):
                archive.writestr('repo/' + name, '# New version\n' if name.endswith('.py') else b'new')
            for name, content in (extras or {}).items():
                archive.writestr(name, content)
        return data.getvalue()

    def stage(self):
        return updater.prepare_update(self.root, {'revision': SHA}, fetch=lambda *_: self.archive({'repo/private/profiles/secret.json': 'overwrite', 'repo/.venv/marker': 'overwrite'}))

    def runtime(self, root, staging):
        environment = root / '.runtimes/test'
        executable = updater.python_at(environment)
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text('test runtime')
        return environment

    def test_remote_revision_is_pinned_and_same_revision_is_ignored(self):
        fetch = Mock(return_value=json.dumps({'sha': SHA, 'commit': {'message': 'Fix\nDetails'}}).encode())
        self.assertEqual(updater.check_update(self.root, fetch)['revision'], SHA)
        self.assertIn('/commits/main', fetch.call_args.args[0])
        updater.write_json(self.root / updater.STATE, {'managed': True, 'repository': updater.REPOSITORY, 'revision': SHA})
        self.assertIsNone(updater.check_update(self.root, fetch))

    def test_development_checkout_never_checks_network(self):
        (self.root / '.git').mkdir()
        fetch = Mock()
        self.assertIsNone(updater.check_update(self.root, fetch))
        fetch.assert_not_called()

    def test_update_preserves_local_data_and_switches_runtime(self):
        keep = ['private/profiles/secret.json', 'private/adapters/local.py', '.venv/marker', 'runtime_windows.json', 'profiles/custom.json', 'lots/product.csv']
        for name in keep:
            file = self.root / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('preserve')
        (self.root / 'core').mkdir(); (self.root / 'core/obsolete.py').write_text('old')
        staging = self.stage()
        updater.apply_update(self.root, staging, self.runtime)
        for name in keep:
            self.assertEqual((self.root / name).read_text(), 'preserve')
        self.assertFalse((self.root / 'core/obsolete.py').exists())
        self.assertEqual(json.loads((self.root / updater.STATE).read_text())['revision'], SHA)
        self.assertEqual(Path(json.loads((self.root / updater.RUNTIME).read_text())['directory']), Path('.runtimes/test'))
        self.assertFalse((self.root / '.update.lock').exists())

    def test_failure_restores_code_and_state(self):
        (self.root / 'client.py').write_text('# old client')
        old_state = (self.root / updater.STATE).read_bytes()
        staging = self.stage()
        original = updater.write_json
        def fail(path, data):
            if Path(path).name == updater.STATE:
                raise OSError('Simulated disk failure')
            return original(path, data)
        with patch.object(updater, 'write_json', side_effect=fail):
            with self.assertRaises(OSError):
                updater.apply_update(self.root, staging, self.runtime)
        self.assertEqual((self.root / 'client.py').read_text(), '# old client')
        self.assertEqual((self.root / updater.STATE).read_bytes(), old_state)
        self.assertFalse((self.root / updater.RUNTIME).exists())
        self.assertFalse((self.root / '.runtimes/test').exists())
        self.assertFalse((self.root / '.update.lock').exists())

    def test_dependency_failure_leaves_installation_untouched(self):
        (self.root / 'client.py').write_text('# old')
        with self.assertRaises(RuntimeError):
            updater.apply_update(self.root, self.stage(), Mock(side_effect=RuntimeError('offline')))
        self.assertEqual((self.root / 'client.py').read_text(), '# old')

    def test_archive_rejects_traversal_and_missing_files(self):
        for payload in [self.archive({'repo/../escape': 'bad'}), self.archive({'repo/core/../../escape': 'bad'})]:
            with self.assertRaises(updater.UpdateError):
                updater.extract_archive(io.BytesIO(payload), self.root / 'extracted')
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, 'w'): pass
        with self.assertRaises(updater.UpdateError):
            updater.extract_archive(io.BytesIO(empty.getvalue()), self.root / 'extracted')

    def test_tampered_plan_cannot_replace_private_files(self):
        staging = self.stage()
        plan = json.loads((staging / 'plan.json').read_text()); plan['files'].append('private/profiles/customer.json')
        updater.write_json(staging / 'plan.json', plan)
        runtime = Mock()
        with self.assertRaises(updater.UpdateError):
            updater.apply_update(self.root, staging, runtime)
        runtime.assert_not_called()

    def test_existing_update_lock_blocks_changes(self):
        (self.root / '.update.lock').touch()
        with self.assertRaises(updater.UpdateError):
            updater.apply_update(self.root, self.stage(), self.runtime)
        self.assertTrue((self.root / '.update.lock').exists())


class ResumeLotTests(unittest.TestCase):
    def test_retry_uses_same_lot_and_keeps_completed_images(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'invoice.csv'; source.write_text('data')
            first, copied, _ = prepare_lot(source, 'Demo', root=root / 'lots')
            image = first / 'resultats/images_produits/photo.webp'; image.parent.mkdir(); image.write_bytes(b'cached')
            second, source_again, _ = prepare_lot(copied, 'Demo', root=root / 'lots')
            self.assertEqual(first, second); self.assertEqual(copied, source_again)
            self.assertEqual(image.read_bytes(), b'cached')
            third, _, _ = prepare_lot(copied, 'Other supplier', root=root / 'lots')
            self.assertNotEqual(third, first)
