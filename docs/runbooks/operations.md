# Exploitation native — phase 10

Ces procédures Windows sont livrées pour le local et la recette synthétique. Elles ne
certifient pas un hébergement de production. Aucun Docker, GitHub Actions ou pipeline
n'est requis par l'adaptation retenue. L'exploitant indépendant du coffre reste à désigner.

## Initialiser les opérations locales

Après `python scripts/tasks.py migrate`, initialiser une seule fois chaque registre :

```powershell
python scripts/noel_operator.py operations-init --role control
python scripts/noel_operator.py operations-init --role vault
```

Le wrapper génère les clés locales manquantes sans les afficher. Les registres chiffrés
sont dans `.local/operations/control` et `.local/operations/vault`. Ne jamais réinitialiser
un registre existant ou restaurer ce dossier depuis le même ancien instantané que la base.
En production, définir `OPERATIONS_DIRECTORY` sur un stockage indépendant, durable et
contrôlé par l'opérateur de ce service, avec sa clé Fernet `OPERATIONS_KEY` sauvegardée
séparément. Le compte web/worker ne reçoit ni cette clé ni les credentials SQL de backup.
Un fichier `.pending`, une clé incorrecte ou un registre absent bloque la vérification.
La protection contre l'effacement/rollback du stockage externe dépend de ses droits et
versions immuables : le chiffrement authentifié seul ne prouve pas sa fraîcheur.

## Entretien et conservation

Exécuter chaque jour pour chaque rôle, dans cet ordre. Arrêter la séquence dès qu'une
commande échoue ; conserver la maintenance et traiter l'incident avant reprise.

```powershell
python scripts/noel_operator.py maintenance --role vault
python scripts/noel_operator.py purge --role vault
python scripts/noel_operator.py verify --role vault
python scripts/noel_operator.py backup --role vault
python scripts/noel_operator.py resume --role vault
python scripts/noel_operator.py expire-backups --role vault
python scripts/noel_operator.py status --role vault
```

Répéter avec `--role control`. `verify` convient à l'entretien sans restauration et ne
neutralise pas l'outbox courante. `recover` est réservé à une base restaurée : il retient
les anciens messages et commandes, révoque les sessions et désactive les rappels restaurés.
Le verrou partagé des requêtes et ticks de worker est compatible avec leurs transactions
métier ; la maintenance attend leur fin avec un verrou exclusif, puis bloque les suivants.
Les pages et la disponibilité rendent 503 ; la vivacité reste accessible sans base.

La purge supprime l'événement à J+90 (instant UTC), ses membres/propositions, invitations,
consentements, souhaits/historiques, achat, clés par événement, tirage scellé et notifications
liées. Le portail perd aussi les commandes, exports reconstituables et projections nominatives.
Les identités privées sans autre adhésion sont retirées ; un compte enregistré est conservé
jusqu'à la demande de son titulaire. Les comptes d'invitation non revendiqués sont supprimés.
Les réservations cryptographiques de nonce restent tant que leurs clés/copies sont utilisables.

Après vérification de la demande personnelle, l'opérateur peut utiliser en maintenance
`delete-account --user-id <identifiant> --role <rôle>`. L'opération refuse tout compte encore
lié à un échange ou transfert ; appliquer retrait/annulation, transfert et conservation avant
de réessayer. Le registre empêche sa résurrection après restauration. Il ne contient aucun
email, seulement l'identifiant et une empreinte HMAC liée à l'identité ; un identifiant réutilisé
avec une autre identité bloque la récupération plutôt que supprimer le mauvais compte.

Les tombstones d'événements contiennent seulement UUID et instant de suppression. Conserver
ce registre au moins 120 jours et tant qu'une copie rejouable existe. Après inventaire des
copies et destruction attestée, l'opérateur doit revoir et réduire les anciennes entrées ;
aucune expiration automatique n'est effectuée sans preuve de disparition des copies.
Cette revue manuelle reste une condition d'exploitation, pas une suppression déjà démontrée.

Les backups réguliers et de durabilité **nouveaux** portent un préfixe de rôle et sont dans
`.local/backups/<rôle>`. `expire-backups` ne supprime que ces archives de plus de 30 jours.
Inventorier séparément les anciens fichiers sans préfixe et les copies externes : cette
commande ne prétend pas les effacer. Une clé active supprimée ne détruit pas ses copies.

## Supervision

`status` donne seulement profondeur/âge de queue, baux expirés, livraison inconnue, rejets
et, au coffre, jobs bloqués et résultats en attente de durabilité. Ne pas publier sa sortie
sur un endpoint organisateur. Surveiller séparément les deux `/health/ready`, l'âge du
dernier backup vérifié, les échecs de commande et la réception des webhooks lorsqu'ils sont
configurés. Proposer une alerte si queue/âge augmente durablement, si un bail reste expiré,
si une durabilité est retenue ou si une sauvegarde dépasse l'objectif choisi.

Le superviseur OS doit redémarrer les workers après panne et exécuter l'entretien avec un
compte opérateur dédié. Aucun planificateur de production n'a été installé sur ce poste.
Configurer une rétention de 30 jours pour les journaux opérationnels du superviseur, sans
corps HTTP, payloads, secrets ou adresses. Les logs privés du coffre ne vont jamais dans
le compte de supervision du portail. Les fichiers de preuve sont synthétiques et locaux.

## Sauvegardes et objectifs

`BACKUP_ENCRYPTION_KEY`, `BACKUP_DB_USER`, `BACKUP_DB_PASSWORD` et `PG_BIN` sont réservés
aux commandes opérateur. Les archives sont chiffrées, relues et déchiffrées pour vérification.
Une libération de tirage exige en plus une vraie restauration et l'inscription durable du
fingerprint scellé dans le registre externe avant disponibilité.

Les objectifs proposés restent RPO 15 minutes / RTO 4 heures. Le backup complet ponctuel
et le drill local ne démontrent pas ces objectifs en production. Choisir et exercer une
chaîne de snapshots suffisamment fréquents ou WAL/PITR, ainsi que la récupération des
anciennes clés. Confirmer stockage indépendant, restauration hors site, délais et alertes
avant toute ouverture réelle. Voir [récupération](restore.md) et [incident](incident.md).
