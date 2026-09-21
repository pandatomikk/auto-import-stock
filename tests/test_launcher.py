from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json
import lancer


class Handoff(Exception):
    pass


class LauncherTests(unittest.TestCase):
    def test_client_bootstraps_dependencies_before_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); env = root / '.venv'
            python = env / ('Scripts/python.exe' if lancer.os.name == 'nt' else 'bin/python')
            python.parent.mkdir(parents=True); python.touch()
            with patch.object(lancer, 'APP_DIR', root), patch.object(lancer, 'VENV_DIR', env), patch.object(lancer, 'CONVERTER', root/'convertisseur.py'), patch.object(lancer.sys, 'argv', ['lancer.py', '--client']), patch.object(lancer, 'in_our_venv', return_value=False), patch.object(lancer, 'dependency_ok', return_value=False), patch.object(lancer, 'install_dependencies') as install, patch.object(lancer.os, 'execv', side_effect=Handoff) as handoff:
                with self.assertRaises(Handoff): lancer.main()
                install.assert_called_once_with(python)
                self.assertEqual(handoff.call_args.args[1][1], str(root / 'client.py'))

    def test_active_update_runtime_and_escape_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch.object(lancer, 'APP_DIR', root):
                (root/'active_runtime.json').write_text(json.dumps({'directory': '.runtimes/version'}))
                self.assertEqual(lancer.venv_python().parent.parent, root / '.runtimes/version')
                (root/'active_runtime.json').write_text(json.dumps({'directory': '../outside'}))
                with self.assertRaises(RuntimeError): lancer.venv_python()

    def test_update_lock_prevents_starting_partial_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); (root / '.update.lock').touch()
            with patch.object(lancer, 'APP_DIR', root), patch.object(lancer.os, 'execv') as handoff:
                self.assertEqual(lancer.main(), 1)
                handoff.assert_not_called()
