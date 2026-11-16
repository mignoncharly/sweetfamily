# Développement local

Prérequis Windows x64 : Python 3.13, uv, Node.js 24/npm. Aucun Docker ou pipeline CI/CD.
Versions et intégrité : uv.lock, frontend/package-lock.json, infra/tool-versions.json.

## Installation et commandes

python scripts/tasks.py bootstrap génère .env local une seule fois sans afficher de secrets,
installe les dépendances verrouillées et les outils natifs vérifiés, puis compile les assets.
python scripts/tasks.py dev-up démarre les clusters PostgreSQL, applique les migrations,
compile/collecte les assets, puis supervise deux apps, deux workers et Mailpit.
Ctrl+C arrête le groupe de processus. python scripts/tasks.py db-down arrête les bases sans les effacer.

Les clusters .local/pg-control et .local/pg-vault utilisent PostgreSQL 17.12, SCRAM et des secrets
distincts. Ils écoutent uniquement 127.0.0.1:55431 et :55432. Les rôles applicatifs ne sont ni
superutilisateurs ni créateurs de bases/rôles ; ils ne peuvent pas lire l'autre instance.
Aucune installation PostgreSQL système n'est modifiée. Les données locales restent synthétiques.

Applications : http://127.0.0.1:8001/ et :8002/ ; Mailpit « Simulation » : :18025, SMTP :11025.
Le worker coffre traite invitations/challenges SQL chiffrés et projections signées périodiques.
Le worker portail est un socle supervisé. La livraison externe reste indisponible avant phase 7.

Le téléchargement automatique des outils est Windows x64. Linux exige ses binaires et empreintes
correspondants, et n'a pas été qualifié. Ne pas présenter cette limitation comme un succès Linux.

## Configuration

| Variable | Usage |
|---|---|
| APP_ENV | local, staging ou production ; comparé au marqueur en base |
| SERVICE_ROLE | control ou vault ; correspondance avec le code obligatoire |
| DJANGO_SECRET_KEY | Secret indépendant par service, 50 caractères minimum |
| AUTH_DATA_KEY | Clé Fernet du service pour sessions, facteurs et payloads temporaires |
| COMMAND_KEY | Privée Ed25519 portail ; publique coffre |
| PROJECTION_KEY | Privée Ed25519 coffre ; publique portail |
| PUBLIC_ORIGIN | Origine propre du service, HTTPS hors local |
| VAULT_ORIGIN / CONTROL_ORIGIN | Destinations de service explicitement configurées, HTTPS hors local |
| DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT | PostgreSQL propre au service, aucun fallback SQLite |
| DB_SSLMODE | disable sur les clusters locaux ; verify-full obligatoire hors local |
| ALLOWED_HOSTS | Liste explicite, aucun wildcard |
| DEBUG | false par défaut ; true refusé hors local |
| ENABLE_SYNTHETIC_DIAGNOSTICS | false uniquement, diagnostics absents |
| MAILPIT_SMTP_PORT | 11025, backend local uniquement |
| DJANGO_SETTINGS_MODULE / PYTHONPATH | Configuration et chemin du service, contrats publics partagés |
| PORT | Port loopback du lanceur de distribution, 8000 par défaut |

Le runner mappe les noms CONTROL_/VAULT_ de .env vers les variables du seul processus concerné.
migrate étend un environnement de phase 2 avec les clés de phase 3 ; aucune clé n'est imprimée.
.env.example contient uniquement des placeholders. .env, .local et artifacts sont ignorés par Git.
Les secrets administrateurs DB ne sont jamais injectés dans les applications.
Réserver les fichiers au compte Windows local ; les modes POSIX ne remplacent pas les ACL Windows.

Les sessions allauth sont chiffrées par le backend DB du service. Les compteurs de fréquence sont
dans auth_rate_cache, avec clés HMACées. Les POST d'authentification existants sont sérialisés
sous verrou SQL jusqu'à la sauvegarde de session. Changer AUTH_DATA_KEY sans migrer les anciens
secrets MFA rend ceux-ci illisibles ; rotation et restauration doivent être qualifiées avant production.

