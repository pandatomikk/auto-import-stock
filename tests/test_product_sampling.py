import csv
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from core.converter import convert_catalogue
from core.media_workflow import prepare_catalogue, finalize_catalogue
from core.sampling import catalogue_output

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/woocommerce.json'


def make_source(path, count=7):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Reference', 'Barcode', 'Name', 'Quantity', 'Price', 'Color', 'Color code'])
        for i in range(count):
            writer.writerow([f'ITEM{i}', f'{i+1:013}', f'Article {i}', 2, 39, 'BLACK', '001'])
    return path


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


class ProductSamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = make_source(self.root / 'catalogue.csv')
        self.profile = ROOT / 'profiles/demo.json'

    def test_sample_and_full_catalogue_have_independent_outputs(self):
        test = convert_catalogue(self.source, self.profile, SCHEMA, product_limit=5)
        full = convert_catalogue(self.source, self.profile, SCHEMA)
        self.assertEqual(test.row_count, 5); self.assertEqual(full.row_count, 7)
        self.assertNotEqual(test.output_path, full.output_path)
        self.assertEqual(len(read_rows(test.output_path)), 5)
        self.assertEqual(len(read_rows(full.output_path)), 7)

    def test_two_pass_sample_retains_all_photos_and_missing_photo_product(self):
        session, data = prepare_catalogue(self.source, self.profile, SCHEMA, product_limit=5)
        full_session, full = prepare_catalogue(self.source, self.profile, SCHEMA)
        self.assertNotEqual(session, full_session)
        self.assertEqual(data['products'], 5); self.assertEqual(full['products'], 7)
        image = self.root / 'photo.png'; Image.new('RGB', (20,20), 'red').save(image)
        archive = self.root / 'photos.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            for i in [0,1,2,3,5,6]:
                for number in range(1,4):
                    z.write(image, f'PHOTO_ITEM{i}_001_{number}.png')
        result = finalize_catalogue(session, archive)
        rows = read_rows(self.root / result['final_csv'])
        self.assertEqual(len(rows), 5)
        self.assertEqual([len(row['Images'].split(', ')) for row in rows[:4]], [3]*4)
        self.assertEqual(rows[4]['Images'], '')
        self.assertEqual(result['missing_images'], ['0000000000005'])

    def test_manual_addition_cannot_expand_sample_before_finalizing(self):
        session, data = prepare_catalogue(self.source, self.profile, SCHEMA, product_limit=5)
        prepared = self.root / data['prepared_csv']
        rows = read_rows(prepared)
        with prepared.open('a', encoding='utf-8', newline='') as stream:
            csv.DictWriter(stream, fieldnames=list(rows[0])).writerow(rows[0])
        with self.assertRaisesRegex(ValueError, 'limitée à 5'):
            finalize_catalogue(session, self.root/'unused.zip')

    def test_cli_new_flag_and_legacy_alias_both_limit_products(self):
        for flag in ['--test-products', '--test-images']:
            destination = self.root / (flag[2:] + '.csv')
            result = subprocess.run([sys.executable, '-B', str(ROOT/'convertisseur.py'), '--supplier', 'demo', '--source', str(self.source), '--output', str(destination), flag], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(destination.with_name(destination.stem+'_session.json').read_text())
            self.assertEqual(data['products'], 5)

    def test_small_catalogue_and_invalid_limit(self):
        small = make_source(self.root/'small.csv', 2)
        self.assertEqual(convert_catalogue(small, self.profile, SCHEMA, product_limit=5).row_count, 2)
        with self.assertRaises(ValueError):
            convert_catalogue(small, self.profile, SCHEMA, product_limit=0)


    def test_publication_plan_contains_only_the_five_sample_products(self):
        from core.shop_publication import prepare_publication
        from core.shop_products import import_plan
        from test_shop_products import FakeAPI
        result = convert_catalogue(self.source, self.profile, SCHEMA, product_limit=5)
        api = FakeAPI()
        plan = prepare_publication(result.output_path, api)
        self.assertFalse(plan['errors'])
        self.assertEqual(len(plan['items']), 5)
        report = import_plan(plan, api, self.root/'publication.json')
        self.assertEqual(len(api.created), 5)
        self.assertEqual(len(report['results']), 5)

    def test_completed_sample_can_switch_to_full_mode_without_display(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from client import Client
        session, data = prepare_catalogue(self.source, self.profile, SCHEMA, product_limit=5)
        class Value:
            def __init__(self, value): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value
        ui = SimpleNamespace(proc=None, source=Value(str(self.source)), test=Value(True),
            is_two_pass=lambda: True, stage=Value(''), status=Value(''),
            **{key: Mock() for key in ['two_pass_tools','start_button','image_label','image_entry',
                                     'image_browse','test_widget','web_widget','ean_button','open_button']})
        ui.refresh_two_pass = lambda **kwargs: Client.refresh_two_pass(ui, **kwargs)
        ui.refresh_two_pass()
        self.assertEqual(ui.resume_path, session)
        ui.test_widget.configure.assert_called_with(state='disabled')
        data['status'] = 'complete'; session.write_text(json.dumps(data))
        ui.source.set(str(session)); ui.refresh_two_pass()
        ui.test_widget.configure.assert_called_with(state='normal')
        ui.test.set(False)
        Client.test_mode_changed(ui)
        self.assertEqual(ui.source.get(), str(self.source))
        self.assertIsNone(ui.resume_path)
        self.assertFalse(ui.test.get())
