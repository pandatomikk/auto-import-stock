"""Connection dialog; workers communicate with Tk only through a queue."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from core.shop_connection import Credentials, ConnectionFailure, check_connection, load_settings, save_settings


class ShopDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Ma boutique · V0.20')
        self.geometry('740x650')
        self.transient(parent)
        self.parent = parent
        self.events = queue.Queue()
        self.timer = None
        self.busy = False
        self.protocol('WM_DELETE_WINDOW', self.close)
        box = ttk.Frame(self, padding=24)
        box.pack(fill='both', expand=True)
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Connexion WordPress et WooCommerce', font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 16))
        credentials = getattr(parent, 'shop_credentials', None) or load_settings()
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
        self.remember_button = ttk.Checkbutton(box, text='Mémoriser l’adresse et l’identifiant sur ce poste', variable=self.remember)
        self.remember_button.grid(row=7, column=0, columnspan=2, sticky='w')
        ttk.Label(box, text='Les clés et le mot de passe restent en mémoire jusqu’à la fermeture de l’application. Ils devront être saisis au prochain lancement.', wraplength=680).grid(row=8, column=0, columnspan=2, sticky='w', pady=8)
        self.button = ttk.Button(box, text='Tester la connexion', command=self.start)
        self.button.grid(row=9, column=0, columnspan=2, sticky='w', pady=10)
        self.status = tk.StringVar(value='Le test consulte les API. Aucun produit ni média ne sera envoyé.')
        ttk.Label(box, textvariable=self.status, wraplength=680).grid(row=10, column=0, columnspan=2, sticky='w', pady=10)

    def start(self):
        if self.busy:
            return
        try:
            credentials = Credentials(**{key: value.get() for key, value in self.values.items()}).validated()
        except ConnectionFailure as exc:
            self.status.set(str(exc))
            return
        self.parent.shop_credentials = credentials
        if self.remember.get():
            try:
                save_settings(credentials)
            except OSError:
                self.status.set('Impossible de mémoriser l’adresse sur ce poste. Décochez la mémorisation pour tester sans enregistrer.')
                return
        self.busy = True
        for widget in [self.button, self.remember_button, *self.entries]:
            widget.configure(state='disabled')
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
        for widget in [self.button, self.remember_button, *self.entries]:
            widget.configure(state='normal')
        self.status.set('\n\n'.join(f"{name.title()} — {'OK' if item['ok'] else 'Échec'} : {item['message']}" for name, item in result.items()))

    def destroy(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
        super().destroy()

    def close(self):
        self.destroy()
