import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.profiles import discover_profiles, load_adapter, resolve_profile
from core.enrichment import SupplierDescriptions
from core.media_workflow import load_session


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        setting = patch.dict(os.environ, {'AUTO_IMPORT_PRIVATE_DIR':str(self.root)})
        setting.start()
        self.addCleanup(setting.stop)

    def test_no_private_pack_uses_public_demo(self):
        self.assertEqual([p.stem for p in discover_profiles()], ['demo'])
        self.assertEqual(resolve_profile('demo').name, 'demo.json')

    def test_private_profile_overrides_demo_without_leaking_into_public_folder(self):
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles/custom.json').write_text('{"supplier_name":"Custom"}')
        self.assertEqual([p.stem for p in discover_profiles()], ['custom'])
        self.assertEqual(resolve_profile('custom').parent, self.root / 'profiles')
        with self.assertRaises(ValueError):
            resolve_profile('../custom')

    def test_local_enrichment_adapter_can_import_siblings(self):
        (self.root / 'adapters').mkdir()
        (self.root / 'adapters/helper.py').write_text("TEXT='Local description'\n")
        (self.root / 'adapters/custom.py').write_text('''from .helper import TEXT
class SupplierDescriptions:
    def __init__(self, settings): self.records=[]
    def get(self, values):
        self.records.append({'status':'retrieved'})
        return TEXT
''')
        provider = SupplierDescriptions({'enabled':True, 'adapter':'custom'})
        self.assertEqual(provider.get({}), 'Local description')
        self.assertEqual(provider.records, [{'status':'retrieved'}])
        with self.assertRaises(ValueError):
            load_adapter('../custom')
        with self.assertRaises(ValueError):
            load_adapter('missing')

    def test_legacy_session_loads_its_local_profile_rules(self):
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles/custom.json').write_text(json.dumps({
            'supplier_name':'Custom','workflow':{'kind':'two_pass'},
            'images':{'directory':'images_custom'}}))
        session = self.root / 'legacy_session.json'
        session.write_text(json.dumps(dict(version=1, supplier='custom', status='waiting_images',
            source=str(self.root/'source.csv'), products=1, prepared_csv='prepared.csv',
            ean_text='eans.txt', preparation_report='prepared.json',
            final_csv='final.csv', final_report='final.json')))
        data = load_session(session)
        self.assertEqual(data['workflow'], 'two_pass')
        self.assertEqual(data['image_settings']['directory'], 'images_custom')

    def test_new_input_format_uses_the_common_woocommerce_export(self):
        import csv
        from core.converter import convert_catalogue
        from core.profiles import APP_DIR
        (self.root / 'adapters').mkdir()
        (self.root / 'adapters/feed.py').write_text('''def read_source(path, options):
    return ['code','label','amount'], [{'code':path.read_text().strip(),'label':'Demo','amount':12.5}]
''')
        source = self.root / 'catalogue.feed'
        source.write_text('ITEM100')
        config = self.root / 'custom.json'
        config.write_text(json.dumps(dict(source_options={'adapter':'feed'}, mapping_only=True,
            force_mapping={'sku':'code','name':'label','regular_price':'amount'})))
        result = convert_catalogue(source, config, APP_DIR / 'schemas/woocommerce.json')
        with result.output_path.open(encoding='utf-8-sig') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['UGS'], 'ITEM100')
        self.assertEqual(row['Tarif régulier'], '12.5')
        self.assertEqual(row['Publié'], '1')
