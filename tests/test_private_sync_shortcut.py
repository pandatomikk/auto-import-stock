"""The main-window shortcut starts the existing update flow once configured."""
import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from core.private_sync_ui import open_pack_dialog

class PackShortcutTest(unittest.TestCase):
    def test_saved_pack_downloads_without_second_click(self):
        try: app = tk.Tk()
        except tk.TclError: self.skipTest('Display unavailable')
        app.proc=None; app.update_controller=SimpleNamespace(busy=False); app.close=Mock()
        try:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                (root/'.sync-config.json').write_text(json.dumps({'repository':'owner/pack','branch':'main'}))
                vault=Mock();vault.get_password.return_value='saved-token'
                with patch('core.private_sync_ui.private_directory',return_value=root), patch('core.private_sync_ui.system_vault',return_value=vault), patch('core.private_sync_ui.download_pack',return_value=('revision',{})) as download, patch('core.private_sync_ui.apply_pack',return_value=0) as apply:
                    open_pack_dialog(app,auto_update=True)
                    deadline=time.monotonic()+3
                    while not apply.called and time.monotonic()<deadline:
                        app.update();time.sleep(.01)
                    download.assert_called_once_with('owner/pack','main','saved-token')
                    apply.assert_called_once()
                    until=time.monotonic()+.25
                    while time.monotonic()<until:
                        app.update();time.sleep(.01)
        finally: app.destroy()

    def test_unconfigured_pack_does_not_start_download(self):
        try: app = tk.Tk()
        except tk.TclError: self.skipTest('Display unavailable')
        app.proc=None; app.update_controller=SimpleNamespace(busy=False)
        try:
            with tempfile.TemporaryDirectory() as folder, patch('core.private_sync_ui.private_directory',return_value=Path(folder)), patch('core.private_sync_ui.download_pack') as download:
                open_pack_dialog(app,auto_update=True);app.update()
                download.assert_not_called()
        finally: app.destroy()
