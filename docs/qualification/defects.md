# Défauts et critères non clos — phase 9

| ID | État | Conséquence et résolution attendue |
|---|---|---|
| PERF-01 | PASS_LOCAL Ubuntu / production ouverte | P95 final 282,695 ms portail et 327,425 ms coffre, cible 500 ms atteinte avec 2 processus × 2 threads par rôle. Rendu et lectures SQL optimisés, mêmes 40 clients/400 GET. Le mode 1 × 4 reste au-dessus côté coffre. HTTPS, limites CPU/RAM et hôte de production restent à qualifier ; aucun engagement de capacité. Voir ubuntu-2026-11-16.md. Les mesures Windows restent historiques. |
| REC-01 / T18 | PASS_LOCAL phase 10 / production ouverte | Restauration native isolée, maintenance, contrôle du résultat, clôture des anciens jobs et rétention des envois exercés. Stockage indépendant, réconciliation fournisseur réelle et RPO/RTO à qualifier. Voir phase-10.md. |
| RET-01 / T20 | PASS_LOCAL phase 10 / copies externes ouvertes | Purge J+90, reçus externes avant commit, replay de suppression et de demande de compte, backup ancien réellement restauré puis repurgé. Inventaire des copies externes/anciennes et réduction contrôlée du registre restent opérateur. |
| A11Y-01 / T22 | PARTIAL | Téléphone, lecteur d’écran et zoom manuel non exécutés ; protocole manual-gates.md. |
| MAIL-01 / T23 | BLOCKED, différé utilisateur | Secrets/configuration gtech à fournir localement plus tard ; vérifier sender/domaine et remise à la boîte autorisée, sans divulguer de secret. |
| IND-01 | BLOCKED | Opérateur, DNS, ressources, clés et récupération indépendants non démontrés ; revue de sécurité externe de la version exacte requise. |

Aucune défaillance critique de confidentialité, intégrité du tirage, authentification ou perte de
données n’a été détectée par les tests exécutés. Cela ne ferme pas les critères ci-dessus et ne
prouve pas l’absence de défaut inconnu. `verify-release` reste bloqué. La phase 10 peut implémenter
les travaux locaux nécessaires ; elle ne doit pas ouvrir la production avant requalification.

La requalification Ubuntu passe 74 tests racine, 51/164 cas imbriqués et les deux parcours
Chromium/Axe ; voir [rapport du 16 novembre](ubuntu-2026-11-16.md). Le PostgreSQL 17.11 conservé
sur cet hôte ne valide pas le minimum de correctif de production 17.12. Les critères HTTPS,
supervision/entretien planifié, stockage/alertes et restauration indépendante avec RPO/RTO
restent ouverts en plus des critères manuels et d'indépendance ci-dessus.

## Extension sans email — 16 novembre 2026

| ID | État | Conséquence et preuve attendue |
|---|---|---|
| AUTH-01 | **BLOCKED / rôle NON ATTRIBUÉ** | Lien organisateur non authentifiant, demande liée au navigateur et approbation par signature distincte implémentés. Nommer le vérificateur indépendant, recetter son contrôle humain, protéger sa clé et les voies de récupération hors du contrôle de l'organisateur. Aucune attribution réelle n'est créée. |
| PACKAGE-01 | Corrigé, requalification finale PASS | La première recette HTTPS du nouveau parcours a révélé un module de vérification absent de l'allowlist de distribution. Ajout au seul coffre et smoke import depuis le ZIP extrait, sans chemin de secours vers le dépôt. Les runs locaux précédents ne prouvaient pas ce chemin hébergé. Run final 20261116T143006Z-ae8bc273 et recette HTTPS synthétique 20261116T143416Z PASS ; voir le rapport du parcours sans email. |

La [préparation production](production-readiness.md) reste la liste actuelle des portes non
fermées. MAIL-01 concerne encore le parcours organisateur existant et tout email optionnel
réellement retenu ; les participants sans email ne nécessitent aucun envoi de courrier.
