# Recette native Ubuntu sur hôte partagé

Périmètre : données fictives, interfaces loopback, Mailpit, aucun DNS ni email réel.
Le même hôte ne prouve jamais l'indépendance du coffre. Ne pas utiliser les ressources,
secrets, bases, environnements virtuels ou services d'une autre application, notamment gtech.

## Inventaire avant installation

Depuis le clone, lire les rapports et runbooks puis exécuter :

```bash
uname -a
cat /etc/os-release
id
nproc
free -h
df -h . /tmp
ss -ltnp
systemctl list-units --type=service --state=running --no-pager
systemctl is-active gtech
git status --short --branch
git fetch origin
git rev-list --left-right --count HEAD...origin/main
/usr/lib/postgresql/17/bin/postgres --version
python3 --version
node --version
npm --version
```

Ne pas lancer bootstrap avant cet inventaire. Le runner ne doit ni installer des paquets
système ni gérer les clusters système. Il utilise les binaires PostgreSQL 17/18 déjà présents
ou `NOEL_PG_BIN`. Si ces binaires manquent, arrêter cette étape et prévoir une installation
isolée revue avec l'exploitant. `initdb` s'exécute sans root.

## Outils et environnement du projet

Les commandes suivantes ont été exécutées sur cet hôte. Les dépendances restent celles des
locks ; uv et Mailpit Linux x86_64 ont des empreintes d'archive **et** de binaire enregistrées
dans `infra/tool-versions.json`. Le helper uv ne modifie ni PATH global ni profil shell.

```bash
cd /home/mignon/apps/sweetfamily
python3 scripts/install_uv.py
export UV_PYTHON_INSTALL_DIR="$PWD/.local/python"
export UV_CACHE_DIR="$PWD/.local/uv-cache"
.local/tools/uv python install --no-bin 3.13.11
.local/tools/uv sync --locked --python .local/python/cpython-3.13.11-linux-x86_64-gnu/bin/python3.13 --group control --group vault
npm --prefix frontend ci
.venv/bin/python scripts/tasks.py init-local
.venv/bin/python scripts/tasks.py install-tools
```

