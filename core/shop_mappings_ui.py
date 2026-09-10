"""Editable review of source labels against existing shop taxonomies."""
import tkinter as tk
import threading
import queue
from tkinter import ttk
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
        self.geometry('920x580')
        self.transient(owner)
        owner.busy = True
        owner.select.configure(state='disabled')
        owner.mapping_button.configure(state='disabled')
        self.protocol('WM_DELETE_WINDOW', self.close)
        box = ttk.Frame(self, padding=20); box.pack(fill='both', expand=True)
        ttk.Label(box, text='Marques et catégories : choisissez les destinations', font=('Arial', 14, 'bold')).pack(anchor='w')
        ttk.Label(box, text=review['site'], wraplength=860).pack(anchor='w', pady=8)
        ttk.Label(box, text='Sélectionnez une ligne pour corriger sa destination. Les suggestions seront appliquées uniquement après votre validation. Aucun nom ne sera modifié dans la boutique ou dans le CSV.', wraplength=860).pack(anchor='w')
        frame = ttk.Frame(box); frame.pack(fill='both', expand=True, pady=10)
        self.table = ttk.Treeview(frame, columns=('kind', 'source', 'target', 'state'), show='headings', selectmode='browse')
        for key, label, width in [('kind', 'Type', 90), ('source', 'Dans le CSV', 200), ('target', 'Dans la boutique', 330), ('state', 'Détection', 200)]:
            self.table.heading(key, text=label); self.table.column(key, width=width)
        scroll = ttk.Scrollbar(frame, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set); scroll.pack(side='right', fill='y'); self.table.pack(fill='both', expand=True)
        for index, row in enumerate(review['rows']):
            self.table.insert('', 'end', iid=str(index), values=self.row_values(row))
        self.table.bind('<<TreeviewSelect>>', self.selected)
        ttk.Label(box, text='Destination de la ligne sélectionnée :').pack(anchor='w')
        self.choice = ttk.Combobox(box, state='readonly')
        self.choice.pack(fill='x', pady=8)
        self.choice.bind('<<ComboboxSelected>>', self.changed)
        self.status = tk.StringVar(value='Les choix mémorisés seront proposés pour les prochains CSV de cette boutique.')
        ttk.Label(box, textvariable=self.status, wraplength=860).pack(anchor='w', pady=8)
        self.apply_button = ttk.Button(box, text='Mémoriser et valider ces correspondances', command=self.apply)
        self.apply_button.pack(anchor='w')
        create_box = ttk.Frame(box); create_box.pack(fill='x', pady=8)
        self.category_name = tk.StringVar()
        ttk.Entry(create_box, textvariable=self.category_name, width=45).pack(side='left')
        self.create_button = ttk.Button(create_box, text='Créer cette catégorie sur la boutique', command=self.create_category)
        self.create_button.pack(side='left', padx=8)
        if review['rows']:
            self.table.selection_set('0'); self.selected()

    def row_values(self, row):
        return (KINDS[row['kind']], row['source'], self.review['options'][row['kind']].get(row['id'], '— À choisir —'), row['state'])

    def selected(self, event=None):
        selection = self.table.selection()
        if not selection:
            return
        row = self.review['rows'][int(selection[0])]
        self.category_name.set(row['source'])
        self.create_button.configure(state='normal' if row['kind']=='categories' and not self.creating else 'disabled')
        options = self.review['options'][row['kind']]
        self.option_ids = [None] + sorted(options, key=lambda key: (options[key].casefold(), key))
        self.choice.configure(values=['— Choisir une destination —'] + [f'{options[key]} [#{key}]' for key in self.option_ids[1:]])
        self.choice.current(self.option_ids.index(row['id']) if row['id'] in self.option_ids else 0)

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
        name = self.category_name.get().strip()
        if not name:return
        self.creating = True
        self.create_button.configure(state='disabled');self.apply_button.configure(state='disabled')
        self.status.set('Création de la catégorie sur la boutique…')
        def worker():
            try:self.category_events.put((index, self.owner.api.create_category(name), None))
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
            self.review['options']['categories'][result['id']]=result['name']
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
