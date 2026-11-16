# Contrats de phase 3

Les chemins sans barre finale sont ceux des API métier ; les routes allauth gardent leur barre finale.
Portail et coffre ont des cookies, secrets, connexions SQL et domaines propres. Les erreurs métier
contiennent code, message français et correlation_id opaque. 401/403 pour identité insuffisante,
404 uniforme pour événement inaccessible, 409 pour version/commande incompatible, 503 pour transport
indisponible, 429 ou erreur de formulaire pour limitation allauth. CSRF obligatoire sur toute mutation
web ; seule la vérification cryptographique dédiée remplace CSRF sur les endpoints de service.

## Identité et accès

Le portail permet l'inscription email via /accounts/signup/. Le coffre refuse l'inscription publique :
ses comptes sans mot de passe utilisable sont préparés seulement par une invitation authentifiée.
Dans les deux services : /accounts/login/code/, /accounts/login/code/confirm/, /accounts/logout/,
 /accounts/email/, /accounts/2fa/ et /accounts/sessions/ sont gérés par django-allauth 65.22.1.
Les formulaires et emails sont traduits par la bibliothèque et intégrés dans un cadre local français.

Challenges de connexion/vérification : 600 secondes, cinq essais maximum, deux renvois au plus pour
la connexion. Limite de demande : trois/minute par email et soixante/minute par IP, pour permettre
plusieurs membres sur une connexion familiale. Compteurs dans PostgreSQL, clés de cache HMACées ;
sessions et secrets MFA chiffrés avec Fernet. Les POST allauth portant une session existante sont
sérialisés sous verrou SQL jusqu'à la sauvegarde de session, afin d'éviter les mises à jour perdues
des compteurs. Les réponses de demande de code connu/inconnu ont la même redirection publique.
Ouverture d'invitations : dix/heure par compte organisateur et trente/heure par IP ;
corrections : trente/heure par compte et soixante/heure par IP. Le coffre impose aussi
trois réémissions maximum par membre sur une heure glissante, invitation initiale comprise.

Email vérifié et MFA réellement accompli dans la session sont requis pour toutes les API organisateur,
y compris en local. Activer un facteur puis se reconnecter ; posséder une ligne Authenticator sans
preuve MFA dans la session ne suffit pas. Le dernier facteur TOTP/passkey ne peut pas être retiré
tant que la personne possède des événements. Les codes de récupération sont affichés une seule fois.

Un lien d'invitation contient 32 octets aléatoires minimum, expire après sept jours et n'est stocké
qu'en empreinte SHA-256 dans Invitation. Le payload email temporaire est chiffré séparément puis purgé
après envoi/expiration. GET /join/{token} présente l'événement sans session ni mutation métier.
POST prépare l'inscription et redirige vers le code email. Le contexte d'invitation peut survivre
à la rotation de session grâce à un cookie signé HttpOnly de dix minutes contenant uniquement
l'empreinte ; ce cookie n'authentifie personne. POST /api/me/invitations/accept vérifie sous verrou
l'invitation, la boîte vérifiée et l'identité exacte, puis consomme le lien une seule fois.

## Portail

| Route | Contrat |
|---|---|
| GET/POST /api/events | Liste de ses événements ou création d'un brouillon |
| GET/PATCH /api/events/{id} | Propriétaire vérifié ; PATCH avec version et event complet ; brouillon seulement |
| POST /api/events/{id}/participants | version, display_name, country ISO, email ; zéro envoi immédiat |
| POST /api/events/{id}/open | version et header Idempotency-Key ; groupe de 4 à 20 ; snapshot durable puis commande signée |
| GET /api/events/{id}/status | Noms/pays/emails saisis, inscription et état neutre de notification uniquement |
| POST /api/events/{id}/participants/{member_id}/email | version, email et Idempotency-Key ; correction non revendiquée validée par le coffre |

Création : title (1–120 caractères), celebration_at et wishlist_deadline (ISO 8601 avec offset,
échéance avant réveillon), timezone (IANA), shipping_included (booléen), handover (1–500).
Aucune date imposée. PATCH utilise exactement {version, event: ces six champs}.
Ajout : exactement {version, display_name, country, email}. Nom d'affichage distinct dans le groupe,
80 caractères maximum ; des prénoms identiques peuvent employer « Alex FR » et « Alex DE ».
Les emails sont nettoyés par EmailField allauth ; aucune suppression des points ou suffixes +.

