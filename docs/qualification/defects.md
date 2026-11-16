# Défauts et critères non clos — phase 9

| ID | État | Conséquence et résolution attendue |
|---|---|---|
| PERF-01 | OPEN / cible non atteinte | Dernier p95 phase 10 : 725 ms portail et 1401 ms coffre, cible 500 ms. Mesures locales sans limites de ressources ; profiler et qualifier l’hôte de référence. Les valeurs de phase 9 restent historiques. Aucun engagement de capacité pour la production. |
| REC-01 / T18 | PASS_LOCAL phase 10 / production ouverte | Restauration native isolée, maintenance, contrôle du résultat, clôture des anciens jobs et rétention des envois exercés. Stockage indépendant, réconciliation fournisseur réelle et RPO/RTO à qualifier. Voir phase-10.md. |
| RET-01 / T20 | PASS_LOCAL phase 10 / copies externes ouvertes | Purge J+90, reçus externes avant commit, replay de suppression et de demande de compte, backup ancien réellement restauré puis repurgé. Inventaire des copies externes/anciennes et réduction contrôlée du registre restent opérateur. |
| A11Y-01 / T22 | PARTIAL | Téléphone, lecteur d’écran et zoom manuel non exécutés ; protocole manual-gates.md. |
| MAIL-01 / T23 | BLOCKED, différé utilisateur | Secrets/configuration gtech à fournir localement plus tard ; vérifier sender/domaine et remise à la boîte autorisée, sans divulguer de secret. |
| IND-01 | BLOCKED | Opérateur, DNS, ressources, clés et récupération indépendants non démontrés ; revue de sécurité externe de la version exacte requise. |

Aucune défaillance critique de confidentialité, intégrité du tirage, authentification ou perte de
données n’a été détectée par les tests exécutés. Cela ne ferme pas les critères ci-dessus et ne
prouve pas l’absence de défaut inconnu. `verify-release` reste bloqué. La phase 10 peut implémenter
les travaux locaux nécessaires ; elle ne doit pas ouvrir la production avant requalification.
