# ADR-0007 — Tirage exact, baux et libération durable

Statut : accepté pour la réalisation locale de phase 5, 15 novembre 2026.

## Décision

Le coffre calcule un couplage parfait uniforme exact pour quatre à vingt personnes, hors soi et
exclusions dirigées. Une table de comptes entiers sur les sous-ensembles pondère chaque choix
secrets.randbelow. Les cycles de deux sont autorisés ; aucun cycle unique imposé. Les comptes
et les choix restent en mémoire ; aucune graine ou empreinte de permutation n'est conservée.

Avant tout tirage, un algorithme de support par cycles alternants teste chaque attribution
possible conditionnellement : tout autre donneur doit conserver au moins deux destinataires
réalisables. Une énumération indépendante de petits graphes vérifie cette optimisation.
La protection ne couvre pas coalitions, indiscrétions ou informations externes.

Le manifeste canonique contient toutes les identités du groupe, noms, pays, règles et exclusions,
sans emails. Tous confirment la même version/empreinte ; un changement invalide tous les accords.
Un compteur ne réutilise jamais un numéro, y compris après réouverture opérateur.

Le job est unique par événement. L'événement est verrouillé avant le job ; un bail et une tentative
monotone empêchent une écriture par un ancien worker. Le calcul se déroule hors transaction.
Le scellement valide le snapshot et écrit dans une transaction résultat chiffré, DRAWN et avis HELD.
Une clé AES-256 aléatoire par résultat est enveloppée sous la clé maîtresse indépendante du coffre.
Les contextes associés lient chiffrement, événement, job et manifeste ; les nonces sont réservés.

Le résultat commence PENDING_DURABILITY. Un processus opérateur distinct chiffre un pg_dump natif,
restaure dans une base neuve isolée et vérifie les octets scellés et le manifeste avant AVAILABLE.
Les avis neutres sont alors mis en queue, avec nouvelle vérification indépendante par le dispatcher.
L'opérateur reçoit uniquement un succès/échec neutre. Un échec de backup ne crée pas un nouveau tirage.

## Conséquences

Coût O(n·2^n) en temps et O(2^n) en mémoire pour les comptes ; limite ferme de vingt.
Le prototype natif utilise un fichier local chiffré, avec restauration effective, sans conteneur
ou pipeline. Il ne démontre pas la survie à la perte de la machine, la conservation des clés ni
l'indépendance de production : ces exigences restent en phase 10.
Les lectures personnelles et la migration des autres données vers des enveloppes restent en phase 6.
L'annulation conserve le ciphertext et ne recolle jamais les attributions.