Ouvrir stocke ControlCommand avant le transport. Une panne laisse PUBLISHING et permet de réessayer
avec la même clé ; un changement de contenu sous cette clé est refusé. Le coffre reste l'autorité.
La réponse ne contient aucun jeton privé. Les audits gardent des catégories, pas les payloads email.

## Coffre

| Route | Contrat |
|---|---|
| GET /api/me/events | Appartenances revendiquées de l'identité vérifiée connectée |
| GET/PATCH /api/me/profile?event_id={uuid} | Événement autorisé à chaque appel ; aucun participant_id sélectionnable |
| POST /api/me/invitations/accept | Invitation préparée par POST /join ; aucune revendication par GET |
| POST /internal/commands | Enveloppe signée de commande ; pas de session navigateur requise |

PATCH profil utilise exactement revision, display_name, country ; conflit si révision ancienne.
Avant tirage, un changement rouvre la préparation et invalide les consentements. Après DRAWN,
l'attribution sera conservée ; aucun moteur de tirage n'existe encore dans cette phase.
Le profil retourne son email actuel seulement ; cet email n'enrichit pas la projection portail.
La liste et l'acceptation du manifeste gelé sont livrées en phase 5, après les souhaits de phase 4.

## Transport authentifié et projection

Format JSON fermé : id UUID, schema_version=1, timestamp Unix entier, nonce aléatoire, type, payload,
body_digest SHA-256 du type/payload canonique et signature Ed25519 de l'enveloppe sans signature.
JSON canonique : clés triées, séparateurs compacts, UTF-8. Fenêtre de fraîcheur de cinq minutes.
Les ID et nonces sont persistés au coffre. Un même ID et contenu retourne le reçu précédent
sans réémettre d'invitation ; un contenu différent ou nonce déjà affecté à un autre ID est refusé.

Types actuels : open et correct_invitation. open porte event_id, version, event et members ;
chaque membre porte id UUID, display_name, country, email. correct_invitation porte event_id,
version, member_id, email. Tout autre type/champ est refusé. Aucun secret participant dans la réponse.

Le coffre signe les status_projection avec une AUTRE paire de clés. POST /internal/status-projections
sur le portail accepte uniquement le schéma fermé de docs/permissions.md, event_id et projection_version
dans le payload de transport. Le dernier numéro appliqué est persisté ; les anciennes versions sont
ignorées. Références étrangères, doublons et champs supplémentaires sont refusés.
La projection est regroupée toutes les quinze minutes, sans horodatage individuel ; un échec de
transport entraîne une nouvelle tentative après trente secondes. Les états de souhait/tirage/achat
restent incomplets car ces fonctions ne sont pas implémentées. SUBMITTED en local signifie remis
au SMTP Mailpit, jamais livraison à une vraie boîte.

## Secrets et exécution locale

bootstrap/migrate génèrent les nouvelles clés locales sans affichage. Les apps reçoivent seulement :
AUTH_DATA_KEY propre au service ; COMMAND_KEY privée côté portail/publique côté coffre ;
PROJECTION_KEY privée côté coffre/publique côté portail ; PUBLIC_ORIGIN, CONTROL_ORIGIN, VAULT_ORIGIN.
Hors local, les trois origines doivent être HTTPS ; les clés privées ne changent jamais de frontière.
Ces clés ne figurent ni dans la base ni dans les distributions. Sauvegarder les clés d'authentification
séparément avant tout changement : remplacer AUTH_DATA_KEY invalide les sessions et rend les anciens
secrets MFA illisibles sans migration. La rotation contrôlée et restauration restent en phases 6/10.

Le worker coffre traite les emails d'invitation/authentification dans une queue SQL chiffrée avec
verrou, délais et cinq tentatives bornées ; expiration ou succès purge le payload. Changement d'email
révoque les anciennes sessions et challenges, sans modifier les identifiants d'appartenance.
Ce dispatcher local ne revendique ni envoi exactement une fois, ni réconciliation fournisseur :
leases, outbox métier complète et adaptateur Resend sont à qualifier en phase 7. Hors local,
le backend réel reste explicitement bloqué. Aucun envoi réel n'est réalisé par ces commandes.

