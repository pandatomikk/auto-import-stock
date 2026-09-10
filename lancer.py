#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
VENV_DIR = APP_DIR / ".venv"
REQ_FILE = APP_DIR / "requirements.txt"
CONVERTER = APP_DIR / "convertisseur.py"

def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def in_our_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except Exception:
        return False

def create_venv() -> None:
    print("Environnement Python absent : création automatique...")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])

def install_dependencies(py: Path) -> None:
    print("Vérification des dépendances...")
    subprocess.check_call([
        str(py),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(REQ_FILE),
    ])

def dependency_ok(py: Path) -> bool:
    result = subprocess.run(
        [str(py), "-c", "import openpyxl; import PIL; import gdown"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0

def main() -> int:
    # Si déjà lancé dans le venv géré par l'application, on va directement au convertisseur.
    if in_our_venv():
        os.execv(sys.executable, [sys.executable, str(CONVERTER), *sys.argv[1:]])

    py = venv_python()

    if not py.exists():
        try:
            create_venv()
        except Exception as exc:
            print()
            print("ERREUR : impossible de créer l'environnement Python.")
            print(f"Détail : {exc}")
            print()
            print("Sous Debian, vérifie que le module venv est installé :")
            print("  sudo apt install python3-venv")
            return 1

    if not dependency_ok(py):
        try:
            install_dependencies(py)
        except Exception as exc:
            print()
            print("ERREUR : impossible d'installer les dépendances.")
            print(f"Détail : {exc}")
            return 1

    # Relance réelle dans le venv local.
    os.execv(str(py), [str(py), str(CONVERTER), *sys.argv[1:]])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
