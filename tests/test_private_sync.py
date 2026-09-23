import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import private_sync as sync

class PrivateSyncTests(unittest.TestCase):
    def test_one_way_conflict_protection_and_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            files={'client.json':b'{"image_filename_suffix":"a"}', 'adapters/tool.py': b'x=1\n'}
            self.assertEqual(sync.apply_pack(root,'owner/repo','a',files),2)
            local=root/'client.json';local.write_text('{"image_filename_suffix":"local"}')
            newer={**files,'adapters/tool.py':b'x=2\n'}
            self.assertEqual(sync.apply_pack(root,'owner/repo','b',newer),1)
            conflict={**newer,'client.json':b'{"image_filename_suffix":"remote"}'}
            with self.assertRaisesRegex(ValueError,'Réglages locaux'):
                sync.apply_pack(root,'owner/repo','c',conflict)
            self.assertIn('local',local.read_text())
            self.assertEqual(sync.apply_pack(root,'owner/repo','d',{'client.json':files['client.json']}),1)
            self.assertFalse((root/'adapters/tool.py').exists())

    def test_initial_existing_settings_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'client.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Réglages locaux'):
                sync.apply_pack(root,'owner/repo','a',{'client.json':b'{"a":1}'})
            self.assertEqual((root/'client.json').read_text(),'{}')

    def test_invalid_paths_and_syntax_rejected_before_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            for files in ({'../escape.json':b'{}'}, {'adapters/bad.py':b'def !'}, {'profiles/x.json':b'['}):
                with self.subTest(files=files), self.assertRaises((ValueError,SyntaxError)):
                    sync.apply_pack(temp,'owner/repo','a',files)
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_failure_rolls_back_all_files_and_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);files={'client.json':b'{}', 'adapters/tool.py':b'x=1'}
            sync.apply_pack(root,'owner/repo','a',files)
            original=sync.atomic_write
            def fail(path,data):
                if Path(path).name == sync.STATE and b'"revision": "b"' in data:
                    raise OSError('disk full')
                original(path,data)
            with patch.object(sync,'atomic_write',side_effect=fail), self.assertRaises(OSError):
                sync.apply_pack(root,'owner/repo','b',{'client.json':b'{"a":1}','adapters/tool.py':b'x=2'})
            for name,data in files.items():self.assertEqual((root/name).read_bytes(),data)
            self.assertEqual(json.loads((root/sync.STATE).read_text())['revision'],'a')

    def test_download_uses_only_read_requests_and_checks_blobs(self):
        import base64, hashlib
        data=b'{"image_filename_suffix":"example.fr"}'
        sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        commit='a'*40
        entry={'path':'client.json','sha':sha,'size':len(data),'type':'file'}
        responses=[[entry], {**entry,'encoding':'base64','content':base64.b64encode(data).decode()}, [entry]]
        requests=[]
        class Response:
            def __init__(self,data): self.data=json.dumps(data).encode()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return self.data[:limit]
        class Opener:
            def open(self,req,timeout):
                requests.append(req)
                return Response(responses.pop(0))
        with patch.object(sync,'build_opener',return_value=Opener()):
            revision,files=sync.download_pack('owner/repo','main','test-token')
        self.assertEqual(files,{'client.json':data})
        self.assertEqual(len(revision),40)
        self.assertTrue(all('/contents' in r.full_url for r in requests))
        self.assertTrue(all(r.get_method()=='GET' for r in requests))
        self.assertTrue(all(r.full_url.startswith('https://api.github.com/repos/owner/repo/') for r in requests))

    def test_github_denial_reports_reason_without_token(self):
        import io
        from urllib.error import HTTPError
        from unittest.mock import Mock
        opener = Mock()
        opener.open.side_effect = HTTPError('https://api.github.com', 403, 'Forbidden', {}, io.BytesIO(b'{"message":"Resource not accessible: secret-token"}'))
        with patch.object(sync, 'build_opener', return_value=opener):
            with self.assertRaises(ValueError) as caught:
                sync.download_pack('owner/repo', 'main', 'secret-token')
        self.assertIn('Resource not accessible', str(caught.exception))
        self.assertNotIn('secret-token', str(caught.exception))
        self.assertIn('/contents?ref=main', str(caught.exception))

    def test_contents_download_rejects_change_before_installation(self):
        import base64, hashlib
        from unittest.mock import Mock
        data=b'{}'
        sha=hashlib.sha1(b'blob 2\0'+data).hexdigest()
        entry={'path':'client.json','type':'file','sha':sha,'size':2}
        responses=[[entry],{**entry,'encoding':'base64','content':base64.b64encode(data).decode()},[{**entry,'sha':'f'*40}]]
        def response(*args, **kwargs):
            value=Mock()
            value.__enter__=Mock(return_value=value)
            value.__exit__=Mock(return_value=False)
            value.read.return_value=json.dumps(responses.pop(0)).encode()
            return value
        opener=Mock();opener.open.side_effect=response
        with patch.object(sync,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'changé pendant'):
                sync.download_pack('owner/repo','main','token')

    def test_explicit_replacement_backs_up_manual_install_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'profiles').mkdir()
            (root/'profiles/test.json').write_bytes(b'{"local":true}')
            (root/'other.txt').write_text('keep')
            files={'profiles/test.json':b'{"remote":true}','client.json':b'{}'}
            with self.assertRaises(sync.PackConflict):sync.apply_pack(root,'owner/repo','a',files)
            self.assertEqual(sync.apply_pack(root,'owner/repo','a',files,replace_conflicts=True),2)
            self.assertEqual((root/'profiles/test.json').read_bytes(),files['profiles/test.json'])
            backup=next(root.glob('pack-backup-*'))
            self.assertEqual((backup/'profiles/test.json').read_bytes(),b'{"local":true}')
            self.assertEqual((root/'other.txt').read_text(),'keep')
            self.assertEqual(sync.apply_pack(root,'owner/repo','a',files),0)

    def test_failed_backup_never_replaces_local_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'client.json').write_bytes(b'{"local":true}')
            with patch.object(sync,'atomic_write',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):sync.apply_pack(root,'owner/repo','a',{'client.json':b'{}'},replace_conflicts=True)
            self.assertEqual((root/'client.json').read_bytes(),b'{"local":true}')
            self.assertFalse((root/sync.STATE).exists())
