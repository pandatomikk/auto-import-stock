# ZPSI Media

Extension de test pour le renommage des images générées par ZPSI Catalogue. Installer le ZIP dans WordPress : Extensions → Ajouter une extension → Téléverser, puis activer.

L’outil utilise le compte WordPress et son mot de passe d’application déjà configurés. Ce compte doit pouvoir téléverser des fichiers et modifier le média concerné. L’extension n’ajoute aucun accès anonyme.

Avec `rename_existing_media: true` dans le fichier privé `client.json`, une image reconnue sans le suffixe du site est renommée avant son association au nouveau produit. Le nom complet hors suffixe, notamment l’identifiant de source de 12 caractères, doit correspondre. Le média conserve son identifiant, ses associations aux produits, son titre et son texte alternatif. Les nouvelles URL et métadonnées pointent vers les nouveaux noms. Les miniatures standard sont traitées également.

Les anciens fichiers restent accessibles afin que les URL inscrites dans d’anciens articles, thèmes ou caches continuent de fonctionner. Il n’y a aucune seconde entrée dans la médiathèque. Les fichiers utilisent des liens physiques quand le serveur le permet ; sinon des copies occupent temporairement davantage d’espace. Aucun nettoyage automatique des anciennes adresses n’est effectué.

Les fichiers hors du répertoire uploads local, liens symboliques, noms ambigus et destinations déjà utilisées sont refusés. Les bibliothèques externalisées vers un stockage distant ne sont pas prises en charge. Le renommage des images aux noms arbitraires ou éditées par WordPress n’est pas garanti : le module limite les opérations aux noms générés reconnus.

Un verrou empêche les renommages simultanés effectués par cette extension. Les anciennes métadonnées sont conservées dans `_zpsi_media_rename_backup`. En cas d’erreur détectée, les références sont restaurées ; les anciennes adresses restent disponibles. Après une réponse perdue, relancer le contrôle permet de retrouver le même média. En cas de collision réelle, aucune autre image n’est écrasée et aucun nouvel envoi n’est tenté.

Tests disponibles : `php tests/php/test_media_rename.php` utilise des doubles des fonctions WordPress pour vérifier le même identifiant, les anciennes URL, les miniatures, l’idempotence, les collisions et le retour arrière. Une validation sur une installation WordPress de test est nécessaire avant utilisation générale.
