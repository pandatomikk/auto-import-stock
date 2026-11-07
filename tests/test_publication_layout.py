"""The final action must remain accessible on a short desktop window."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock
from core.shop_connection import Credentials
from core.shop_products_ui import ProductsDialog

class PublicationLayoutTests(unittest.TestCase):
    def test_import_action_stays_visible_and_runs_existing_pipeline(self):
        try: owner = tk.Tk()
        except tk.TclError: self.skipTest('Display unavailable')
        owner.set_controls = Mock()
        style = ttk.Style(owner)
        style.configure('Primary.TButton', padding=(16,10))
        dialog = ProductsDialog(owner, Credentials('https://shop.example', consumer_key='k', consumer_secret='s'), publication=True)
        try:
            self.assertTrue(dialog.draft.get())
            dialog.geometry('720x420'); dialog.update()
            dialog.events.put(('plan', {'items':[{'state':'new','line':2,'sku':'ABC','name':'Article','payload':{'status':'draft'}}], 'errors':[], 'local_files':{'photo.webp':'hash'}, 'source':'/tmp/articles.csv'}))
            dialog.poll(); dialog.update()
            self.assertEqual(dialog.table.item(dialog.table.get_children()[0], 'values')[-1], 'Créer en brouillon')
            self.assertEqual(dialog.send['text'], 'Importer le lot')
            self.assertEqual(str(dialog.send['state']), 'normal')
            self.assertGreaterEqual(dialog.send.winfo_height(), dialog.send.winfo_reqheight())
            self.assertLessEqual(dialog.send.winfo_rooty()+dialog.send.winfo_height(), dialog.winfo_rooty()+dialog.winfo_height())
            dialog.run = Mock()
            dialog.send.invoke()
            self.assertEqual(dialog.run.call_args.args[0], 'report')
            dialog.update()
            self.assertEqual(str(dialog.import_progress['mode']), 'indeterminate')
            self.assertTrue(dialog.import_progress.winfo_ismapped())
            dialog.events.put(('import_progress', {'done': 3, 'total': 5, 'eta': 2}))
            dialog.poll()
            self.assertEqual(str(dialog.import_progress['mode']), 'determinate')
            self.assertEqual(float(dialog.import_progress['value']), 3)
            dialog.events.put(('error', 'WooCommerce indisponible'))
            dialog.poll(); dialog.update()
            self.assertFalse(dialog.import_progress.winfo_ismapped())
            self.assertEqual(dialog.status.get(), 'WooCommerce indisponible')
        finally:
            dialog.close(); owner.destroy()