## Vérifier et distribuer

check exécute Ruff/formatage, TypeScript, compilation/collectstatic, checks Django et migrations
manquantes. Faire db-up avant check. test-unit, test-integration, test-privacy et check-security
sont manuels. Le dernier lance scan de secrets, pip-audit, npm audit et les checks Django stricts
avec une configuration de production synthétique, sans envoyer d'email réel.

Les tests d'intégration créent puis suppriment seulement leurs bases noel_phase2_test_* et
noel_phase3_test_*. Ils utilisent de vrais PostgreSQL et, pour le smoke test, les apps/SMTP Mailpit.
Le smoke test emploie des adresses .invalid uniques et supprime ses acteurs/événement ensuite.
Aucune base utilisateur existante n'est supprimée.

build-prod crée une archive par service avec requirements.txt haché, contrats publics,
templates et assets locaux ; build-test crée une distribution de tests distincte.
check-prod-artifact refuse diagnostics, tests, secrets de configuration ou modèles de l'autre
service en production. Installer les dépendances extraites avec
python -m pip install --require-hashes -r requirements.txt, configurer les variables du service,
migrer, lier une seule fois l'environnement, puis lancer python serve.py derrière un proxy HTTPS.
Le proxy de production doit retirer les headers forwarded non fiables ; sa configuration
Waitress/domaines réels reste à qualifier en phase 10.

Les scripts WebAuthn allauth sont collectés localement, sans CDN. Les images data: permettent
le QR TOTP généré par la bibliothèque. Aucun matériel passkey réel n'est encore qualifié.
Les archives ne constituent pas une autorisation de production ; le backend email hors local
reste explicitement bloqué. L'indépendance du coffre n'est pas démontrée sur un ordinateur partagé.

test-e2e/check-accessibility (phase 8), backup-drill (phase 10) et
verify-release (phases 9–10) retournent BLOCKED/code 2 tant que ces fonctions sont absentes.
Le Makefile expose les mêmes cibles, mais n'a pas été exécuté directement sans make installé.

## Dépôt Windows

.git appartient au compte de l'ancienne sandbox. Les lectures sont possibles avec
git -c safe.directory=C:/noel ; le scanner applique cette exception à sa seule commande.
L'OS a refusé la correction de propriétaire. Faire corriger les ACL par un administrateur
pour les écritures Git si nécessaire ; aucune configuration Git globale n'a été modifiée.

## Ajouts de phase 4

migrate/bootstrap étendent .env avec VAULT_WISHLIST_KEY sans affichage. Seul le processus coffre
reçoit WISHLIST_KEYS et WISHLIST_ACTIVE_KEY ; le portail reçoit un objet vide et aucun secret
de liste. Les clés protègent aussi les historiques, donc les conserver avec les sauvegardes
privées du coffre. Les archives distribuent merchants.json, jamais ses clés.

Les suites de service du runner d'intégration incluent maintenant wishlist_cases.py : validation,
URL malveillante, chiffrement, historique et deux transactions PostgreSQL concurrentes.
Le smoke test sauvegarde et valide aussi une liste via le vrai serveur HTTP avec CSRF.
Le scénario DRAWN utilise un état synthétique, aucun résultat de tirage n'est créé.

## Ajouts de phase 5

migrate ajoute VAULT_DRAW_MASTER_KEY et VAULT_BACKUP_KEY au fichier local ignoré, sans affichage.
Seul le coffre reçoit DRAW_MASTER_KEYS / DRAW_ACTIVE_KEY ; la clé de sauvegarde et les accès SQL
administrateurs ne sont transmis que par scripts/noel_operator.py au processus opérateur.
La configuration refuse une clé de tirage identique à une clé de souhait ou d'authentification.
Les clés doivent être conservées séparément des archives ; ne pas les perdre ou les remplacer.

