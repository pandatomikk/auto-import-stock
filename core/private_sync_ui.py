"""Manual one-way update of a client pack, with credentials in the OS vault."""
import json
import queue
import threading
from tkinter import Toplevel, StringVar, ttk, messagebox
from .profiles import private_directory
from .secret_store import system_vault, atomic_write
from .private_sync import download_pack, apply_pack, PackConflict


def open_pack_dialog(app, owner=None, site=None):
    if app.proc or getattr(app.update_controller, 'busy', False):
        messagebox.showinfo('Pack client', 'Attendez la fin du traitement en cours.', parent=app)
        return
    if app.grab_current():
        return
    path = private_directory() / '.sync-config.json'
    config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    owner = owner or app
    dialog = Toplevel(owner)
    dialog.title('Mise à jour du pack client')
    dialog.transient(owner); dialog.grab_set()
    box = ttk.Frame(dialog, padding=20); box.pack(fill='both', expand=True)
    linked_site = site or config.get('site', '')
    if linked_site:
        ttk.Label(box, text='Boutique associée : ' + linked_site, wraplength=480).grid(row=0, column=0, sticky='w', pady=(0, 10))
    repo = StringVar(value=config.get('repository', ''))
    branch = StringVar(value=config.get('branch', 'main'))
    token = StringVar()
    status = StringVar(value='Réception des mises à jour uniquement. Aucun paramètre envoyé.')
    for row, (label, variable) in enumerate([('Dépôt GitHub privé (compte/dépôt)', repo), ('Branche', branch), ('Jeton en lecture seule (vide si déjà enregistré)', token)]):
        ttk.Label(box, text=label).grid(row=row*2+1, column=0, sticky='w', pady=(8, 2))
        ttk.Entry(box, textvariable=variable, width=58, show='*' if variable is token else '').grid(row=row*2+2, column=0, sticky='ew')
    ttk.Label(box, textvariable=status, wraplength=480).grid(row=7, column=0, pady=12)
    events = queue.Queue()
    pending = {}
    def update(replace=False):
        repository, ref, entered = repo.get().strip(), branch.get().strip(), token.get().strip()
        if replace and (not pending or pending['repository'] != repository or pending['branch'] != ref):
            status.set('Le dépôt ou la branche a changé : recevez à nouveau les mises à jour.'); return
        token.set('')
        replace_button.grid_remove()
        button.configure(state='disabled')
        dialog.protocol('WM_DELETE_WINDOW', lambda: None)
        status.set('Vérification et téléchargement du pack…')
        def work():
            try:
                vault = system_vault()
                secret = entered or vault.get_password('zpsi-private-pack', repository)
                if not secret:
                    raise ValueError('Renseignez un jeton GitHub limité à ce dépôt, avec Contents en lecture seule.')
                revision, files = (pending['revision'], pending['files']) if replace else download_pack(repository, ref, secret)
                if entered:
                    vault.set_password('zpsi-private-pack', repository, entered)
                count = apply_pack(private_directory(), repository, revision, files, replace_conflicts=replace)
                atomic_write(path, json.dumps({'repository': repository, 'branch': ref, 'site': linked_site}).encode())
                events.put((True, f'{count} fichier(s) mis à jour. ' + ('Anciens fichiers sauvegardés dans private/pack-backup-… . ' if replace else '') + 'Fermez puis rouvrez l’application pour charger le pack.', None))
            except PackConflict as exc:
                events.put((False, str(exc), {'repository': repository, 'branch': ref, 'revision': revision, 'files': files}))
            except Exception as exc:
                events.put((False, str(exc), None))
        threading.Thread(target=work, daemon=True).start()
        poll()
    def poll():
        try:
            success, text, conflict = events.get_nowait()
        except queue.Empty:
            dialog.after(150, poll); return
        pending.clear()
        if conflict:
            pending.update(conflict)
            replace_button.grid()
            text += '\nLe bouton de remplacement sauvegarde les fichiers locaux avant d’installer ceux du dépôt.'
        status.set(text)
        button.configure(state='normal')
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        if success:
            button.configure(state='disabled')
            # Keep the modal open until the app is closed: no stale profiles used.
            dialog.protocol('WM_DELETE_WINDOW', app.close)
            ttk.Button(box, text='Fermer l’application', command=app.close).grid(row=10, column=0, pady=8)
    button = ttk.Button(box, text='Recevoir les mises à jour', command=update)
    button.grid(row=8, column=0, sticky='ew')

    replace_button = ttk.Button(box, text='Remplacer les fichiers locaux (avec sauvegarde)', command=lambda: update(replace=True))
    replace_button.grid(row=9, column=0, sticky='ew', pady=8)
    replace_button.grid_remove()
