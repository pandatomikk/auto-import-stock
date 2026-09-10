# Auto Import Stock · V0.20

**Moins de saisie, plus de temps pour votre commerce : préparez et ajoutez vos produits sur WooCommerce à partir des fichiers de vos fournisseurs.**

Vous recevez un catalogue Excel, une facture ou un dossier de photos et devez tout reprendre pour votre boutique en ligne ? Auto Import Stock est né de ce besoin : simplifier la préparation des fiches produit, des quantités et des images, puis leur mise en ligne sur **WooCommerce**.

L’outil s’adresse aux commerçants qui souhaitent réduire les manipulations répétitives. Il propose plusieurs parcours selon les documents disponibles et peut être adapté à différents fournisseurs et secteurs. Certaines adaptations nécessitent un profil ou un traitement spécifique : il ne reconnaît pas encore automatiquement tous les formats.

## Besoin d’un accompagnement ?

Je peux vous accompagner dans la mise en place de votre boutique WooCommerce, son déploiement, l’installation de cet outil et son adaptation à vos fichiers fournisseurs. L’objectif est de construire un fonctionnement adapté à votre commerce et de vous aider à le prendre en main.

**Pour présenter votre projet ou échanger sur vos besoins : [ZPSI — zpsi.fr](https://zpsi.fr).**


## État du projet

La V0.10 a établi la base multimarque. La V0.20 ouvre le chantier de connexion à WordPress et WooCommerce, avec la configuration des accès, l’envoi d’une image dans la médiathèque et la création d’articles depuis un CSV WooCommerce. Elle peut être adaptée à la maroquinerie, au vêtement ou à d’autres commerces, en ajoutant les profils et traitements nécessaires.

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
  shop_connection.py       Authentification et tests API en lecture seule
  shop_ui.py               Configuration de la boutique
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

L’installation Windows complète, les traitements OCR réels et l’import dans une boutique WooCommerce doivent être vérifiés dans leurs environnements cibles. Le projet prépare les fichiers produits et permet un test d’envoi d’image dans WordPress. Il peut créer des produits publiés depuis un CSV contrôlé ; il ne met jamais à jour les produits existants et n’effectue pas encore le parcours complet automatiquement.

## Connexion à la boutique · V0.20

Dans le client, cliquez sur **Ma boutique**. Renseignez l’adresse HTTPS du site, votre identifiant WordPress, un mot de passe d’application WordPress, ainsi que la clé client et le secret WooCommerce.

- WordPress : **Utilisateurs → Profil → Mots de passe d’application**. Le compte doit disposer des droits nécessaires pour les futurs envois de médias.
- WooCommerce : **Réglages → Avancé → API REST → Ajouter une clé**, avec accès **Lecture/Écriture** pour la suite du chantier.
- Cliquez sur **Tester la connexion**. Les résultats WordPress et WooCommerce sont séparés : l’un peut réussir tandis que l’autre échoue.

Le test authentifie l’utilisateur WordPress et consulte ses capacités, puis lit au maximum un identifiant de produit via WooCommerce. Il ne crée et ne modifie rien. Une lecture réussie ne garantit pas les droits d’écriture des clés WooCommerce ; ceux-ci seront contrôlés lors du chantier d’import.

Les accès peuvent être mémorisés avec **Enregistrer les accès**. L’installation Windows et le démarrage du client créent les dossiers `private/profiles`, `private/rules` et `private/adapters`, ainsi que la configuration utilisateur : `~/.config/auto-import-stock/` sous Linux (ou `$XDG_CONFIG_HOME/auto-import-stock/`) et `%LOCALAPPDATA%/auto-import-stock/` sous Windows. `shop.json` ne contient que l’adresse et l’identifiant ; `secrets/shop.enc` contient les secrets chiffrés par Fernet. La clé reste dans le coffre du système via keyring, séparément du fichier (gestionnaire Windows, trousseau macOS ou Secret Service/KWallet sous Linux). Ces données sont hors Git et conservées par les mises à jour.

Un coffre système disponible et déverrouillé est requis pour mémoriser les secrets. Aucun stockage en clair de secours n’est utilisé. Sous Linux, installez/configurez un trousseau de session tel que GNOME Keyring si nécessaire. La protection de ce trousseau dépend de la configuration du système. Les anciens secrets en clair sont migrés à l’ouverture de Ma boutique ou pendant l’installation Windows : le JSON est nettoyé seulement après réussite du stockage chiffré. En cas d’échec, un message est affiché et le fichier d’origine est conservé pour éviter la perte des accès. Les copies de sauvegarde anciennes ne sont pas modifiées.

Décochez la mémorisation puis enregistrez pour supprimer le fichier chiffré. Copier ce fichier sur un autre poste ne suffit pas à récupérer les accès : la clé appartient au coffre du compte système.

Utilisez l’adresse définitive du site (avec son sous-dossier éventuel), sans `/wp-admin` ni `/wp-json`. HTTPS et un certificat valide sont requis ; les redirections sont refusées pour protéger les identifiants. Cette première version cible les installations WordPress/WooCommerce exposant les API standard `/wp-json/`.

L’envoi des images par lots et l’enchaînement automatique sources → images WordPress → CSV → création des articles feront l’objet des étapes suivantes. Les mises à jour de produits restent hors du périmètre actuel. L’export CSV actuel reste disponible.

Références : [clés WooCommerce](https://woocommerce.com/document/woocommerce-rest-api/) et [mots de passe d’application WordPress](https://developer.wordpress.org/advanced-administration/security/application-passwords/).

### Tester l’envoi d’une image

Dans **Ma boutique**, choisissez une image puis cliquez sur **Envoyer l’image sur ce site**. Cette action crée réellement un média WordPress, sans créer de produit. Formats : JPEG, PNG, WebP ; maximum local de 20 Mo, soumis également à la limite du serveur. Le fichier est envoyé tel quel, sans conversion. L’identifiant et l’URL retournés permettent de vérifier le résultat dans la médiathèque.

Chaque nouvel envoi crée un média : cette étape ne détecte pas encore les doublons. En cas d’envoi non confirmé, vérifiez la médiathèque avant de réessayer. Aucun nouvel essai automatique n’est effectué.

### Évolution conservée pour plus tard

Prévoir des connecteurs vers les API de données et d’images des fournisseurs, distincts des profils de transformation. Les développer à partir de cas réels ; ce chantier est différé au profit de l’import WordPress/WooCommerce.

### Tester la création d’articles depuis un CSV

Dans **Ma boutique → Importer un CSV d’articles**, sélectionnez un **CSV WooCommerce UTF-8 avec les colonnes françaises de l’outil**. Les séparateurs virgule, point-virgule et tabulation sont détectés. Le contrôle est en lecture seule : il affiche les nouveaux articles, les UGS existantes à ignorer et les erreurs. Cliquez ensuite sur **Créer et publier les … nouveaux articles** pour effectuer l’envoi réel. Le fichier est lu localement puis traduit en requêtes JSON de création, conformément à l’[API produits WooCommerce](https://developer.woocommerce.com/docs/apis/rest-api/v3/products/).

- Produits simples uniquement, avec UGS et nom obligatoires, ID vide et statut publié. Aucune mise à jour ni suppression.
- Les UGS déjà présentes sont ignorées, avec un second contrôle immédiatement avant chaque création. Les UGS en double dans le CSV bloquent l’envoi.
- Les prix, stocks, descriptions, EAN, dimensions, catégories, marques, étiquettes et attributs sont repris lorsqu’ils sont renseignés. Les colonnes non prises en charge mais renseignées bloquent le lot, plutôt que d’être omises silencieusement. Les unités de poids et dimensions de la boutique doivent correspondre au CSV.
- Les catégories (y compris `Parent > Enfant`), marques, étiquettes et attributs globaux doivent déjà exister dans la boutique. Les noms de marques et catégories différents du CSV peuvent être associés manuellement aux destinations du site. Ce test ne crée pas ces référentiels.
- La colonne Images accepte les URL exactes WordPress ou les noms de fichiers uniques présents dans sa médiathèque. L’outil retrouve les identifiants des médias et les associe sans les télécharger à nouveau. Une image absente ou ambiguë bloque le lot. Une colonne Images vide crée un article sans photo.
- Toute erreur de contrôle bloque l’ensemble de l’envoi. Les données de l’aperçu sont conservées en mémoire : après modification du CSV, sélectionnez-le à nouveau.
- Un rapport `rapport_import_*.json` est enregistré à côté du CSV, avec les créations, les articles ignorés et les envois non confirmés. Une erreur de création arrête le lot sans nouvel essai automatique ; vérifiez le rapport et la boutique avant une nouvelle sélection du CSV.

- ## Pourquoi ce projet, et comment il est développé

Je ne suis pas développeur de métier. J’avais des demandes concrètes de commerçants, mais ni les compétences ni le temps nécessaires pour développer seul l’outil de manière classique, et personne de disponible pour le réaliser. J’ai donc choisi de le construire avec l’aide de l’IA, dans une démarche souvent appelée « vibe coding ».

Ce choix m’a permis de transformer un besoin de terrain en une base utilisable. Le code reste un chantier en évolution : il comporte des tests automatisés, mais ceux-ci ne garantissent pas la prise en charge de tous les fournisseurs ni de toutes les configurations WooCommerce.

Le code de ce dépôt est **open source, sous [licence MIT](LICENSE)** : vous pouvez l’utiliser, le modifier, le redistribuer et l’intégrer à un projet commercial, en conservant la notice de licence. Les packs privés ne font pas partie de ce dépôt.

Si vous êtes développeur, cette origine fait partie du contexte du projet. Les retours, corrections, améliorations d’architecture et propositions de réécriture sont les bienvenus. Vous souhaitez reprendre tout ou partie de l’outil et le réécrire à la main ? C’est aussi une contribution bienvenue. Le but est de disposer d’un outil utile, compréhensible et durable pour les commerçants.

Commencez avec un petit lot. Le scénario complet prévu ensuite est : fournir les sources, préparer et envoyer les images, renseigner le CSV avec leurs URL WordPress, attendre la fin des images puis créer les articles. Cette étape teste seulement la dernière partie, avec des images déjà présentes sur le site.

### Sélection des fichiers sous Linux

Les boutons de sélection utilisent le sélecteur natif GNOME via Zenity, ou KDE via KDialog selon le bureau. Sous GNOME, la fenêtre utilise les conventions du bureau et complète Nautilus ; elle ne lance pas Nautilus comme sélecteur. Si aucun de ces composants n’est disponible, le sélecteur Tkinter reste utilisé. Sur Debian/GNOME, Zenity s’installe avec `sudo apt install zenity`.

### Suivre une préparation

Le client affiche l’étape courante (lecture du catalogue, indexation du ZIP, descriptions fournisseur, conversion WebP, écriture des fichiers), la référence en cours et les compteurs disponibles. Le temps écoulé reste visible ; après 15 secondes sans nouvel événement, une indication d’attente apparaît. Elle ne prouve pas un blocage : une opération disque ou réseau peut encore être en cours. **Voir le journal** ouvre le diagnostic du traitement.

Un CSV WooCommerce déjà préparé doit passer par **Ma boutique → Importer un CSV d’articles**. Le moteur de préparation le signale avant d’indexer les photos : utilisez le catalogue fournisseur original pour refaire une préparation.

### Correspondances des marques et catégories

À la sélection du CSV, une fenêtre compare ses libellés de marques et catégories à ceux de la boutique. Elle affiche les correspondances exactes, les choix mémorisés et les suggestions à valider. Par exemple, un nom court dans le CSV peut être associé au nom commercial complet de la boutique.

Sélectionnez une ligne et choisissez sa destination dans la liste. Les catégories sont affichées avec leur chemin complet pour distinguer les noms identiques sous différents parents. Vous pouvez corriger n’importe quelle proposition, même une correspondance exacte. Cliquez sur **Mémoriser et valider ces correspondances** pour poursuivre le contrôle des articles. Une suggestion ne devient jamais une association sans cette validation. Une ligne sans destination bloque la validation.

Les choix sont mémorisés par adresse de boutique dans le dossier local `auto-import-stock/correspondances/`, à côté de `shop.json`, hors GitHub. Ils sont réutilisés lors des prochains imports et restent modifiables avec **Revoir les correspondances…**. Une destination supprimée doit être remplacée manuellement. Les associations utilisées figurent dans le rapport d’import. Le CSV et les noms présents sur la boutique ne sont pas modifiés ; seules les associations des nouveaux articles utilisent les identifiants choisis.
