import tempfile,unittest,zipfile
from pathlib import Path
from PIL import Image
from core.images import prepare_local_zip_images,images_for_sku
from core.converter import build_zip_image_context
class LocalZipTest(unittest.TestCase):
 def test_local_names_and_reuse(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);im=root/'a.png';Image.new('RGBA',(20,30),(20,30,40,100)).save(im)
   z=root/'images.zip'
   with zipfile.ZipFile(z,'w') as f:f.write(im,'dossier/123-01.png')
   ctx=build_zip_image_context({'images':{'mode':'zip_by_sku','output_mode':'local'}},z,None)
   names=images_for_sku(ctx['index'],'123',ctx['base_url'])
   out=prepare_local_zip_images(z,names,root,'Example','Sac bleu')
   target=root/'images_example'/'fichiers_webp'/out[0]
   self.assertTrue(target.exists());self.assertTrue(out[0].endswith('.webp'))
   before=target.stat().st_mtime_ns
   self.assertEqual(prepare_local_zip_images(z,names,root,'Example','Sac bleu'),out)
   self.assertEqual(before,target.stat().st_mtime_ns)
