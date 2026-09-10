"""Use the desktop's native file chooser on Linux; Tk is a fallback."""
import os
import shutil
import subprocess
import sys
from tkinter import filedialog as tk_filedialog


def askopenfilename(**options):
    if not sys.platform.startswith('linux'):
        return tk_filedialog.askopenfilename(**options)
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').casefold()
    candidates = ('kdialog', 'zenity') if 'kde' in desktop else ('zenity', 'kdialog')
    for program in candidates:
        executable = shutil.which(program)
        if not executable:
            continue
        title = options.get('title', 'Choisir un fichier')
        initial = options.get('initialdir', '')
        filters = options.get('filetypes', [])
        if program == 'zenity':
            args = [executable, '--file-selection', '--title=' + title]
            if initial:
                args.append('--filename=' + os.path.join(str(initial), ''))
            for label, patterns in filters:
                pattern = ' '.join(patterns) if isinstance(patterns, (tuple, list)) else patterns
                args.append('--file-filter=' + label + ' | ' + pattern)
        else:
            filter_text = '\n'.join((' '.join(patterns) if isinstance(patterns, (tuple, list)) else patterns) + '|' + label for label, patterns in filters)
            args = [executable, '--getopenfilename', str(initial), filter_text, '--title', title]
        try:
            result = subprocess.run(args, capture_output=True, text=True)
        except OSError:
            continue
        if result.returncode == 0:
            # Preserve spaces in filenames; only remove the line terminator.
            return result.stdout.rstrip('\r\n')
        if result.returncode == 1:
            return ''  # User cancelled: do not open a second dialog.
    return tk_filedialog.askopenfilename(**options)
