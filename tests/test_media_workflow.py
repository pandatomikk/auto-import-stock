import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from openpyxl import Workbook
from PIL import Image

from core.converter import convert_catalogue
from core.media_workflow import (
    EAN_COLUMN, finalize_catalogue, load_session, prepare_catalogue, select_zip_images,
)

ROOT = Path(__file__).resolve().parent.parent
EAN = '0000000000017'
OTHER = '0000000000024'
HEADERS = ['Reference', 'Color code', 'Barcode', 'Price', 'Quantity', 'Name', 'Color', 'Category']


from core.media_workflow import select_zip_images as _select_zip_images
def select_zip_images(archive, references, identities=()):
    settings = json.loads((ROOT / 'profiles/demo.json').read_text())['images']
    return _select_zip_images(archive, references, identities, settings)


def make_source(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['Commande de test'])
    sheet.append(HEADERS)
    sheet.append(['ITEM100', '001', EAN, 99.9, 2, 'Demo', 'BLACK', 'Sac'])
    sheet.append(['ITEM100', '058', OTHER, 89, 1, 'Demo', 'RED', 'Sac'])
    sheet.append(['NONCOMMANDE', '001', '0000000000031', 50, 0, 'Sans commande', 'BLACK', 'Sac'])
    workbook.save(path)
    workbook.close()
    return path


def make_zip(path, names):
    image = io.BytesIO()
    Image.new('RGB', (32, 24), 'purple').save(image, format='JPEG')
    with zipfile.ZipFile(path, 'w') as archive:
        for name in names:
            archive.writestr(name, image.getvalue())
    return path


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


class ExampleWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = make_source(self.root / 'commande.xlsx')

    def prepare(self):
        return prepare_catalogue(self.source, ROOT / 'profiles/demo.json', ROOT / 'schemas/woocommerce.json')

    def finalize(self, session, archive):
        with contextlib.redirect_stdout(io.StringIO()):
            return finalize_catalogue(session, archive)

    def test_two_passes_preserve_preparation_and_manual_edits(self):
        session, data = self.prepare()
        self.assertEqual(load_session(session)['status'], 'waiting_images')
        self.assertFalse((self.root / data['final_csv']).exists())
        self.assertEqual((self.root / data['ean_text']).read_text().splitlines(), [EAN, OTHER])
        prepared = self.root / data['prepared_csv']
        rows = read_rows(prepared)
        self.assertEqual([r['Stock'] for r in rows], ['2', '1'])
        self.assertTrue(all(r['Publié'] == '1' and not r['Images'] for r in rows))
        # The final pass must use the prepared CSV, including user corrections.
        text = prepared.read_text(encoding='utf-8-sig').replace('Demo -', 'Libellé corrigé -')
        prepared.write_text(text, encoding='utf-8-sig')
        before = prepared.read_bytes()
        self.source.unlink()
        archive = make_zip(self.root / 'photos.zip', [
            'batch/PHOTO_ITEM100_001_10.jpg',
            'batch/PHOTO_ITEM100_001_2.jpg',
            'batch/PHOTO_ITEM100_001.jpg',
            'batch/PHOTO_ITEM100_058.jpg',
            'batch/PHOTO_ITEM100EXTRA_058.jpg',
        ])
        result = self.finalize(session, archive)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['missing_images'], [])
        self.assertEqual(prepared.read_bytes(), before)
        final = read_rows(self.root / result['final_csv'])
        for original, row in zip(read_rows(prepared), final):
            self.assertEqual({k:v for k,v in original.items() if k != 'Images'},
                             {k:v for k,v in row.items() if k != 'Images'})
        images = final[0]['Images'].split(', ')
        self.assertEqual(len(images), 3)
        paths = [self.root / 'images_demo/fichiers_webp' / name for name in images]
        for path in paths:
            with Image.open(path) as image:
                self.assertEqual(image.format, 'WEBP')
        report = json.loads((self.root / data['final_report']).read_text())
        self.assertEqual([Path(r['archive_path']).name for r in report['images'][:3]], [
            'PHOTO_ITEM100_001.jpg', 'PHOTO_ITEM100_001_2.jpg',
            'PHOTO_ITEM100_001_10.jpg'])
        times = [p.stat().st_mtime_ns for p in paths]
        self.finalize(session, archive)
        self.assertEqual([p.stat().st_mtime_ns for p in paths], times)

    def test_pending_session_reused_without_rebuilding(self):
        session, data = self.prepare()
        prepared = self.root / data['prepared_csv']
        before = prepared.read_bytes()
        self.source.write_bytes(b'source changed during the pause')
        again, resumed = self.prepare()
        self.assertEqual(again, session)
        self.assertEqual(resumed, data)
        self.assertEqual(prepared.read_bytes(), before)

    def test_partial_zip_keeps_all_products_and_reports_missing(self):
        session, data = self.prepare()
        archive = make_zip(self.root / 'photos.zip', ['PHOTO_ITEM100_BLACK.jpg'])
        result = self.finalize(session, archive)
        self.assertEqual(result['missing_images'], [OTHER])
        rows = read_rows(self.root / data['final_csv'])
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]['Images'])
        self.assertEqual(rows[1]['Images'], '')
        self.assertTrue(all(row['Publié'] == '1' for row in rows))

    def test_no_match_or_corrupt_image_keeps_session_pending(self):
        session, data = self.prepare()
        archive = make_zip(self.root / 'unrelated.zip', ['PHOTO_OTHER_069.jpg'])
        with self.assertRaisesRegex(ValueError, 'Aucune image'):
            self.finalize(session, archive)
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('PHOTO_ITEM100_001.jpg', b'not an image')
        with self.assertRaises(OSError):
            self.finalize(session, archive)
        self.assertEqual(load_session(session)['status'], 'waiting_images')
        self.assertFalse((self.root / data['final_csv']).exists())
        self.assertTrue((self.root / data['prepared_csv']).exists())

    def test_pattern_color_aliases_and_no_cross_color_assignment(self):
        archive = make_zip(self.root / 'photos.zip', [
            'PHOTO_ITEM100_1.jpg', 'PHOTO_ITEM100_BLACK_2.jpg',
            'PHOTO_ITEM100_E52.jpg', 'PHOTO_ITEM100_GREYMULTICOLOR_2.jpg',
            'PHOTO_ITEM100_RED.jpg',
        ])
        identities = [dict(ean=EAN, article='ITEM100', color_code='001', color='BLACK'),
                      dict(ean=OTHER, article='ITEM100', color_code='E52', color='GREY/MULTICOLOR')]
        with zipfile.ZipFile(archive) as z:
            selected, ignored = select_zip_images(z, {EAN, OTHER}, identities)
        self.assertEqual(len(selected[EAN]), 2)
        self.assertEqual(len(selected[OTHER]), 2)
        self.assertEqual(ignored, ['PHOTO_ITEM100_RED.jpg'])
        identities[1].update(color_code='001', color='BLACK')
        with zipfile.ZipFile(archive) as z, self.assertRaisesRegex(ValueError, 'ambiguë'):
            select_zip_images(z, {EAN, OTHER}, identities)

    def test_ean_fallback_is_exact_and_supports_product_folders(self):
        archive = make_zip(self.root / 'photos.zip', [
            '20260910/' + EAN + '_2.jpg', OTHER + '/front.jpg', '9' + EAN + '_1.jpg',
        ])
        with zipfile.ZipFile(archive) as z:
            selected, ignored = select_zip_images(z, {EAN, OTHER})
        self.assertEqual(len(selected[EAN]), 1)
        self.assertEqual(len(selected[OTHER]), 1)
        self.assertEqual(len(ignored), 1)

    def test_preparation_folder_can_be_moved(self):
        session, data = self.prepare()
        moved = self.root / 'moved'
        moved.mkdir()
        for key in ('prepared_csv', 'ean_text', 'preparation_report'):
            shutil.move(self.root / data[key], moved / data[key])
        session = Path(shutil.move(session, moved / session.name))
        archive = make_zip(self.root / 'photos.zip', [EAN + '.jpg'])
        self.finalize(session, archive)
        self.assertTrue((moved / data['final_csv']).is_file())

    def test_old_profile_cannot_restore_draft_status(self):
        config = json.loads((ROOT / 'profiles/demo.json').read_text())
        config['fixed_values']['Publié'] = -1
        config['images']['mode'] = 'none'
        path = self.root / 'old.json'
        path.write_text(json.dumps(config))
        result = convert_catalogue(self.source, path, ROOT / 'schemas/woocommerce.json')
        self.assertTrue(all(row['Publié'] == '1' for row in read_rows(result.output_path)))

    def test_single_pass_stays_published(self):
        source = self.root / 'single.csv'
        source.write_text('Reference,Color code,Barcode,Price,Quantity,Name,Color,Category\nITEM100,001,0000000000017,99,2,Demo,BLACK,Sac\n')
        result = convert_catalogue(source, ROOT / 'profiles/demo.json', ROOT / 'schemas/woocommerce.json', web_descriptions=False)
        self.assertEqual(read_rows(result.output_path)[0]['Publié'], '1')

    def test_cli_requires_explicit_second_pass(self):
        base = [sys.executable, '-B', str(ROOT / 'convertisseur.py')]
        first = subprocess.run(base + ['--supplier', 'demo', '--source', str(self.source)], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        event = json.loads(next(line.split(' ', 1)[1] for line in first.stdout.splitlines() if line.startswith('ZPSI_WORKFLOW ')))
        self.assertEqual(event['status'], 'waiting_images')
        self.assertFalse(Path(event['final_csv']).exists())
        archive = make_zip(self.root / 'photos.zip', ['PHOTO_ITEM100_001.jpg'])
        second = subprocess.run(base + ['--resume-session', event['session'], '--images-zip', str(archive)], capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(Path(event['final_csv']).exists())
        missing_zip = subprocess.run(base + ['--resume-session', event['session']], capture_output=True, text=True)
        self.assertNotEqual(missing_zip.returncode, 0)

    def test_empty_order_does_not_create_a_session(self):
        source = self.root / 'empty.csv'
        source.write_text(','.join(HEADERS) + '\nA,001,' + EAN + ',99,0,Test,BLACK,Sac\n')
        with self.assertRaisesRegex(ValueError, 'Aucun produit'):
            prepare_catalogue(source, ROOT / 'profiles/demo.json', ROOT / 'schemas/woocommerce.json')
        self.assertFalse(list(self.root.glob('*_session.json')))
