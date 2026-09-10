import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from core.shop_mappings import prepare_mappings, load_mappings, save_mappings, source_key, term_labels
from core.shop_products import prepare_csv
from core.shop_connection import ConnectionFailure
from test_shop_products import FakeAPI


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch('core.shop_mappings.settings_path', return_value=self.root / 'shop.json')
        patcher.start(); self.addCleanup(patcher.stop)
        self.api = FakeAPI()
        self.path = self.root / 'articles.csv'
        self.path.write_text('UGS,Nom,Marques,Catégories\nABC,Article,Exem,Petits sacs\n')

    def test_suggestion_is_not_used_without_confirmed_mapping(self):
        review = prepare_mappings(self.path, self.api)
        brand = next(r for r in review['rows'] if r['kind'] == 'brands')
        self.assertEqual(brand['id'], 8)
        self.assertEqual(brand['state'], 'Suggestion à valider')
        self.assertTrue(prepare_csv(self.path, self.api)['errors'])
        self.assertEqual(self.api.created, [])

    def test_saved_aliases_are_applied_to_payload_and_scoped_to_shop(self):
        choices = {'brands': {'exem': 8}, 'categories': {'petits sacs': 4}}
        save_mappings(self.api.url, choices)
        self.assertEqual(load_mappings('https://another.example'), {})
        plan = prepare_csv(self.path, self.api, mappings=load_mappings(self.api.url))
        self.assertEqual(plan['errors'], [])
        self.assertEqual(plan['items'][0]['payload']['brands'], [{'id': 8}])
        self.assertEqual(plan['items'][0]['payload']['categories'], [{'id': 4}])
        self.assertEqual(plan['correspondences'][1]['destination'], 'Exemple')
        self.assertTrue(all(row['state'] == 'Mémorisé' for row in prepare_mappings(self.path, self.api)['rows']))
        self.assertIn('Exem', self.path.read_text())

    def test_manual_override_preserves_other_aliases(self):
        save_mappings(self.api.url, {'brands': {'other': 2, 'exem': 3}})
        save_mappings(self.api.url, {'brands': {'exem': 8}})
        self.assertEqual(load_mappings(self.api.url)['brands'], {'other': 2, 'exem': 8})

    def test_deleted_destination_requires_a_new_choice(self):
        save_mappings(self.api.url, {'brands': {'exem': 999}})
        row = next(r for r in prepare_mappings(self.path, self.api)['rows'] if r['kind'] == 'brands')
        self.assertIsNone(row['id'])
        self.assertIn('absente', row['state'])
        self.assertTrue(prepare_csv(self.path, self.api, mappings={'brands': {'exem': 999}})['errors'])

    def test_duplicate_category_names_are_disambiguated_by_path(self):
        terms = [{'id': 1, 'name': 'A', 'parent': 0}, {'id': 2, 'name': 'B', 'parent': 0}, {'id': 3, 'name': 'Sacs', 'parent': 1}, {'id': 4, 'name': 'Sacs', 'parent': 2}]
        self.api.listing = Mock(return_value=terms)
        self.path.write_text('UGS,Nom,Catégories\nABC,Article,Sacs\n')
        review = prepare_mappings(self.path, self.api)
        self.assertIsNone(review['rows'][0]['id'])
        self.assertEqual(review['options']['categories'][4], 'B > Sacs')
        self.path.write_text('UGS,Nom,Catégories\nABC,Article,A > Sacs\n')
        self.assertEqual(prepare_mappings(self.path, self.api)['rows'][0]['id'], 3)

    def test_corrupt_or_wrong_shop_mapping_is_not_silently_applied(self):
        path = self.root / 'bad.json'
        path.write_text(json.dumps({'site': 'https://other.example', 'mappings': {'brands': {'x': 3}}}))
        with self.assertRaises(ConnectionFailure):
            load_mappings(self.api.url, path)

    def test_editor_allows_manual_override_and_requires_explicit_apply(self):
        import tkinter as tk
        from core.shop_mappings_ui import MappingsDialog
        try:
            owner = tk.Tk()
        except tk.TclError:
            self.skipTest('Display unavailable')
        owner.withdraw(); owner.select = Mock(); owner.mapping_button = Mock()
        review = {'site': self.api.url, 'options': {'brands': {8: 'Exemple', 9: 'Autre'}}, 'rows': [{'kind': 'brands', 'source': 'Exem', 'id': 8, 'state': 'Suggestion à valider'}]}
        callback = Mock()
        dialog = MappingsDialog(owner, review, callback); dialog.withdraw()
        try:
            callback.assert_not_called()
            self.assertEqual(load_mappings(self.api.url), {})
            dialog.choice.current(dialog.option_ids.index(9)); dialog.changed()
            dialog.apply()
            callback.assert_called_once_with({'brands': {'exem': 9}})
            self.assertEqual(load_mappings(self.api.url)['brands']['exem'], 9)
        finally:
            if dialog.winfo_exists(): dialog.close()
            owner.destroy()
