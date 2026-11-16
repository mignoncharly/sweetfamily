# Recette hébergée Sweetfamily — préparation du 16 novembre 2026

**État actuel : recette publique HTTPS active ; production BLOCKED.** Le portail demandé est
`sweetfamily.gestionatech.de`, le coffre confirmé par l'utilisateur est
`vault.sweetfamily.gestionatech.de`. Les deux readiness et les pages publiques sont maintenant
vérifiés sur le certificat Let's Encrypt couvrant les deux noms. La production reste bloquée.
L'utilisateur a exécuté l'activation sudo ; la session agent a vérifié les résultats sans
modifier la configuration d'une autre application. Les premiers blocages ci-dessous sont historiques.

Les fichiers exacts de mise en service sont préparés et le [runbook hébergé](../runbooks/hosted-staging.md)
donne la commande administrateur pour une réactivation. Les premiers essais privés ne
valaient pas accès public. L'activation administrateur et les contrôles publics sont désormais
réussis ; voir la preuve de fin de rapport et le résumé JSON.

## Résultats réellement obtenus

- Six unités utilisateur actives : DB/web/worker pour chaque rôle, aucun restart inattendu.
- Artefacts de rôles séparés, venv/credentials/bases neuves dans `.local/hosted`, APP_ENV=staging.
- SQL privé 55441/55443, HTTP privé 8101/8102 ; aucune exposition directe de ces ports.
- PostgreSQL verify-full TLS 1.3/256 bits vérifié ; mauvaise CA et credentials du portail
  refusés sur le coffre. Bases d'événements vides ; aucun événement familial créé.
- Migrations, identité staging, check_runtime et Django --deploy --fail-level WARNING PASS.
- Registres opérateur initialisés ; maintenance, backup chiffré, vérification et reprise PASS
  pour les deux rôles. Profondeurs de queue nulles et zéro tirage bloqué/en attente de durabilité.
- Nginx privé : syntaxe, CA validée par curl, GET ready des deux rôles et header forgé écrasé PASS.
- Chromium privé : quatre pages, quatre scans Axe sans violation, CSRF Secure et host-only PASS.
  Le navigateur ignorait le certificat temporaire ; aucune validation publique n'est revendiquée.
- gtech reste active/running, MainPID 1733623, NRestarts=0. Les clusters de qualification
  55431/55433 ont été arrêtés ; les six services hébergés restent actifs en loopback.

## Requalification de cette source

Run `20261116T122921Z-db5d1327` : **PASS local / release BLOCKED**.
Source SHA-256 : `641a67a0b6571fae5a60fc4c90b53213d6bad32f1f5915935c72d5159bedf627`.

| Contrôle | Résultat |
|---|---|
| Checks Python/TypeScript/Django/migrations | PASS |
| Secrets/dépendances/paramètres stricts | PASS |
| Artefacts de production et séparation | PASS |
| Tests racine | 76 PASS ; inclut deux nouvelles vérifications HTTP de la frontière proxy |
| Suites de service imbriquées | 51 portail / 164 coffre PASS ; ne pas additionner comme preuves indépendantes |
| Chromium et Axe de qualification | Deux parcours PASS, 33 scans sans violation |
| HTTP p95 portail/coffre, loopback non instrumenté | 243.380 / 304.977 ms ; cible locale atteinte |

Le [résumé JSON](hosted-staging-2026-11-16.json) lie mesures, empreintes d'artefacts et fichiers
d'activation. Les hashes supplémentaires couvrent explicitement le shell et le .conf, qui
ne sont pas inclus par l'ancien calcul source_digest du runner. Les preuves brutes sont sous
`.local/qualification/20261116T122921Z-db5d1327` et `.local/hosted`.

Le changement serveur préserve le retrait par défaut des headers forwarded. Une confiance
explicite 127.0.0.1 autorise seulement proto/adresse client, avec les valeurs remplacées par
nginx. Les tests exercent acceptation explicite et retrait sans confiance, y compris Host
et Forwarded falsifiés. Un bandeau staging indique données fictives et email désactivé.

## Blocages et portée

Activation publique terminée. Les deux A résolvent vers 217.154.166.155, le certificat est
validé sans contournement et les six unités sont enabled avec Linger=yes. Le reboot de l'hôte,
la reprise après panne publique et une charge HTTPS authentifiée restent non exercés.

