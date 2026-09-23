# Livraisons

À chaque passage en production (dev vers main), incrémenter le numéro dans core/version.py (0.21, puis 0.22, etc.), mettre à jour les notes README, exécuter les tests et vérifier les CI Windows/Linux. Créer le tag v<version> sur la révision livrée. Les travaux intermédiaires restent sur dev. Les profils clients restent dans le dépôt privé ; livrer sa branche main compatible après le moteur.
