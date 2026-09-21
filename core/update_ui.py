"""Startup update prompt; all Tk work stays on the UI thread."""
import json
import queue
import threading
from tkinter import Toplevel, messagebox, ttk
from core import updater


class UpdateController:
    def __init__(self, app, root):
        self.app, self.root = app, root
        self.busy = False
        self.timer = None
        self.window = None
        self.events = queue.Queue()
        self.pending = None
        if updater.installed_state(root) is None:
            return
        result = root / 'update_result.json'
        if result.exists():
            try:
                message = json.loads(result.read_text(encoding='utf-8'))
                app.status.set(message['message'])
                result.unlink()
            except (OSError, ValueError, KeyError):
                pass
        def check():
            try:
                self.events.put(('available', updater.check_update(root)))
            except Exception:
                self.events.put(('offline', None))  # Offline startup remains usable.
        threading.Thread(target=check, daemon=True).start()
        self.timer = app.after(1000, self.poll)

    def idle(self):
        shop = getattr(self.app, 'shop_dialog', None)
        return not self.app.proc and not (shop and shop.winfo_exists()) and not self.app.grab_current()

    def poll(self):
        self.timer = None
        try:
            kind, value = self.events.get_nowait()
        except queue.Empty:
            kind, value = None, None
        if kind == 'available':
            self.pending = value
        elif kind == 'ready':
            try:
                updater.launch_helper(self.root, value)
            except Exception as exc:
                self.finish_error('Impossible de lancer la mise à jour : ' + str(exc))
            else:
                self.app.destroy()
                return
        elif kind == 'error':
            self.finish_error(value)
        if self.pending and self.idle() and not self.busy:
            update, self.pending = self.pending, None
            if messagebox.askyesno('Mise à jour disponible', 'Une nouvelle version est disponible sur GitHub.\n\n' + update['message'] + '\n\nInstaller maintenant ? L’application redémarrera. Vos accès, réglages, lots et fournisseurs privés seront conservés.', parent=self.app):
                self.start(update)
        self.timer = self.app.after(1000, self.poll)

    def start(self, update):
        self.busy = True
        self.window = Toplevel(self.app)
        self.window.title('Mise à jour de ZPSI Catalogue')
        self.window.transient(self.app)
        self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(self.window, text='Téléchargement et préparation de la mise à jour…\nCela peut prendre quelques minutes. L’application redémarrera automatiquement.', padding=24, wraplength=430).pack()
        bar = ttk.Progressbar(self.window, mode='indeterminate')
        bar.pack(fill='x', padx=24, pady=(0,24)); bar.start()
        def prepare():
            staging = None
            try:
                staging = updater.prepare_update(self.root, update)
                runtime = updater.build_runtime(self.root, staging)
                plan = json.loads((staging / 'plan.json').read_text(encoding='utf-8'))
                plan['runtime'] = str(runtime.relative_to(self.root))
                updater.write_json(staging / 'plan.json', plan)
                self.events.put(('ready', staging))
            except Exception as exc:
                self.events.put(('error', 'Mise à jour non installée. La version actuelle reste utilisable.\n' + str(exc)))
        threading.Thread(target=prepare, daemon=True).start()

    def finish_error(self, message):
        self.busy = False
        if self.window:
            self.window.destroy(); self.window = None
        messagebox.showerror('Mise à jour', message, parent=self.app)

    def close(self):
        if self.timer is not None:
            self.app.after_cancel(self.timer)
            self.timer = None
