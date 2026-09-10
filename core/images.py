from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import quote
import re
import zipfile


def _natural_image_sort(name: str):
    stem = Path(name).stem

    m = re.search(r"-(\d+)$", stem)
    if m:
        return (0, int(m.group(1)), "", stem.casefold())

    m = re.search(r"-(\d+)([a-z]+)$", stem, re.I)
    if m:
        return (1, int(m.group(1)), m.group(2).casefold(), stem.casefold())

    return (2, 999999, "", stem.casefold())


def index_zip_images(zip_path: Path, extensions: list[str]) -> dict[str, list[str]]:
    allowed = {"." + ext.lower().lstrip(".") for ext in extensions}
    files: list[str] = []

    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue

            filename = PurePosixPath(info.filename).name

            if Path(filename).suffix.lower() in allowed:
                files.append(filename)

    # Déduplication exacte des noms au cas où le ZIP contiendrait des doublons.
    files = list(dict.fromkeys(files))
    files.sort(key=_natural_image_sort)

    return {"__all__": files}


def images_for_sku(
    index: dict[str, list[str]],
    sku: str,
    base_url: str,
) -> list[str]:
    """
    RÈGLE STRICTE V5.2 :
    - ne considère QUE les fichiers réellement présents dans le ZIP ;
    - le basename doit commencer par "UGS-" ;
    - aucun nom n'est fabriqué ;
    - aucun fallback fournisseur n'est ajouté ici.
    """
    sku = str(sku).strip()
    if not sku:
        return []

    prefix = sku.casefold() + "-"

    matches = [
        filename
        for filename in index.get("__all__", [])
        if filename.casefold().startswith(prefix)
    ]

    matches.sort(key=_natural_image_sort)

    if not base_url:return matches
    base = base_url.rstrip("/") + "/"
    return [base + quote(filename) for filename in matches]


def prepare_local_zip_images(zip_path,names,parent,brand,product):
    import hashlib, tempfile, unicodedata
    from .image_webp import optimize_webp
    from .shared import image_ok
    def slug(value):
        value=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()
        return re.sub(r'[^a-z0-9]+','-',value).strip('-')[:100] or 'produit'
    root=Path(parent)/('images_'+slug(brand))/'fichiers_webp';root.mkdir(parents=True,exist_ok=True)
    results=[]
    with zipfile.ZipFile(zip_path) as z:
        for number,name in enumerate(names,1):
            entries=[i for i in z.infolist() if not i.is_dir() and PurePosixPath(i.filename).name==name]
            if len(entries)!=1:raise ValueError('Nom image ambigu dans le ZIP : '+name)
            info=entries[0]
            digest=hashlib.sha256((info.filename+str(info.CRC)).encode()).hexdigest()[:12]
            target=root/(slug(product)+f'-{number:02d}__{digest}.webp')
            if not image_ok(target):
                import shutil
                with tempfile.TemporaryDirectory() as tmp:
                    source=Path(tmp)/'source'
                    with z.open(info) as src,source.open('wb') as dst:shutil.copyfileobj(src,dst)
                    optimize_webp(source,target)
            results.append(target.name)
    return results
