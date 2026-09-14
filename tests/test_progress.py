import unittest
from core.progress import ImageProgress
class ProgressTest(unittest.TestCase):
 def test_cached_does_not_set_rate(self):
  p=ImageProgress(5,2)
  self.assertIsNone(p.update({'status':'existing','duration':0.01})['eta'])
  r=p.update({'status':'downloaded','duration':10})
  self.assertEqual(r['eta'],15)
  self.assertEqual(r['existing'],1)
  p.update({'status':'failed'});p.update({'status':'existing'})
  self.assertEqual(p.update({'status':'downloaded','duration':10})['eta'],0)

class ConversionProgressTests(unittest.TestCase):
 def test_first_image_then_average_every_ten_and_remaining_count(self):
  from core.progress import ConversionProgress
  p=ConversionProgress(25)
  self.assertIsNone(p.snapshot()['eta'])
  self.assertEqual(p.update(2)['eta'],48)
  for _ in range(8):p.update(4)
  self.assertEqual(p.snapshot()['eta'],32)
  self.assertEqual(p.update(4)['eta'],57)
  for _ in range(15):p.update(3)
  self.assertEqual(p.snapshot()['eta'],0)
 def test_cached_images_do_not_distort_conversion_sample(self):
  from core.progress import ConversionProgress
  p=ConversionProgress(12)
  self.assertIsNone(p.update(.001,cached=True)['eta'])
  self.assertEqual(p.update(5)['eta'],50)
  for _ in range(8):p.update(.001,cached=True)
  self.assertEqual(p.snapshot()['eta'],10)
  p.update(.001,cached=True)
  self.assertEqual(p.update(.001,cached=True)['eta'],0)
 def test_eta_text_handles_seconds_minutes_hours_and_unknown(self):
  from core.progress import format_image_eta
  self.assertIn('première conversion',format_image_eta(None))
  self.assertIn('2 s',format_image_eta(1.1))
  self.assertIn('2 min 05 s',format_image_eta(125))
  self.assertIn('2 h 03 min',format_image_eta(7380))
  self.assertIn('terminée',format_image_eta(0))
