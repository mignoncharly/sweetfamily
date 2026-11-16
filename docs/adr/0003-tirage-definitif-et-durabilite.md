# ADR-0003 — Tirage définitif et publication durable

Date : 15 novembre 2026. Statut : retenu pour la conception ; algorithme et performances non encore testés.

## Décision

Limiter l'effectif à 4–20. Avant tout tirage, vérifier un couplage parfait puis, pour chaque attribution réalisable fixée hypothétiquement, vérifier qu'aucun autre donneur n'a moins de deux destinataires possibles. Le contrôle porte sur les couplages complets, pas les seuls degrés du graphe. Échantillonner uniformément les couplages par DP sur sous-ensembles, entiers exacts et secrets.randbelow. Uniformité des couplages ne signifie pas égalité des probabilités marginales avec exclusions. Ne pas imposer de cycle unique.

Un job métier unique par événement ; commandes idempotentes, verrou événement, bail et tentative monotone. Calcul sur snapshot gelé hors transaction longue ; au commit, revérifier bail/snapshot/état/absence de résultat. Écrire atomiquement permutation chiffrée, état DRAWN et outbox retenue. Aucun résultat ne sort avant commit et preuve de durabilité : PENDING_DURABILITY puis AVAILABLE. Pour WAL/PITR, preuve d'archivage durable de la barrière après commit avec base exploitable, ou backup complet ponctuel vérifié. Le reçu ne contient pas la permutation.

## Alternatives et conséquences

Premier couplage trouvé, random, tri aléatoire, graine temporelle et reroll au renvoi ne satisfont pas le contrat. Un nouveau tirage après incident changerait les engagements déjà révélés. La confirmation de backup ajoute une attente visible mais évite de publier un résultat non récupérable. Retrait après scellement nécessite annulation explicite, jamais réparation silencieuse. Un résultat perdu après divulgation devient un incident.

Valider DP et arêtes conditionnelles contre énumération indépendante, propriétés sur graphes et tests PostgreSQL concurrents/crash/restauration. La limite de 20 et l'objectif de 60 secondes doivent être mesurés sans relâcher le contrôle. Cibles DRW-01 à DRW-05, T01/T04/T08–T10/T18/T26, C10. Aucun test statistique seul ne prouve l'uniformité.
