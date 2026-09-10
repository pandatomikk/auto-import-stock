import tempfile,unittest
from pathlib import Path
from PIL import Image
from core.image_webp import optimize_webp
class WebpTest(unittest.TestCase):
 def test_dimensions_alpha_and_original(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'original.png';out=Path(d)/'photo.webp'
   Image.new('RGBA',(3200,2400),(70,20,120,100)).save(p)
   data=p.read_bytes();r=optimize_webp(p,out)
   with Image.open(out) as im:
    self.assertEqual(im.size,(1600,1200));self.assertEqual(im.mode,'RGBA');self.assertEqual(im.getpixel((10,10))[3],100)
   self.assertEqual(p.read_bytes(),data)
 def test_no_upscale(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'small.png';Image.new('RGB',(100,80)).save(p)
   r=optimize_webp(p,Path(d)/'small.webp');self.assertEqual(r['width'],100)
