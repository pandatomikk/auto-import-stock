"""Connection dialog; workers communicate with Tk only through a queue."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from core import file_picker as filedialog
from core.shop_connection import Credentials, ConnectionFailure, check_connection, load_settings, save_settings, VaultError


class ShopDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Ma boutique · V0.20')
        self.geometry(f'780x{min(820, max(500, self.winfo_screenheight()-100))}')
        self.transient(parent)
        self.parent = parent
        self.events = queue.Queue()
        self.timer = None
        self.busy = False
        self.protocol('WM_DELETE_WINDOW', self.close)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); canvas.pack(fill='both', expand=True)
        box = ttk.Frame(canvas, padding=24)
        window = canvas.create_window((0, 0), window=box, anchor='nw')
        box.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Connexion WordPress et WooCommerce', font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 16))
        storage_error = ''
        try:
            credentials = getattr(parent, 'shop_credentials', None) or load_settings()
        except (VaultError, OSError) as exc:
            credentials = Credentials()
            storage_error = str(exc) if isinstance(exc, VaultError) else 'Configuration locale inaccessible.'
        self.values = {}
        self.entries = []
        fields = [('url', 'Adresse HTTPS de la boutique'), ('username', 'Identifiant WordPress'), ('application_password', 'Mot de passe d’application WordPress'), ('consumer_key', 'Clé client WooCommerce'), ('consumer_secret', 'Secret client WooCommerce')]
        for row, (name, label) in enumerate(fields, 1):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=6)
            value = tk.StringVar(value=getattr(credentials, name))
            self.values[name] = value
            entry = ttk.Entry(box, textvariable=value, show='•' if name in ('application_password', 'consumer_key', 'consumer_secret') else '')
            entry.grid(row=row, column=1, sticky='ew')
            self.entries.append(entry)
        instructions = 'WordPress : Utilisateurs → Profil → Mots de passe d’application.\nWooCommerce : Réglages → Avancé → API REST → Ajouter une clé (Lecture/Écriture).\nUtilisez l’adresse de la boutique, y compris son sous-dossier éventuel.'
        ttk.Label(box, text=instructions, wraplength=680).grid(row=6, column=0, columnspan=2, sticky='w', pady=16)
        self.remember = tk.BooleanVar(value=True)
        self.remember_button = ttk.Checkbutton(box, text='Mémoriser les accès sur ce poste (mot de passe et clés inclus)', variable=self.remember)
        self.remember_button.grid(row=7, column=0, columnspan=2, sticky='w')
        ttk.Label(box, text='Secrets chiffrés hors GitHub ; clé protégée par le coffre système. Décochez puis enregistrez pour supprimer le fichier de secrets.', wraplength=680).grid(row=8, column=0, columnspan=2, sticky='w', pady=8)
        self.button = ttk.Button(box, text='Tester la connexion', command=self.start)
        self.button.grid(row=9, column=0, sticky='w', pady=10)
        self.save_button = ttk.Button(box, text='Enregistrer les accès', command=self.persist)
        self.save_button.grid(row=9, column=1, sticky='w', pady=10)
        self.status = tk.StringVar(value=storage_error or 'Le test consulte les API. Aucun produit ni média ne sera envoyé.')
        ttk.Label(box, textvariable=self.status, wraplength=680).grid(row=10, column=0, columnspan=2, sticky='w', pady=10)

        ttk.Separator(box).grid(row=11, column=0, columnspan=2, sticky='ew', pady=10)
        ttk.Label(box, text='Test d’import d’une image', font=('Arial', 13, 'bold')).grid(row=12, column=0, columnspan=2, sticky='w')
        ttk.Label(box, text='Crée réellement un média sur le site indiqué ci-dessus. Aucun produit ne sera créé. JPEG, PNG ou WebP, 20 Mo maximum. Chaque nouvel envoi crée un média.', wraplength=700).grid(row=13, column=0, columnspan=2, sticky='w', pady=8)
        self.image_label = tk.StringVar(value='Aucune image sélectionnée')
        ttk.Label(box, textvariable=self.image_label, wraplength=700).grid(row=14, column=0, columnspan=2, sticky='w')
        self.choose_button = ttk.Button(box, text='Choisir une image…', command=self.choose_image)
        self.choose_button.grid(row=15, column=0, sticky='w', pady=8)
        self.upload_button = ttk.Button(box, text='Envoyer l’image sur ce site', command=self.send_image, state='disabled')
        self.upload_button.grid(row=15, column=1, sticky='w', pady=8)

        self.csv_button = ttk.Button(box, text='Importer un CSV d’articles…', command=self.open_products)
        self.csv_button.grid(row=16, column=0, columnspan=2, sticky='w', pady=10)

    def open_products(self):
        if self.busy:
            return
        from core.shop_products_ui import ProductsDialog
        credentials = Credentials(**{key: value.get() for key, value in self.values.items()})
        try:
            self.products_dialog = ProductsDialog(self, credentials)
        except ConnectionFailure as exc:
            self.status.set(str(exc))

    def persist(self):
        try:
            credentials = Credentials(**{key: value.get() for key, value in self.values.items()})
            save_settings(credentials, remember_secrets=self.remember.get())
        except VaultError as exc:
            self.status.set(str(exc));return False
        except (ConnectionFailure, OSError):
            self.status.set('Enregistrement impossible : vérifiez l’adresse HTTPS et les droits du dossier de configuration.')
            return False
        self.parent.shop_credentials = credentials
        self.status.set('Accès enregistrés sur ce poste.' if self.remember.get() else 'Secrets retirés du fichier local ; ils restent disponibles pour cette session.')
        return True

    def choose_image(self):
        filename = filedialog.askopenfilename(parent=self, title='Choisir une image à envoyer', filetypes=[('Images', '*.jpg *.jpeg *.png *.webp')])
        if filename:
            self.image_path = filename
            self.image_label.set(filename)
            self.upload_button.configure(state='normal')

    def send_image(self):
        if self.busy or not getattr(self, 'image_path', None):
            return
        from core.shop_media import upload_image
        credentials = Credentials(**{key: value.get() for key, value in self.values.items()})
        filename = self.image_path
        self.busy = True
        self.set_controls('disabled')
        self.status.set('Envoi de l’image dans la médiathèque WordPress…')
        def worker():
            try:
                result = upload_image(credentials, filename)
                self.events.put({'image': {'ok': True, 'message': f"Image créée dans la médiathèque (ID {result['id']}).\n{result['url']}"}})
            except ConnectionFailure as exc:
                self.events.put({'image': {'ok': False, 'message': str(exc)}})
            except Exception:
                self.events.put({'image': {'ok': False, 'message': 'Envoi non confirmé. Vérifiez la médiathèque avant de réessayer.'}})
        threading.Thread(target=worker, daemon=True).start()
        self.timer = self.after(100, self.poll)

    def set_controls(self, state):
        for widget in [self.button, self.save_button, self.remember_button, self.choose_button, self.upload_button, self.csv_button, *self.entries]:
            widget.configure(state=state)
        if state == 'normal' and not getattr(self, 'image_path', None):
            self.upload_button.configure(state='disabled')

    def start(self):
        if self.busy:
            return
        try:
            credentials = Credentials(**{key: value.get() for key, value in self.values.items()}).validated()
        except ConnectionFailure as exc:
            self.status.set(str(exc))
            return
        self.parent.shop_credentials = credentials
        if not self.persist():
            return
        self.busy = True
        self.set_controls('disabled')
        self.status.set('Vérification en cours…')
        def worker():
            try:
                self.events.put(check_connection(credentials))
            except Exception:
                self.events.put({'connexion': {'ok': False, 'message': 'Le test a échoué de manière inattendue. Réessayez.'}})
        threading.Thread(target=worker, daemon=True).start()
        self.timer = self.after(100, self.poll)

    def poll(self):
        self.timer = None
        try:
            result = self.events.get_nowait()
        except queue.Empty:
            self.timer = self.after(100, self.poll)
            return
        self.busy = False
        self.set_controls('normal')
        if 'image' in result:
            self.image_path = None
            self.upload_button.configure(state='disabled')
        self.status.set('\n\n'.join(f"{name.title()} — {'OK' if item['ok'] else 'Échec'} : {item['message']}" for name, item in result.items()))

    def destroy(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
        super().destroy()

    def close(self):
        if self.busy:
            self.status.set('Opération en cours. Attendez le résultat avant de fermer cette fenêtre.');return
        self.destroy()
