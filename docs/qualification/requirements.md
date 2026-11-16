# Exigences et preuves — phase 9

La matrice T01–T26 de matrix.md est construite à partir des cas JUnit réellement exécutés.
Les lignes suivantes relient les familles d’exigences du produit à cette matrice ; elles ne
transforment pas une vérification locale en garantie de production.

| Exigences du produit | Scénarios et preuves | Limite |
|---|---|---|
| IDN-01/02/03, API-01 | T06, T07, T13, T24 ; suites vault/control, expiration/limites code, MFA, correction, CSRF, signature/nonce/replay | Récupération et opérateur indépendants à qualifier en production |
| CTY-01, DLV-01 | T01, T14, T24 ; huit FR/DE dans la chaîne native, conseils selon pays propre, profil et manifeste | Aucun achat/livraison marchand garanti |
| WSH-01/02/03, BUD-01, URL-01 | T05, T14, T16 ; centimes exacts, trois souhaits, conflits, historique et URLs refusées sans fetch | Aucun prix ou stock marchand vérifié |
| CNS-01 | T04, T24 ; même manifeste, confirmations et invalidations structurelles | Identité réelle non prouvée par email seul |
| DRW-01/02/03 | T01, T03, T04 ; référence exhaustive quatre personnes, graphes Hypothesis jusqu’à huit, DP/poids exacts, secrets de production | Mesure maximale locale, sans preuve de capacité d’hôte de production |
| DRW-04/05 | T08, T09, T10, T18, T26 ; 20 appels concurrents, deux workers, fences, commit/rollback et restore natif ; opérations de phase 10 | Maintenance/replay locaux exercés en phase 10 ; infrastructure indépendante à qualifier |
| PRV-01/02/03/04 | T02, T07, T13, T15, T16, T17, T21 ; allowlists, SQL portail, logs, CSV, en-têtes, ancien onglet et purge de phase 10 | Indépendance et revue externe non démontrées ; copies externes à inventorier |
| Notifications et rappels | T11, T12, T23, T25 ; vrais SDK/signatures, doubles de pannes documentés, SMTP local réel | T23 bloqué sur essai externe différé ; pas de preuve de remise réelle |
| Accessibilité et cas de vie | T19, T21, T22 ; Chromium, clavier, erreurs, reprises et scans Axe | T22 partiel : téléphone, lecteur d’écran et zoom manuel non exécutés |
| Conservation, restauration et remise | T18, T20 ; pg_dump/pg_restore natifs, repurge d'un ancien backup, registre externe et récupération de phase 10 | Voir phase-10.md ; déploiement, stockage indépendant et RPO/RTO restent ouverts |

Le scan de canaris complète la revue des champs et permissions, il ne suffit pas à la prouver.
Les cas imbriqués des services ne s’additionnent pas aux cas racine comme preuves indépendantes.
