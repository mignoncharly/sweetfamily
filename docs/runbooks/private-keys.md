# Clés et espaces privés — exploitation native

Les clés restent hors PostgreSQL et hors distributions. Le compte du coffre, ses domaines,
TLS, accès SQL, secrets et récupération doivent être indépendants du portail. Le poste partagé
local ne prouve pas cette indépendance. Ne pas communiquer de clé dans un ticket ou cette conversation.

## Stockage livré

DRAW_MASTER_KEYS est le nom de configuration conservé depuis la phase 5 : une map JSON de versions
maîtresses base64, avec DRAW_ACTIVE_KEY. Les versions sont immuables ; ne jamais remplacer la valeur
d'un identifiant ni renommer une même clé pour contourner le registre de nonces. Les paramètres
refusent clés dupliquées et réutilisation des clés d'authentification ou de souhaits historiques.
Le fournisseur local AES-GCM est connecté. MasterKeyProvider définit le point d'intégration d'un
futur adaptateur KMS ; aucun KMS ni hébergement externe n'est connecté ou qualifié.

EventDataKey enveloppe une clé AES-256 par événement pour les historiques de souhaits et achats.
Le résultat scellé garde sa clé AES-256 propre à l'événement, créée en phase 5, afin de conserver
son ciphertext et ses archives. Les deux enveloppes se rewrappent sous les mêmes versions maîtresses.
Tous les nouveaux nonces passent par le registre central DrawNonce (nom historique conservé).
Les anciens WishlistNonce restent conservés pour les clés historiques.

## Migration des souhaits existants

python scripts/tasks.py migrate applique les migrations puis convertit les révisions historiques
v1 vers les enveloppes v2, événement par événement, sous verrou transactionnel. Une interruption
est reprenable ; les révisions utilisateur et UUID de souhait ne changent pas. Un échec annule
l'événement traité, sans rendre les anciennes clés inutiles et sans créer un nouveau tirage.
Commande locale ciblée :

~~~powershell
python scripts/noel_operator.py migrate-envelopes <event_uuid>
~~~

Conserver WISHLIST_KEYS même après migration : les sauvegardes antérieures en dépendent encore.
Une clé manquante ou corrompue donne une erreur neutre et un SecurityEvent local. Le coffre ne
génère jamais une clé de remplacement si des objets v2 ou achats existent déjà. Ne pas réinitialiser
les enveloppes pour masquer une erreur. Restaurer les clés appropriées ou traiter un incident.

## Rotation locale sans nouveau tirage

Arrêter les processus coffre pendant une opération globale afin qu'ils utilisent la même map de clés.
La version d'exemple v2 est un identifiant opaque ; le script produit la valeur secrète sans affichage.

~~~powershell
python scripts/noel_operator.py stage-master-key --to-key v2
python scripts/noel_operator.py rotate-keys <event_uuid> --to-key v2
python scripts/noel_operator.py activate-master-key --to-key v2
~~~

Le staging est idempotent et ne remplace jamais une valeur existante. Pour une rotation globale,
traiter tous les événements avant retrait éventuel d'une ancienne version. La rotation réenveloppe
les clés de données ; ni permutation, ciphertext métier, nonce de données, état de consultation,
choix d'achat ni révision ne changent. Activation change seulement la version utilisée pour les
nouvelles enveloppes. Redémarrer les processus avec la map complète, puis confirmer une nouvelle
sauvegarde chiffrée restaurée du même résultat. Ne jamais appeler draw pour tester une rotation.

En distribution native : manage.py migrate_private_envelopes [--event-id UUID], puis
manage.py rotate_private_keys --to-key VERSION [--event-id UUID]. Ces commandes attendent les
variables du coffre, sans dépendre du runner local. Le secret manager de production doit fournir
l'ancienne et la nouvelle version pendant la transition ; le fichier local .env n'est pas ce manager.

## Sauvegarde et restauration des clés

Sauvegarder séparément la map complète maîtresse, les clés d'authentification, WISHLIST_KEYS
historiques et la clé des archives. Une archive d'avant rotation contient les anciennes clés de
données enveloppées : elle exige l'ancienne version maîtresse. Les essais locaux vérifient cette
compatibilité, pas une récupération indépendante de l'infrastructure. Ne retirer une ancienne
version qu'après expiration/purge de toutes les données et archives qui en dépendent, et après
une recette de restauration indépendante en phase 10. Le registre de nonces doit être restauré
avec les données ; une restauration globale doit aussi respecter le registre de suppression.

## Mémoire et processus de production

Avant de servir le WSGI du coffre ou son worker, les hooks de debugger/profiler Python et modules
debugpy/pydevd/pdb connus sont refusés, ainsi que PYTHONINSPECT/PYTHONFAULTHANDLER. Les breakpoints
Python sont désactivés. Sur Unix, RLIMIT_CORE est fixé à zéro ; Linux passe aussi en non-dumpable
avec prctl. Ces branches Unix ne sont pas exécutées sur le poste Windows de qualification.
Sur Windows, le coffre refuse les configurations WER LocalDumps et debugger postmortem AeDebug
repérées dans la vue 64 bits du registre. Il ne modifie pas les réglages de la machine.
L'opérateur doit désactiver la collecte de dumps et les outils APM/EDR qui capturent mémoire ou
variables, interdire l'attachement de debugger dans le compte de service et qualifier la politique
OS avant production. Aucune garantie contre l'opérateur privilégié, ni effacement mémoire garanti
par Python. La surveillance externe des alertes neutres reste à configurer en phase 10.

Références : [resource Python](https://docs.python.org/3/library/resource.html),
[Linux non-dumpable](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html),
[WER LocalDumps](https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps).
