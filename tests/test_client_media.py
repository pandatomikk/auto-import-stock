"""Exercise the real Tk state transitions; skip when no display is available."""
import os
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from client import Client
from test_media_workflow import make_source, make_zip


class ExampleClientTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pack_env = patch.dict(os.environ, {'AUTO_IMPORT_PRIVATE_DIR':str(self.root / 'empty-pack')})
        pack_env.start()
        self.addCleanup(pack_env.stop)
        try:
            self.app = Client()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.app.withdraw()
        self.addCleanup(self.destroy_client)
        self.source = make_source(self.root / 'commande.xlsx')
        self.app.brand.set('demo')
        self.app.brand_changed()
        self.app.source.set(str(self.source))
        # Exercise the actual converter process without reinstalling its venv.
        real_popen = subprocess.Popen
        def launch(args, **kwargs):
            args = [str(Path(a).with_name('convertisseur.py')) if Path(a).name == 'lancer.py' else a for a in args]
            return real_popen(args, **kwargs)
        self.popen_patch = patch('client.subprocess.Popen', side_effect=launch)
        self.popen_patch.start()
        self.addCleanup(self.popen_patch.stop)

    def destroy_client(self):
        if self.app.proc and self.app.proc.poll() is None:
            self.app.stop()
            self.app.proc.wait(timeout=10)
        self.app.destroy()

    def wait_for_worker(self):
        deadline = time.monotonic() + 10
        while self.app.proc is not None and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertIsNone(self.app.proc, 'Le processus ne termine pas')

    def test_pause_retry_and_finalize(self):
        self.assertIn('1 ·', self.app.start_button['text'])
        self.assertEqual(str(self.app.image_entry['state']), 'disabled')
        self.app.start()
        self.assertEqual(str(self.app.select['state']), 'disabled')
        self.wait_for_worker()
        self.assertIsNotNone(self.app.resume_path)
        self.assertIn('En pause', self.app.stage.get())
        self.assertIn('2 ·', self.app.start_button['text'])
        self.assertEqual(str(self.app.image_entry['state']), 'normal')
        self.assertEqual(str(self.app.ean_button['state']), 'normal')
        with patch.object(self.app, 'open_path') as open_path:
            self.app.open_eans()
            self.assertTrue(open_path.call_args.args[0].is_file())
        archive = make_zip(self.root / 'bad.zip', ['unrelated.jpg'])
        self.app.drive.set(str(archive))
        self.app.start()
        self.wait_for_worker()
        self.assertIn('Aucune image', self.app.status.get())
        self.assertIsNotNone(self.app.resume_path)
        self.assertIn('2 ·', self.app.start_button['text'])
        archive = make_zip(self.root / 'good.zip', ['PHOTO_ITEM100_001.jpg'])
        self.app.drive.set(str(archive))
        self.app.start()
        self.wait_for_worker()
        self.assertIn('CSV final prêt', self.app.stage.get())
        self.assertIn('1 référence(s) sans image', self.app.status.get())
        self.assertTrue((self.root / 'commande_woocommerce.csv').is_file())

    def test_resume_after_reopening_and_switching_supplier(self):
        self.app.start()
        self.wait_for_worker()
        session = self.app.resume_path
        self.app.destroy()
        self.app = Client()
        self.app.withdraw()
        self.app.brand.set('demo')
        self.app.brand_changed()
        self.app.source.set(str(self.source))
        self.assertEqual(self.app.resume_path, session)
        self.app.configs['single']={'supplier_name':'Example single','workflow':{'kind':'catalogue'}}
        self.app.brand.set('single')
        self.app.brand_changed()
        self.assertIsNone(self.app.resume_path)
        self.assertEqual(self.app.start_button['text'], 'Préparer mes produits')
        self.app.brand.set('demo')
        self.app.brand_changed()
        self.source.unlink()
        self.app.source.set(str(session))
        self.assertEqual(self.app.resume_path, session)
        self.app.drive.set(str(make_zip(self.root / 'good.zip', ['PHOTO_ITEM100_001.jpg'])))
        self.app.start()
        self.wait_for_worker()
        self.assertIn('CSV final prêt', self.app.stage.get())