`init-local` génère/réutilise les secrets sans les afficher. `.env` est mode 0600 et `.local`
mode 0700 sous POSIX ; les clusters et sockets sont privés. Ne jamais versionner ces dossiers.
Ne pas remplacer un `.env` existant par `.env.example`, qui contient des placeholders.
Les versions Python disponibles dépendent de la version uv utilisée ; le chemin explicite
évite d'utiliser un Python d'une autre application ([documentation uv](https://docs.astral.sh/uv/concepts/python-versions/)).

Avant le premier `db-up`, vérifier de nouveau les ports. Valeurs de cette recette :

| Ressource | Port loopback |
|---|---|
| SQL portail / coffre | 55431 / 55433 |
| HTTP portail / coffre | 8001 / 8002 |
| HTTP navigateurs / charge | 8201 / 8202 |
| Mailpit HTTP / SMTP | 18025 / 11025 |

55432 était déjà occupé et n'a pas été utilisé. Les options non secrètes `CONTROL_DB_PORT`,
`VAULT_DB_PORT`, `CONTROL_WEB_PORT`, `VAULT_WEB_PORT`, `CONTROL_BROWSER_PORT`,
`VAULT_BROWSER_PORT`, `MAILPIT_HTTP_PORT`, `MAILPIT_SMTP_PORT`, `PG_BIN` peuvent être placées
dans `.env` ou surchargées par les variables `NOEL_<nom>`. Conserver les anciens ports des
clusters Windows existants explicitement, notamment `VAULT_DB_PORT=55432` si nécessaire.
Ne jamais changer le port d'une base déjà démarrée sans l'arrêter avec son runner.

Le runner refuse un port occupé ; le contrôle tolère TIME_WAIT sous Linux. Chaque connexion
administrateur est vérifiée contre le répertoire de données du rôle avant toute configuration.
Chaque rôle a son instance, compte SQL non privilégié, base, secrets, sessions, migrations et
processus. Les variables opérateur et secrets préfixés d'un autre rôle ne sont pas hérités
par les processus applicatifs. Le wrapper opérateur injecte ses clés uniquement pour sa commande.
Cette isolation locale n'est pas une séparation de confiance de production.

## Migrations, navigateur et qualification

Pour un clone neuf, installer les navigateurs **dans le projet**, sans nettoyage d'un cache
Playwright partagé. La recette a d'abord installé Chromium puis copié sa révision 1255 et
ffmpeg-1013 dans ce dossier ; la commande ci-dessous a aussi été vérifiée sur ce dossier.

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.local/pw-browsers" npm --prefix frontend exec -- playwright install chromium
.venv/bin/python scripts/tasks.py db-up
.venv/bin/python scripts/tasks.py migrate
.venv/bin/python scripts/tasks.py check
.venv/bin/python scripts/tasks.py backup-drill
.venv/bin/python scripts/tasks.py qualify
.venv/bin/python scripts/tasks.py build-test
.venv/bin/python scripts/tasks.py verify-release
```

`qualify` conserve logs, JUnit, mesures et empreintes sous `.local/qualification/`.
`verify-release` doit sortir avec code 2 tant que les critères de production sont ouverts ;
ce blocage est attendu et ne constitue pas un échec à masquer. Ne pas modifier les sources
pendant une qualification. Les rapports Markdown sont distincts des preuves hashées locales.
Les tests imposent Mailpit et ne constituent pas une autorisation d'envoi réel.

`dev-up` supervise deux applications et deux workers plus Mailpit en simulation. Ctrl+C
arrête ces processus ; `db-down` arrête uniquement les deux clusters du projet sans les effacer.
Les bases ne sont pas des services de production et aucun démarrage automatique n'est installé.
Ne pas exécuter plusieurs suites utilisant les mêmes ports simultanément.

## Charge et profilage reproductibles

```bash
.venv/bin/python scripts/tasks.py benchmark-http
.venv/bin/python scripts/tasks.py profile-http
```

Deux événements synthétiques, 20 sessions chacun, concurrence 40, 40 requêtes de chauffe puis
400 GET authentifiés avec nouvelles connexions HTTP loopback, sans TLS. Le serveur utilise
quatre threads par défaut ; les comparaisons à deux/huit threads sont explicitement identifiées.
Le portail charge des groupes de 20 et 8 propositions ; le coffre utilise les fixtures à
4 et 8 membres. Cela ne prouve pas un groupe réel de 20 membres sur chaque événement.

Le profilage utilise un lanceur dans `tests/`, jamais une route ni un middleware de production.
Il compte les requêtes SQL et mesure SQL, application et templates ; le temps templates est
inclusif et peut recouvrir des appels imbriqués. HTTP moins application comprend réseau,
ordonnancement client et attente serveur : ce n'est pas une mesure pure de file. Aucun SQL,
paramètre, cookie, corps HTTP ou attribution n'est enregistré. Le profil CPU série est séparé
de la charge HTTP. Les JSON et profils texte restent dans `.local/performance/`.

## Opérations et arrêt

Les commandes des guides [exploitation](operations.md) et [restauration](restore.md) utilisent
`.venv/bin/python` sous Ubuntu à la place de `python`. `PG_BIN` est résolu vers les mêmes
binaires que le cluster ; aucun chemin Windows n'est imposé aux backups/restaurations.
Initialiser les registres une seule fois avec `operations-init`, puis vérifier `status` par rôle.
Conserver les registres les plus récents hors des snapshots SQL. Les gardes maintenance,
replay des suppressions et vérification du scellement restent obligatoires avant reprise.

```bash
.venv/bin/python scripts/noel_operator.py operations-init --role control
.venv/bin/python scripts/noel_operator.py operations-init --role vault
.venv/bin/python scripts/noel_operator.py status --role control
.venv/bin/python scripts/noel_operator.py status --role vault
.venv/bin/python scripts/tasks.py db-down
systemctl is-active gtech
ss -ltnp
```

Les critères HTTPS, supervision, entretien planifié, sauvegardes externes/alertes, opérateur
indépendant, RPO 15 minutes/RTO 4 heures, restauration indépendante, revue de sécurité externe,
email autorisé et matériel assistif restent à qualifier. Aucun résultat automatisé ne suffit
à déclarer la production prête.

## Mode web mesuré sous la cible locale

Le mode retenu sur cet hôte est **deux processus × deux threads par rôle**, soit quatre
threads de requête au total comme dans le protocole initial. Il est configuré par les options
non secrètes `WEB_PROCESSES=2` et `WEB_THREADS=2` dans le `.env` local. Un clone neuf conserve
le défaut compatible Windows : un processus × quatre threads. Pour sélectionner la recette :

```bash
NOEL_WEB_PROCESSES=2 NOEL_WEB_THREADS=2 .venv/bin/python scripts/tasks.py benchmark-http
NOEL_WEB_PROCESSES=2 NOEL_WEB_THREADS=2 .venv/bin/python scripts/tasks.py qualify
```

Ces commandes ont été exercées par configuration équivalente du `.env` ; le benchmark initial
à deux processus a aussi utilisé les deux variables `NOEL_` explicitement. Pour reproduire
l'ancien mode, surcharger **les deux** options, même si le `.env` a déjà été ajusté :

```bash
NOEL_WEB_PROCESSES=1 NOEL_WEB_THREADS=4 .venv/bin/python scripts/tasks.py benchmark-http
NOEL_WEB_PROCESSES=1 NOEL_WEB_THREADS=8 .venv/bin/python scripts/tasks.py benchmark-http
NOEL_WEB_PROCESSES=1 NOEL_WEB_THREADS=2 .venv/bin/python scripts/tasks.py benchmark-http
```

Le lanceur POSIX ouvre un seul socket 127.0.0.1 puis transmet uniquement ce descripteur à des
interpréteurs neufs. Chaque enfant charge le seul service autorisé ; aucune connexion SQL,
session ou donnée déchiffrée n'est héritée d'un interpréteur parent. Les secrets du rôle restent
dans son environnement. Les paramètres de proxy non fiables sont toujours supprimés.
Limites du lanceur : au plus quatre processus et seize threads au total. Deux processus par
rôle augmentent la mémoire et peuvent consommer deux cœurs ; recontrôler l'hôte partagé avant
chaque charge. Ces limites ne sont pas des quotas CPU/mémoire de production.

SIGTERM/Ctrl+C du parent arrête et récolte les enfants. Un enfant en panne arrête ses frères
et fait sortir le parent en erreur ; il ne prétend pas les redémarrer. Les tests exercent les
deux cas et vérifient la libération du port. SIGKILL du parent exige encore un superviseur OS
qui gère tout le groupe de processus. Les workers métier restent des processus distincts.

Les distributions natives embarquent le même lanceur ; elles lisent `WEB_PROCESSES` et
`WEB_THREADS` sans préfixe `NOEL_`, avec les anciens défauts 1/4. La production doit qualifier
ses limites, HTTPS, supervision, redémarrages et charge de référence avant de choisir ce mode.
Le respect de la cible loopback locale ne ferme pas ce critère de production.
