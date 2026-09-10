import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from core.shop_connection import Credentials, ConnectionFailure, NoRedirect, check_connection, get_json, load_settings, normalize_url, save_settings


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        self.vault = Mock()
        keys = {}
        self.vault.get_password.side_effect = lambda service, account: keys.get((service, account))
        self.vault.set_password.side_effect = lambda service, account, key: keys.__setitem__((service, account), key)
        patcher = patch('core.secret_store.system_vault', return_value=self.vault)
        patcher.start(); self.addCleanup(patcher.stop)
        self.credentials = Credentials('https://shop.example/store/', 'operator', 'abcd efgh', 'ck_test', 'cs_test')

    def test_url_validation(self):
        self.assertEqual(normalize_url(self.credentials.url), 'https://shop.example/store')
        for url in ['http://shop.example', 'https://user:password@shop.example', 'https://shop.example/?key=secret', 'https://shop.example/#a', 'https://shop.example/wp-admin', 'https://shop.example:bad', 'https://']:
            with self.subTest(url=url), self.assertRaises(ConnectionFailure):
                normalize_url(url)

    def test_success_and_separate_authentication(self):
        calls = []
        def fetch(url, user, password):
            calls.append((url, user, password))
            return {'id': 5, 'capabilities': {'upload_files': True}} if '/wp/v2/' in url else []
        result = check_connection(self.credentials, fetch)
        self.assertTrue(all(v['ok'] for v in result.values()))
        self.assertEqual(calls[0], ('https://shop.example/store/wp-json/wp/v2/users/me?context=edit', 'operator', 'abcdefgh'))
        self.assertEqual(calls[1][1:], ('ck_test', 'cs_test'))
        self.assertIn('écriture', result['woocommerce']['message'])

    def test_independent_failures(self):
        def fetch(url, *_):
            if '/wp/v2/' in url:
                raise ConnectionFailure('Identifiants refusés.')
            return [{'id': 2}]
        result = check_connection(self.credentials, fetch)
        self.assertFalse(result['wordpress']['ok'])
        self.assertTrue(result['woocommerce']['ok'])

    def test_invalid_responses(self):
        result = check_connection(self.credentials, lambda *_: {'unexpected': True})
        self.assertFalse(any(v['ok'] for v in result.values()))

    def test_missing_fields_do_not_send_requests(self):
        with self.assertRaises(ConnectionFailure):
            check_connection(Credentials(url='https://shop.example'), lambda *_: self.fail('Network called'))

    def test_settings_never_save_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'shop.json'
            save_settings(self.credentials, path)
            self.assertEqual(json.loads(path.read_text()), {'url': 'https://shop.example/store', 'username': 'operator'})
            restored = load_settings(path)
            self.assertEqual(restored.application_password, '')
            self.assertEqual(restored.consumer_secret, '')
            path.write_text('broken')
            self.assertEqual(load_settings(path).url, '')
        self.assertNotIn('cs_test', repr(self.credentials))

    def test_saved_credentials_survive_restart_and_can_be_removed(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'shop.json'
            save_settings(self.credentials, path, remember_secrets=True)
            self.assertNotIn(self.credentials.consumer_secret, path.read_text())
            encrypted = path.parent / 'secrets/shop.enc'
            self.assertNotIn(self.credentials.consumer_secret.encode(), encrypted.read_bytes())
            restored = load_settings(path)
            self.assertEqual(restored.application_password, self.credentials.application_password)
            self.assertEqual(restored.consumer_secret, self.credentials.consumer_secret)
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            save_settings(restored, path, remember_secrets=False)
            self.assertEqual(load_settings(path).consumer_secret, '')
            self.assertNotIn('application_password', json.loads(path.read_text()))
            self.assertEqual(list(Path(folder).glob('.shop-*')), [])

    def test_plaintext_migration_and_vault_failure(self):
        from core.secret_store import VaultError
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'shop.json'
            legacy = {'url': self.credentials.url, 'username': 'operator', 'application_password': 'old-secret'}
            path.write_text(json.dumps(legacy))
            with patch('core.secret_store.system_vault', side_effect=VaultError('Locked')):
                with self.assertRaises(VaultError):
                    load_settings(path)
            self.assertEqual(json.loads(path.read_text()), legacy)
            self.assertEqual(load_settings(path).application_password, 'old-secret')
            self.assertNotIn('old-secret', path.read_text())

    @patch('core.shop_connection.build_opener')
    def test_transport_is_get_and_header_auth(self, opener):
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'[]'
        self.assertEqual(get_json('https://shop.example/wp-json/wc/v3/products', 'ck_test', 'cs_test'), [])
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.method, 'GET')
        self.assertEqual(request.headers['Authorization'], 'Basic ' + base64.b64encode(b'ck_test:cs_test').decode())
        self.assertNotIn('cs_test', request.full_url)
        self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 15)
        self.assertIsNone(NoRedirect().redirect_request(request, None, 302, '', {}, 'https://other.example'))

    @patch('core.shop_connection.build_opener')
    def test_errors_do_not_expose_server_content_or_secrets(self, opener):
        for error in [HTTPError('https://shop.example', 401, 'cs_test', {}, io.BytesIO(b'cs_test')), HTTPError('https://shop.example', 302, 'cs_test', {}, None), URLError('cs_test'), TimeoutError('cs_test')]:
            opener.return_value.open.side_effect = error
            with self.assertRaises(ConnectionFailure) as caught:
                get_json('https://shop.example', 'ck_test', 'cs_test')
            self.assertNotIn('cs_test', str(caught.exception))

    @patch('core.shop_connection.build_opener')
    def test_html_response(self, opener):
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'<html>login</html>'
        with self.assertRaises(ConnectionFailure):
            get_json('https://shop.example', 'ck_test', 'cs_test')


class ShopDialogTests(unittest.TestCase):
    def test_dialog_connection_and_session(self):
        import tkinter as tk
        import time
        from core.shop_ui import ShopDialog
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('Display unavailable')
        root.withdraw()
        root.shop_credentials = Credentials('https://shop.example', 'operator', 'app-pass', 'ck_test', 'cs_test')
        try:
            with patch('core.shop_ui.save_settings'), patch('core.shop_ui.check_connection', return_value={'wordpress': {'ok': True, 'message': 'Test OK'}, 'woocommerce': {'ok': False, 'message': 'Accès refusé'}}):
                dialog = ShopDialog(root)
                dialog.withdraw()
                dialog.remember.set(False)
                dialog.start()
                deadline = time.monotonic() + 3
                while dialog.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.02)
                self.assertFalse(dialog.busy)
                self.assertIn('Accès refusé', dialog.status.get())
                self.assertEqual(dialog.entries[2].cget('show'), '•')
                dialog.close()
                reopened = ShopDialog(root)
                self.assertEqual(reopened.values['consumer_secret'].get(), 'cs_test')
                reopened.close()
        finally:
            root.destroy()
