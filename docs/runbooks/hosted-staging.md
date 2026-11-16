# Sweetfamily : activation HTTPS de la recette hébergée

Demande du 16 novembre 2026 : portail `sweetfamily.gestionatech.de`, coffre séparé
`vault.sweetfamily.gestionatech.de` confirmé par l'utilisateur. Ce déploiement est une
**recette synthétique**, avec `APP_ENV=staging`. Le bandeau indique données fictives et
email/connexion email désactivés. Aucune garantie d'indépendance du coffre n'est revendiquée
sur cet hôte partagé et `verify-release` reste bloqué.

## Étapes administrateur restantes

Le portail résout déjà vers 217.154.166.155. Ajouter dans la zone gestionatech.de :

```text
Type : A
Nom : vault.sweetfamily
Valeur : 217.154.166.155
```

Ne pas modifier les MX, autres domaines ou entrées gtech. Aucun AAAA n'est prévu sur cet hôte
sans IPv6 publique. Attendre que `dig +short A vault.sweetfamily.gestionatech.de` retourne
cette adresse, puis exécuter depuis un terminal administrateur du serveur :

```bash
sudo bash /home/mignon/apps/sweetfamily/scripts/activate_hosted.sh
```

Si le record vient d'être créé, les DNS publics peuvent déjà retourner la bonne adresse
alors que le résolveur du serveur conserve un ancien NXDOMAIN. Le script vérifie 1.1.1.1,
puis attend au plus six minutes que `getent ahostsv4` confirme la bonne adresse localement.
Il ne change aucun résolveur partagé et ne touche nginx qu'après cette confirmation.
Un record réellement absent conserve un refus explicite avant toute modification.

La session agent ne peut pas exécuter ce dernier pas : sudo exige une authentification et
`/etc/nginx` ainsi que les certificats sont détenus par root. Ne jamais coller de mot de passe
ou secret dans la conversation. Les fichiers exacts sont reviewables :
`scripts/activate_hosted.sh` et `infra/hosted/sweetfamily.conf`.

Le script vérifie DNS et les backends, refuse de remplacer une configuration étrangère,
installe un seul site Sweetfamily dans nginx, obtient un certificat SAN pour les deux noms
avec Certbot webroot, teste nginx avant chaque reload et vérifie HTTPS sans ignorer le
certificat. Il sauvegarde/restaure l'ancien état de ce site si l'activation échoue.
Les fichiers et unités gtech ne sont pas modifiés ; le PID du service et l'empreinte de sa
configuration nginx sont contrôlés avant/après. Seul un reload gracieux de nginx est requis.
Les clés Let's Encrypt ne sont jamais copiées dans le dépôt.

Un hook propre à ces deux noms recharge nginx après renouvellement réussi. Le timer Certbot
système existant est déjà activé ; le script ne remplace aucun autre hook ou timer. Il active
le linger de mignon et les six unités utilisateur Sweetfamily, sans créer de service système
applicatif ni modifier une unité existante d'une autre application.

## Ressources déjà préparées et testées

| Rôle | PostgreSQL privé | HTTP backend privé | Configuration |
|---|---|---|---|
| Portail | 127.0.0.1:55441 | 127.0.0.1:8101 | `.local/hosted/control/app.json` |
| Coffre | 127.0.0.1:55443 | 127.0.0.1:8102 | `.local/hosted/vault/app.json` |

Ce sont des bases neuves, séparées des bases de qualification 55431/55433, avec marqueurs
`staging`, utilisateurs non privilégiés, secrets distincts et sockets 0700. Chaque rôle a une
venv Python 3.13.11 propre avec requirements à hashes, un artefact de production séparé, ses
processus web et worker. Deux processus × deux threads servent chaque rôle.

