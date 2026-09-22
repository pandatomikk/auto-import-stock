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
        self.root = Path(self.temp.name).resolve()
        patcher = patch('core.shop_mappings.settings_path', return_value=self.root / 'shop.json')
        patcher.start(); self.addCleanup(patcher.stop)
        self.api = FakeAPI()
        self.path = self.root / 'articles.csv'
        self.path.write_text('UGS,Nom,Marques,Catégories\nABC,Article,Exem,Petits sacs\n', encoding='utf-8')

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
        self.assertIn('Exem', self.path.read_text(encoding='utf-8'))

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
        self.path.write_text('UGS,Nom,Catégories\nABC,Article,Sacs\n', encoding='utf-8')
        review = prepare_mappings(self.path, self.api)
        self.assertIsNone(review['rows'][0]['id'])
        self.assertEqual(review['options']['categories'][4], 'B > Sacs')
        self.path.write_text('UGS,Nom,Catégories\nABC,Article,A > Sacs\n', encoding='utf-8')
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
            dialog.group.current(dialog.group_ids.index(9)); dialog.group_changed()
            dialog.apply()
            callback.assert_called_once_with({'brands': {'exem': 9}})
            self.assertEqual(load_mappings(self.api.url)['brands']['exem'], 9)
        finally:
            if dialog.winfo_exists(): dialog.close()
            owner.destroy()


    def test_category_groups_filter_destinations_and_clear_previous_choice(self):
        import tkinter as tk
        from core.shop_mappings_ui import MappingsDialog
        try: owner = tk.Tk()
        except tk.TclError: self.skipTest('Display unavailable')
        owner.withdraw(); owner.select = Mock(); owner.mapping_button = Mock()
        review = {'site': self.api.url, 'options': {'categories': {1:'A', 2:'B', 3:'A > Sacs', 4:'B > Sacs', 5:'A > Sacs > Mini'}}, 'category_parents': {1:0, 2:0, 3:1, 4:2, 5:3}, 'rows': [{'kind':'categories', 'source':'Sacs', 'id':3, 'state':'Choisi'}]}
        callback = Mock()
        dialog = MappingsDialog(owner, review, callback); dialog.withdraw()
        try:
            self.assertEqual(dialog.group_ids[dialog.group.current()], 1)
            self.assertEqual(set(dialog.option_ids), {None,1,3,5})
            dialog.group.current(dialog.group_ids.index(2)); dialog.group_changed()
            self.assertIsNone(review['rows'][0]['id'])
            self.assertEqual(set(dialog.option_ids), {None,2,4})
            dialog.apply(); callback.assert_not_called()
            dialog.choice.current(dialog.option_ids.index(4)); dialog.changed()
            dialog.apply()
            callback.assert_called_once_with({'categories': {'sacs':4}})
        finally:
            if dialog.winfo_exists():dialog.close()
            owner.destroy()

    def test_create_category_under_selected_parent(self):
        from core.shop_products import ProductAPI
        from core.shop_connection import Credentials
        api = ProductAPI(Credentials('https://shop.example', consumer_key='k', consumer_secret='s'))
        terms = [{'id':1,'name':'A','parent':0}, {'id':2,'name':'Sacs','parent':0}]
        with patch.object(api, 'listing', return_value=terms), patch.object(api, 'request', return_value={'id':3,'name':'Sacs','parent':1}) as request:
            self.assertEqual(api.create_category('Sacs', parent=1)['id'],3)
            request.assert_called_once_with('wc/v3/products/categories', payload={'name':'Sacs','parent':1})
        with patch.object(api, 'listing', return_value=terms+[{'id':3,'name':'Sacs','parent':1}]), patch.object(api, 'request') as request:
            self.assertEqual(api.create_category('Sacs', parent=1)['id'],3)
            request.assert_not_called()
        with patch.object(api, 'listing', return_value=terms), patch.object(api, 'request') as request:
            with self.assertRaises(ConnectionFailure):api.create_category('Sacs', parent=999)
            request.assert_not_called()

    def test_create_brand_or_reuse_without_duplicate(self):
        from core.shop_products import ProductAPI
        from core.shop_connection import Credentials
        api = ProductAPI(Credentials('https://shop.example', consumer_key='k', consumer_secret='s'))
        with patch.object(api, 'listing', return_value=[]), patch.object(api, 'request', return_value={'id': 9, 'name': 'Test & Co'}) as request:
            self.assertEqual(api.create_brand(' Test & Co ')['id'], 9)
            request.assert_called_once_with('wc/v3/products/brands', payload={'name': 'Test & Co'})
        with patch.object(api, 'listing', return_value=[{'id': 9, 'name': 'Test &amp; Co'}]), patch.object(api, 'request') as request:
            self.assertEqual(api.create_brand('test & co')['id'], 9)
            request.assert_not_called()
        with patch.object(api, 'listing', return_value=[]), patch.object(api, 'request', return_value={}):
            with self.assertRaisesRegex(ConnectionFailure, 'non confirmée'):
                api.create_brand('Test')

    def test_brand_creation_selects_new_destination(self):
        import tkinter as tk
        import time
        from core.shop_mappings_ui import MappingsDialog
        try: owner = tk.Tk()
        except tk.TclError: self.skipTest('Display unavailable')
        owner.withdraw(); owner.select = Mock(); owner.mapping_button = Mock()
        owner.api = Mock()
        owner.api.create_brand.return_value = {'id': 12, 'name': 'Nouvelle &amp; marque'}
        review = {'site': self.api.url, 'options': {'brands': {}}, 'rows': [{'kind': 'brands', 'source': 'Nouvelle marque', 'id': None, 'state': 'À choisir'}]}
        callback = Mock()
        dialog = MappingsDialog(owner, review, callback); dialog.withdraw()
        try:
            self.assertEqual(dialog.create_button['text'], 'Nouvelle marque…')
            with patch('core.shop_mappings_ui.simpledialog.askstring', return_value='Nouvelle & marque'):
                dialog.create_category()
            deadline = time.monotonic() + 3
            while dialog.creating and time.monotonic() < deadline:
                owner.update(); time.sleep(.01)
            self.assertFalse(dialog.creating)
            owner.api.create_brand.assert_called_once_with('Nouvelle & marque')
            self.assertEqual(review['rows'][0]['id'], 12)
            self.assertEqual(review['options']['brands'][12], 'Nouvelle & marque')
            dialog.apply()
            callback.assert_called_once_with({'brands': {'nouvelle marque': 12}})
        finally:
            if dialog.winfo_exists(): dialog.close()
            owner.destroy()
