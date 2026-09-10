import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from core.shop_connection import Credentials, ConnectionFailure
from core.shop_media import upload_image


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'photo.webp'
        Image.new('RGB', (8, 8)).save(self.path)
        self.credentials = Credentials('https://shop.example/store', 'operator', 'app password')

    @patch('core.shop_media.build_opener')
    def test_upload_binary_and_wordpress_credentials(self, opener):
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"id":42,"source_url":"https://shop.example/photo.webp"}'
        result = upload_image(self.credentials, self.path)
        self.assertEqual(result['id'], 42)
        req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.full_url, 'https://shop.example/store/wp-json/wp/v2/media')
        self.assertEqual(req.data, self.path.read_bytes())
        self.assertEqual(req.get_header('Content-type'), 'image/webp')
        self.assertEqual(req.get_header('Content-disposition'), 'attachment; filename="photo.webp"')
        self.assertNotIn('password', req.full_url)

    @patch('core.shop_media.build_opener')
    def test_bad_image_does_not_send(self, opener):
        self.path.write_text('not an image')
        with self.assertRaises(ConnectionFailure):
            upload_image(self.credentials, self.path)
        opener.assert_not_called()

    @patch('core.shop_media.build_opener')
    def test_uncertain_upload_is_not_retried(self, opener):
        opener.return_value.open.side_effect = TimeoutError('secret')
        with self.assertRaises(ConnectionFailure) as caught:
            upload_image(self.credentials, self.path)
        self.assertIn('peut-être', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(opener.return_value.open.call_count, 1)

    @patch('core.shop_media.MAX_BYTES', 10)
    @patch('core.shop_media.build_opener')
    def test_size_limit(self, opener):
        with self.assertRaisesRegex(ConnectionFailure, 'maximum'):
            upload_image(self.credentials, self.path)
        opener.assert_not_called()
