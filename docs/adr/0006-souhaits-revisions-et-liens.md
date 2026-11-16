# ADR-0006 — Souhaits privés, révisions et liens marchands

Date : 15 novembre 2026. Statut : appliquée en phase 4.

Les contenus des souhaits restent exclusivement au coffre. Wishlist conserve propriétaire, état,
révision courante et date de validation. GiftWish réserve trois slots UUID stables ; les contenus
courants et historiques sont dans les snapshots chiffrés WishlistRevision. Les montants EUR y
restent des entiers de centimes, validés côté serveur, sans float ni conversion automatique.

Le chiffrement de phase 4 utilise AES-256-GCM de cryptography avec une clé dédiée au coffre,
versionnée dans l'environnement. Un registre SQL réserve chaque nonce de 96 bits avant le
chiffrement ; l'identité événement/membre/liste/révision figure dans les données associées.
Le registre n'a pas de lien personnel et survit à la suppression des listes tant que la clé
reste utilisable. Ce socle évite un historique privé en clair dès la phase 4. La migration vers
les enveloppes par événement et la rotation/restauration restent à qualifier en phase 6/10.

Les écritures prennent le verrou d'événement et comparent la révision attendue dans la même
transaction. Les lectures ne créent pas de liste. Une liste validée conserve trois souhaits
valides à chaque édition, y compris après DRAWN ; aucune opération de liste ne touche un tirage.
Le coût de cette sérialisation pour vingt personnes sera mesuré en phase 9.

Les liens sont vérifiés syntaxiquement puis comparés à une liste fermée de domaines marchands,
sans résolution DNS ni récupération réseau de contenu. Aucun scraping, vignette distante,
réécriture automatique de fiche par pays ou redirecteur de l'application. Une demande d'ajout
est un enregistrement local pour l'opérateur, sans fetch ni approbation automatique.

Les paramètres originaux sont conservés pour ne pas casser une référence produit. L'heuristique
de doublon compare seulement hostname normalisé, chemin et paramètres hors tracking/fragment ;
elle ne prétend pas reconnaître un même article entre marchands. L'aide à la recherche utilise
le pays explicite de l'acheteur et encode le titre comme terme de recherche, pas comme chemin
de fiche produit. La référence du destinataire est conservée.

Le portail reçoit uniquement le booléen wishlist_complete réel, dans la projection fermée.
Les modifications d'une liste validée ne changent pas ce booléen et ne déclenchent aucun message
ciblé permettant de corréler propriétaire et acheteur. L'accès aux souhaits de la personne tirée,
la comparaison au moment du choix et le digest neutre de changement restent en phases 6 et 7.
