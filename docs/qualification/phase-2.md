# Qualification de phase 2

Date : 15 novembre 2026. P?rim?tre : socle local Windows x64, données synthétiques uniquement.
Adaptation utilisateur : aucun Docker, GitHub Actions, CI/CD ou dépôt distant créé.
R?f?rence : [ADR-0004](../adr/0004-execution-locale.md).

## Livrables

Deux projets Django indépendants, migrations propres et marqueur d'environnement en base.
Deux clusters PostgreSQL 17.12, comptes applicatifs non privilègi?s et secrets distincts.
Waitress, processus workers supervis?s, Mailpit 1.33.1 à Simulation à sur loopback.
Groupes de dépendances control/vault, uv.lock avec hashes, package-lock.json et assets locaux.
Runner Python manuel et alias Makefile pour toutes les cibles prévues.
Distributions production par service et distribution de tests sépar?e ; aucun secret local inclus.

Versions principales réellement installées : Python 3.13.11, Django 5.2.19, django-allauth 65.22.1,
psycopg 3.3.9, cryptography 50.0.2, Waitress 3.0.2, WhiteNoise 6.12.0,
Node.js 24.19.0. Versions compl?tes dans les locks et infra/tool-versions.json.

## R?sultats exécut?s

| Commande / contrôle | R?sultat réel |
|---|---|
| uv lock puis uv sync --locked --group control --group vault | PASS : 52 entrées résolues, 51 biblioth?ques installées dans .venv |
| npm --prefix frontend ci | PASS : installation verrouillée |
| python scripts/tasks.py bootstrap | PASS : installation/dépendances/assets et secrets locaux génér?s sans impression |
| python scripts/tasks.py install-tools | PASS : empreintes des outils installés vérifi?es |
| python scripts/tasks.py check | PASS : Ruff, formatage, TypeScript, compilation, checks Django et aucune migration manquante |
| python scripts/tasks.py test-unit | PASS : 26 tests, 5 tests d'intégration d?sélectionn?s lors de ce run initial |
| python scripts/tasks.py test-integration | PASS final : 6 tests, 26 d?sélectionn?s |
| python scripts/tasks.py test-privacy | PASS : 20 tests, 12 d?sélectionn?s |
| python scripts/tasks.py check-security | PASS final : scan source/canaris, pip-audit, npm audit et check --deploy --fail-level WARNING sur les deux configurations production |
| python scripts/tasks.py build-prod | PASS : archives sépar?es, dépendances avec hashes, sources ?trang?res/tests/diagnostics exclus |
| python scripts/tasks.py build-test | PASS : distribution de tests distincte |
| python scripts/tasks.py check-prod-artifact | PASS : appel? par build-prod sur les deux archives |
| Import des deux archives extraites hors chemin des sources de service | PASS : configuration et routes valides |
| Rebuild production et comparaison SHA-256 avant/après | PASS : les deux ZIP sont identiques octet pour octet |

Les suites se recouvrent : ne pas additionner leurs nombres comme des tests distincts.
Les tests d'intégration ont utilisé de vrais processus et PostgreSQL 17.12, pas SQLite ni mocks
de base. Ils vérifient les refus d'accès crois?s, les privilèges SQL, les marqueurs incoh?rents,
les migrations sur deux bases temporaires neuves avec rollback/réapplication et la stabilit?
des migrations au second lancement. Les bases temporaires ont été supprimées après chaque test.

Le test de processus a démarr? les deux apps et les deux workers avec le vrai Mailpit,
interrog? les endpoints HTTP de disponibilit?, puis envoy? un email synthétique par le backend
SMTP Django et constat? sa présence via l'API Mailpit. Les cinq processus ont été arrêt?s
après le test. Cette preuve est locale ; elle ne prouve aucune livraison à une boîte réelle.

## D?fauts corrigés pendant la qualification

Une erreur de nom de variable de r?le a été corrigée avant les résultats ci-dessus.
Le contrôle Django strict a détect? l'absence de middleware anti-iframe ; il a été ajout?
aux deux services, puis les contrôles de déploiement sont passés sans avertissement masqu?.
Le premier test d'isolation attendait une exception plus spécifique que celle de psycopg
lors de l'authentification initiale. Le refus réel ?tait correct ; le test vérifie maintenant
OperationalError et le motif explicite de rejet du mot de passe, pas un simple timeout.
Une valeur de credential SQL local ?tait incluse dans ce premier traceback pytest : les mots
de passe applicatifs des deux clusters ont été renouvelés et les tests finaux ont utilisé les
nouvelles valeurs. Les tracebacks pytest sont d?sormais courts. Aucune clé de production concern?e.

## Limites et conditions restantes

Le socle a été installé sur ce workspace Windows, puis les distributions ont été extraites et
import?es sépar?ment. Aucun essai sur une seconde machine, Linux ou clone indépendant n'est
revendiqué. Le Makefile n'a pas été exécut? directement car make n'est pas installé ; les mêmes
commandes Python ont été exécut?es. Les distributions sont des artefacts de préparation,
pas des releases approuv?es pour des données réelles.

Le dossier .git créé dans l'ancienne session appartient au compte CodexSandboxOffline.
L'OS refuse sa réattribution au compte courant ; aucun fichier n'a été réattribu?.
Les lectures Git et le scanner fonctionnent avec une exception safe.directory limitée ?
leur commande. Les opérations d'?criture Git peuvent nécessiter une correction des ACL/propriétaire
par un administrateur Windows. Aucune configuration Git globale n'a été modifiée.

Les workers n'ont pas encore de consommateur métier. Authentification/invitations, stockage
privé métier, tirage, durable outbox, envois Resend, domaine HTTPS et restauration compl?te
restent à impl?menter aux phases prévues. Hors local, les emails ?chouent explicitement.

Les cibles test-draw, test-e2e, check-accessibility, backup-drill et verify-release retournent
BLOCKED/code 2 jusqu'aux phases correspondantes ; ce ne sont pas des contrôles r?ussis.
Les sc?narios T01?T26 du produit complet ne sont pas valid?s en bloc par ces tests du socle.
L'indépendance de production du coffre et sa revue de sécurit? restent NON VALID?ES.
Le travail de phase 3 peut commencer sans attendre une infrastructure de production.

## Sources vérifi?es

- [Django 5.2 : checklist de déploiement](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
- [Django 5.2 : applications et précautions AppConfig.ready](https://docs.djangoproject.com/en/5.2/ref/applications/).
- [Django : m?tadonnées officielles PyPI](https://pypi.org/pypi/Django/json) pour le correctif 5.2.19.
- [PostgreSQL : versions maintenues](https://www.postgresql.org/support/versioning/), 17.12 publi? ; l'installation système 18.0 n'a pas été utilisée pour les tests.
- [Mailpit 1.33.1 : release et empreintes fournisseur](https://github.com/axllent/mailpit/releases/tag/v1.33.1).
