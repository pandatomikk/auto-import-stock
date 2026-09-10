import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core.product_rules import display_values, load_rules, save_rules, rules_path
from core.media_workflow import prepare_catalogue, finalize_catalogue
from test_media_workflow import make_source, make_zip, EAN, OTHER, ROOT

RULES = {'enabled': True, 'model_field': 'name', 'name_template': '{model} — {color}', 'category_template': 'Collection {model}', 'colors': {'BLACK': 'Noir', 'RED': 'Rouge'}, 'models': {}}


class ProductRulesTests(unittest.TestCase):
    def test_composite_colors_and_unknown_colors(self):
        result = display_values({'name': 'DEMO', 'color': 'BLACK/RED'}, RULES)
        self.assertEqual(result['title'], 'Demo — Noir / Rouge')
        self.assertEqual(result['category'], 'Collection Demo')
        with self.assertRaisesRegex(ValueError, 'Couleur non traduite'):
            display_values({'name': 'DEMO', 'color': 'UNKNOWN'}, RULES)

    def test_overrides_survive_reload_and_are_shop_supplier_specific(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.product_rules.settings_path', return_value=Path(folder) / 'shop.json'):
            a = rules_path('supplier-a', 'https://one.example')
            b = rules_path('supplier-b', 'https://one.example')
            c = rules_path('supplier-a', 'https://two.example')
            self.assertEqual(len({a,b,c}),3)
            save_rules(a, {'models': {'DEMO': {'name': 'Modèle choisi', 'category': 'Ma catégorie'}}})
            merged = load_rules({'product_rules': RULES}, a)
            shown = display_values({'name': 'DEMO', 'color': 'BLACK'}, merged)
            self.assertEqual(shown['category'], 'Ma catégorie')
            self.assertEqual(shown['title'], 'Modèle choisi — Noir')

    def test_two_pass_rebuild_keeps_backups_and_raw_image_identifiers(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(folder)
            source = make_source(folder / 'order.xlsx')
            config = ROOT / 'profiles/demo.json'
            session, old = prepare_catalogue(source, config, ROOT / 'schemas/woocommerce.json')
            previous = (folder / old['prepared_csv']).read_bytes()
            rules = folder / 'rules.json'; save_rules(rules, RULES)
            _, new = prepare_catalogue(source, config, ROOT / 'schemas/woocommerce.json', rules_path=rules, rebuild=True)
            backups = list(folder.glob('sauvegarde_preparation_*'))
            self.assertEqual(len(backups),1)
            self.assertEqual((backups[0] / old['prepared_csv']).read_bytes(), previous)
            self.assertEqual(new['image_identifiers'], old['image_identifiers'])
            photos = make_zip(folder / 'photos.zip', ['PHOTO_ITEM100_001_1.jpg', 'PHOTO_ITEM100_058_1.jpg'])
            final = finalize_catalogue(session, photos)
            with (folder / final['final_csv']).open(encoding='utf-8-sig') as stream: rows=list(csv.DictReader(stream))
            self.assertEqual([r['Nom'] for r in rows], ['Demo — Noir','Demo — Rouge'])
            self.assertTrue(all(r['Catégories']=='Collection Demo' and r['Type']=='simple' and r['Images'] for r in rows))
            self.assertEqual([r['UGS'] for r in rows], [EAN,OTHER])

    def test_category_creation_reuses_existing_root_category(self):
        from core.shop_products import ProductAPI
        from core.shop_connection import Credentials
        api=ProductAPI(Credentials('https://shop.example',consumer_key='k',consumer_secret='s'))
        with patch.object(api,'listing',return_value=[{'id':3,'name':'Collection Demo','parent':0}]), patch.object(api,'request') as request:
            self.assertEqual(api.create_category('Collection Demo')['id'],3)
            request.assert_not_called()

    def test_rules_editor_saves_model_group_and_translation(self):
        import tkinter as tk
        from unittest.mock import Mock
        from core.product_rules_ui import ProductRulesDialog
        try: owner=tk.Tk()
        except tk.TclError:self.skipTest('Display unavailable')
        owner.withdraw()
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); source=make_source(folder/'order.xlsx')
            config=json.loads((ROOT/'profiles/demo.json').read_text());config['product_rules']=RULES
            path=folder/'rules.json'; callback=Mock()
            dialog=ProductRulesDialog(owner,config,source,path,callback)
            try:
                table=dialog.tables['models'];first=table.get_children()[0]
                table.selection_set(first);dialog.selected('models')
                dialog.edits['models']['category'].set('Collection choisie');dialog.edit('models')
                dialog.save()
                callback.assert_called_once()
                self.assertEqual(load_rules(config,path)['models']['DEMO']['category'],'Collection choisie')
            finally:
                if dialog.winfo_exists():dialog.destroy()
                owner.destroy()
