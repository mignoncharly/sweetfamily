# Sweetfamily : activation HTTPS de la recette hébergée

Demande du 16 novembre 2026 : portail `sweetfamily.gestionatech.de`, coffre séparé
`vault.sweetfamily.gestionatech.de` confirmé par l'utilisateur. Ce déploiement est une
**recette synthétique**, avec `APP_ENV=staging`. Le bandeau indique données fictives et
email/connexion email désactivés. Aucune garantie d'indépendance du coffre n'est revendiquée
sur cet hôte partagé et `verify-release` reste bloqué.

## État actuel vérifié

Recette publique active ; vérification enregistrée le `2026-11-16T13:40:57.725439+00:00`.

- https://sweetfamily.gestionatech.de/ : portail, HTTP 200.
- https://vault.sweetfamily.gestionatech.de/ : coffre, HTTP 200.
- HTTP redirige en 301 vers HTTPS ; les deux readiness rendent 200 et status=ok.
- Certificat Let's Encrypt YE1 couvrant les deux SAN, valide jusqu'au 14 février 2027.
- Chromium sans ignoreHTTPSErrors ni override DNS : quatre pages, quatre scans Axe sans
  violation, cookies CSRF Secure/host-only PASS. Les pages affichent le bandeau staging.
- Vérifications externes Firecrawl en fetch live : les deux readiness rendent HTTP 200.
- Six unités actives et enabled, Linger=yes, timer Certbot actif et hook propre aux deux noms.
- gtech actif/running, PID 1733623, zéro restart. Aucun redémarrage du serveur n'a été testé.

L'email et la connexion email restent désactivés. Les limites de production et d'indépendance
restent celles du rapport ; ces GET publics ne sont pas une recette authentifiée sous charge.

## Activation et réactivation administrateur

Les deux domaines résolvent maintenant vers 217.154.166.155. Le record attendu dans la zone gestionatech.de est :

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

L’utilisateur a exécuté ce pas avec succès. Toute réactivation reste une action administrateur : sudo exige une authentification et
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

## Suivi de l'émission du certificat et de la course au reload

Le second lancement administrateur a émis le certificat des deux noms, annoncé valide
jusqu'au 14 février 2027, puis a rollbacké le site après un contrôle TLS immédiat. Le reload
systemd envoie le signal à nginx sans attendre que les nouveaux workers acceptent des
connexions. Le contrôle exécuté dans la même seconde peut donc observer l'ancien certificat
du vhost par défaut ; cela correspond au journal fourni. Les avertissements « protocol options
redefined » n'étaient pas des erreurs de syntaxe et les autres sites ne sont pas modifiés.
Voir [séquence de reload nginx](https://nginx.org/en/docs/control.html).

L'activation réutilise désormais le certificat existant si chaîne, usage serveur, deux noms
et plus de trente jours de validité sont vérifiés. Aucun nouvel appel Certbot n'est alors
nécessaire. `openssl verify -verify_hostname` est utilisé : sur l'OpenSSL installé,
`x509 -checkhost` peut afficher un échec de correspondance tout en sortant avec code zéro.
En cas de nouvelle émission, le webroot ACME est testé après reload avant Certbot.

Après installation HTTPS, un contrôle attend au plus soixante secondes par domaine en ciblant
127.0.0.1 avec le vrai SNI et la validation CA/hostname active. Un second contrôle utilise la
résolution publique, sans proxy HTTP sortant hérité. Les réponses doivent être HTTP 200 avec
l'état ready. Aucun contrôle n'utilise `-k`, ne suit de redirection, ni n'accepte un mauvais
certificat. Une défaillance persistante déclenche toujours le rollback du seul site Sweetfamily.

Vérification privée exécutée : ancienne identité TLS refusée, ancien certificat pendant un
reload retardé puis nouveau worker accepté, deux SAN acceptés et certificat de mauvais nom
refusé pour réutilisation. Temps du scénario de reload : environ une seconde. Le nginx de test
sur 127.0.0.1:18463 est arrêté. Cette preuve ne constitue pas une validation HTTPS publique.
Relancer la même commande sudo ; le certificat déjà obtenu est conservé après rollback.

## Activation réussie et vérification publique

Le lancement administrateur de 13:37 UTC a réutilisé le certificat et attendu les nouveaux
workers. Le script a terminé avec succès et les deux services sont maintenant vérifiés en
HTTPS public. Les tentatives précédentes et les tests privés ci-dessus constituent l'historique
du diagnostic ; ils ne sont plus les blocages courants. Le rapport JSON conserve la vérification
publique, les informations TLS et l'état des unités. Aucun secret ou email réel n'est utilisé.

## Mise à jour du parcours sans email — 16 novembre 2026

Les releases ont été mises à niveau après le run `20261116T143006Z-ae8bc273`, avec backup chiffré
par rôle, maintenance, arrêt des quatre seuls web/worker Sweetfamily, conservation des releases
précédentes, migrations, checks, vérification/reprise puis redémarrage de ces unités. Les exigences
verrouillées n'ont pas changé ; les venvs et clés/bases ne sont pas recréées. Les preuves d'upgrade
sont dans `.local/hosted/upgrades/20261116T143006Z-ae8bc273`.

Le [rapport sans email](../qualification/email-free-enrollment-2026-11-16.md) consigne une recette
synthétique sur le vrai HTTPS du coffre : sept scans Axe, approbation signée, code/session et
remplacement PASS, puis purge des quatre participants et révocation/suppression du rôle test.
Aucune donnée réelle ni tirage réel. La première version du ZIP omettait un module ; le correctif
et son import depuis l'archive extraite ont été requalifiés avant la dernière promotion.

Le flag WHATSAPP_ENROLLMENT_ENABLED est revenu à false ; la route de connexion par code renvoie
404 tant que cette fonctionnalité est désactivée. Le rôle **Independent vault operator demeure
NON ATTRIBUÉ**. La recette ne nomme personne et ne prouve pas l'indépendance d'un serveur/DNS
encore contrôlés ensemble. Ne pas activer pour de vrais utilisateurs sur cette seule preuve.
Le [runbook de vérification](independent-enrollment.md) précise les conditions d'attribution.
