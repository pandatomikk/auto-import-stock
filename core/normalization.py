from __future__ import annotations
import re
import unicodedata
from typing import Any

def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )

def normalize_name(value: Any) -> str:
    """
    Normalisation forte des noms de colonnes :
    Produit / produits / PRODUIT / produit-fr / produit_fr => formes comparables.
    """
    if value is None:
        return ""
    text = strip_accents(str(value)).casefold().replace("\xa0", " ")
    text = re.sub(r"[_\-/\\.,;:()\[\]{}]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def singularize_token(token: str) -> str:
    # Conservateur : évite les transformations agressives.
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token

def canonical_name(value: Any) -> str:
    return " ".join(singularize_token(t) for t in normalize_name(value).split())
