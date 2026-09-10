import subprocess
import unittest
from unittest.mock import patch
from core.file_picker import askopenfilename


class PickerTests(unittest.TestCase):
    @patch('core.file_picker.sys.platform', 'linux')
    @patch('core.file_picker.shutil.which', return_value='/usr/bin/zenity')
    @patch('core.file_picker.subprocess.run')
    def test_native_filters_and_spaces(self, run, which):
        run.return_value = subprocess.CompletedProcess([], 0, '/tmp/une image.webp\n', '')
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'GNOME'}):
            result = askopenfilename(title='Choisir une image', filetypes=[('Images', '*.jpg *.webp')])
        self.assertEqual(result, '/tmp/une image.webp')
        self.assertIn('--file-filter=Images | *.jpg *.webp', run.call_args.args[0])
        self.assertNotIn('shell', run.call_args.kwargs)

    @patch('core.file_picker.sys.platform', 'linux')
    @patch('core.file_picker.shutil.which', return_value='/usr/bin/zenity')
    @patch('core.file_picker.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', ''))
    @patch('core.file_picker.tk_filedialog.askopenfilename')
    def test_cancel_does_not_open_fallback(self, fallback, run, which):
        self.assertEqual(askopenfilename(), '')
        fallback.assert_not_called()

    @patch('core.file_picker.sys.platform', 'linux')
    @patch('core.file_picker.shutil.which', return_value=None)
    @patch('core.file_picker.tk_filedialog.askopenfilename', return_value='fallback')
    def test_missing_native_component(self, fallback, which):
        self.assertEqual(askopenfilename(title='CSV'), 'fallback')
        fallback.assert_called_once_with(title='CSV')

    @patch('core.file_picker.sys.platform', 'win32')
    @patch('core.file_picker.tk_filedialog.askopenfilename', return_value='windows')
    def test_windows_unchanged(self, fallback):
        self.assertEqual(askopenfilename(), 'windows')