PostgreSQL impose TLS sur TCP et SCRAM. Des CA et certificats locaux distincts par rôle
permettent `sslmode=verify-full` avec SAN 127.0.0.1 ; TLS 1.3/256 bits a été vérifié sur les
deux connexions applicatives. Mauvaise CA et credentials de l'autre rôle sont refusés.
Les clés et JSON sont 0600 sous `.local/hosted` privé ; aucune valeur n'est affichée ou commitée.
Les CA de SQL sont propres au projet, sans relation avec les certificats publics nginx.
Le certificat SQL expire après 90 jours : prévoir sa rotation avant échéance, avec nouvelle
CA et configuration cliente revue (la clé de signature CA initiale n'est pas retenue).
Ce mécanisme ponctuel n'est pas une gestion de certificats de production.

Les six unités `sweetfamily-staging-{control,vault}-{db,web,worker}.service` sont dans
`~/.config/systemd/user`. Elles utilisent restart-on-failure, KillMode=control-group,
LimitCORE=0 et UMask=0077. Limites mémoire : DB 192 MiB, web 384 MiB, worker 192 MiB par rôle.
Les valeurs MemoryMax effectives ont été vérifiées ; elles ne constituent pas une preuve de
capacité sous charge de production. Les processus applicatifs n'héritent pas des credentials
opérateur ou d'un environnement d'une autre application.

Les migrations, bind_environment, check_runtime et checks Django stricts passent sur les
deux bases neuves. Les journaux opérateur sont initialisés hors des snapshots SQL. Maintenance,
backup chiffré, vérification et reprise ont été exécutés pour chaque rôle. Aucun événement ou
compte réel n'est créé ; les bases d'événements sont vides. Ce backup initial n'est pas une
restauration indépendante ni une preuve RPO/RTO.

## Commandes de préparation réellement exécutées

Après revue des ports et ressources et construction des artefacts :

```bash
.venv/bin/python scripts/hosted.py prepare
.venv/bin/python scripts/hosted.py units
systemctl --user start sweetfamily-staging-control-db sweetfamily-staging-vault-db
.venv/bin/python scripts/hosted.py provision --role control
.venv/bin/python scripts/hosted.py provision --role vault
systemctl --user start sweetfamily-staging-control-web sweetfamily-staging-control-worker sweetfamily-staging-vault-web sweetfamily-staging-vault-worker
```

`prepare` refuse un état existant pour ne jamais régénérer silencieusement des clés. Il ne
copie aucun fichier gtech, aucun secret de qualification et aucune base existante.
Ne pas le relancer sur cette installation. Garder les fichiers d'opérateur propres au rôle.

```bash
systemctl --user list-units 'sweetfamily-staging-*' --type=service
.venv/bin/python scripts/hosted.py manage --role control check_runtime
.venv/bin/python scripts/hosted.py manage --role vault check_runtime
.venv/bin/python scripts/hosted.py operator --role control operations status
.venv/bin/python scripts/hosted.py operator --role vault operations status
```

Pour l'entretien manuel, arrêter au premier échec et garder la maintenance :

```bash
set -e
.venv/bin/python scripts/hosted.py operator --role control operations maintenance
.venv/bin/python scripts/hosted.py operator --role control operations backup --directory "$PWD/.local/hosted/backups/control"
.venv/bin/python scripts/hosted.py operator --role control operations verify
.venv/bin/python scripts/hosted.py operator --role control operations resume
```

Répéter pour vault avec son répertoire. Les règles de purge et de restauration du
[runbook de restauration](restore.md) restent obligatoires. Aucun replay, reset de journal,
recalcul de tirage ou reprise d'envoi ambigu n'est exécuté par l'activation nginx.
Le wrapper hébergé ne sélectionne pas d'autre base ; une restauration doit utiliser un
environnement opérateur distinct configuré et revu selon ce runbook.

## Vérifications HTTPS et limites

Une instance nginx privée temporaire sur 127.0.0.1:18443 a validé la configuration de proxy
avec un certificat local : `nginx -t`, GET ready des deux rôles, rejet/écrasement des headers
forwarded forgés, puis Chromium sur les deux noms mappés vers loopback. Quatre pages et
quatre scans Axe passent, avec cookies CSRF Secure et host-only. Le GET curl validait la CA ;
le navigateur de ce test privé ignorait le certificat temporaire qui ne couvre pas les noms
publics. Cette preuve ne doit pas être présentée comme une validation HTTPS publique.
L'instance nginx temporaire est arrêtée après les tests.

Le proxy public impose Host et X-Forwarded-Proto, remplace X-Forwarded-For par l'adresse
cliente et retire les autres headers forwarded. Waitress ne fait confiance à ces deux
headers que lorsque `TRUSTED_PROXY=127.0.0.1` est explicite ; le défaut continue de les retirer.
Cela évite la boucle de redirection HTTPS sans faire confiance aux headers Internet.
Les pages sont no-store et le site de recette est noindex ; les accès contenant des liens
privés ne sont pas écrits dans un access log nginx.
Référence : [directives proxy nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

Après l'action administrateur, vérifier sans `-k` :

```bash
curl --fail https://sweetfamily.gestionatech.de/health/ready
curl --fail https://vault.sweetfamily.gestionatech.de/health/ready
```

Les emails restent `MAIL_PROVIDER=blocked`, `MAIL_LIVE_ENABLED=false`. Le parcours de
connexion par email ne peut pas être déclaré utilisable. Une configuration email réelle
exige un chemin de fichier explicitement autorisé et une autorisation d'envoi ; aucun secret
gtech n'a été lu et aucun email réel n'a été envoyé. Les critères de production restants
(indépendance, matériel assistif, email, backups/alertes/maintenance programmée, restauration,
patch PostgreSQL et revue externe) restent ouverts.

## Suivi DNS après le premier essai administrateur

L'essai utilisateur s'est arrêté sur le garde DNS avant toute modification nginx.
Le record du coffre est maintenant confirmé à 217.154.166.155 par ns41/ns42.domaincontrol.com,
1.1.1.1 et 8.8.8.8. Le résolveur configuré sur le serveur (212.227.123.16) conserve un ancien
NXDOMAIN avec TTL résiduel de quelques minutes. Un flush local a été exécuté sans changer
la configuration DNS ; le cache amont reste la cause observée. L'activation a été ajustée
pour attendre cette propagation locale, sans contourner le garde.

`bash -n` et trois prévols isolés avec commandes simulées passent : DNS absent refusé,
cache périmé puis résolu accepté, résolution immédiate acceptée. Les prévols s'arrêtent avant
nginx ; aucun certificat public ou succès de déploiement n'est revendiqué sur cette preuve.
Relancer la même commande sudo ; elle peut maintenant attendre jusqu'à six minutes.
