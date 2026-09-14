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
    def __init__(self, owner, credentials, publication=False):
        self.publication = publication
        self.api = ProductAPI(credentials)
        super().__init__(owner)
        self.owner = owner
        owner.busy = True
        owner.set_controls('disabled')
        self.title('Import CSV · Ajout uniquement')
        self.geometry(f'920x{min(740, max(480, self.winfo_screenheight()-90))}')
        self.minsize(720, 420)
        self.transient(owner)
        self.busy = False
        self.plan = None
        self.events = queue.Queue()
        self.timer = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        footer = ttk.Frame(self, padding=(20, 10, 20, 16))
        footer.pack(side='bottom', fill='x')
        self.status = tk.StringVar(value='Le contrôle du CSV ne modifie pas la boutique.')
        status_label = ttk.Label(footer, textvariable=self.status, wraplength=850)
        status_label.pack(anchor='w', pady=(0, 8))
        footer.bind('<Configure>', lambda event: status_label.configure(wraplength=max(200, event.width-40)))
        self.send = ttk.Button(footer, text='Importer le lot' if publication else 'Créer les nouveaux articles', style='Primary.TButton', state='disabled', command=self.start_import)
        self.send.pack(anchor='w')
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); canvas.pack(fill='both', expand=True)
        box = ttk.Frame(canvas, padding=20)
        window = canvas.create_window((0, 0), window=box, anchor='nw')
        box.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(box, text='Publier un lot sur le site' if publication else 'Créer des articles depuis un CSV', font=('Arial', 16, 'bold')).pack(anchor='w')
        ttk.Label(box, text='Boutique : ' + self.api.url, wraplength=850).pack(anchor='w', pady=8)
        ttk.Label(box, text=('Choisissez le CSV final du lot. Après contrôle, ses images locales seront envoyées puis ses produits publiés. Les UGS existantes seront ignorées.' if publication else 'Produits simples publiés. Les UGS déjà présentes seront ignorées. Les images et les catégories doivent déjà exister sur le site.'), wraplength=850).pack(anchor='w')
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

    def detail(self, text):
        self.details.configure(state='normal'); self.details.delete('1.0', 'end')
        self.details.insert('1.0', text); self.details.configure(state='disabled')

    def choose(self):
        if self.busy:
            return
        from core.lots import lots_directory
        filename = filedialog.askopenfilename(parent=self, initialdir=str(lots_directory()) if self.publication else '', title='Choisir le CSV final du lot', filetypes=[('CSV WooCommerce', '*.csv')])
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
        from core.shop_publication import prepare_publication
        prepare = prepare_publication if self.publication else prepare_csv
        self.run('plan', lambda: prepare(filename, self.api, self.progress, mappings=choices))

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
        from core.shop_publication import publish_plan
        operation = publish_plan if self.publication else import_plan
        self.run('report', lambda: operation(self.plan, self.api, self.report_path, self.progress))

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
                self.status.set(f"{counts['new']} à créer · {counts['existing']} déjà présents · {len(result['errors'])} erreur(s)" + (f" · {len(result.get('local_files', {}))} images locales" if self.publication else ''))
                self.send.configure(text=("Importer le lot" if self.publication else f"Créer et publier les {counts['new']} nouveaux articles"), state='normal' if counts['new'] and not result['errors'] else 'disabled')
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
