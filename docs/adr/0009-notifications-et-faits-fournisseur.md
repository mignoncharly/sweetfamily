# ADR-0009 — Notifications, ambiguïtés et preuves fournisseur

Statut : accepté pour la phase 7 locale, 15 novembre 2026.

Conserver la table PendingMail du coffre et ses FK historiques ; NotificationOutbox est son
nom métier proxy. Ajouter clé d'unicité métier, baux, tentatives et reçus techniques.
Le portail possède sa propre AuthMail pour ses codes, son worker et ses credentials séparés.
Le module public noel_delivery mutualise seulement primitives de transport et calendrier,
jamais modèles métier ou données du coffre dans le portail.

I/O hors transaction SQL, bail et tentative vérifiés au retour. Payload/sender et credential
fingerprint sont figés au premier envoi. Resend dispose d'une clé stable et fenêtre bornée ;
SMTP Zoho ne donne pas cette déduplication. Une ambiguïté SMTP s'arrête immédiatement en
DELIVERY_UNKNOWN. Un renvoi explicite crée une nouvelle notification, pas un nouveau résultat.

Les webhooks sont vérifiés par le SDK officiel sur octets bruts et timestamp frais, puis les
faits minimaux sont commités avant ACK. On conserve des faits distincts plutôt qu'un simple
« dernier événement » écrasant une livraison. Les ouvertures/clics sont ignorés. La réconciliation
ne lit que les faits fournisseur et ne renvoie jamais un email automatiquement après ambiguïté.

Les tâches optionnelles sont proposées puis activées explicitement, datées dans le fuseau local,
avec préférences et revalidation à exécution. Le digest de souhaits est identique au groupe,
regroupé quotidiennement, sans nom de propriétaire ou d'acheteur. La projection reste fermée.

Mailpit est la simulation. Resend réel reste non vérifié. À la demande de l'utilisateur, Zoho EU
est aussi supporté avec info@gestionatech.de comme boîte d'essai ; le chemin du .env gtech sera
fourni plus tard. Aucun secret copié ou essai externe effectué sans ces paramètres. Le domaine
sweetfamily.gestionatech.de n'est ni connecté ni déployé par cette phase. L'isolation de production,
DNS, comptes indépendants et restauration fournisseur restent conditionnels à leur qualification.
