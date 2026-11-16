# Rapport de qualification — phase 9

Ce rapport conserve les mesures historiques du run ci-dessous. La requalification et les
travaux de conservation/récupération ajoutés ensuite sont dans [phase-10.md](phase-10.md).
Consulter ce complément et l'état d'implémentation pour les critères T18/T20 actuels.

Date : 16 novembre 2026, Europe/Berlin. **Contrôles automatisés locaux : PASS. Sortie production : BLOCKED.**
Le PASS local désigne les checks/tests exécutés ; il ne signifie pas que la cible de performance ou
les critères externes/manuels sont satisfaits. Aucun défaut critique de confidentialité, tirage,
authentification ou perte de données n’a été détecté dans le périmètre exécuté ; aucune garantie
globale de production n’en est déduite.

## Version et preuves

Run final : `20261115T235657Z-e9e40b1a`. Source SHA-256 :
`bb79fa71a3193495dc00670894ec36ea962481aca9f7857fda45afd89385b83d`.
Les preuves brutes sont dans [le répertoire du run](../../.local/qualification/20261115T235657Z-e9e40b1a/result.json).
Le manifeste lie sources et hashes des preuves ; les instantanés Axe et l’inventaire matériel
ont été joints à la clôture documentaire sans modifier les résultats. Les rapports Markdown
photographient ce run et ne se mettent pas à jour lors d’un nouveau lancement.

Le premier run `20261115T232431Z-a76e63bb` est conservé comme baseline avec son propre hash de sources.
Le probe intermédiaire `connection-reuse-probe` est un essai ciblé, pas une qualification complète.
La qualification finale est rejouée intégralement après la correction de configuration.

## Résultats exécutés

| Contrôle | Résultat |
|---|---|
| Ruff/formatage, TypeScript, assets, Django et migrations | PASS |
| Scan secrets, pip-audit, npm audit, checks Django stricts | PASS : aucun signalement dans ce run, sans équivalence avec une revue indépendante |
| Distributions de production | PASS : dépendances avec hashes, séparation des rôles, pas de tests/secrets/diagnostics embarqués |
| Tests racine complets | PASS : 70 cas |
| Suite service portail imbriquée | PASS : 40 cas |
| Suite service coffre imbriquée | PASS : 151 cas |
| Parcours Chromium natifs | PASS : deux rôles, y compris ancien onglet après annulation |
| Axe | 11 scans portail + 22 coffre, zéro violation signalée dans ce périmètre |
| Reconnexion SQL après terminaison réelle des backends de test | PASS sur les deux rôles, cinq backends terminés par rôle puis requête authentifiée réussie |
| Tirage cryptographique 20 membres, trois essais | PASS : 4.475, 4.155, 4.234 s, contrôle de confidentialité et résultat inclus, plafond 60 s |
| Worker et SMTP Mailpit réels | PASS : observations de poll 0.951, 5.636 s, sous 60 s ; aucune preuve de remise externe |
| Cible HTTP p95 500 ms | **UNMET** sur la charge locale définie ci-dessous |
| `verify-release` | BLOCKED attendu, critères essentiels encore ouverts |

Les cas des services sont imbriqués dans les runners racine et ne s’additionnent pas comme preuves
indépendantes. Le groupe de huit FR/DE passe par les vrais services/workers/Mailpit et le backup
restauré. Une seule cérémonie de connexion complète par rôle utilise réellement SMTP dans ce
parcours ; les sept autres membres sont des fixtures explicitement synthétiques. Le test complémentaire
vérifie la bijection et la lecture propre à chacun des huit membres. Les pannes de provider sont
simulées ; elles ne remplacent pas une recette Zoho/Resend externe.

## Performance observée et écart conservé

Hôte : Windows x64, Python 3.13.11, 8 processeurs logiques, 34 061 664 256 octets de RAM physique.
Aucune limite de CPU/RAM appliquée. Rôles mesurés successivement, quatre threads Waitress par rôle,
PostgreSQL 17.12 natif ; workers arrêtés pendant le benchmark HTTP. Deux événements, vingt sessions
par événement, jusqu’à quarante requêtes concurrentes, quarante requêtes de chauffe puis quatre cents
requêtes mesurées par rôle. HTTP loopback sans TLS ; p95 complet incluant queue, SQL et rendu.

| Rôle | p95 baseline, connexion fermée par requête | p50 final | p95 final | Cible |
|---|---:|---:|---:|---:|
| Portail | 2 528,498 ms | 788.037 ms | 921.595 ms | < 500 ms — non atteint |
| Coffre | 3 591,802 ms | 1633.781 ms | 1819.876 ms | < 500 ms — non atteint |

La réutilisation SQL WSGI bornée à 60 secondes, avec contrôle de santé, réduit le coût observé mais
ne résout pas toute la latence. La cible n’est ni relevée ni déclarée atteinte. PERF-01 reste ouvert :
profiler rendu/SQL/file d’attente et mesurer l’hôte de référence avant engagement de capacité.
Les propositions portail 1 vCPU/1 Go et coffre 2 vCPU/4 Go ne sont pas qualifiées par ce poste local.
Voir [méthode](performance-method.md) et [ADR-0011](../adr/0011-wsgi-database-reuse.md).

## Correctifs qualifiés

- Disponibilité personnelle minimale en GET, sans marqueur de consultation : l’onglet visible
  actualise son état toutes les 15 s et au retour de focus/visibilité. Après annulation il retire
  le cadeau et la révélation ; le serveur refuse immédiatement toute nouvelle lecture/mutation.
  Le réseau indisponible est signalé ; une connaissance déjà acquise ne peut pas être révoquée.
- Connexions WSGI réutilisées pour une durée bornée et health checks, validation stricte de la
  configuration, séparation des credentials inchangée. Reconnexion réelle et régressions rejouées.
- Runner manuel, sorties JUnit imbriquées, matrice issue des cas exécutés et gate de release
  refusant les preuves manquantes/modifiées, les sources devenues différentes et la sortie globale.
  Le retour CLI BLOCKED est vérifié sans traceback, y compris quand tasks.py est exécuté comme __main__.

## Critères ouverts et suite

T01–T17, T19, T21, T24–T26 : PASS_LOCAL, dans le périmètre de [matrix.md](matrix.md).
T18 : PARTIAL (restore scellé prouvé ; reprise en maintenance/replay à exercer en phase 10).
T20 : BLOCKED (purge, tombstones et repurge après ancien backup à implémenter/exercer en phase 10).
T22 : PARTIAL (Chromium/Axe/clavier/reflow ; téléphone, lecteur d’écran et zoom manuel non exécutés).
T23 : BLOCKED (recette email réelle différée par l’utilisateur).
PERF-01 : UNMET (p95). IND-01 : BLOCKED (opérateur/domaines/accès/récupération indépendants et revue externe).

Les recettes précises sont dans [manual-gates.md](manual-gates.md), les défauts dans
[defects.md](defects.md), les frontières dans [privacy-review.md](privacy-review.md) et les
résultats d’accessibilité dans [accessibility.md](accessibility.md).
La phase 10 peut traiter les travaux locaux de conservation/restauration ; une ouverture réelle
attend leur requalification et la levée des critères essentiels. Aucun déploiement, DNS, email réel,
Docker, GitHub Actions ou CI/CD n’a été utilisé pour cette phase.
