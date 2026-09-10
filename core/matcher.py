from __future__ import annotations
import difflib
from typing import Any
from .normalization import canonical_name

DEFAULT_ALIASES = {
    "sku": ["sku", "ugs", "reference", "référence", "ref", "code article", "code produit", "product code"],
    "ean": ["ean", "ean13", "gtin", "barcode", "code barre", "code barres", "upc", "isbn"],
    "name": ["nom", "nom produit", "produit", "produits", "titre", "titre fr", "designation", "désignation", "libellé", "product name", "name", "title"],
    "description": ["description", "description fr", "description produit", "descriptif", "product description"],
    "short_description": ["description courte", "resume", "résumé", "short description"],
    "stock": ["stock", "qte", "qté", "quantite", "quantité", "quantity", "qty", "disponible"],
    "regular_price": ["tarif regulier", "tarif régulier", "prix public", "prix vente", "prix de vente", "prix ttc", "rrp", "prix france rrp", "retail price", "regular price"],
    "sale_price": ["tarif promo", "prix promo", "prix promotionnel", "sale price"],
    "wholesale_price": ["prix achat", "prix d achat", "prix fournisseur", "prix wholesale", "prix france ws", "cost"],
    "brand": ["marque", "brand", "fabricant", "manufacturer"],
    "image": ["photo", "photos", "image", "images", "image principale", "photo principale", "picture", "image url", "url image"],
    "weight": ["poids", "poids net", "poids kg", "weight", "net weight"],
    "length": ["longueur", "length"],
    "width": ["largeur", "width"],
    "height": ["hauteur", "height"],
    "categories": ["categorie", "catégorie", "categories", "catégories", "famille", "family"],
    "tags": ["etiquettes", "étiquettes", "tags", "mots cles", "mots clés"],
    "color": ["couleur", "color", "colour", "spec couleur", "coloris"],
    "material": ["matiere", "matière", "matiere ext fr", "matière extérieure", "material"],
    "inner_material": ["matiere int fr", "matière intérieure", "inner material", "lining", "doublure"],
    "model": ["modele", "modèle", "model", "ligne", "collection"],
    "url": ["url", "url web", "url produit", "product url", "lien produit"],
}

def _aliases(config: dict) -> dict[str, set[str]]:
    out = {
        logical: {canonical_name(v) for v in values}
        for logical, values in DEFAULT_ALIASES.items()
    }
    for logical, values in config.get("aliases", {}).items():
        out.setdefault(logical, set()).update(canonical_name(v) for v in values)
    return out

def _score(a: str, b: str) -> float:
    a, b = canonical_name(a), canonical_name(b)
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    sa, sb = set(a.split()), set(b.split())
    jac = len(sa & sb) / max(1, len(sa | sb))
    return max(seq, 0.65 * seq + 0.35 * jac)

def detect_mapping(headers: list[str], config: dict) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    aliases = _aliases(config)
    mapping: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    canon_headers = {h: canonical_name(h) for h in headers}

    # Mapping forcé = priorité absolue, mais insensible casse/accents/pluriel simple.
    for logical, requested in config.get("force_mapping", {}).items():
        req = canonical_name(requested)
        candidates = [h for h, c in canon_headers.items() if c == req]
        if len(candidates) == 1:
            mapping[logical] = {"source": candidates[0], "method": "forced", "confidence": 1.0}
        elif len(candidates) > 1:
            issues.append({"type": "ambiguous_forced", "logical": logical, "candidates": candidates})
        else:
            issues.append({"type": "forced_not_found", "logical": logical, "requested": requested})

    if config.get("mapping_only"):
        return mapping, issues

    # Synonymes exacts normalisés.
    for logical, values in aliases.items():
        if logical in mapping:
            continue
        candidates = [h for h, c in canon_headers.items() if c in values]
        if len(candidates) == 1:
            mapping[logical] = {"source": candidates[0], "method": "alias", "confidence": 1.0}
        elif len(candidates) > 1:
            issues.append({"type": "ambiguous_alias", "logical": logical, "candidates": candidates})

    # Fuzzy prudent.
    threshold = float(config.get("fuzzy_threshold", 0.90))
    margin = float(config.get("ambiguity_margin", 0.05))

    for logical, values in aliases.items():
        if logical in mapping:
            continue
        scores = []
        for header in headers:
            best = max((_score(header, alias) for alias in values), default=0.0)
            scores.append((best, header))
        scores.sort(reverse=True)
        if not scores:
            continue
        best_score, best_header = scores[0]
        second_score = scores[1][0] if len(scores) > 1 else 0.0

        if best_score >= threshold:
            if best_score - second_score < margin:
                issues.append({
                    "type": "ambiguous_fuzzy",
                    "logical": logical,
                    "best": best_header,
                    "best_score": round(best_score, 3),
                    "second": scores[1][1] if len(scores) > 1 else None,
                    "second_score": round(second_score, 3),
                })
            else:
                mapping[logical] = {
                    "source": best_header,
                    "method": "fuzzy",
                    "confidence": round(best_score, 3),
                }

    return mapping, issues
