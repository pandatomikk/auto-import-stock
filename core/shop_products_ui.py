"""Review an immutable CSV import plan, then explicitly create products."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
from core import file_picker as filedialog
import uuid
from core.shop_connection import ConnectionFailure
from core.shop_products import ProductAPI, prepare_csv, import_plan


class ProductsDialog(tk.Toplevel):
    def __init__(self, owner, credentials):
        self.api = ProductAPI(credentials)
        super().__init__(owner)
        self.owner = owner
        owner.busy = True
        owner.set_controls('disabled')
        self.title('Import CSV · Ajout uniquement')
        self.geometry('900x680')
        self.transient(owner)
        self.busy = False
        self.plan = None
        self.events = queue.Queue()
        self.timer = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        box = ttk.Frame(self, padding=20)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text='Créer des articles depuis un CSV', font=('Arial', 16, 'bold')).pack(anchor='w')
        ttk.Label(box, text='Boutique : ' + self.api.url, wraplength=850).pack(anchor='w', pady=8)
        ttk.Label(box, text='Produits simples publiés. Les UGS déjà présentes seront ignorées. Les images et les catégories doivent déjà exister sur le site.', wraplength=850).pack(anchor='w')
        self.select = ttk.Button(box, text='Choisir et contrôler un CSV…', command=self.choose)
        self.select.pack(anchor='w', pady=12)
        self.mapping_button = ttk.Button(box, text='Revoir les correspondances…', command=self.review_mappings, state='disabled')
        self.mapping_button.pack(anchor='w', pady=(0, 8))
        self.source = tk.StringVar(value='Aucun CSV sélectionné')
        ttk.Label(box, textvariable=self.source, wraplength=850).pack(anchor='w')
        table_box = ttk.Frame(box)
        table_box.pack(fill='both', expand=True, pady=10)
        self.table = ttk.Treeview(table_box, columns=('line', 'sku', 'name', 'action'), show='headings', height=9)
        for name, title, width in [('line', 'Ligne', 60), ('sku', 'UGS', 160), ('name', 'Nom', 380), ('action', 'Action', 150)]:
            self.table.heading(name, text=title); self.table.column(name, width=width)
        scroll = ttk.Scrollbar(table_box, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.table.pack(fill='both', expand=True)
        self.details = tk.Text(box, height=6, wrap='word', state='disabled')
        self.details.pack(fill='x')
        self.status = tk.StringVar(value='Le contrôle du CSV ne modifie pas la boutique.')
        ttk.Label(box, textvariable=self.status, wraplength=850).pack(anchor='w', pady=8)
        self.send = ttk.Button(box, text='Créer les nouveaux articles', state='disabled', command=self.start_import)
        self.send.pack(anchor='w')

    def detail(self, text):
        self.details.configure(state='normal'); self.details.delete('1.0', 'end')
        self.details.insert('1.0', text); self.details.configure(state='disabled')

    def choose(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(parent=self, title='CSV WooCommerce à ajouter', filetypes=[('CSV WooCommerce', '*.csv')])
        if not filename:
            return
        self.plan = None
        self.send.configure(state='disabled')
        self.source.set(filename)
        self.table.delete(*self.table.get_children())
        self.detail('')
        self.review_mappings()

    def review_mappings(self):
        if self.busy:
            return
        from core.shop_mappings import prepare_mappings
        self.plan = None
        self.table.delete(*self.table.get_children())
        filename = self.source.get()
        self.run('mappings', lambda: prepare_mappings(filename, self.api, self.progress))

    def apply_mappings(self, choices):
        filename = self.source.get()
        self.run('plan', lambda: prepare_csv(filename, self.api, self.progress, mappings=choices))

    def progress(self, text):
        self.events.put(('progress', text))

    def run(self, kind, operation):
        self.busy = True
        self.select.configure(state='disabled'); self.send.configure(state='disabled'); self.mapping_button.configure(state='disabled')
        def worker():
            try:
                self.events.put((kind, operation()))
            except ConnectionFailure as exc:
                self.events.put(('error', str(exc)))
            except OSError:
                self.events.put(('error', 'Fichier ou rapport inaccessible. Si un envoi était en cours, vérifiez le rapport et la boutique avant de relancer.'))
            except Exception:
                self.events.put(('error', 'Opération interrompue. Si un envoi était en cours, vérifiez le rapport et la boutique avant de relancer.'))
        threading.Thread(target=worker, daemon=True).start()
        self.timer = self.after(100, self.poll)

    def start_import(self):
        if self.busy or not self.plan or self.plan['errors']:
            return
        filename = 'rapport_import_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8] + '.json'
        self.report_path = Path(self.plan['source']).parent / filename
        self.detail('Rapport : ' + str(self.report_path))
        self.run('report', lambda: import_plan(self.plan, self.api, self.report_path, self.progress))

    def poll(self):
        self.timer = None
        while True:
            try:
                kind, result = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                self.status.set(result)
                continue
            self.busy = False
            self.select.configure(state='normal'); self.mapping_button.configure(state='normal')
            if kind == 'mappings':
                if result['rows']:
                    from core.shop_mappings_ui import MappingsDialog
                    self.mappings_dialog = MappingsDialog(self, result, self.apply_mappings)
                else:
                    self.apply_mappings({})
            elif kind == 'plan':
                self.plan = result
                counts = Counter(item['state'] for item in result['items'])
                for item in result['items']:
                    self.table.insert('', 'end', values=(item['line'], item['sku'], item['name'], 'Créer' if item['state'] == 'new' else 'Ignorer : existe'))
                self.detail('\n'.join(result['errors'] + result.get('warnings', [])) or 'Contrôle terminé. Les données contrôlées seront utilisées telles quelles pour cet envoi.')
                self.status.set(f"{counts['new']} à créer · {counts['existing']} déjà présents · {len(result['errors'])} erreur(s)")
                self.send.configure(text=f"Créer et publier les {counts['new']} nouveaux articles", state='normal' if counts['new'] and not result['errors'] else 'disabled')
            elif kind == 'report':
                counts = Counter(item['state'] for item in result['results'])
                self.status.set(f"{counts['created']} créé(s) · {counts['skipped']} ignoré(s) · {counts['rejected']} refusé(s) · {counts['unconfirmed']} non confirmé(s) · {result['total'] - len(result['results'])} non traité(s)." + (' Envoi arrêté : vérifiez la boutique.' if counts['unconfirmed'] or counts['rejected'] else ''))
                messages = [r['message'] for r in result['results'] if r.get('message')]
                self.detail('Rapport : ' + str(self.report_path) + '\n' + '\n'.join(messages))
                self.plan = None
            else:
                self.status.set(result)
                self.plan = None
        if self.busy and self.timer is None and not (getattr(self, 'mappings_dialog', None) and self.mappings_dialog.winfo_exists()):
            self.timer = self.after(100, self.poll)

    def close(self):
        if self.busy:
            self.status.set('Opération en cours. Attendez le résultat avant de fermer.'); return
        self.destroy()

    def destroy(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
        self.owner.busy = False
        self.owner.set_controls('normal')
        super().destroy()