MAIL_PROVIDER=blocked et MAIL_LIVE_ENABLED=false : les connexions par email restent
indisponibles. Aucun secret email gtech n'est lu/copié et aucun email réel n'est envoyé.
Aucune clé de qualification n'est réutilisée. L'opérateur indépendant du coffre, l'infrastructure,
DNS/accès/récupération séparés, matériel assistif, envois réels, restauration indépendante,
RPO/RTO, backups externes/alertes, entretien programmé, correctif PostgreSQL et revue externe
restent des conditions de production. Cette préparation n'autorise pas l'usage familial réel.

## Suivi du premier lancement administrateur

Le script s'est arrêté au contrôle DNS avant modification nginx. Le record du coffre est
maintenant correct sur les deux serveurs autoritaires et 1.1.1.1/8.8.8.8. Le résolveur amont du
serveur conserve un ancien NXDOMAIN. L'activation attend désormais au plus 360 secondes si
le record est déjà public, puis exige toujours la résolution locale correcte avant nginx.
Un record absent reste bloqué. Syntaxe bash et trois prévols isolés PASS, sans exécution de
commande nginx réelle. La preuve Python précédente reste inchangée ; le nouveau hash du shell
est enregistré séparément dans le résumé JSON. Les deux backends et gtech restent actifs.

## Suivi TLS du second lancement administrateur

Les deux domaines résolvent désormais correctement sur le serveur. Selon le journal de
l'utilisateur, Let's Encrypt a émis le certificat des deux noms jusqu'au 14 février 2027.
Le contrôle TLS exécuté immédiatement après reload a reçu un certificat non correspondant,
puis le script a restauré l'état nginx précédent. Le certificat émis reste conservé.

Le script attend maintenant la readiness TLS des nouveaux workers, d'abord sur loopback
avec le vrai SNI, puis via le domaine public. Les contrôles maintiennent validation CA/nom,
exigent HTTP 200/ready et échouent toujours sur un problème persistant. Un certificat existant
valide est réutilisé ; le webroot ACME est vérifié seulement lorsqu'une nouvelle émission
est nécessaire. Les hashes du script et de son helper sont enregistrés dans le résumé JSON.

`bash -n`, scan de secrets et scénario nginx/TLS privé PASS : mauvais certificat durable
refusé ; ancien certificat pendant reload retardé puis nouveau certificat accepté ; les deux
noms SAN vérifiés. Les preuves privées sont dans `.local/tls-reload-check/result.json` et
l'instance de test est arrêtée. Aucun changement du runtime Django ; la requalification
Python précédente reste celle de son snapshot. La validation publique demeure en attente
d'une nouvelle exécution sudo. gtech reste actif, même PID et zéro restart.

## Activation publique finale — 2026-11-16T13:40:57.725439+00:00

L'utilisateur a relancé le script avec sudo ; il a attendu le reload, réutilisé le certificat,
installé le hook de renouvellement et activé les six unités avec linger. L'activation a terminé
avec succès. Les contrôles indépendants effectués par l'agent passent :

| Contrôle public | Résultat |
|---|---|
| Ready portail / coffre, curl normal sans -k | 200 / 200, status=ok |
| HTTP vers HTTPS | 301 vers le bon domaine pour chaque rôle |
| Certificat | Let's Encrypt YE1, deux SAN exacts, expiration 2027-02-14 12:31 UTC |
| TLS | TLS 1.3, chaîne et hostname validés par Python ssl et Chromium |
| Headers forwarded forgés | Les deux ready restent HTTPS/200, pas de redirection vers un hôte fourni |
| Chromium public | Quatre pages HTTP 200, quatre scans Axe sans violation |
| Cookies | CSRF Secure et host-only, domaine propre à chaque rôle |
| Vérification hors serveur | Deux fetch live Firecrawl indépendants, 200/status=ok |
| Persistance configurée | Six unités actives/enabled, Linger=yes ; reboot non testé |
| Renouvellement | Timer Certbot actif et hook de reload limité aux deux noms présent |
| gtech | Actif, MainPID 1733623, NRestarts=0 |

Les preuves locales sont dans `.local/hosted/public-verification.json` et
`.local/hosted/browser-public/result.json`, avec captures synthétiques. Le résumé JSON versionné
conserve ces faits sans cookies ou secrets. Les checks système ne remplacent pas la recette
manuelle assistive, email, charge authentifiée, supervision d'incident, maintenance planifiée,
restauration indépendante/RPO/RTO et revue externe. Aucun email réel ou tirage familial n'est
exécuté. L'email et la connexion email restent explicitement désactivés dans le bandeau.
