import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from core.shop_connection import Credentials, ConnectionFailure
from core.shop_products import ProductAPI, prepare_csv, import_plan, row_payload, Resolver


class FakeAPI:
    url = 'https://shop.example'

    def __init__(self):
        self.created = []
        self.products = {'EXISTING': {'id': 5}}
        self.calls = []

    def existing(self, sku):
        self.calls.append(('GET', sku))
        return [self.products[sku]] if sku in self.products else []

    def listing(self, route):
        self.calls.append(('LIST', route))
        return {
            'wp/v2/media': [{'id': 10, 'source_url': 'https://shop.example/uploads/photo.webp'}],
            'wc/v3/products/categories': [{'id': 3, 'name': 'Accessoires', 'parent': 0}, {'id': 4, 'name': 'Sacs', 'parent': 3}],
            'wc/v3/products/brands': [{'id': 8, 'name': 'Exemple'}],
            'wc/v3/products/tags': [{'id': 12, 'name': 'Été'}],
        }.get(route, [])

    def create(self, payload):
        self.calls.append(('POST', payload['sku']))
        self.created.append(payload)
        self.products[payload['sku']] = {'id': len(self.created) + 20, 'sku': payload['sku'], 'permalink': 'https://shop.example/product'}
        return self.products[payload['sku']]


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'articles.csv'
        self.api = FakeAPI()

    def csv(self, rows, delimiter=','):
        headers = list(dict.fromkeys(k for row in rows for k in row))
        with self.path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=headers, delimiter=delimiter)
            writer.writeheader(); writer.writerows(rows)
        return self.path

    def test_preview_then_create_only_with_wp_image_ids_and_taxonomies(self):
        path = self.csv([{'UGS': '000123', 'Nom': 'Sac', 'Tarif régulier': '49,90', 'Stock': '2', 'Images': 'https://shop.example/uploads/photo.webp', 'Catégories': 'Accessoires > Sacs', 'Marques': 'Exemple', 'GTIN, UPC, EAN ou ISBN': '0000000000017'}, {'UGS': 'EXISTING', 'Nom': 'Never change'}], ';')
        plan = prepare_csv(path, self.api)
        self.assertEqual(plan['errors'], [])
        self.assertEqual(self.api.created, [])
        payload = plan['items'][0]['payload']
        self.assertEqual(payload['images'], [{'id': 10}])
        self.assertEqual(payload['categories'], [{'id': 4}])
        self.assertEqual(payload['regular_price'], '49.90')
        self.assertEqual(payload['status'], 'publish')
        self.assertEqual(payload['global_unique_id'], '0000000000017')
        report = import_plan(plan, self.api, self.folder / 'report.json')
        self.assertEqual([r['state'] for r in report['results']], ['created', 'skipped'])
        self.assertEqual(len(self.api.created), 1)
        import_plan(plan, self.api, self.folder / 'report2.json')
        self.assertEqual(len(self.api.created), 1)

    def test_current_schema_defaults_are_accepted(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/woocommerce.json').read_text())
        row = {key: '' for key in schema['columns']}
        row.update({k: str(v) for k, v in schema['defaults'].items()})
        row.update(UGS='TEST', Nom='Article')
        plan = prepare_csv(self.csv([row]), self.api)
        self.assertEqual(plan['errors'], [])

    def test_errors_block_all_writes(self):
        for extra in [{'Images': 'missing.webp'}, {'Catégories': 'Inconnue'}, {'Type': 'variable'}, {'ID': '12'}, {'Tarif régulier': 'NaN'}, {'Stock': '2.5'}, {'Publié': '-1'}, {'Custom field': 'do not drop me'}]:
            with self.subTest(extra=extra):
                plan = prepare_csv(self.csv([{'UGS': 'NEW', 'Nom': 'Test', **extra}]), self.api)
                self.assertTrue(plan['errors'])
                with self.assertRaises(ConnectionFailure):
                    import_plan(plan, self.api, self.folder / 'report.json')
        self.assertEqual(self.api.created, [])

    def test_duplicate_csv_sku_and_missing_sku(self):
        plan = prepare_csv(self.csv([{'UGS': 'abc', 'Nom': 'A'}, {'UGS': 'ABC', 'Nom': 'B'}, {'UGS': '', 'Nom': 'C'}]), self.api)
        self.assertEqual(len(plan['errors']), 2)

    def test_uncertain_creation_stops_and_persists_report(self):
        plan = prepare_csv(self.csv([{'UGS': 'A', 'Nom': 'A'}, {'UGS': 'B', 'Nom': 'B'}]), self.api)
        def uncertain(payload):
            self.assertEqual(json.loads((self.folder / 'report.json').read_text())['results'][0]['state'], 'unconfirmed')
            raise ConnectionFailure('Timeout')
        self.api.create = Mock(side_effect=uncertain)
        report = import_plan(plan, self.api, self.folder / 'report.json')
        self.assertEqual(self.api.create.call_count, 1)
        self.assertEqual(report['results'][0]['state'], 'unconfirmed')
        self.assertEqual(len(report['results']), 1)

    def test_newly_existing_product_between_preview_and_send_is_skipped(self):
        plan = prepare_csv(self.csv([{'UGS': 'A', 'Nom': 'A'}]), self.api)
        self.api.products['A'] = {'id': 50}
        report = import_plan(plan, self.api, self.folder / 'report.json')
        self.assertEqual(report['results'][0]['state'], 'skipped')
        self.assertFalse(self.api.created)

    @patch('core.shop_products.build_opener')
    def test_transport_never_updates_and_uses_json(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = b'{"id":1,"sku":"A"}'
        response.headers = {}
        api = ProductAPI(Credentials('https://shop.example', consumer_key='ck_key', consumer_secret='cs_secret'))
        api.create({'sku': 'A', 'name': 'A'})
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.method, 'POST')
        self.assertTrue(request.full_url.endswith('/wc/v3/products'))
        self.assertNotIn('cs_secret', request.full_url)
        self.assertEqual(json.loads(request.data), {'sku': 'A', 'name': 'A'})
        with self.assertRaises(ConnectionFailure):
            api.request('wc/v3/products/1', payload={'name': 'update'})
        self.assertEqual(opener.return_value.open.call_count, 1)

    def test_exact_page_boundary_uses_total_pages(self):
        api = ProductAPI(Credentials('https://shop.example', consumer_key='k', consumer_secret='s'))
        api.last_total_pages = 1
        api.request = Mock(return_value=[{'id': n} for n in range(100)])
        self.assertEqual(len(api.listing('wp/v2/media')), 100)
        self.assertEqual(api.request.call_count, 1)


class ProductDialogTests(unittest.TestCase):
    def test_review_requires_explicit_send_and_disables_repeat(self):
        import tkinter as tk
        import time
        from core.shop_products_ui import ProductsDialog
        try:
            owner = tk.Tk()
        except tk.TclError:
            self.skipTest('Display unavailable')
        owner.withdraw()
        owner.set_controls = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.csv'
            path.write_text('UGS,Nom\nUI-TEST,Test\n')
            dialog = ProductsDialog(owner, Credentials('https://shop.example', consumer_key='k', consumer_secret='s'))
            dialog.withdraw()
            api = FakeAPI()
            dialog.api = api
            def wait():
                deadline = time.monotonic() + 3
                while dialog.busy and time.monotonic() < deadline:
                    owner.update(); time.sleep(.02)
                self.assertFalse(dialog.busy)
            try:
                with patch('core.shop_products_ui.filedialog.askopenfilename', return_value=str(path)):
                    dialog.choose()
                wait()
                self.assertEqual(api.created, [])
                self.assertEqual(str(dialog.send.cget('state')), 'normal')
                dialog.start_import(); wait()
                self.assertEqual(len(api.created), 1)
                self.assertIsNone(dialog.plan)
                self.assertEqual(str(dialog.send.cget('state')), 'disabled')
                self.assertTrue(dialog.report_path.exists())
            finally:
                dialog.close(); owner.destroy()
