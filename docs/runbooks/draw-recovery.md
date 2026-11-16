# Reprise du tirage — phase 5 locale

Le coffre fait autorité. Ne jamais changer manuellement un état pour obtenir un nouveau tirage.
La permutation ne doit pas être affichée dans une console, un ticket, un audit ou un hash public.

## Calcul interrompu

Un worker peut reprendre un bail expiré avec un numéro de tentative supérieur ; l'ancien worker
ne peut plus sceller. Avant commit, aucun résultat n'est exposé. Après commit, seul le résultat
scellé est repris, même si le worker n'a pas reçu la réponse. Une erreur technique laisse le
même job en FAILED_RETRYABLE, puis FAILED_FINAL après trois calculs échoués.

En FAILED_FINAL sans résultat, l'opérateur local peut exécuter :

~~~powershell
python scripts/noel_operator.py reopen-failed <event_uuid>
~~~

Le groupe revient OPEN, tous les consentements sont supprimés, les baux sont révoqués.
Un nouveau gel incrémente le manifeste et exige de nouvelles confirmations avant le même job.
Si un résultat scellé existe, la commande échoue : reprise de ce résultat ou annulation explicite.

## Résultat en finalisation

~~~powershell
python scripts/noel_operator.py confirm-durability <event_uuid>
~~~

Cette commande utilise pg_dump natif, chiffre l'archive Fernet avec VAULT_BACKUP_KEY, écrit et
synchronise le fichier, relit/déchiffre, restaure via pg_restore dans une nouvelle base isolée,
vérifie les octets scellés et le manifeste, puis supprime uniquement cette base temporaire.
Aucun worker, app, email ou projection n'est lancé contre la restauration. Les fichiers chiffrés
restent dans .local/backups. Le reçu privé contient l'empreinte de l'archive chiffrée, jamais celle
de la permutation. Une commande répétée après réussite ne crée pas de nouveaux avis.

Toute erreur retourne un échec neutre. Vérifier espace disque, accès opérateur, outils et clés,
puis relancer la sauvegarde du même résultat. Ne pas relancer le tirage. Si l'événement a été
annulé pendant la sauvegarde, la libération est refusée. Aucun endpoint HTTP ne libère le résultat.
En distribution, utiliser manage.py confirm_draw_durability UUID --directory CHEMIN avec PG_BIN,
BACKUP_DB_USER, BACKUP_DB_PASSWORD et BACKUP_ENCRYPTION_KEY réservés au processus opérateur.
Les variables DB du coffre restent nécessaires ; leur mode TLS est repris par les outils de backup.

Le compte opérateur doit pouvoir créer et supprimer sa base temporaire ; le compte app n'obtient
pas ce privilège. Protéger le répertoire et les clés par ACL. Sauvegarder séparément DRAW_MASTER_KEYS,
WISHLIST_KEYS et les clés d'authentification, ainsi que la clé de chiffrement des archives.
La production exige copie hors machine, gestion de rétention, récupération des clés et opérateur
indépendant, qualifiés en phase 10. Cette restauration locale ne remplit pas ces garanties.

## Retrait ou annulation

Avant calcul : le retrait invalide toutes les confirmations ; moins de quatre membres bloque
le gel. Dès DRAWING ou DRAWN : le retrait annule tout l'événement et envoie des avis neutres.
Le ciphertext reste inchangé. Ne jamais recoller les associations. Une annulation ne peut effacer
ce qu'une personne a déjà vu ou acheté. Un nouvel échange exige un nouvel événement et ses consentements.
