# Mise à jour des packs clients

Le moteur public et le pack privé sont deux dépôts distincts. Le pack contient à sa racine `client.json`, `profiles/`, `rules/` et `adapters/`. Les documents fournisseurs, lots, sauvegardes et identifiants de boutique ne doivent pas être ajoutés au dépôt.

`client.json` accepte `image_filename_suffix`. Exemple fictif : `{"image_filename_suffix":"www.example.fr"}`. Les images nouvellement préparées portent ce suffixe avant `.webp`, et les CSV utilisent les mêmes noms. Les images déjà publiées ne sont pas renommées.

## Installation initiale

Installer le moteur compatible depuis la branche dev pour tester cette fonctionnalité. Copier le pack initial complet dans le dossier `private` de l’installation. Le pack fourni peut inclure `.sync-state.json` pour identifier sa révision et détecter ensuite les modifications locales. Ce fichier est local et exclu du dépôt.

Ouvrir **Paramètres → Pack client…**, renseigner le dépôt `compte/dépôt`, la branche de diffusion, et un jeton GitHub à accès fin limité à ce seul dépôt avec **Contents: Read-only**. Ce jeton est conservé dans le coffre du système, jamais dans le pack. Un jeton expiré doit être remplacé dans cette fenêtre.

La synchronisation se déclenche avec **Recevoir les mises à jour**. Elle effectue uniquement des lectures GitHub. Elle valide et télécharge tous les fichiers avant de les appliquer. Elle refuse les conflits avec les modifications locales et conserve les réglages locaux lorsque leur version distante n’a pas changé. Les règles produits personnelles stockées hors du pack ne sont pas touchées.

Après succès, fermer puis rouvrir l’application pour charger les profils et adaptateurs. La mise à jour du moteur suit `main` par défaut, ou `dev` pour une distribution de test marquée ainsi. Elle est indépendante de la branche choisie pour le pack privé.

En cas de conflit lors d’une première synchronisation, comparer les fichiers indiqués avec le pack fourni : aucune fusion implicite ni écrasement n’est effectué. Sauvegarder et résoudre ces différences avant de relancer.

Les adaptateurs sont du code Python exécuté localement : utiliser uniquement le dépôt du prestataire attendu. Un renommage du dépôt ou une redirection GitHub n’est pas suivi automatiquement avec le jeton ; mettre à jour le nom du dépôt dans la configuration.
