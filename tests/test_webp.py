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
 def test_trim_light_margins_without_square_padding(self):
  from PIL import ImageDraw
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'photo.png';out=Path(d)/'photo.webp'
   im=Image.new('RGB',(1000,1000),(246,246,246));ImageDraw.Draw(im).rectangle((350,650,650,850),fill=(210,190,160));im.save(p)
   r=optimize_webp(p,out)
   self.assertLess(r['width'],500);self.assertLess(r['height'],400)
   self.assertGreater(r['width'],r['height'])
 def test_coloured_background_is_not_cropped(self):
  from core.image_webp import trim_product_background
  from PIL import ImageDraw
  im=Image.new('RGB',(500,700),(20,80,120));ImageDraw.Draw(im).rectangle((200,300,300,400),fill='white')
  self.assertEqual(trim_product_background(im).size,im.size)
