#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from core import convert_catalogue
from core.profiles import discover_profiles, resolve_profile, workflow_kind, load_adapter

APP_DIR = Path(__file__).resolve().parent
SCHEMA = APP_DIR / "schemas" / "woocommerce.json"

def load_supplier_name(path: Path) -> str:
    import json
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("supplier_name") or path.stem)
    except Exception:
        return path.stem

def discover_suppliers() -> list[Path]:
    return discover_profiles()

def choose_supplier() -> Path:
    suppliers = discover_suppliers()
    if not suppliers:
        raise RuntimeError("Aucun profil disponible. Installer un profil dans private/profiles/.")

    print("\n=== FOURNISSEURS DISPONIBLES ===")
    for i, path in enumerate(suppliers, 1):
        print(f"{i:>2} - {load_supplier_name(path)}")

    while True:
        value = input("\nFournisseur (numéro) : ").strip()
        try:
            idx = int(value)
            if 1 <= idx <= len(suppliers):
                return suppliers[idx - 1]
        except ValueError:
            pass
        print("Choix invalide.")

def choose_source_cli() -> Path:
    """
    Aujourd'hui : CLI pure.
    Cette fonction est volontairement isolée :
    la future GUI remplacera cette étape par un filedialog sans toucher au moteur.
    """
    while True:
        value = input("\nChemin du fichier fournisseur : ").strip().strip('"').strip("'")
        path = Path(value).expanduser()
        if path.is_file():
            return path.resolve()
        print("Fichier introuvable.")

