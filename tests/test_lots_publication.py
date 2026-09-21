import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image
from core.io import write_csv
from core.lots import create_lot, attach_archive
from core.shop_publication import prepare_publication, publish_plan
from core.shop_connection import ConnectionFailure
from test_shop_products import FakeAPI


class LotsPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.csv = self.root / 'articles.csv'
        self.image = self.root / 'images' / 'photo.webp'
        self.image.parent.mkdir()
        Image.new('RGB', (32, 40), 'red').save(self.image)
        write_csv(self.csv, ['UGS', 'Nom', 'Images'], [{'UGS': 'NEW', 'Nom': 'Article', 'Images': 'photo.webp'}, {'UGS': 'EXISTING', 'Nom': 'Ancien', 'Images': 'photo.webp'}])
        self.api = FakeAPI()
        self.api.credentials = object()
        self.upload = Mock(return_value={'id': 33, 'url': 'https://shop.example/uploads/photo-1.webp', 'filename': 'photo-1.webp'})

    def test_lot_copies_originals_and_attaches_second_archive(self):
        archive = self.root / 'photos.zip'; archive.write_bytes(b'original')
        a, source, copied = create_lot(self.csv, 'Demo / Boutique', archive, root=self.root/'lots')
        b, _, _ = create_lot(self.csv, 'Demo / Boutique', root=self.root/'lots')
        self.assertNotEqual(a, b)
        self.assertEqual(source.read_bytes(), self.csv.read_bytes())
        self.assertEqual(copied.read_bytes(), archive.read_bytes())
        later = attach_archive(a/'resultats'/'test_session.json', archive)
        self.assertNotEqual(later, copied)
        self.assertTrue(later.is_relative_to(a/'sources'))

    def test_preview_readonly_then_media_before_products_and_online_csv(self):
        plan = prepare_publication(self.csv, self.api)
        self.assertFalse(plan['errors'])
        self.assertEqual(self.api.created, [])
        self.assertEqual(len(plan['local_files']), 1)
        report = publish_plan(plan, self.api, self.root/'report.json', uploader=self.upload)
        self.assertEqual(self.upload.call_count, 1)
        self.assertEqual(self.api.created[0]['images'], [{'id': 33}])
        self.assertEqual([r['state'] for r in report['results']], ['created', 'skipped'])
        self.assertIn('photo-1.webp', (self.root/'articles_en_ligne.csv').read_text(encoding='utf-8'))
        self.assertNotIn('photo-1.webp', self.csv.read_text(encoding='utf-8'))

    def test_confirmed_images_reused_after_product_failure(self):
        plan = prepare_publication(self.csv, self.api)
        self.api.create = Mock(side_effect=ConnectionFailure('API indisponible'))
        publish_plan(plan, self.api, self.root/'first.json', uploader=self.upload)
        publish_plan(plan, self.api, self.root/'second.json', uploader=self.upload)
        self.assertEqual(self.upload.call_count, 1)

    def test_uncertain_upload_blocks_retry_and_no_products_created(self):
        plan = prepare_publication(self.csv, self.api)
        self.upload.side_effect = ConnectionFailure('Réponse perdue')
        with self.assertRaises(ConnectionFailure):
            publish_plan(plan, self.api, self.root/'report.json', uploader=self.upload)
        with self.assertRaisesRegex(ConnectionFailure, 'non confirmé'):
            publish_plan(plan, self.api, self.root/'report.json', uploader=self.upload)
        self.assertEqual(self.upload.call_count, 1)
        self.assertEqual(self.api.created, [])

    def test_changed_image_blocks_all_writes(self):
        plan = prepare_publication(self.csv, self.api)
        Image.new('RGB', (40, 32), 'blue').save(self.image)
        with self.assertRaisesRegex(ConnectionFailure, 'changé'):
            publish_plan(plan, self.api, self.root/'report.json', uploader=self.upload)
        self.upload.assert_not_called()

    def test_product_appearing_after_preview_needs_no_upload(self):
        plan = prepare_publication(self.csv, self.api)
        self.api.products['NEW'] = {'id': 45}
        publish_plan(plan, self.api, self.root/'report.json', uploader=self.upload)
        self.upload.assert_not_called()
        self.assertEqual(self.api.created, [])

    def test_unfinished_csv_and_duplicate_photo_are_blocked(self):
        pending = self.root/'articles_preparation.csv'; pending.write_bytes(self.csv.read_bytes())
        with self.assertRaisesRegex(ConnectionFailure, 'attend encore'):
            prepare_publication(pending, self.api)
        (self.root/'photo.webp').write_bytes(self.image.read_bytes())
        with self.assertRaisesRegex(ConnectionFailure, 'Plusieurs images'):
            prepare_publication(self.csv, self.api)

    def test_csv_changed_after_preview_blocks_all_writes(self):
        plan = prepare_publication(self.csv, self.api)
        self.csv.write_text(self.csv.read_text(encoding='utf-8') + '\n')
        with self.assertRaisesRegex(ConnectionFailure, 'CSV a changé'):
            publish_plan(plan, self.api, self.root/'report.json', uploader=self.upload)
        self.upload.assert_not_called()


    def test_publication_reports_separate_image_and_product_estimates(self):
        from unittest.mock import patch
        Image.new('RGB', (32,40), 'blue').save(self.image.parent/'other.webp')
        write_csv(self.csv, ['UGS','Nom','Images'], [{'UGS':'NEW','Nom':'A','Images':'photo.webp'}, {'UGS':'NEW2','Nom':'B','Images':'other.webp'}])
        plan = prepare_publication(self.csv, self.api)
        messages = []
        with patch('core.shop_publication.time.monotonic', side_effect=[0,5,5,10,10,13,13,16]):
            publish_plan(plan, self.api, self.root/'report.json', progress=messages.append, uploader=self.upload)
        self.assertTrue(any('Envoi des images : 1/2' in text and '5 s' in text for text in messages))
        self.assertTrue(any('Création des articles : 1/2' in text and '3 s' in text for text in messages))
        self.assertIn('Création des articles : 2/2 · étape terminée', messages)
