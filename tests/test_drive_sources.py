import unittest
from core.drive_sources import parse_drive_sources

class DriveSourcesTests(unittest.TestCase):
    def test_multiple_and_duplicate_sources(self):
        self.assertEqual(parse_drive_sources('https://drive.google.com/drive/folders/AAA?usp=sharing;\nhttps://drive.google.com/drive/u/0/folders/BBB https://drive.google.com/drive/folders/AAA'), ['https://drive.google.com/drive/folders/AAA', 'https://drive.google.com/drive/folders/BBB'])

    def test_reject_invalid_source_among_valid(self):
        for value in ['', 'https://docs.google.com/document/d/AAA', 'https://drive.google.com/drive/folders/AAA; https://example.com/folder']:
            with self.assertRaises(ValueError): parse_drive_sources(value)
