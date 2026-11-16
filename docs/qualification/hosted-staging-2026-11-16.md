# Recette hébergée Sweetfamily — préparation du 16 novembre 2026

**État : services privés prêts ; activation publique bloquée.** Le portail demandé est
`sweetfamily.gestionatech.de`, le coffre confirmé par l'utilisateur est
`vault.sweetfamily.gestionatech.de`. Le portail résout vers 217.154.166.155 ; le coffre n'a
pas encore de record A. Le TLS public du portail présente actuellement un autre certificat.
La session ne dispose pas de sudo sans authentification ; aucun fichier nginx système,
certificat public, DNS ou service gtech n'est modifié par l'agent.

Les fichiers exacts de mise en service sont préparés et le [runbook hébergé](../runbooks/hosted-staging.md)
donne la seule commande administrateur restante, après création de l'A du coffre. Le script
n'a **pas** été exécuté avec root. Sa syntaxe bash et la configuration nginx ont été validées,
et un proxy HTTPS privé utilisant le même routage a été exercé ; ces résultats ne valent
pas réussite d'une émission Let's Encrypt ou d'un accès public.

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

Activation publique : ajouter A vault.sweetfamily.gestionatech.de vers 217.154.166.155, puis
exécuter `sudo bash /home/mignon/apps/sweetfamily/scripts/activate_hosted.sh` depuis un terminal
administrateur. La demande a été présentée à l'utilisateur ; aucune exécution n'est inventée.
Une fois cette action effectuée, vérifier les deux URL HTTPS sans ignorer TLS et rejouer les
contrôles navigateur publics. Les six unités ne sont pas encore activées au boot et le linger
est désactivé ; l'activation administrateur complète ces deux points.

MAIL_PROVIDER=blocked et MAIL_LIVE_ENABLED=false : les connexions par email restent
indisponibles. Aucun secret email gtech n'est lu/copié et aucun email réel n'est envoyé.
Aucune clé de qualification n'est réutilisée. L'opérateur indépendant du coffre, l'infrastructure,
DNS/accès/récupération séparés, matériel assistif, envois réels, restauration indépendante,
RPO/RTO, backups externes/alertes, entretien programmé, correctif PostgreSQL et revue externe
restent des conditions de production. Cette préparation n'autorise pas l'usage familial réel.
