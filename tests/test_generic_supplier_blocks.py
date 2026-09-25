import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from core.io import compose_columns
from core.image_archive import ImageArchive
from core.media_workflow import select_zip_images

class GenericSupplierBlocksTest(unittest.TestCase):
    def test_composition_preserves_leading_zeros_and_source(self):
        row={'Model':'ABC','Part':'00123'}
        h,r=compose_columns(list(row),[row],{'composed_columns':[{'name':'Photo','columns':['Model','Part'],'separator':'_'}]})
        self.assertEqual(r[0]['Photo'],'ABC_00123')
        self.assertNotIn('Photo',row)
        with self.assertRaises(ValueError):
            compose_columns(list(row),[row],{'composed_columns':[{'name':'Model','columns':['Part']}]})
        with self.assertRaises(ValueError):
            compose_columns(['Model'],[{'Model':''}],{'composed_columns':[{'name':'Photo','columns':['Model']}]})

    def test_nested_images_are_read_and_matched_without_extraction(self):
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w') as z:z.writestr('folder/ABC_00123_RED_1.jpg',b'image')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'outer.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('inside.zip',inner.getvalue())
            with ImageArchive(path,nested=True) as z:
                selected,_=select_zip_images(z,{'sku'},[{'ean':'sku','article':'ABC_00123','color_code':'RED','color':'Red'}],{'filename_pattern':r'(?P<article>ABC_\d+)_(?P<color>[A-Z]+)_(?P<order>\d+)'})
                self.assertEqual(len(selected['sku']),1)
                with z.open(selected['sku'][0]) as f:self.assertEqual(f.read(),b'image')
            with ImageArchive(path) as z:self.assertEqual(z.infolist()[0].filename,'inside.zip')
            with self.assertRaises(ValueError):ImageArchive(path,nested=True,max_depth=0)
            with self.assertRaises(ValueError):ImageArchive(path,nested=True,max_bytes=2)
            with zipfile.ZipFile(path,'w') as z:z.writestr('../escape.jpg',b'image')
            with self.assertRaises(ValueError):ImageArchive(path,nested=True)

    def test_nested_duplicates_require_identical_content(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'outer.zip'
            for second in (b'image',b'other'):
                with zipfile.ZipFile(path,'w') as outer:
                    for name,content in [('first.zip',b'image'),('second.zip',second)]:
                        data=io.BytesIO()
                        with zipfile.ZipFile(data,'w') as inner:inner.writestr('photo.jpg',content)
                        outer.writestr(name,data.getvalue())
                if second == b'image':
                    with ImageArchive(path,nested=True) as archive:
                        self.assertEqual(len(archive.infolist()),1)
                else:
                    with self.assertRaisesRegex(ValueError,'contenus différents'):
                        ImageArchive(path,nested=True)
