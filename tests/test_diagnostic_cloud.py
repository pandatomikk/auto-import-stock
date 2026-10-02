import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from core.diagnostic_cloud import bundle, scrub, send_pending
import hashlib

class DiagnosticCloudTests(unittest.TestCase):
    def test_bundle_only_diagnostics_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'rapport_import.json').write_text(json.dumps({'token':'private', 'nested':{'consumer_key':'secret'},'sku':'123'}))
            (root/'diagnostic_preparation.txt').write_text('Authorization: Bearer something\npassword=very-secret\nck_'+'a'*40)
            (root/'client.json').write_text('do not send')
            (root/'source.csv').write_text('do not send')
            with zipfile.ZipFile(io.BytesIO(bundle(root,'test','ok'))) as archive:
                self.assertEqual(set(archive.namelist()),{'execution.json','rapport_import.json','diagnostic_preparation.txt'})
                text=''.join(archive.read(n).decode() for n in archive.namelist())
                self.assertNotIn('very-secret',text)
                self.assertNotIn('something',text)
                self.assertNotIn('private',text)
                self.assertIn('123',text)

    def test_failed_upload_kept_then_sent_without_redirect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);endpoint='https://cloud.example/public.php/webdav/';token='abc'
            queue=root/'.diagnostics_cloud'/hashlib.sha256(endpoint.encode()+token.encode()).hexdigest()[:16]
            queue.mkdir(parents=True);path=queue/'test.zip';path.write_bytes(b'diagnostic')
            with patch('core.diagnostic_cloud.requests.put',return_value=Mock(status_code=503)):
                send_pending(root,endpoint,token)
            self.assertTrue(path.exists())
            with patch('core.diagnostic_cloud.requests.put',return_value=Mock(status_code=201)) as put:
                send_pending(root,endpoint,token)
                self.assertFalse(put.call_args.kwargs['allow_redirects'])
            self.assertFalse(path.exists())
            self.assertTrue(path.with_suffix('.sent').exists())
