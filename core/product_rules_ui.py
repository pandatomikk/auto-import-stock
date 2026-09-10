"""Edit product naming, model categories and colour translations locally."""
from collections import Counter
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from core.product_rules import load_rules, save_rules, rule_key, display_values, logical_values
from core.io import read_source
from core.matcher import detect_mapping


class ProductRulesDialog(tk.Toplevel):
    def __init__(self, owner, config, source, path, saved):
        super().__init__(owner)
        self.title('Règles produits · Modèles et couleurs')
        self.geometry('920x680'); self.transient(owner); self.grab_set()
        self.rules = load_rules(config, path)
        self.path = path; self.saved = saved
        self.config = config; self.source = source
        self.enabled = tk.BooleanVar(value=self.rules.get('enabled', False))
        box = ttk.Frame(self, padding=20); box.pack(fill='both', expand=True)
        ttk.Label(box, text='Règles de présentation — ' + config.get('supplier_name', ''), font=('Arial', 15, 'bold')).pack(anchor='w')
        ttk.Label(box, text='Une fiche simple par couleur. Les références et EAN restent inchangés.', wraplength=860).pack(anchor='w', pady=6)
        ttk.Checkbutton(box, text='Appliquer ces règles à la préparation', variable=self.enabled).pack(anchor='w')
        fields = ttk.Frame(box); fields.pack(fill='x', pady=8)
        self.model_field = tk.StringVar(value=self.rules.get('model_field', 'name'))
        self.name_template = tk.StringVar(value=self.rules.get('name_template', '{model} — {color}'))
        self.category_template = tk.StringVar(value=self.rules.get('category_template', '{model}'))
        for row, (label, variable) in enumerate([('Champ du modèle (name ou model)', self.model_field), ('Format du nom', self.name_template), ('Catégorie proposée', self.category_template)]):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky='w', padx=8)
            ttk.Entry(fields, textvariable=variable, width=55).grid(row=row, column=1, sticky='ew')
        ttk.Label(box, text='Nom : {model}, {model_upper}, {color}, {color_compact}, {color_compact_initial_lower}. Catégorie : {model}. Rechargez les groupes après changement du champ modèle.', wraplength=860).pack(anchor='w')
        ttk.Button(box, text='Charger les modèles et couleurs du document', command=self.populate).pack(anchor='w', pady=8)
        notebook = ttk.Notebook(box); notebook.pack(fill='both', expand=True)
        self.tables = {}; self.edits = {}
        for kind, title, columns in [('models', 'Catégories par modèle', ('source', 'name', 'category')), ('colors', 'Traductions des couleurs', ('source', 'color'))]:
            frame = ttk.Frame(notebook, padding=8); notebook.add(frame, text=title)
            treebox = ttk.Frame(frame); treebox.pack(fill='both', expand=True)
            table = ttk.Treeview(treebox, columns=columns, show='headings', selectmode='browse', height=8)
            labels = {'source': 'Dans le fournisseur', 'name': 'Modèle affiché', 'category': 'Catégorie du groupe', 'color': 'Couleur en français'}
            for column in columns:
                table.heading(column, text=labels[column]); table.column(column, width=230)
            scroll = ttk.Scrollbar(treebox, command=table.yview); table.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y'); table.pack(fill='both', expand=True)
            self.tables[kind] = table; self.edits[kind] = {}
            line = ttk.Frame(frame); line.pack(fill='x', pady=8)
            for column in columns[1:]:
                value = tk.StringVar(); self.edits[kind][column] = value
                ttk.Label(line, text=labels[column]).pack(side='left')
                ttk.Entry(line, textvariable=value, width=24).pack(side='left', padx=5)
            ttk.Button(frame, text='Appliquer à la sélection', command=lambda k=kind: self.edit(k)).pack(anchor='w')
            table.bind('<<TreeviewSelect>>', lambda event, k=kind: self.selected(k))
        self.status = tk.StringVar(value='Choix enregistrés pour ce fournisseur et la boutique configurée. Les destinations WooCommerce seront choisies lors de l’import.')
        ttk.Label(box, textvariable=self.status, wraplength=860).pack(anchor='w', pady=8)
        ttk.Button(box, text='Enregistrer les règles', command=self.save).pack(anchor='w')
        self.populate()

    def templates(self):
        self.rules.update(enabled=self.enabled.get(), model_field=self.model_field.get().strip(), name_template=self.name_template.get(), category_template=self.category_template.get())
        self.rules['name_template'].format(model='Modèle', model_upper='MODÈLE', color='Couleur', color_compact='Couleur', color_compact_initial_lower='couleur')
        self.rules['category_template'].format(model='Modèle')

    def populate(self):
        try:
            self.templates()
            headers, rows = read_source(Path(self.source), self.config.get('source_options'))
            if {'UGS', 'Nom', 'Publié', 'Type'}.issubset(headers):
                raise ValueError('Choisissez le document fournisseur original pour charger les modèles.')
            mapping, _ = detect_mapping(headers, self.config)
            if self.rules['model_field'] not in mapping:
                raise ValueError('Champ modèle non reconnu dans ce document.')
            values = [logical_values(row, mapping) for row in rows]
            models = sorted({v.get(self.rules['model_field'], '') for v in values} - {''})
            colors = sorted({v.get('color', '') for v in values} - {''})
            for table in self.tables.values(): table.delete(*table.get_children())
            for model in models:
                shown = display_values({self.rules['model_field']: model}, self.rules)
                self.tables['models'].insert('', 'end', values=(model, shown['model'], shown['category']))
            unknown = 0
            for color in colors:
                from core.color_translations import translate_color
                translated = translate_color(color, self.rules['colors']) or ''
                if not translated: unknown += 1
                self.tables['colors'].insert('', 'end', values=(color, translated))
            self.status.set(f'{len(models)} modèles · {len(colors)} couleurs · {unknown} traduction(s) à compléter.')
        except (OSError, ValueError, KeyError) as exc:
            self.status.set(str(exc))

    def selected(self, kind):
        selected = self.tables[kind].selection()
        if not selected: return
        values = self.tables[kind].item(selected[0], 'values')
        for variable, value in zip(self.edits[kind].values(), values[1:]): variable.set(value)

    def edit(self, kind):
        selected = self.tables[kind].selection()
        if not selected: return
        source = self.tables[kind].item(selected[0], 'values')[0]
        edited = {name: variable.get().strip() for name, variable in self.edits[kind].items()}
        self.tables[kind].item(selected[0], values=(source, *edited.values()))
        self.rules[kind][rule_key(source)] = edited if kind == 'models' else edited['color']

    def save(self):
        try:
            for kind in self.tables: self.edit(kind)
            self.templates()
            if self.enabled.get() and any(not self.tables['colors'].item(item, 'values')[1] for item in self.tables['colors'].get_children()):
                raise ValueError('Complétez les couleurs inconnues avant d’enregistrer les règles actives.')
            save_rules(self.path, self.rules)
        except (OSError, ValueError, KeyError) as exc:
            self.status.set(str(exc)); return
        self.saved(); self.destroy()
