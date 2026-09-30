import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from core.drive_download import download_public_file


class DriveDownloadTest(unittest.TestCase):
    def response(self, content_type='image/png', status=200, chunks=(b'image',)):
        response = Mock(status_code=status, headers={'Content-Type': content_type})
        response.iter_content.return_value = iter(chunks)
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_direct_download_and_explicit_export(self):
        with tempfile.TemporaryDirectory() as tmp, patch('core.drive_download.requests.get', return_value=self.response()) as get:
            output = Path(tmp)/'image.part'
            download_public_file('abc-123', output)
            self.assertEqual(output.read_bytes(), b'image')
            self.assertEqual(get.call_args.kwargs['params']['export'], 'download')

    def test_html_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch('core.drive_download.requests.get', return_value=self.response('text/html')):
            fallback = Mock(return_value='downloaded')
            self.assertEqual(download_public_file('abc', Path(tmp)/'part', fallback=fallback), 'downloaded')
            fallback.assert_called_once()

    def test_quota_and_oversize_remove_partial_without_fallback(self):
        for response in (self.response(status=429), self.response(chunks=(b'123', b'456'))):
            with tempfile.TemporaryDirectory() as tmp, patch('core.drive_download.requests.get', return_value=response):
                output = Path(tmp)/'part'
                fallback = Mock()
                with self.assertRaises((RuntimeError, ValueError)):
                    download_public_file('abc', output, fallback=fallback, max_bytes=4)
                self.assertFalse(output.exists())
                fallback.assert_not_called()
