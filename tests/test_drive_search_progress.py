import unittest
from core.progress import DriveSearchProgress, format_drive_eta

class DriveSearchProgressTests(unittest.TestCase):
    def test_first_match_then_ten_additional_unique_products(self):
        now = [0]
        tracker = DriveSearchProgress(20, clock=lambda: now[0])
        self.assertIsNone(tracker.update([])['eta'])
        now[0] = 10
        self.assertEqual(tracker.update(['a'])['eta'], 190)
        now[0] = 30
        self.assertEqual(tracker.update(['a'])['eta'], 190)
        # Other sources may return the same references; never count them again.
        self.assertEqual(tracker.update([str(i) for i in range(9)])['eta'], 100)
        now[0] = 44
        result = tracker.update(['new'])
        self.assertEqual(result['done'], 11)
        self.assertEqual(result['eta'], 36)

    def test_missing_references_and_all_found_are_not_completion(self):
        tracker = DriveSearchProgress(2, clock=lambda: 10)
        event = tracker.update(['a', 'b'])
        self.assertFalse(event['finished'])
        self.assertIn('vérification', format_drive_eta(event))
        tracker = DriveSearchProgress(2)
        tracker.update(['a'])
        self.assertIn('1 produit(s)', format_drive_eta(tracker.snapshot(finished=True)))
