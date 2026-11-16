# Restauration en maintenance

Ne jamais relancer le web ou les workers sur un ancien backup en configuration normale.
Arrêter les processus concernés, fermer leur entrée réseau et définir
`FORCE_MAINTENANCE=true` **avant** de connecter le service à la base restaurée. L'option
s'applique également aux workers ; elle est indépendante de l'état stocké dans le backup.

Conserver hors de cette restauration le registre opérateur le plus récent et ses clés.
Restaurer les clés d'authentification, de souhaits historiques, de maîtres et de backups
nécessaires, dans le service autorisé seulement. Le portail ne reçoit jamais celles du coffre.

Pour exercer une copie locale, sans remplacer une base existante :

```powershell
python scripts/noel_operator.py restore-isolated --role vault --archive <archive-chiffrée>
python scripts/noel_operator.py maintenance --role vault --database <noel_recovery_uuid>
python scripts/noel_operator.py recover --role vault --database <noel_recovery_uuid>
python scripts/noel_operator.py status --role vault --database <noel_recovery_uuid>
```

La première commande crée un nom `noel_recovery_` suivi de 32 caractères hexadécimaux.
Le wrapper n'accepte que cette forme pour `--database` et force la maintenance. Aucun
serveur HTTP/worker n'est lancé par ces commandes. Répéter le protocole pour le portail.
Les commandes `manage.py operations` équivalentes sont disponibles dans chaque distribution
pour un opérateur ayant déjà configuré l'environnement indépendant de production.

`recover` réapplique les tombstones avant accès, repurge les événements expirés et demandes
de comptes, contrôle l'identité/fingerprint des tirages connus, déchiffre les résultats,
souhaits et achats, et vérifie la bijection avec le manifeste/exclusions. Il bloque si un
résultat enregistré avant divulgation manque ou diffère. Il ne relance jamais un tirage.
Les jobs non scellés sont clôturés pour revue ; les anciens baux ne peuvent plus sceller.

Les messages restaurés non terminaux, y compris ceux encore `QUEUED` au moment du backup,
passent en `DELIVERY_UNKNOWN`. Ils ne sont pas renvoyés automatiquement : ils ont pu être
acceptés depuis cet instantané. Réconcilier les IDs fournisseur disponibles avec les outils
de lecture existants. Avec SMTP/Zoho sans preuve externe, conserver l'incertitude et utiliser
ensuite le renvoi explicite limité si nécessaire. Ne pas remplacer ce statut par « livré ».
Le rétablissement des rappels exige une confirmation explicite des dates par l'organisateur.

Révoquer les sessions et renouveler les connexions. Vérifier les deux états publics, les
consentements, les files et les anciennes commandes portail retenues. Une commande ancienne
ne doit pas être rejouée aveuglément ; reconstruire l'état depuis le coffre et reprendre
l'action publique idempotente après revue. Un résultat encore en attente de durabilité reste
retenu jusqu'à une nouvelle preuve de backup. `resume` exige une vérification réussie.

Ne retirer `FORCE_MAINTENANCE` et la fermeture réseau qu'après ces contrôles, la validation
de l'opérateur, la commande `resume` sur la base retenue et un redémarrage contrôlé. Tester
connexion et notifications synthétiques séparément des événements réels.

`python scripts/tasks.py backup-drill` exerce pour les deux rôles pg_dump/pg_restore vers
une base jetable, puis une récupération dans un autre processus. Il vérifie une suppression
postérieure au backup, une demande de compte supprimé, un résultat scellé inchangé et la
rétention des envois restaurés. Il n'envoie aucun email réel. Ces preuves locales ne valent
pas restauration indépendante de production ni garantie RPO/RTO.
