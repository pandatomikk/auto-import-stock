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
