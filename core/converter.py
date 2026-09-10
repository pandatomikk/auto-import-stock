from __future__ import annotations
import json
import re
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import read_source, write_csv
from .progress import preparation_event
from .matcher import detect_mapping
from .normalization import normalize_name
from .images import index_zip_images, images_for_sku

IMAGE_FORMULA_RE = re.compile(r'^\s*=?\s*IMAGE\s*\(\s*["\']([^"\']+)["\']', re.I)
URL_RE = re.compile(r'https?://[^\s"\')>,]+', re.I)

LOGICAL_TO_WC = {
    "sku": "UGS",
    "ean": "GTIN, UPC, EAN ou ISBN",
    "name": "Nom",
    "description": "Description",
    "short_description": "Description courte",
    "stock": "Stock",
    "regular_price": "Tarif régulier",
    "sale_price": "Tarif promo",
    "brand": "Marques",
    "image": "Images",
    "weight": "Poids (kg)",
    "length": "Longueur (cm)",
    "width": "Largeur (cm)",
    "height": "Hauteur (cm)",
    "categories": "Catégories",
    "tags": "Étiquettes",
    "url": "URL externe",
}

@dataclass
class ConversionResult:
    output_path: Path
    report_path: Path
    row_count: int
    source_row_count: int
    excluded_count: int
    merged_count: int
    mapping: dict
    issues: list
    warnings: list

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def extract_url(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    m = IMAGE_FORMULA_RE.search(text)
    if m:
        return m.group(1)
    m = URL_RE.search(text)
    return m.group(0) if m else text

def clean_identifier(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text

def clean_number(value: Any) -> Any:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if isinstance(value, float) and value.is_integer() else value
    text = str(value).strip().replace("\xa0", " ").replace("€", "")
    candidate = text.replace(" ", "").replace(",", ".")
    try:
        number = float(candidate)
        return int(number) if number.is_integer() else number
    except ValueError:
        return text

def _rule_matches(raw: Any, rule: dict) -> bool:
    normalized = normalize_name(raw)
    if "equals" in rule:
        return normalized == normalize_name(rule["equals"])
    if "contains" in rule:
        return normalize_name(rule["contains"]) in normalized
    if "regex" in rule:
        return re.search(str(rule["regex"]), str(raw), re.I) is not None
    return False

def should_exclude(row: dict[str, Any], rules: list[dict], mapping: dict) -> tuple[bool, str]:
    for rule in rules:
        logical = rule.get("source", "name")
        info = mapping.get(logical)
        if not info:
            continue
        raw = row.get(info["source"], "")
        if _rule_matches(raw, rule):
            return True, str(rule.get("reason", "Règle d'exclusion"))
    return False, ""

def category_from_rules(row: dict[str, Any], rules: list[dict], mapping: dict) -> str:
    for rule in rules:
        logical = rule.get("source", "name")
        info = mapping.get(logical)
        if not info:
            continue
        raw = row.get(info["source"], "")
        if _rule_matches(raw, rule):
            return str(rule.get("value", ""))
    return ""

def _logical_value(row: dict[str, Any], logical: str, mapping: dict) -> Any:
    info = mapping.get(logical)
    if not info:
        return ""
    return row.get(info["source"], "")

def merge_duplicates(
    rows: list[dict[str, Any]],
    config: dict,
    mapping: dict,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    settings = config.get("duplicate_handling", {})
    strategy = str(settings.get("strategy", "keep")).lower()

    if strategy == "keep":
        return rows, 0, []

    if strategy not in {"merge", "reject"}:
        raise ValueError(f"Stratégie de doublons inconnue : {strategy}")

    key_logical = settings.get("key", "sku")
    key_info = mapping.get(key_logical)
    if not key_info:
        return rows, 0, [{
            "type": "duplicate_key_not_mapped",
            "logical": key_logical,
        }]

    key_source = key_info["source"]
    sum_logicals = set(settings.get("sum", []))
    grouped: dict[str, list[dict[str, Any]]] = {}
    unkeyed: list[dict[str, Any]] = []

    for row in rows:
        key = clean_identifier(row.get(key_source, ""))
        if not key:
            unkeyed.append(row)
        else:
            grouped.setdefault(key, []).append(row)

    conflicts: list[dict[str, Any]] = []
    merged_rows: list[dict[str, Any]] = []
    merged_count = 0

    sum_source_cols = {
        mapping[l]["source"]
        for l in sum_logicals
        if l in mapping
    }

    for key, items in grouped.items():
        if len(items) == 1:
            merged_rows.append(items[0])
            continue

        if strategy == "reject":
            conflicts.append({
                "type": "duplicate_rejected",
                "key": key,
                "count": len(items),
            })
            merged_rows.extend(items)
            continue

        merged_count += len(items) - 1
        merged = dict(items[0])

        # Sum configured logical fields, e.g. stock.
        for logical in sum_logicals:
            info = mapping.get(logical)
            if not info:
                conflicts.append({
                    "type": "duplicate_sum_field_not_mapped",
                    "key": key,
                    "logical": logical,
                })
                continue

            source_col = info["source"]
            total = 0.0
            valid = False
            for item in items:
                val = clean_number(item.get(source_col, ""))
                try:
                    total += float(val)
                    valid = True
                except (TypeError, ValueError):
                    pass

            if valid:
                merged[source_col] = int(total) if total.is_integer() else total

        # Keep first non-empty value for other fields and report conflicts.
        all_cols = set()
        for item in items:
            all_cols.update(item.keys())

        for source_col in all_cols:
            if source_col in sum_source_cols:
                continue

            values = [
                item.get(source_col, "")
                for item in items
                if item.get(source_col, "") not in (None, "")
            ]
            if not values:
                continue

            merged[source_col] = values[0]
            normalized_values = {str(v).strip() for v in values}

            if len(normalized_values) > 1:
                conflicts.append({
                    "type": "duplicate_conflict",
                    "key": key,
                    "column": source_col,
                    "values": list(normalized_values)[:10],
                })

        merged_rows.append(merged)

    merged_rows.extend(unkeyed)
    return merged_rows, merged_count, conflicts




def _logical_values(source_row: dict[str, Any], mapping: dict) -> dict[str, str]:
    values: dict[str, str] = {}

    for logical, info in mapping.items():
        raw = source_row.get(info["source"], "")
        if raw is None:
            raw = ""
        values[logical] = str(raw).strip()

    return values


def _render_template(template: str, values: dict[str, str]) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return ""

    return str(template).format_map(SafeDict(values)).strip()


def _field_value(
    source_row: dict[str, Any],
    logical: str,
    mapping: dict,
) -> str:
    info = mapping.get(logical)
    if not info:
        return ""

    raw = source_row.get(info["source"], "")
    if raw is None:
        return ""

    return str(raw).strip()


def build_generic_description(
    source_row: dict[str, Any],
    config: dict,
    mapping: dict,
) -> str | None:
    """
    Génère une description WooCommerce factuelle uniquement à partir
    des données réellement présentes dans le fichier fournisseur.

    Configuration attendue :

    "description_generator": {
      "enabled": true,
      "heading_template": "Caractéristiques du {name}",
      "intro_field": "description",
      "fields": [
        {"logical": "color", "label": "Coloris"},
        {"logical": "material", "label": "Matière extérieure"},
        {"logical": "inner_material", "label": "Matière intérieure"},
        {"logical": "weight", "label": "Poids", "suffix": " kg"}
      ],
      "dimensions": {
        "enabled": true,
        "fields": [
          {"logical": "length", "label": "Longueur", "suffix": " cm"},
          {"logical": "width", "label": "Largeur", "suffix": " cm"},
          {"logical": "height", "label": "Hauteur", "suffix": " cm"}
        ]
      }
    }

    Les champs absents ou vides sont simplement ignorés.
    """
    settings = config.get("description_generator", {})

    if not settings.get("enabled"):
        return None

    values = _logical_values(source_row, mapping)
    chunks: list[str] = []

    heading_template = settings.get(
        "heading_template",
        "Caractéristiques du {name}",
    )
    heading = _render_template(heading_template, values)
    if heading and not settings.get("intro_first", False):
        chunks.append(f"<h4>{escape(heading)}</h4>")

    intro_field = settings.get("intro_field")
    if intro_field:
        intro = _field_value(source_row, intro_field, mapping)
        if intro:
            chunks.append(f"<p>{escape(intro)}</p>")

    if heading and settings.get("intro_first", False):
        chunks.append(f"<h4>{escape(heading)}</h4>")

    field_lines: list[str] = []

    for field in settings.get("fields", []):
        logical = field.get("logical")
        if not logical:
            continue

        value = _field_value(source_row, logical, mapping)
        if not value:
            continue

        label = str(field.get("label", logical)).strip()
        prefix = str(field.get("prefix", ""))
        suffix = str(field.get("suffix", ""))

        rendered = f"{prefix}{value}{suffix}"

        field_lines.append(
            f"<li><strong>{escape(label)} :</strong> {escape(rendered)}</li>"
        )

    if field_lines:
        chunks.append("<ul>" + "".join(field_lines) + "</ul>")

    dimensions = settings.get("dimensions", {})
    if dimensions.get("enabled"):
        dim_lines: list[str] = []

        for field in dimensions.get("fields", []):
            logical = field.get("logical")
            if not logical:
                continue

            value = _field_value(source_row, logical, mapping)
            if not value:
                continue

            label = str(field.get("label", logical)).strip()
            prefix = str(field.get("prefix", ""))
            suffix = str(field.get("suffix", ""))

            rendered = f"{prefix}{value}{suffix}"

            dim_lines.append(
                f"<li><strong>{escape(label)} :</strong> {escape(rendered)}</li>"
            )

        if dim_lines:
            title = str(dimensions.get("title", "Dimensions")).strip()
            chunks.append(f"<p><strong>{escape(title)} :</strong></p>")
            chunks.append("<ul>" + "".join(dim_lines) + "</ul>")

    static_blocks = settings.get("static_blocks", [])
    for block in static_blocks:
        html = str(block.get("html", "")).strip()
        if html:
            chunks.append(html)

    return "\n".join(chunks) if chunks else None


def format_short_description(
    source_row: dict[str, Any],
    config: dict,
    mapping: dict,
) -> str | None:
    settings = config.get("short_description", {})
    template = settings.get("template")

    if not template:
        return None

    values = {}
    for logical, info in mapping.items():
        raw = source_row.get(info["source"], "")
        values[logical] = "" if raw is None else str(raw).strip()

    try:
        return str(template).format_map(values)
    except KeyError:
        return None


def format_product_name(source_row: dict[str, Any], config: dict, mapping: dict) -> str | None:
    settings = config.get("product_name", {})
    template = settings.get("template")
    if not template:
        return None

    values = {}
    for logical, info in mapping.items():
        raw = source_row.get(info["source"], "")
        values[logical] = "" if raw is None else str(raw).strip()

    try:
        result = str(template).format_map(values)
    except KeyError:
        return None

    # Nettoyage simple des séparateurs laissés par un champ vide.
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"(?:\s*-\s*)+$", "", result).strip()
    return result


def build_zip_image_context(config: dict, zip_path: Path | None, base_url: str | None):
    settings = config.get("images", {})
    if settings.get("mode") != "zip_by_sku" or zip_path is None:
        return None

    extensions = settings.get("extensions", ["png", "jpg", "jpeg", "webp"])
    url = (base_url or settings.get("base_url") or "").strip()
    if not url and settings.get('output_mode') != 'local':
        raise ValueError("Une URL WordPress de base est nécessaire pour les images du ZIP.")

    return {
        "index": index_zip_images(zip_path, extensions),
        "zip_path":zip_path,
        "local":settings.get("output_mode")=="local",
        "config":config,
        "base_url": url,
    }


def validate(rows: list[dict[str, Any]]) -> list[str]:
    warnings = []

    skus = [str(r.get("UGS", "")).strip() for r in rows]
    missing_sku = sum(not s for s in skus)
    if missing_sku:
        warnings.append(f"{missing_sku} produit(s) sans UGS/SKU.")

    nonempty = [s for s in skus if s]
    duplicates = len(nonempty) - len(set(nonempty))
    if duplicates:
        warnings.append(f"{duplicates} UGS/SKU dupliquée(s) après traitement.")

    missing_name = sum(not str(r.get("Nom", "")).strip() for r in rows)
    if missing_name:
        warnings.append(f"{missing_name} produit(s) sans nom.")

    missing_price = sum(not str(r.get("Tarif régulier", "")).strip() for r in rows)
    if missing_price:
        warnings.append(f"{missing_price} produit(s) sans prix régulier.")

    missing_images = sum(not str(r.get("Images", "")).strip() for r in rows)
    if missing_images:
        warnings.append(f"{missing_images} produit(s) sans image.")

    missing_categories = sum(not str(r.get("Catégories", "")).strip() for r in rows)
    if missing_categories:
        warnings.append(f"{missing_categories} produit(s) sans catégorie.")

    return warnings

def convert_catalogue(
    source_path: Path,
    supplier_config_path: Path,
    schema_path: Path,
    output_path: Path | None = None,
    images_zip_path: Path | None = None,
    images_base_url: str | None = None,
    web_descriptions: bool | None = None,
    product_rules_path: Path | None = None,
) -> ConversionResult:
    """
    Public conversion engine used by the CLI today and a future GUI later.
    """
    preparation_event('Configuration', 'Chargement du profil fournisseur et des règles de conversion…')
    config = load_json(supplier_config_path)
    from .product_rules import load_rules, display_values, logical_values
    presentation_rules = load_rules(config, product_rules_path)
    from .enrichment import SupplierDescriptions
    settings = dict(config.get("supplier_descriptions", {}))
    if web_descriptions is not None:
        settings["enabled"] = web_descriptions
    descriptions = SupplierDescriptions(settings)
    schema = load_json(schema_path)
    wc_columns: list[str] = schema["columns"]

    preparation_event('Lecture du catalogue', 'Lecture de ' + source_path.name + '…')
    headers, source_rows = read_source(source_path, config.get("source_options"))
    if {'UGS', 'Nom', 'Type', 'Publié'}.issubset(set(headers)):
        raise ValueError('Ce fichier est déjà un CSV WooCommerce. Pour l’envoyer, utilisez Ma boutique → Importer un CSV d’articles. Pour préparer le catalogue, sélectionnez le document fournisseur original.')
    source_row_count = len(source_rows)
    preparation_event('Analyse des colonnes', f'{source_row_count} lignes lues. Association des colonnes aux champs produit…')
    mapping, issues = detect_mapping(headers, config)

    for column in config.get("required_columns", []):
        if column not in headers:
            raise ValueError("Colonne obligatoire absente : " + column)

    preparation_event('Contrôle du catalogue', 'Vérification des quantités, exclusions et doublons…')
    # Exclusions before duplicate handling.
    filtered_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for idx, row in enumerate(source_rows, start=2):
        exclude, reason = should_exclude(row, config.get("exclude_rules", []), mapping)
        for column in ([] if exclude else config.get("positive_quantity_columns", [])):
            raw = clean_number(row.get(column))
            if raw == "" or raw == 0:
                exclude, reason = True, "Quantité vide ou nulle"
            elif not isinstance(raw, (int, float)) or raw < 0 or not float(raw).is_integer():
                raise ValueError(f"Quantité invalide ({column}) : {row.get(column)!r}")
        if exclude:
            excluded.append({
                "source_row": idx,
                "reason": reason,
                "sku": clean_identifier(_logical_value(row, "sku", mapping)),
                "name": str(_logical_value(row, "name", mapping)),
            })
        else:
            filtered_rows.append(row)

    # Duplicate handling.
    filtered_rows, merged_count, duplicate_issues = merge_duplicates(
        filtered_rows, config, mapping
    )
    issues.extend(duplicate_issues)

    preparation_event('Lecture des images', ('Indexation de ' + images_zip_path.name + '…') if images_zip_path else 'Aucun ZIP à indexer.')
    image_context = build_zip_image_context(config, images_zip_path, images_base_url)
    if image_context:
        preparation_event('Lecture des images', f"{len(image_context['index'].get('__all__', []))} images trouvées dans le ZIP.")
    fixed = dict(schema.get("defaults", {}))
    fixed.update(config.get("fixed_values", {}))
    # Publication is the common export policy, including older installed profiles.
    fixed["Publié"] = 1

    converted: list[dict[str, Any]] = []
    image_identifiers = []

    for product_index, source_row in enumerate(filtered_rows, 1):
        out = {column: "" for column in wc_columns}

        for column, value in fixed.items():
            if column in out:
                out[column] = value

        for logical, wc_col in LOGICAL_TO_WC.items():
            info = mapping.get(logical)
            if not info or wc_col not in out:
                continue

            value = source_row.get(info["source"], "")

            if logical == "image":
                value = extract_url(value)
            elif logical in {"sku", "ean"}:
                value = clean_identifier(value)
            elif logical in {
                "stock", "regular_price", "sale_price",
                "weight", "length", "width", "height"
            }:
                value = clean_number(value)
            elif value is None:
                value = ""

            out[wc_col] = value

        generated_category = category_from_rules(
            source_row, config.get("category_rules", []), mapping
        )
        if generated_category and "Catégories" in out:
            out["Catégories"] = generated_category

        if "En stock ?" in out and "stock" in mapping:
            val = clean_number(source_row.get(mapping["stock"]["source"], ""))
            try:
                out["En stock ?"] = 1 if float(val) > 0 else 0
            except (TypeError, ValueError):
                pass

        attr = config.get("attribute_rules", {})
        logical_attr = attr.get("source_logical_field")
        if attr.get("enabled") and logical_attr in mapping:
            value = source_row.get(mapping[logical_attr]["source"], "")
            if "Nom de l’attribut 1" in out:
                out["Nom de l’attribut 1"] = attr.get("name", logical_attr)
            if "Valeur(s) de l’attribut 1 " in out:
                out["Valeur(s) de l’attribut 1 "] = "" if value is None else value
            if "Attribut 1 visible" in out:
                out["Attribut 1 visible"] = attr.get("visible", 1)
            if "Attribut 1 global" in out:
                out["Attribut 1 global"] = attr.get("global", 0)

        reference = str(out.get('UGS') or product_index)
        preparation_event('Préparation des articles', f'Article {product_index}/{len(filtered_rows)} — {reference}', product_index - 1, len(filtered_rows))
        presentation = display_values(logical_values(source_row, mapping), presentation_rules) if presentation_rules.get('enabled') else None
        # Description longue générique et factuelle, construite uniquement
        # à partir des champs réellement disponibles chez le fournisseur.
        if descriptions.provider:
            preparation_event('Descriptions fournisseur', f'Article {product_index}/{len(filtered_rows)} — {reference} : recherche de la description (attente du fournisseur possible).', product_index - 1, len(filtered_rows))
        web_text = descriptions.get(_logical_values(source_row, mapping))
        if descriptions.provider:
            preparation_event('Descriptions fournisseur', f'{reference} : description récupérée.' if web_text else f'{reference} : description générique conservée.', product_index - 1, len(filtered_rows))
        description_row = source_row
        description_mapping = mapping
        if web_text:
            description_row = dict(source_row, __web_description=web_text)
            description_mapping = dict(mapping, description={"source": "__web_description"})
        if presentation and 'color' in mapping:
            description_row = dict(description_row)
            description_row[mapping['color']['source']] = presentation['color']
        generated_description = build_generic_description(
            description_row,
            config,
            description_mapping,
        )
        if generated_description and "Description" in out:
            out["Description"] = generated_description

        # Description courte configurable, par exemple la référence commerciale.
        formatted_short_description = format_short_description(
            source_row,
            config,
            mapping,
        )
        if formatted_short_description and "Description courte" in out:
            out["Description courte"] = formatted_short_description

        # Nom commercial enrichi (ex. nom + coloris).
        formatted_name = format_product_name(source_row, config, mapping)
        if formatted_name and "Nom" in out:
            out["Nom"] = formatted_name

        if presentation:
            out['Nom'] = presentation['title']
            out['Catégories'] = presentation['category']
            if logical_attr == 'color':
                out['Valeur(s) de l’attribut 1 '] = presentation['color']
        # V5.3 : si un ZIP est fourni, on efface d'abord toute valeur image
        # issue du fichier fournisseur, puis on reconstruit Images UNIQUEMENT
        # avec les fichiers réellement présents dans le ZIP courant.
        if image_context and "sku" in mapping and "Images" in out:
            out["Images"] = ""

            sku = clean_identifier(
                source_row.get(mapping["sku"]["source"], "")
            )

            urls = images_for_sku(
                image_context["index"],
                sku,
                image_context["base_url"],
            )

            if image_context['local']:
                from .images import prepare_local_zip_images
                names=images_for_sku(image_context['index'],sku,'')
                preparation_event('Images de l’article', f'{reference} : {len(names)} photo(s) à vérifier / convertir en WebP.', product_index - 1, len(filtered_rows))
                urls=prepare_local_zip_images(image_context['zip_path'],names,source_path.parent,config.get('supplier_name','fournisseur'),out.get('Nom',sku))
            if urls:
                out["Images"] = ", ".join(urls)

        preparation_event('Préparation des articles', f'Article {product_index}/{len(filtered_rows)} terminé — {reference}', product_index, len(filtered_rows))
        converted.append(out)
        if config.get("export_ean_text"):
            image_identifiers.append({
                "ean": clean_identifier(out.get("GTIN, UPC, EAN ou ISBN", "")),
                "article": clean_identifier(_logical_value(source_row, "model", mapping)),
                "color_code": clean_identifier(_logical_value(source_row, "color_code", mapping)),
                "color": str(_logical_value(source_row, "color", mapping) or "").strip(),
            })

    output_path = output_path or source_path.with_name(
        f"{source_path.stem}_woocommerce.csv"
    )
    report_path = output_path.with_name(
        f"{output_path.stem}_rapport.json"
    )

    preparation_event('Écriture des fichiers', f'Écriture du CSV : {len(converted)} articles…')
    write_csv(output_path, wc_columns, converted)
    ean_export = None
    if config.get("export_ean_text", False):
        # Preserve identifiers and CSV order; one code per line, no heading.
        eans = list(dict.fromkeys(
            clean_identifier(row.get("GTIN, UPC, EAN ou ISBN", ""))
            for row in converted
            if clean_identifier(row.get("GTIN, UPC, EAN ou ISBN", ""))
        ))
        ean_path = output_path.with_name(output_path.stem + "_ean.txt")
        ean_path.write_text("\n".join(eans) + ("\n" if eans else ""), encoding="utf-8")
        ean_export = {"path": str(ean_path), "count": len(eans)}
    warnings = validate(converted)
    failed = sum(r["status"] == "fallback" for r in descriptions.records)
    if failed:
        warnings.append(f"{failed} description(s) web non récupérée(s) : descriptions génériques conservées. Voir supplier_descriptions dans le rapport.")

    report = {
        "supplier": config.get("supplier_name", supplier_config_path.stem),
        "source": str(source_path),
        "source_rows": source_row_count,
        "excluded_rows": len(excluded),
        "merged_duplicate_rows": merged_count,
        "output_products": len(converted),
        "ean_text": ean_export,
        "image_identifiers": image_identifiers,
        "mapping": mapping,
        "issues": issues,
        "warnings": warnings,
        "excluded": excluded,
        "supplier_descriptions": descriptions.records,
        "images_zip": str(images_zip_path) if images_zip_path else None,
        "images_base_url": image_context["base_url"] if image_context else None,
        "unmapped_source_columns": [
            h for h in headers
            if h not in {i["source"] for i in mapping.values()}
        ],
    }

    preparation_event('Écriture des fichiers', 'Enregistrement du rapport de contrôle…')
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    preparation_event('Fichiers prêts', f'{len(converted)} articles exportés dans {output_path.name}.', len(converted), len(converted))
    return ConversionResult(
        output_path=output_path,
        report_path=report_path,
        row_count=len(converted),
        source_row_count=source_row_count,
        excluded_count=len(excluded),
        merged_count=merged_count,
        mapping=mapping,
        issues=issues,
        warnings=warnings,
    )