## Phase 4 — souhaits privés

Les routes restent sur le coffre, avec session personnelle vérifiée, appartenance revendiquée
et event_id explicite à chaque requête. Le navigateur ne choisit jamais un autre membre.

| Route | Usage |
|---|---|
| GET /wishlist?event_id={uuid} | Éditeur HTML privé, aucun enregistrement par GET |
| POST /wishlist?event_id={uuid} | Formulaire CSRF, sauvegarde ou validation explicite |
| GET /api/me/wishlist?event_id={uuid} | Liste courante ; révision zéro/brouillon vide si aucune liste |
| GET /api/me/wishlist?event_id={uuid}&revision={entier} | Ancienne révision de sa propre liste |
| PUT /api/me/wishlist?event_id={uuid} | Objet exact revision + wishes ; contrôle optimiste |
| POST /api/me/wishlist/validate?event_id={uuid} | Objet exact revision ; exige trois souhaits complets |
| POST /api/me/merchant-requests?event_id={uuid} | Objet exact hostname ; demande stockée sans fetch, dix domaines maximum |

Un souhait d'entrée contient exactement slot (1–3), title (160 caractères maximum), url HTTPS,
price_eur_cents (entier 1–4999), currency (code ISO d'origine), price_date (ISO YYYY-MM-DD),
note (1000 caractères maximum), exact_model et equivalent_ok (booléens non simultanément vrais).
Pour un brouillon incomplet, title/url/date peuvent être vides et price_eur_cents null.
Un montant fourni doit toujours être valide. La validation exige les trois emplacements complets ;
une liste validée conserve trois souhaits valides lors des modifications, même dans l'état DRAWN.

La devise d'origine ne déclenche aucun calcul : le prix EUR est saisi manuellement et marqué
comme estimation lorsque currency diffère de EUR. Tous les prix restent indicatifs, jamais vérifiés.
Lorsque shipping_included est vrai, price_eur_cents est le total estimé frais compris ; sinon les
frais sont hors plafond. Cette base est enregistrée dans la révision. Le coût final dans le pays
de l'acheteur doit toujours être vérifié chez le marchand avant achat.

La lecture ajoute id stable de chaque emplacement et métadonnées merchant_domain, indicative,
eur_estimate et shipping_included. Ces champs calculés ne sont pas acceptés en écriture.
Une validation produit une nouvelle révision comme une modification. Un ancien numéro retourne
409, sans effacer le formulaire ou écraser la liste. Les historiques ne sont pas exportés au portail.
Les événements DRAWING/CLOSED/CANCELLED/ARCHIVED refusent les modifications ; l'état DRAWN est
supporté par le moteur livré en phase 5.

La liste de marchands est le fichier local vault_core/merchants.json, remplaçable par
MERCHANT_ALLOWLIST sur l'exploitation du coffre. Amazon FR/DE, Fnac, Thalia et Decathlon FR/DE
illustrent les recherches explicites. L'opérateur ajoute un domaine exact, son nom, pays ISO et
préfixe HTTPS de recherche ; aucun wildcard, domaine raccourci, IP ou identifiant intégré.
Les domaines non approuvés sont refusés. Une demande d'ajout n'est ni une approbation ni un fetch.

Les URLs sont bornées à 2048 caractères, normalisées par hostname IDNA et ouvertes avec
noopener/noreferrer. L'application n'est pas un redirecteur. Les paramètres produits sont conservés ;
aucune suppression automatique de tracking n'est faite sans preuve de conservation de la référence.
Pour détecter un doublon évident seulement, fragment et paramètres UTM/gclid/fbclid sont ignorés ;
les variantes produits restent distinctes. Cela ne reconnaît pas les mêmes articles entre marchands.

L'aide shopping_advice reçoit explicitement le pays de l'acheteur et conserve la référence originale.
Dans l'éditeur actuel, il s'agit d'un aperçu sur ses propres souhaits. L'endpoint de résultat
privé réutilise cette fonction après autorisation de l'attribution en phase 6 ; aucun accès libre
à une liste étrangère n'est ajouté. Les liens de recherche ne promettent pas qu'une fiche existe,
ni stock ou livraison. L'application ne collecte adresse postale ou données de paiement.

Chiffrement actuel : AES-256-GCM via cryptography, clé dédiée WISHLIST_KEYS versionnée, nonce 96 bits
réservé dans WishlistNonce avant chiffrement, contexte associé événement/membre/liste/révision.
Les contenus sont dans WishlistRevision ; GiftWish ne garde que les UUID et slots stables.
Le registre sans lien personnel est conservé tant que la clé correspondante reste utilisable,
même si une liste est supprimée. Les clés sont hors base, dépôt et archives. Ne pas retirer une
ancienne clé avant migration/purge des historiques et expiration de ses sauvegardes.
Les enveloppes par événement, rotation et restauration de production restent en phases 6 et 10.

La projection du coffre remplace uniquement wishlist_complete par l'état VALIDATED réel,
sans titre, URL, prix, note, identifiant de souhait, révision privée ou timestamp fin.
Aucune modification de liste n'émet de notification ciblée au portail ou à un acheteur.

## Phase 5 — manifeste et cycle de vie

Toutes les commandes portail ci-dessous sont POST /api/events/{uuid}/{action}, avec session
organisateur vérifiée + MFA, CSRF et Idempotency-Key (1–100 caractères). Le corps JSON est fermé :

| action | Corps, en plus de version (entier attendu) |
|---|---|
| rules | event, même objet public que la création |
| exclusions | exclusions, liste de paires dirigées [member_uuid, member_uuid] |
| confirm-roster | Aucun ; gèle le manifeste et demande les confirmations |
| draw | Aucun ; exige READY et revérifie listes/identités/consentements |
| remove-member | member_id et confirm:true |
| cancel | confirm:true, conséquences pour tout le groupe |
| close | confirm:true, uniquement DRAWN et AVAILABLE |

Le coffre reçoit ces actions signées comme update_rules/exclusions/freeze/draw/remove_member/
cancel/close. Un reçu contient seulement event_id, version et state. Un double déclenchement
ne crée jamais un second job. Réutiliser la clé avec un autre corps est un conflit. Le coffre
reste autorité sur les versions ; les anciens reçus ne font pas régresser l'état du portail.
Les changements structurels suppriment tous les consentements et réouvrent OPEN. Chaque gel
incrémente le compteur de manifeste, sans réutiliser un ancien numéro.

Routes coffre, session vérifiée et appartenance revendiquée, avec event_id en query :

| Route | Contrat |
|---|---|
| GET /rules | Roster public, pays, règles, exclusions et formulaire de confirmation CSRF |
| GET /api/me/roster | manifest + manifest_digest ; uniquement CONFIRMING ou READY |
| POST /api/me/roster-consent | Exactement manifest_version (entier) et manifest_digest |
| POST /api/me/withdrawal | Exactement confirm:true ; annule tout échange déjà lancé |

Le manifeste contient event_id, version, event (règles publiques, plafond EUR4999, trois souhaits),
members (id, display_name, country), exclusions dirigées ; aucun email ou souhait.
Son empreinte SHA-256 porte uniquement sur ce contenu public canonique. La protection contre
les déductions vérifie les couplages conditionnels, sans couvrir coalitions ou informations externes.
La permutation est chiffrée sous une clé de données AES-256-GCM aléatoire, enveloppée sous une clé
maîtresse indépendante. Aucun hash de permutation, graine ou choix intermédiaire n'est persisté.

La projection ajoute event_version (entier public monotone, optionnel pour compatibilité des
projections de phase 3), et transporte les états réels de consent_received et draw_progress.
Le portail conserve ces seuls statuts et manifest_version ; aucune attribution ou révision privée.
Le résultat reste PENDING_DURABILITY/FINALIZING et les avis HELD jusqu'à sauvegarde chiffrée,
restauration isolée et vérification. L'opérateur libère alors AVAILABLE et les avis neutres.
Les endpoints d'attribution sont livrés en phase 6 ci-dessous. Les actions d'archivage/purge restent
à livrer en phase 10 ; elles ne simulent pas une réussite.

## Phase 6 — attribution et préparation personnelles

Les routes ci-dessous sont uniquement sur le coffre, avec session personnelle vérifiée,
appartenance active revendiquée et exactement event_id en query. Tout identifiant supplémentaire
(member_id, recipient_id, etc.) est refusé. Une signature ou credential de service n'authentifie
jamais ces routes. Le navigateur ne peut pas demander « qui m'offre » ou une autre attribution.

| Route | Contrat |
|---|---|
| GET /private?event_id={uuid} | Écran neutre, aucun nom de destinataire ni souhait affiché |
| POST /private?event_id={uuid} | Révélation explicite, puis formulaire de préparation personnelle, avec CSRF |
| GET /api/me/recipient?event_id={uuid} | Seulement recipient(display_name,country), revision courante, trois wishes et advice selon pays de l'acheteur ; aucune consultation marquée |
| POST /api/me/recipient/reveal?event_id={uuid} | Objet vide {}, marque recipient_viewed et retourne le même résultat ; idempotent |
| GET /api/me/purchase?event_id={uuid} | État personnel, défaut NOT_STARTED/révision 0, sans création en GET |
| PUT /api/me/purchase?event_id={uuid} | Objet exact revision,state,wish_id,wish_revision,note ; conflit optimiste 409 |

Le tirage doit être AVAILABLE, avec événement DRAWN ou CLOSED pour lecture ; seule DRAWN permet
les écritures de préparation. PENDING_DURABILITY/CANCELLED/ARCHIVED sont refusés. La préparation
exige une révélation explicite préalable. Champs d'achat : state parmi NOT_STARTED, ORDERED,
RECEIVED, READY, GIVEN ; note texte de 1 000 caractères maximum ; wish_id d'un des trois souhaits
attribués et wish_revision positive consultée. Sans choix, wish_id/wish_revision sont null et
state doit être NOT_STARTED. Un nouveau choix exige la révision courante ; un choix historique
identique reste conservé lors des changements d'avancement. Chaque écriture incrémente revision.

La lecture d'achat ajoute selected_wish (ancienne référence choisie), current_wishlist_revision
et wishlist_changed, pour comparer après modification sans refaire le tirage. Aucun choix,
avancement ou note n'est retourné au propriétaire de la liste, ni dans une projection portail.
L'état peut être corrigé explicitement ; aucune commande commerciale n'est exécutée par le produit.
La page permet de confirmer explicitement le choix avec la liste courante.

Les souhaits v2 et achats utilisent la clé de données enveloppée EventDataKey. Les anciennes
révisions v1 restent lisibles avec WISHLIST_KEYS jusqu'à migration et expiration des archives.
La rotation de la clé maîtresse change seulement les enveloppes de clés ; les résultats scellés
restent les mêmes. Voir [clés](runbooks/private-keys.md). Une enveloppe manquante/corrompue est
refusée avec 503 et alerte neutre ; aucune clé de remplacement ou nouveau tirage automatique.

La projection fermée conserve ses champs : recipient_viewed vient du POST explicite,
ready_count additionne uniquement READY/GIVEN. Ces informations sont périodiques, sans
identifiant de souhait, état individuel d'achat, note ou timestamp fin. Le portail conserve
les booléens et le total dans son API propriétaire ; aucun credential portail ne lit l'espace privé.

## Phase 7 — notifications, suivi et préférences

Les codes du portail passent par AuthMail, les messages du coffre par NotificationOutbox,
proxy métier de la table PendingMail conservant ses FK. Les payloads chiffrés ne sont jamais
retournés aux API. Chaque message possède une clé métier durable (événement, membre, type,
version logique), une tentative monotone, un bail et un HMAC secret de contenu. Les credentials
et expéditeurs sont configurés séparément par service. Aucune table du portail ne contient
souhait, choix d'achat ou association de tirage.

| Route | Contrat |
|---|---|
| GET portail /api/events/{uuid}/reminders | Organisateur MFA propriétaire : propositions à 18:00 locale, dates/version et activation actuelle |
| POST même route | Idempotency-Key, corps fermé version, enabled(bool), wishlist_deadline et celebration_at courants confirmés |
| POST portail /api/events/{uuid}/resend-notice | Idempotency-Key, version, member_id du roster et notice_type limité |
| GET/PATCH coffre /api/me/notification-preferences?event_id={uuid} | Session vérifiée/appartenance ; PATCH contient seulement reminders_enabled(bool), avec CSRF |
| GET/POST coffre /notifications?event_id={uuid} | Préférence personnelle et suivi neutre ; mode Mailpit marqué Simulation |
| POST /webhooks/resend sur chaque service | Public, CSRF exempt, signature SDK sur corps brut + timestamp frais + svix-id ; aucun cookie de service ou participant |

La création d'événement accepte reminders_enabled facultatif, false par défaut ; les dates du
formulaire sont alors les dates explicitement validées. Le champ voyage dans la commande open
signée ; le coffre conserve l'autorité et initialise les tâches. Après ouverture, activer via
la commande configure_reminders avec version et dates exactes. Une modification de règles/dates
invalide les anciennes tâches ; activation ne change aucune attribution.

resend_notice permet INVITATION, CONSENT, DRAW_READY, LIST_REMINDER ou PREPARATION, selon état,
inscription et préférences. Maximum trois renvois/membre/heure et quarante/événement/heure ;
429 au-delà, sous réserve de la borne d'invitation historique plus stricte. Une répétition de
la même commande retourne le même reçu. Un nouveau renvoi crée seulement un nouveau courrier
neutre ; DRAW_READY exige AVAILABLE, ne relance ni job ni hasard ni scellement.

Les rappels optionnels sont J-7/J-2 de l'échéance de souhaits et J-7/J-1 du réveillon, à 18:00
locale. Chaque tâche vérifie version, échéance, utilité, membre et préférences à la mise en queue
et à l'envoi. Une tâche périmée après panne est ignorée. Les digests de souhaits sont groupés à
18:00, une fois par date locale pour tout le groupe, sous préférences facultatives. Aucun corps
ne contient de personne tirée, souhait, note ou achat. Les notifications du résultat sont HELD
dans la même transaction que le scellement, libérées uniquement après confirmation de durabilité.

Resend reçoit toujours la même clé SERVICE_ROLE/notification_uuid et le même corps. Fenêtre
applicative limitée à 23 h 55, maximum cinq tentatives, puis DELIVERY_UNKNOWN/réconciliation.
Un changement de corps, sender ou credential pendant une reprise est refusé. Les faits vérifiés
sont commités avant ACK ; doublons dédupliqués et ordre d'arrivée non autoritaire. ACCEPTED,
DELIVERED, DEFERRED, REJECTED et FAILED sont conservés distinctement. Une acceptation tardive
n'efface pas DELIVERED. Les erreurs détaillées, adresses/corps de webhook et IDs fournisseur
restent hors projection. Les événements d'ouverture/clic ne modifient jamais recipient_viewed.

Zoho SMTP TLS conserve SUBMITTED après acceptation du relais. Sans webhook/API de preuve,
le code ne fabrique pas DELIVERED. Une ambiguïté ou un worker mort pendant SMTP passe en
DELIVERY_UNKNOWN sans reprise automatique, car Message-ID n'est pas une déduplication garantie.
La projection garde strictement notification_state, sans codes, corps, erreur détaillée ou
association. Une tâche devenue inutile expire sans être présentée comme un échec de livraison.

Les commandes opérateur check_mail_provider et reconcile_mail sont natives, sans endpoint de
lecture globale. Le probe neutre scripts/staging_mail.py est exclu des distributions de production,
exige une boîte autorisée et un drapeau explicite ; consulter l'état ne renvoie aucun message.
Les recettes externes, DNS/SPF/DKIM/DMARC, suivi désactivé et rétention doivent être vérifiés
réellement. [Configuration et limites](runbooks/notifications.md).


## Phase 9 — disponibilité personnelle et ancien onglet

`GET /api/me/availability?event_id=<UUID>` exige la session vérifiée du membre actif et revendiqué.
Le seul paramètre accepté est cet événement explicite. La réponse est exactement
`{"state":"DRAWN","available":true}` dans cet exemple : aucun destinataire, souhait, achat,
identifiant d’autre membre ou timestamp de consultation. GET ne marque jamais la consultation.

`available` exige DRAWN ou CLOSED et un résultat AVAILABLE après durabilité ; les autres états
renvoient false pour le membre autorisé. CLOSED reste en lecture seule pour les achats. Cette
route vérifie un statut, pas le déchiffrement du contenu, qui reste contrôlé lors de la lecture
privée. Les refus d’authentification/autorisation restent neutres et les en-têtes privés no-store,
no-referrer et CSP s’appliquent.

L’onglet privé visible interroge ce statut toutes les 15 secondes et au retour de focus/visibilité.
Une annulation retire le contenu de la page et la révélation ; les nouvelles requêtes de contenu
et mutations sont refusées immédiatement par le serveur. Une panne réseau ne prouve aucun nouvel
état. Le produit ne peut pas révoquer la connaissance d’un cadeau déjà vu ou copié.

## Extension du 16 novembre 2026 : inscription sans email

Voir ADR-0013 et runbooks/independent-enrollment.md. Le parcours email décrit plus haut reste
inchangé. Le flag WHATSAPP_ENROLLMENT_ENABLED est false par défaut dans les deux services.
Quand il est activé, les objets roster gardent exactement leurs clés, mais email peut être
JSON null : adresses non null distinctes, plusieurs null autorisés. Aucun email factice et
aucune conversion implicite d'une identité déjà revendiquée. Le formulaire HTML transforme
son champ vide en null. La correction avant revendication peut renouveler l'invitation sans
créer une seconde identité sans email. La correction après revendication reste refusée.

| Route coffre | Effet |
|---|---|
| GET /accounts/enroll/{member_uuid}/ | Invitation nominative non authentifiante ; aperçu sans mutation |
| POST même route | Confirmation explicite + CSRF ; crée une demande liée au navigateur, jamais une session authentifiée |
| GET /accounts/enrollment/ | État de la seule demande liée à la session de ce navigateur ; comparaison et référence |
| POST /accounts/enrollment/ | Activation après approbation signée indépendante ; consommation atomique et code affiché une fois |
| GET/POST /accounts/personal-code/ | Connexion par code à forte entropie ; option explicite remember |
| GET/POST /accounts/personal-access/ | Remplacement exigeant le code actuel ; nouvelle génération, autres sessions invalidées |

Sans flag, ces routes renvoient 404. Les POST ont CSRF et limitations partagées SQL/allauth :
connexion 30/minute/IP et 10/10 minutes par empreinte de code, demandes/activations 60/10 minutes/IP,
remplacement 5/10 minutes par compte ; au plus 20 demandes par invitation/heure. Les clés du cache
restent HMACées. GET ne revendique rien ; une demande ne déplace/réinitialise jamais un compte.

La référence partageable se construit à partir de l'UUID public du membre et de VAULT_ORIGIN.
Elle ne contient aucun secret d'accès. Elle est distribuée manuellement en message privé, pas
en liste d'accès dans le groupe. Elle cesse de permettre une inscription après activation.
Le secret navigateur et le code permanent ne sont retournés ni aux commandes du portail ni
aux projections. Ces dernières conservent leur liste fermée, sans champ supplémentaire.

L'approbation n'a aucun endpoint HTTP. Un rôle EnrollmentVerifier explicitement attribué signe
une attestation limitée à l'origine, la demande, sa comparaison et cinq minutes ; une commande
opérateur l'importe avec le registre indépendant. Aucun rôle n'est attribué par défaut. Après
import, quinze minutes au maximum pour activer depuis le bon navigateur. Le rôle de commande
portail n'autorise ni approbation ni récupération d'identité revendiquée.

Sans email : aucun courrier ou payload de notification n'est créé. Le résultat reste HELD
avant durabilité ; sa notification interne devient IN_APP après libération. NONE dans le suivi
portail signifie absence de notification email, jamais preuve de livraison. La disponibilité
et la révélation privée suivent les mêmes contrôles de session, manifeste et scellement.
