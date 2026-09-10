# Auto Import Stock · V0.10

**Une base multimarque pour transformer les données fournisseurs en catalogues WooCommerce.**

Auto Import Stock prépare les fiches produit, les quantités et les images à partir de documents fournisseurs. Le moteur commun est indépendant d’une marque ou d’un secteur : les entrées et les règles métier sont définies par des profils, la destination reste **WooCommerce**.

Cette V0.10 est la base de travail du projet. Elle peut être adaptée à la maroquinerie, au vêtement ou à d’autres commerces, en ajoutant les profils et traitements nécessaires.

> Le dépôt public contient le moteur, les interfaces et des données fictives. Les profils réels, les règles commerciales, les liens fournisseurs et les adaptateurs spécifiques sont distribués séparément dans un **pack privé**.

[Démarrer](#démarrer) · [Parcours](#parcours-disponibles) · [Packs privés](#profils-et-packs-privés) · [Compatibilité WooCommerce](#compatibilité-woocommerce) · [Développement](#développement)

## Une base, plusieurs entrées

```text
Document fournisseur
        │
        ▼
Lecture standard ou adaptateur d’entrée
        │
        ▼
Profil : colonnes, identifiants, règles et enrichissement
        │
        ▼
Moteur commun : conversion, images et contrôles
        │
        ▼
CSV WooCommerce + médias + rapport
```

| Cas de figure | Processus prévu |
|---|---|
| Catalogue Excel ou CSV | Lecture, correspondance des colonnes et export WooCommerce |
| Catalogue accompagné d’un ZIP de photos | Association par identifiant et préparation des images |
| Photos à récupérer sur une plateforme | Première préparation, liste de références, pause, puis finalisation avec le ZIP |
| Document PDF ou scanné | Lecture spécialisée et OCR via un adaptateur local optionnel |
| Format fournisseur particulier | Adaptateur d’entrée renvoyant les données au moteur commun |
| Descriptions à enrichir | Adaptateur local optionnel, avec conservation des données source en cas de repli prévu par l’adaptateur |

Les parcours Excel/CSV et la préparation en deux étapes sont inclus dans le moteur public. Les services distants et formats de facture spécifiques nécessitent leur pack d’adaptation.

## Démarrer

### Prérequis

- Python **3.10 ou supérieur**.
- Tkinter/Tcl-Tk pour l’interface graphique.
- `openpyxl`, `Pillow` et `gdown`, installés depuis `requirements.txt`.
- Poppler et Tesseract pour les packs utilisant PDF/OCR.

```bash
git clone https://github.com/pandatomikk/auto-import-stock.git tool-auto-import-stock
cd tool-auto-import-stock
python3 client.py
```

Sous Windows : `py -3 client.py`.

Le lanceur prépare un environnement `.venv` lors du premier traitement. Internet est nécessaire pour installer les dépendances ; un traitement entièrement local peut ensuite fonctionner hors ligne.

| Système | Lanceur graphique |
|---|---|
| Windows | `Ouvrir-Windows.bat` ou `Ouvrir-Windows.vbs` |
| Linux | `./Ouvrir-Linux.sh` |
| macOS | `Ouvrir-macOS.command` |

Sur Debian/Ubuntu, installer `python3-tk` et `python3-venv`. Ajouter `poppler-utils`, `tesseract-ocr` et les langues OCR nécessaires si le pack choisi les utilise.

### Démonstration sans pack privé

Le dépôt fonctionne avec `profiles/demo.json` et `examples/catalogue.csv`, qui contiennent uniquement des exemples fictifs. Quand des profils métier sont installés, ils prennent la place du profil de démonstration dans la liste de sélection.

```bash
# Étape 1 : CSV de préparation et liste EAN
python3 lancer.py --supplier demo --source examples/catalogue.csv

# Étape 2 : utiliser un ZIP avec les photos de démonstration
python3 lancer.py --resume-session examples/catalogue_woocommerce_session.json \
  --images-zip /chemin/photos-demo.zip
```

Le profil de démonstration reconnaît, par exemple, `PHOTO_ITEM100_001.jpg` et `PHOTO_ITEM100_001_2.jpg`. Il faut fournir ses propres images d’essai portant ces noms. Les conventions des profils réels restent dans le pack privé.

### Installation Windows

`Installer-Windows.cmd` installe les composants avec WinGet et prépare l’application dans `%LOCALAPPDATA%\ZPSI\Catalogue`, avec des raccourcis Bureau et menu Démarrer. Il s’agit d’un installateur en ligne, pas d’un exécutable autonome.

Si le dossier source contient un pack `private/`, ses profils, règles et adaptateurs opérationnels sont copiés dans l’installation. Les sauvegardes, tests privés et données d’exemple métier ne sont pas copiés. Une mise à jour conserve les correspondances personnalisées tout en actualisant les références aux adaptateurs. Les anciennes configurations locales connues sont migrées vers le pack privé de l’installation.

## Parcours disponibles

### Conversion directe

Sélectionner un profil, le catalogue et, si demandé, le ZIP d’images. Le moteur associe les colonnes aux champs WooCommerce, applique les règles du profil et produit un CSV accompagné de son rapport.

### Préparation en deux étapes

1. **Préparer le CSV et les EAN** : génération d’un CSV intermédiaire, d’une liste EAN et d’un fichier de session.
2. **Pause** : récupérer manuellement les photos sur la plateforme fournisseur.
3. **Finaliser avec les images** : choisir le ZIP, associer les photos et produire le CSV final.

La préparation est enregistrée sur disque. Après fermeture, sélectionner à nouveau le catalogue retrouve la session en attente ; **Reprendre une préparation…** permet aussi de sélectionner directement son fichier `*_session.json`.

La seconde étape réutilise le CSV préparé et conserve les corrections qui y ont été apportées. Le catalogue d’origine n’a plus besoin d’être présent. Les fichiers de préparation peuvent être déplacés ensemble.

Une association image doit être univoque. Un ZIP sans correspondance ou une image illisible ne valide pas la finalisation. Les produits sans photo dans un lot partiellement couvert restent dans le CSV et sont signalés dans le rapport et le message de fin.

### Images et reprise

Les images traitées localement sont converties en **WebP, qualité 85**, avec un côté maximal de **1 600 pixels**, sans agrandissement. Les fichiers terminés sont réutilisables après une interruption.

Le bouton **Arrêter** termine le processus de travail. La relance réutilise les fichiers disponibles ; ce bouton est distinct de la pause volontaire entre les deux étapes. Éviter les traitements simultanés vers le même dossier.

## Profils et packs privés

```text
profiles/                 Profils fictifs distribués avec le moteur
private/                  Hors du suivi Git
  profiles/               Correspondances et paramètres des fournisseurs
  rules/                  Règles métier particulières
  adapters/               Lecteurs et intégrations spécifiques
```

Le dossier `private/` est local et ignoré par Git. Il n’est ni envoyé ni sauvegardé automatiquement sur GitHub. Il peut être conservé dans un stockage privé ou un dépôt privé séparé ; il faut le transmettre séparément pour retrouver les profils métier sur une autre machine.

La variable `AUTO_IMPORT_PRIVATE_DIR` permet de placer ce pack en dehors du dossier de l’application.

Un profil peut définir les colonnes d’entrée, les identifiants, les filtres, la gestion des doublons, les noms, les descriptions, les catégories et les règles d’association des images. Un nouveau format de fichier peut fournir un adaptateur sans dupliquer l’export WooCommerce.

Le détail des points d’extension est documenté dans [le guide des profils et adaptateurs](docs/profiles.md).

## Compatibilité WooCommerce

La destination de référence est l’**importateur CSV natif de WooCommerce**. Le schéma partagé est dans `schemas/woocommerce.json` ; ses libellés sont actuellement en français. L’écran de correspondance de WooCommerce permet d’associer les colonnes lorsque leur reconnaissance automatique diffère selon la boutique.

- CSV à virgules en UTF-8 avec BOM ; les champs contenant des virgules sont correctement délimités.
- Tous les exports demandent le statut **publié** (`Publié = 1`).
- Identifiants conservés comme du texte pour préserver les zéros initiaux.
- Images référencées par leur nom lorsqu’elles sont préparées pour un téléversement préalable, ou par une URL directe selon le profil.
- Aucun champ technique obligatoire propre à un plugin métier n’est ajouté par défaut.

WooCommerce permet d’associer des images déjà présentes dans la médiathèque par leur nom. Téléverser les images avant le CSV et vérifier le mapping des champs. Les conventions CSV et le statut publié suivent la [documentation officielle WooCommerce](https://woocommerce.com/document/product-csv-importer-exporter/).

Les quantités proviennent du document : aucun rapprochement avec le stock réel ni suivi de réception n’est effectué. Les prix ne subissent pas de conversion HT/TTC automatique. Les catégories, unités, identifiants et paramètres de prix doivent correspondre à la boutique cible.

**La base actuelle génère des produits simples.** Le support complet des produits variables, tailles, couleurs et relations parent/variation est une évolution à réaliser explicitement, notamment pour le vêtement. Une simple modification de profil ne crée pas encore ces relations automatiquement.

## Fichiers produits

| Résultat | Rôle |
|---|---|
| `*_woocommerce.csv` | CSV final destiné à l’import |
| `*_woocommerce_rapport.json` | Bilan et anomalies à contrôler |
| `*_woocommerce_preparation.csv` | Première étape, avant association des images |
| `*_woocommerce_preparation_ean.txt` | EAN à utiliser sur la plateforme fournisseur |
| `*_woocommerce_session.json` | État et paramètres nécessaires à la reprise |
| `images_*/fichiers_webp/` | Images préparées pour la médiathèque |
| `diagnostic_DATE_HEURE.txt` | Journal du traitement graphique |

Les sorties se trouvent à côté du document par défaut. `--output` permet de choisir le CSV final ou son futur emplacement pour une préparation en deux étapes. Les adaptateurs peuvent produire des fichiers de contrôle supplémentaires.

## Développement

```text
client.py                  Interface graphique et progression
lancer.py                  Environnement Python et lancement
convertisseur.py           Commandes et sélection du parcours
core/
  profiles.py              Découverte des profils et chargement des adaptateurs
  io.py                    Lectures standard, adaptateur d’entrée et écriture CSV
  converter.py             Correspondances, transformations et export commun
  matcher.py               Détection des colonnes
  normalization.py         Normalisation des libellés
  media_workflow.py        Préparation persistante en deux étapes
  images.py                Traitement des ZIP par identifiant
  image_webp.py            Conversion des images
  enrichment.py            Interface d’enrichissement optionnel
  shared.py                Validations et écriture JSON
schemas/                   Contrat de sortie WooCommerce
profiles/, examples/       Démonstration fictive
tests/                     Tests du moteur public
```

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Sous Windows, remplacer `.venv/bin/python` par `.venv\Scripts\python.exe`. Les tests graphiques sont ignorés si aucun écran n’est disponible. Les tests propres à un pack restent avec ce pack.

L’installation Windows complète, les traitements OCR réels et l’import dans une boutique WooCommerce doivent être vérifiés dans leurs environnements cibles. Le projet prépare des fichiers : il ne publie pas directement dans WordPress et n’effectue pas de synchronisation automatique par API.