def run_two_pass(source=None, config=None, output=None, session=None, images_zip=None, rules_path=None, rebuild=False):
    import json
    from core.media_workflow import prepare_catalogue, finalize_catalogue, workflow_event
    try:
        if session is not None:
            data = finalize_catalogue(session, images_zip)
        else:
            session, data = prepare_catalogue(source, config, SCHEMA, output, rules_path=rules_path, rebuild=rebuild)
        event = workflow_event(session, data)
        print('ZPSI_WORKFLOW ' + json.dumps(event, ensure_ascii=False), flush=True)
        if data['status'] == 'waiting_images':
            print(f"CSV de préparation : {event['prepared_csv']}\nListe EAN : {event['ean_text']}")
            print('EN PAUSE — Copier les EAN sur la plateforme fournisseur, récupérer le ZIP, puis finaliser.')
            print(f'Pour reprendre : python3 lancer.py --resume-session "{event["session"]}" --images-zip "/chemin/images.zip"')
        else:
            print(f"CSV final : {event['final_csv']}\nProduits au statut publié : {data['products']}")
            if data['missing_images']:
                print(f"Attention : {len(data['missing_images'])} référence(s) sans image. Voir le rapport.")
            print(f"Téléverser {event['images_directory']}/fichiers_webp dans les médias WordPress avant le CSV final.")
        return 0
    except Exception as exc:
        print(f'ERREUR préparation : {exc}', file=sys.stderr)
        return 1

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convertisseur de catalogues fournisseurs vers WooCommerce."
    )
    parser.add_argument('--product-rules', type=Path, help='Règles locales de présentation')
    parser.add_argument('--rebuild-preparation', action='store_true', help='Recréer une préparation en sauvegardant la précédente')
    parser.add_argument("--supplier", help="Nom du fichier config sans .json, ex: demo")
    parser.add_argument("--source", type=Path, help="Catalogue fournisseur")
    parser.add_argument("--output", type=Path, help="CSV WooCommerce de sortie")
    parser.add_argument("--images-zip", type=Path, help="ZIP contenant les images fournisseur")
    parser.add_argument("--resume-session", type=Path, help="Reprendre la seconde étape depuis le fichier *_session.json")
    parser.add_argument("--images-url", help="URL WordPress de base des images")
    parser.add_argument("--no-web-descriptions", action="store_true", help="Désactiver la récupération des descriptions fournisseur")
    parser.add_argument("--ocr-lang", help="Langue Tesseract facture, défaut fra")
    parser.add_argument("--force-ocr", action="store_true", help="Forcer OCR même sur PDF avec texte")
    parser.add_argument("--drive-url", help="Dossier Drive facture")
    parser.add_argument("--download-dir", type=Path, help="Dossier du cache et des rapports images facture")
    parser.add_argument("--refresh-drive", action="store_true", help="Relire la liste Drive")
    parser.add_argument("--plan-images", action="store_true", help="Lister les images correspondantes sans téléchargement")
    parser.add_argument("--workers", type=int, default=4, help="Analyses de dossiers simultanées (1 à 8)")
    parser.add_argument("--full-drive", action="store_true", help="Ignorer les filtres de dossiers, garder le filtre EAN des images")
    parser.add_argument("--download-workers", type=int, default=4, help="Téléchargements simultanés (1 à 8)")
    parser.add_argument("--refresh-descriptions", action="store_true", help="Relire les fiches facture sans cache")
    parser.add_argument("--wc-output", type=Path, help="Chemin du CSV WooCommerce facture final")
    parser.add_argument('--test-images', action='store_true', help='Limiter à 5 images et aux produits associés')
    parser.add_argument('--all-images', action='store_true', help='Télécharger toutes les images correspondantes')
    args = parser.parse_args()
    if args.test_images and args.all_images:parser.error('Choisir test ou toutes les images')

    print("==========================================")
    print("  CONVERTISSEUR FOURNISSEUR -> WOOCOMMERCE")
    print("==========================================")

    if args.resume_session:
        if args.supplier or args.source or args.output:
            parser.error('--resume-session reprend une préparation existante, sans --supplier, --source ni --output.')
        if not args.images_zip:
            parser.error('La seconde étape nécessite --images-zip.')
        return run_two_pass(session=args.resume_session, images_zip=args.images_zip)

    if args.supplier:
        try:
            config = resolve_profile(args.supplier)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        config = choose_supplier()

    source = args.source.expanduser().resolve() if args.source else choose_source_cli()

    print(f"\nFournisseur : {load_supplier_name(config)}")
    print(f"Source      : {source}")

    import json
    supplier_cfg = json.loads(config.read_text(encoding="utf-8"))
    if workflow_kind(supplier_cfg) == 'two_pass':
        if args.images_zip:
            parser.error('Préparer d’abord le catalogue sans ZIP, puis utiliser --resume-session avec --images-zip.')
        return run_two_pass(source, config, args.output, rules_path=args.product_rules, rebuild=args.rebuild_preparation)
    if workflow_kind(supplier_cfg) == 'invoice':
        try:
            return load_adapter(supplier_cfg['workflow']['adapter']).run(args, source, supplier_cfg)
        except Exception as exc:
            print(f'ERREUR lecture de facture : {exc}', file=sys.stderr)
            return 1

    image_settings = supplier_cfg.get("images", {})

    images_zip = args.images_zip
    images_url = args.images_url

    if image_settings.get("mode") == "zip_by_sku":
        if images_zip is None:
            value = input("\nChemin du ZIP images (Entrée = ne pas utiliser le ZIP) : ").strip().strip('"').strip("'")
            if value:
                images_zip = Path(value).expanduser().resolve()

        if images_zip is not None:
            if not images_zip.is_file():
                print(f"ZIP images introuvable : {images_zip}", file=sys.stderr)
                return 2

            default_url = str(image_settings.get("base_url", "")).strip()
            prompt = f"URL WordPress des images [{default_url}] : " if default_url else "URL WordPress des images : "
            if not images_url and image_settings.get('output_mode') != 'local':
                images_url = input(prompt).strip() or default_url

    print("\nConversion...")

    try:
        result = convert_catalogue(
            source_path=source,
            supplier_config_path=config,
            schema_path=SCHEMA,
            output_path=args.output,
            images_zip_path=images_zip,
            images_base_url=images_url,
            web_descriptions=False if args.no_web_descriptions else None,
            product_rules_path=args.product_rules,
        )
    except Exception as exc:
        print(f"ERREUR préparation : {exc}", file=sys.stderr, flush=True)
        return 1

    print("\n=== TERMINÉ ===")
    print(f"Lignes source : {result.source_row_count}")
    print(f"Exclues       : {result.excluded_count}")
    print(f"Fusionnées    : {result.merged_count}")
    print(f"Produits      : {result.row_count}")
    print(f"CSV      : {result.output_path}")
    print(f"Rapport  : {result.report_path}")

    if result.warnings:
        print("\nAvertissements :")
        for warning in result.warnings:
            print(f"  ! {warning}")

    if result.issues:
        print("\nMappings à contrôler :")
        for issue in result.issues:
            print(f"  ! {issue}")

    print("\nLe CSV WooCommerce a bien été généré.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