Le worker coffre réclame un job sous verrou puis calcule hors transaction longue, avec budget
60 secondes et bail 120 secondes. Les tentatives échouées sont bornées ; un opérateur doit
intervenir en FAILED_FINAL. Les notifications de disponibilité restent HELD tant que la commande
opérateur n'a pas restauré une sauvegarde chiffrée dans une base noel_restore_* isolée et vérifié
les octets du résultat et son manifeste. Cette base est ensuite supprimée, sans démarrer d'app.

~~~powershell
python scripts/tasks.py test-draw
python scripts/noel_operator.py confirm-durability <event_uuid>
python scripts/noel_operator.py reopen-failed <event_uuid>
~~~

Le dernier ordre refuse tout résultat déjà scellé et exige ensuite nouveau manifeste et nouveaux
consentements. test-draw lance les tests de référence et les suites de service sur bases jetables.
Il inclut concurrence réelle et sauvegarde/restauration PostgreSQL réelles de données synthétiques.
Les fichiers temporaires pytest restent sous .local/pytest-tmp, sans modifier les ACL du profil.
La copie locale restaurée ne démontre pas une sauvegarde hors machine ni un opérateur indépendant.

## Ajouts de phase 6

migrate convertit les historiques v1 vers des enveloppes par événement ; conserver toutes les
anciennes clés pour les archives. .env reçoit VAULT_MASTER_KEYS et VAULT_ACTIVE_MASTER_KEY ;
seul le coffre reçoit leur mapping sous les noms compatibles DRAW_MASTER_KEYS/DRAW_ACTIVE_KEY.
Le portail reçoit toujours {} et aucun secret privé du coffre. Le scanner vérifie aussi les
valeurs secrètes contenues dans une map JSON, sans les afficher.

Les commandes natives de staging/rotation/activation sont dans le [guide des clés](runbooks/private-keys.md).
Les tests les exécutent dans un répertoire temporaire, sans tourner les clés de l'environnement partagé.
Les suites de service incluent private_cases.py, achats concurrents, rotation et compatibilité ancienne clé.
Le smoke ajoute une vraie sauvegarde/restauration chiffrée, GET/POST reveal et achat via HTTP avec CSRF,
puis un dump PostgreSQL complet du portail vérifié sans canaris privés. Les sessions de ces étapes
privées sont des fixtures explicites ; le premier login SMTP réel reste couvert par le début du smoke.
Les archives chiffrées synthétiques de smoke restent sous .local/smoke-backups, hors dépôt et production.

Le garde de processus s'applique à l'exécution WSGI/worker non locale du coffre. Le check Django
strict est un contrôle de configuration, pas une recette de la politique OS. Un serveur avec debugger
ou collecte de dumps repérés doit refuser de démarrer ; aucun réglage système Windows n'est modifié.

## Ajouts de phase 7

Les deux workers consomment leurs queues indépendantes ; le worker coffre traite aussi les tâches
planifiées et projections. NotificationOutbox conserve le stockage PendingMail historique ; les
migrations ajoutent baux, faits fournisseur et métadonnées, puis rattachent les anciennes invitations
et notifications de tirage sans déchiffrer leur contenu. La bibliothèque partagée noel_delivery.py
ne contient aucun modèle métier et est emballée avec chaque service. Resend est une dépendance
verrouillée des deux distributions pour vérifier les signatures officielles de webhook.

Les paramètres du guide de notification sont préfixés CONTROL_/VAULT_ dans le .env local. Les
runners de tests forcent uniquement Mailpit et effacent les credentials réels transmis à leurs
subprocessus. Cette règle appartient au runner/tests, pas aux routes de production. Même avec
une configuration Zoho active, les suites automatisées ne sont pas des envois externes.

Le smoke exerce maintenant le code de connexion du portail depuis son outbox réelle, worker,
SMTP et Mailpit, puis le MFA. Les codes portail et coffre ont des expéditeurs de simulation
distincts, afin de ne pas confondre deux challenges destinés à la même boîte de test. Les suites
ajoutent delivery_cases.py dans chaque base et notification_cases.py dans le coffre.
Les commandes restent natives, sans conteneur ou pipeline. Voir le [guide de notification](runbooks/notifications.md).
