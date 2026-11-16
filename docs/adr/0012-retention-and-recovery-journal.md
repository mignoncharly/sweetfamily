# ADR-0012 — Maintenance et registre externe de récupération

Statut : adopté pour l'implémentation native locale, qualification de production requise.

La restauration d'un ancien dump ne doit ni ressusciter une suppression, ni réexpédier une
outbox déjà traitée, ni remplacer un tirage divulgué. Un marqueur dans la seule base restaurée
ne suffit pas. Chaque rôle reçoit donc un registre externe chiffré/authentifié et des
tombstones SQL, ainsi qu'un état de maintenance minimal.

Chaque suppression écrit et flush son reçu externe avant le commit SQL. Une interruption
peut laisser la donnée encore présente avec son tombstone externe : la reprise supprime
alors de nouveau avant réouverture. Elle ne peut pas laisser une suppression SQL validée
sans reçu écrit. Les tombstones d'événements ne contiennent aucun prénom/email. Les demandes
de compte utilisent un identifiant et une empreinte HMAC, avec date. Un résultat scellé
est enregistré par ID et fingerprint de nonce/ciphertext avant disponibilité ; aucune
permutation n'est exportée. Une rotation du wrapping ne modifie pas ce fingerprint.

Les fichiers sont propres à un rôle, écrits dans un temporaire exclusif, fsync puis renommés.
Un temporaire inachevé bloque la récupération. Le stockage, ses droits, son indépendance,
sa fraîcheur et sa résistance à la panne restent à qualifier par l'opérateur ; la signature
ou le chiffrement ne détecte pas à lui seul un rollback de tout le stockage externe.

Les requêtes web et ticks de worker prennent un verrou advisory PostgreSQL partagé de
session. L'opérateur prend le verrou exclusif de transaction avant une transition ou purge.
Ce choix attend la fin des actions engagées sans englober le worker dans une transaction
unique : les commits précédant un envoi ou le calcul d'un tirage restent effectifs.
`FORCE_MAINTENANCE=true` protège aussi un backup contenant un ancien état « ouvert ».

Les suppressions explicites du tirage précèdent celles de l'événement, sans changer les
relations `PROTECT` utilisées pendant la vie normale du produit. L'opération de rétention
reste atomique en SQL ; voir [transactions Django](https://docs.djangoproject.com/en/5.2/topics/db/transactions/)
et [suppression et verrouillage des querysets](https://docs.djangoproject.com/en/5.2/ref/models/querysets/).

Après restauration, tous les anciens messages non terminaux sont retenus, même `QUEUED` :
leur envoi a pu avoir lieu depuis le dump. Les IDs fournisseur sont réconciliés sans renvoi,
SMTP reste incertain. Les jobs non scellés et commandes portail encore pendantes sont retenus
pour revue, les sessions révoquées et rappels désactivés. La vérification ordinaire sans
restauration conserve ces états courants. Les deux parcours exigent les clés privées encore
utilisées et la réapplication du registre avant autorisation de reprise.

Les comptes vérifiés conservés à la demande du titulaire sont réutilisés lors d'une nouvelle
invitation après purge de l'ancienne identité d'événement. Aucun souhait, consentement ou
résultat n'est repris pour la nouvelle année.
