import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core.converter import convert_catalogue

ROOT = Path(__file__).resolve().parents[1]


class PreparationTests(unittest.TestCase):
    def test_events_cover_conversion_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.csv'
            source.write_text('Reference,Barcode,Name,Quantity,Price,Color,Color code\nABC,0000000000017,Example,2,12,BLACK,001\n')
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                result = convert_catalogue(source, ROOT / 'profiles/demo.json', ROOT / 'schemas/woocommerce.json', web_descriptions=False)
            events = [json.loads(line.split(' ', 1)[1]) for line in stream.getvalue().splitlines() if line.startswith('ZPSI_PREPARATION ')]
            self.assertEqual(events[0]['stage'], 'Configuration')
            self.assertEqual(events[-1]['stage'], 'Fichiers prêts')
            self.assertTrue(any(e['total'] == 1 and e['done'] == 1 for e in events))
            self.assertTrue(result.output_path.exists())

    def test_already_prepared_csv_stops_before_zip_work(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'ready.csv'
            source.write_text('UGS,Nom,Type,Publié\nABC,Example,simple,1\n')
            with patch('core.converter.build_zip_image_context') as index, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'Ma boutique'):
                    convert_catalogue(source, ROOT / 'profiles/demo.json', ROOT / 'schemas/woocommerce.json', web_descriptions=False)
            index.assert_not_called()
            self.assertFalse((Path(folder) / 'ready_woocommerce.csv').exists())
