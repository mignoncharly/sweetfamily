# Permissions et contrat de projection

Référence : [exigences](product-spec.md), [menaces](threat-model.md). Refus par défaut, contrôle côté coffre même si le portail est compromis. Les permissions sont limitées à l'événement autorisé ; un rôle n'est pas un paramètre choisi par le navigateur.

## Matrice

| Action/donnée | Organisateur | Participant | Worker coffre | Opérateur coffre |
|---|---|---|---|---|
| Créer/modifier avant gel | Ses événements, commandes validées | Non | Applique commande autorisée | Maintenance contrôlée |
| Noms, pays, préparation | Son groupe | Manifeste nécessaire au consentement | Traitement métier | Accès technique audité |
| Emails | Adresses qu'il a saisies | Le sien uniquement | Envoi/vérification nécessaires | Accès technique limité |
| Souhaits | Comme participant uniquement | Les siens et ceux de sa personne tirée disponible | Traitement autorisé | Accès technique contrôlé |
| Attribution | Comme participant uniquement | La sienne seulement, après disponibilité | Calcul/scellement/lecture autorisée | Capacité technique de confiance, aucune console métier |
| Qui lui offre | Non | Non | Traitement interne seulement | Aucun endpoint métier |
| Achat et note | Comme participant uniquement | Son propre choix et statut | Traitement privé | Accès technique contrôlé |
| Renvoi neutre | Commande limitée | Son accès seulement | Exécute sans nouveau tirage | Reprise technique auditée |
| Modifier email revendiqué d'un autre | Non | Non | Refuse | Procédure de récupération vérifiée uniquement |
| Export global d'associations | Jamais | Jamais | Aucun endpoint métier | Aucun écran ou endpoint métier |
| Logs/backups/clés du coffre | Non | Non | Accès strictement nécessaire | Exploitation indépendante |
| Annulation | Son événement, conséquence confirmée | Demande de retrait | Verrouille et applique | Gestion d'incident autorisée |

L'organisateur participant utilise une session sur l'origine indépendante du coffre. Son rôle de portail ne donne ni cookie partagé, ni jeton d'usurpation, ni accès de service aux endpoints personnels. L'opérateur peut techniquement accéder aux données : il reste un acteur de confiance, pas une preuve de confidentialité contre lui.

## Liste fermée coffre → portail (version 1)

Enveloppe signée : `message_id`, `schema_version`, `event_id`, `projection_version`, `issued_at`, `nonce`, `body_digest`, `signature`. L'horodatage technique sert uniquement à l'anti-rejeu ; il ne décrit pas une action individuelle. Conserver la version et le minimum nécessaire à la déduplication, pas les payloads dans des logs.

Corps, sans champ additionnel :

| Champ | Type / valeurs autorisées |
|---|---|
| event_version | Entier positif monotone du coffre ; métadonnée publique de concurrence, optionnelle pour compatibilité phase 3 |
| event_state | DRAFT, OPEN, CONFIRMING, READY, DRAWING, DRAWN, CLOSED, ARCHIVED, CANCELLED |
| manifest_version | Entier positif, ou null avant manifeste |
| draw_progress | NOT_STARTED, PROCESSING, FINALIZING, AVAILABLE, ACTION_REQUIRED ; jamais détail de calcul ou résultat |
| members | Liste d'objets fermés décrits ci-dessous |
| ready_count | Entier entre 0 et effectif ; total périodique, aucun état individuel d'achat |

Objet membre : `member_ref` (UUID opaque), `registration_confirmed` (booléen), `wishlist_complete` (booléen), `consent_received` (booléen pour le manifeste courant), `notification_state` (NONE, QUEUED, SUBMITTED, ACCEPTED, DELIVERED, DEFERRED, REJECTED, FAILED, DELIVERY_UNKNOWN), `recipient_viewed` (booléen). Le statut de notification est celui de la dernière notification neutre de suivi ; il n'inclut ni challenge d'authentification ni digest ciblé de souhaits. Les faits fournisseur complets restent au coffre.

Les noms/pays/emails déjà proposés par l'organisateur appartiennent au roster du portail, pas à un enrichissement libre de cette projection. Les corrections de profil sont présentées au groupe dans le manifeste du coffre ; aucun nouvel email privé n'est retourné au portail. Un nouveau contrat explicite sera nécessaire si la synchronisation des noms/pays est requise.

Interdits : recipient_id, giver_id, souhait/URL/prix/note/révision privée, choix/statut individuel d'achat, token/code/session, nouvel email privé, erreur détaillée, identifiant fournisseur, corps d'email, timestamp fin d'une action de membre, hash de permutation, résultat ou graine. Pas de sérialisation automatique de modèle. Rejeter champs inconnus, types et enums invalides, références étrangères, versions anciennes et signatures/replays invalides. Tester le schéma fermé et les canaris (T15, T24, C11, C13).

Projections périodiques regroupées (proposition : toutes les 15 minutes), sans ordre d'actions individuel ; ready_count suit la même cadence. Les booléens demandés pour le suivi révèlent une préparation et une consultation, jamais une association. Cette cadence est une décision de conception à mesurer, pas une garantie contre toute corrélation externe.

## Commandes portail → coffre

Liste fermée : proposition/création, ouverture/invitation, correction d'invitation non revendiquée, règles/exclusions avant tirage, retrait explicite, gel de manifeste, demande de tirage, annulation, clôture, renvoi/rappel neutre limité. Chaque commande comporte version de schéma, événement, version attendue, identifiant, timestamp, nonce et signature du corps ; idempotence persistante, conflit si même clé et contenu différent. Aucun changement d'identité vérifiée, récupération, lecture de souhait ou extraction du tirage.

Les routes `/api/me/` déduisent le membre de la session et vérifient l'événement explicite à chaque requête ; aucun participant_id pour choisir autrui et aucun contexte global mutable entre onglets. Les lectures ne marquent pas la révélation : seul POST authentifié avec CSRF. Réponses d'accès refusé uniformes, erreurs avec code stable/message français/corrélation opaque ; 409 pour version/idempotence, 429 pour limite, 503 pour indisponibilité. Référence détaillée des chemins : section « Contrats techniques transversaux » du plan.
