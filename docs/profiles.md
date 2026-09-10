# Profils et adaptateurs

Le moteur sert de base multimarque et multisecteur. Les particularités d’un fournisseur sont décrites dans un profil ou un adaptateur local ; elles ne doivent pas être ajoutées sous forme de conditions sur son nom dans l’interface ou le moteur commun.

## Ajouter un profil

Copier `profiles/demo.json` dans `private/profiles/mon_profil.json`, enlever `demo: true`, puis ajuster les champs. Le nom du fichier constitue l’identifiant utilisé par `--supplier`.

| Champ | Rôle |
|---|---|
| `supplier_name` | Libellé affiché |
| `workflow.kind` | `catalogue` (défaut), `two_pass` ou `invoice` |
| `source_options` | Ligne d’en-tête Excel, colonnes permettant de la trouver, ou lecteur local |
| `required_columns` | Colonnes obligatoires |
| `force_mapping` | Correspondance des champs logiques vers les colonnes source |
| `mapping_only` | Désactivation des correspondances automatiques |
| `aliases` | Synonymes supplémentaires pour détecter les colonnes |
| `positive_quantity_columns` | Colonnes de quantité filtrées et validées |
| `exclude_rules` | Lignes à exclure |
| `duplicate_handling` | Stratégie de regroupement et champs à additionner |
| `product_name`, `short_description`, `description_generator` | Construction des textes |
| `category_rules`, `attribute_rules` | Classement et attribut simple |
| `images` | Mode, dossier de sortie et motif des noms |
| `supplier_descriptions` | Adaptateur optionnel de descriptions |
| `export_ean_text` | Liste EAN, requise pour le parcours `two_pass` |

La publication est fixée à `1` par le moteur. Les possibilités de configuration des attributs ne constituent pas encore une génération de variations WooCommerce.

## Ajouter un format d’entrée

Pour un format qui peut être ramené à des lignes de catalogue, préférer un **lecteur**. Le profil contient :

```json
{
  "source_options": {"adapter": "mon_lecteur"},
  "force_mapping": {"sku": "reference", "name": "designation"}
}
```

Dans `private/adapters/mon_lecteur.py` :

```python
def read_source(path, options):
    # Lire le document, contrôler son format, puis renvoyer ses données.
    headers = ["reference", "designation"]
    rows = [{"reference": "ITEM100", "designation": "Article exemple"}]
    return headers, rows
```

L’exemple ci-dessus est fictif ; le vrai lecteur doit extraire les valeurs du document. Le moteur commun conserve la responsabilité du mapping, des transformations et du CSV WooCommerce.

## Définir un motif de photos

Le parcours `two_pass` accepte un motif `images.filename_pattern` avec des groupes nommés `article`, `color` et, éventuellement, `order` :

```json
{
  "images": {
    "mode": "zip_pattern",
    "directory": "images_mon_profil",
    "filename_pattern": "^PHOTO_(?P<article>[^_]+)_(?P<color>[^_]+)(?:_(?P<order>\\d+))?$"
  }
}
```

Le motif s’applique au nom sans extension. La correspondance exige l’article et le code ou le libellé de couleur. Les références utilisées sont enregistrées pendant la première étape. Un EAN exact dans le nom du fichier ou du dossier produit peut aussi identifier une photo. Une correspondance ambiguë provoque une erreur.

## Ajouter un enrichissement

Le profil active `supplier_descriptions.enabled` et renseigne `supplier_descriptions.adapter`. Le module correspondant fournit une classe `SupplierDescriptions(settings)` :

- `get(values)` renvoie un texte ou `None` pour conserver le contenu source ;
- `records` contient le diagnostic par produit, avec notamment `status: retrieved` ou `status: fallback`.

L’adaptateur réalise les contrôles d’identité, accès distants, délais et éventuels caches propres au fournisseur.

## Parcours documentaire complet

Si le traitement nécessite plus qu’un lecteur, le profil peut sélectionner :

```json
{"workflow": {"kind": "invoice", "adapter": "mon_parcours"}}
```

Le module fournit `run(args, source, profile)` et renvoie un code de sortie. Cette extension sert aux parcours documentaires existants. Pour les nouveaux développements, réutiliser autant que possible le schéma et l’écriture CSV communs.

## Distribution et mises à jour

Les packs sont des fichiers locaux de confiance : leurs adaptateurs exécutent du Python. Aucun pack n’est téléchargé automatiquement. Distribuer séparément `profiles/`, `rules/` et `adapters/` dans le dossier privé ; une installation publique seule utilise les exemples fictifs.

`AUTO_IMPORT_PRIVATE_DIR` permet de désigner un autre emplacement. Un pack ne doit pas contenir de données de boutique dans les profils publics ou les tests publics. Le dossier privé peut disposer de son propre dépôt privé, indépendamment du dépôt du moteur.
