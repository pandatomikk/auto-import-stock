"""Editable review of source labels against existing shop taxonomies."""
import tkinter as tk
import threading
import queue
from tkinter import ttk, simpledialog
from core.shop_connection import ConnectionFailure
from core.shop_mappings import KINDS, source_key, save_mappings


class MappingsDialog(tk.Toplevel):
    def __init__(self, owner, review, callback):
        super().__init__(owner)
        self.owner = owner
        self.review = review
        self.callback = callback
        self.creating = False
        self.category_events = queue.Queue()
        self.category_timer = None
        self.title('Correspondances avec la boutique')
        self.geometry(f'960x{min(740, max(500, self.winfo_screenheight()-90))}')
        self.minsize(780, 480)
        self.transient(owner)
        owner.busy = True
        owner.select.configure(state='disabled')
        owner.mapping_button.configure(state='disabled')
        self.protocol('WM_DELETE_WINDOW', self.close)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); canvas.pack(fill='both', expand=True)
        box = ttk.Frame(canvas, padding=20)
        window = canvas.create_window((0, 0), window=box, anchor='nw')
        box.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(box, text='Marques et catégories : choisissez les destinations', font=('Arial', 14, 'bold')).pack(anchor='w')
        ttk.Label(box, text=review['site'], wraplength=860).pack(anchor='w', pady=8)
        ttk.Label(box, text='Sélectionnez une ligne pour corriger sa destination. Les suggestions seront appliquées uniquement après votre validation. Aucun nom ne sera modifié dans la boutique ou dans le CSV.', wraplength=860).pack(anchor='w')
        frame = ttk.Frame(box); frame.pack(fill='both', expand=True, pady=10)
        self.table = ttk.Treeview(frame, columns=('kind', 'source', 'target', 'state'), show='headings', selectmode='browse', height=7)
        for key, label, width in [('kind', 'Type', 90), ('source', 'Dans le CSV', 200), ('target', 'Dans la boutique', 330), ('state', 'Détection', 200)]:
            self.table.heading(key, text=label); self.table.column(key, width=width)
        scroll = ttk.Scrollbar(frame, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set); scroll.pack(side='right', fill='y'); self.table.pack(fill='both', expand=True)
        for index, row in enumerate(review['rows']):
            self.table.insert('', 'end', iid=str(index), values=self.row_values(row))
        self.table.bind('<<TreeviewSelect>>', self.selected)
        destinations = ttk.Frame(box); destinations.pack(fill='x')
        destinations.columnconfigure(0, weight=1); destinations.columnconfigure(1, weight=1)
        self.group_label = ttk.Label(destinations, text='Marque / catégorie principale')
        self.group_label.grid(row=0, column=0, sticky='w')
        ttk.Label(destinations, text='Catégorie de destination').grid(row=0, column=1, sticky='w', padx=(12, 0))
        self.group = ttk.Combobox(destinations, state='readonly')
        self.group.grid(row=1, column=0, sticky='ew', pady=8)
        self.group.bind('<<ComboboxSelected>>', self.group_changed)
        self.choice = ttk.Combobox(destinations, state='readonly')
        self.choice.grid(row=1, column=1, sticky='ew', padx=(12, 0), pady=8)
        self.choice.bind('<<ComboboxSelected>>', self.changed)
        self.create_button = ttk.Button(box, text='Nouvelle catégorie…', command=self.create_category)
        self.create_button.pack(anchor='w', pady=(0, 6))
        self.status = tk.StringVar(value='Les choix mémorisés seront proposés pour les prochains CSV de cette boutique.')
        ttk.Label(box, textvariable=self.status, wraplength=860).pack(anchor='w', pady=8)
        self.apply_button = ttk.Button(box, text='Mémoriser et valider ces correspondances', command=self.apply)
        self.apply_button.pack(anchor='w')
        if review['rows']:
            self.table.selection_set('0'); self.selected()

    def row_values(self, row):
        return (KINDS[row['kind']], row['source'], self.review['options'][row['kind']].get(row['id'], '— À choisir —'), row['state'])

    def parents(self):
        # Older callers may provide only breadcrumbs; normal API reviews carry IDs.
        if 'category_parents' in self.review:
            return self.review['category_parents']
        options = self.review['options'].get('categories', {})
        return {key: next((id_ for id_, text in options.items() if text == label.rsplit(' > ', 1)[0]), 0)
                if ' > ' in label else 0 for key, label in options.items()}

    def root_of(self, id_):
        parents = self.parents()
        seen = set()
        while parents.get(id_):
            if id_ in seen:
                return None
            seen.add(id_); id_ = parents[id_]
        return id_

    def selected(self, event=None):
        selection = self.table.selection()
        if not selection:
            return
        row = self.review['rows'][int(selection[0])]
        options = self.review['options'][row['kind']]
        self.create_button.configure(state='normal' if row['kind']=='categories' and not self.creating else 'disabled')
        if row['kind'] == 'brands':
            self.group_label.configure(text='Marque WooCommerce')
            self.group_ids = [None] + sorted(options, key=lambda key: (options[key].casefold(), key))
            self.group.configure(values=['— Choisir une marque —'] + [f'{options[key]} [#{key}]' for key in self.group_ids[1:]], state='readonly')
            self.group.current(self.group_ids.index(row['id']) if row['id'] in self.group_ids else 0)
            self.choice.set('Sélectionnez une ligne Catégories pour la modifier')
            self.choice.configure(state='disabled')
            return
        self.group_label.configure(text='Marque / catégorie principale')
        roots = [key for key in options if not self.parents().get(key)]
        self.group_ids = [None] + sorted(roots, key=lambda key: (options[key].casefold(), key))
        self.group.configure(values=['— Toutes les catégories —'] + [f'{options[key]} [#{key}]' for key in self.group_ids[1:]], state='readonly')
        root = self.root_of(row['id'])
        self.group.current(self.group_ids.index(root) if root in self.group_ids else 0)
        self.fill_categories(row['id'])

    def fill_categories(self, selected=None):
        options = self.review['options'].get('categories', {})
        root = self.group_ids[self.group.current()]
        keys = [key for key in options if root is None or self.root_of(key) == root]
        self.option_ids = [None] + sorted(keys, key=lambda key: (options[key].casefold(), key))
        self.choice.configure(values=['— Choisir une catégorie —'] + [f'{options[key]} [#{key}]' for key in self.option_ids[1:]], state='readonly')
        self.choice.current(self.option_ids.index(selected) if selected in self.option_ids else 0)

    def group_changed(self, event=None):
        selection = self.table.selection()
        if not selection:
            return
        row = self.review['rows'][int(selection[0])]
        if row['kind'] == 'brands':
            row['id'] = self.group_ids[self.group.current()]
            row['state'] = 'Choisi' if row['id'] is not None else 'À choisir'
            self.table.item(selection[0], values=self.row_values(row))
        else:
            self.fill_categories(row['id'])
            self.changed()

    def changed(self, event=None):
        selection = self.table.selection()
        if not selection:
            return
        row = self.review['rows'][int(selection[0])]
        row['id'] = self.option_ids[self.choice.current()]
        row['state'] = 'Choisi' if row['id'] is not None else 'À choisir'
        self.table.item(selection[0], values=self.row_values(row))

    def apply(self):
        if self.creating:return
        choices = {}
        for row in self.review['rows']:
            if row['id'] not in self.review['options'][row['kind']]:
                self.status.set('Choisissez une destination pour chaque ligne. Si elle n’existe pas, créez-la dans la boutique puis rechargez les correspondances.'); return
            entries = choices.setdefault(row['kind'], {})
            key = source_key(row['source'])
            if key in entries and entries[key] != row['id']:
                self.status.set('Deux variantes du même libellé ont des destinations différentes. Harmonisez les choix.'); return
            entries[key] = row['id']
        try:
            save_mappings(self.review['site'], choices)
        except (OSError, ConnectionFailure):
            self.status.set('Impossible de mémoriser les correspondances. Vérifiez le dossier de configuration.'); return
        self.close()
        self.callback(choices)

    def create_category(self):
        if self.creating or not self.table.selection():return
        index = int(self.table.selection()[0])
        if self.review['rows'][index]['kind'] != 'categories':return
        parent = self.group_ids[self.group.current()] or 0
        label = self.review['options']['categories'].get(parent, 'Racine de la boutique')
        name = simpledialog.askstring('Nouvelle catégorie', 'Créer une catégorie dans : ' + label + '\nNom de la nouvelle catégorie :', parent=self)
        if not name or not name.strip():return
        name = name.strip()
        self.creating = True
        self.create_button.configure(state='disabled');self.apply_button.configure(state='disabled')
        self.status.set('Création de la catégorie sur la boutique…')
        def worker():
            try:self.category_events.put((index, self.owner.api.create_category(name, parent=parent), None))
            except ConnectionFailure as exc:self.category_events.put((index, None, str(exc)))
            except Exception:self.category_events.put((index, None, 'Création non confirmée. Rechargez les correspondances avant de réessayer.'))
        threading.Thread(target=worker,daemon=True).start()
        self.category_timer = self.after(100,self.poll_category)

    def poll_category(self):
        self.category_timer=None
        try:index,result,error=self.category_events.get_nowait()
        except queue.Empty:
            self.category_timer=self.after(100,self.poll_category);return
        self.creating=False
        self.apply_button.configure(state='normal')
        if error:self.status.set(error)
        else:
            parents = dict(self.parents())
            parent = result.get('parent', 0)
            parents[result['id']] = parent
            self.review['category_parents'] = parents
            prefix = self.review['options']['categories'].get(parent, '')
            import html
            self.review['options']['categories'][result['id']] = (prefix + ' > ' if prefix else '') + html.unescape(result['name'])
            row=self.review['rows'][index];row.update(id=result['id'],state='Catégorie disponible')
            self.table.item(str(index),values=self.row_values(row))
            self.status.set('Catégorie prête. Validez les correspondances pour continuer.')
        self.selected()

    def close(self):
        if self.creating:
            self.status.set('Attendez le résultat de la création avant de fermer.');return
        self.owner.busy = False
        self.owner.select.configure(state='normal')
        self.owner.mapping_button.configure(state='normal')
        self.destroy()
