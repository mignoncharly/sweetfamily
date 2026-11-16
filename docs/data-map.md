# Carte des données

Contrat de conception — 15 novembre 2026. [Permissions](permissions.md), [menaces](threat-model.md), exigences RET-01/PRV-01 à PRV-04. « Propriétaire » désigne ici le service responsable, pas une conclusion juridique. Les durées ci-dessous sont proposées avant ouverture et doivent être annoncées.

## Inventaire

| Données / classification | Responsable et stockage | Protection et accès | Conservation cible |
|---|---|---|---|
| Compte organisateur, MFA, session / identité sensible | Portail, base propre | Auth bibliothèque, secrets/facteurs protégés, cookies host-only ; aucun accès coffre | Compte jusqu'à suppression si aucun événement actif ; sessions révoquées à déconnexion/récupération |
| Brouillon événement, titre, dates, fuseau, règle de frais, roster proposé (UUID, nom, pays, email saisi) / personnel | Portail | Propriétaire autorisé, chiffrement stockage et backups ; pas d'email privé modifié retourné | J+90 du réveillon ; brouillon sans date abandonné : purge après 90 jours d'inactivité, avertissement préalable |
| Projections et audit de commandes / personnel minimisé | Portail | Schéma fermé de permissions.md, aucune association ni contenu privé | Projections nominatives J+90 ; audit opérationnel 30 jours |
| Identité vérifiée, email, appartenance, profil/pays / personnel privé | Coffre, base propre | Accès session personne et traitements nécessaires ; chiffrement stockage, pas de duplication portail | Appartenance J+90 ; identité partagée conservée seulement pour autre événement actif ou compte demandé |
| Invitations et challenges / secrets | Coffre | Empreinte invitation seule ; challenge selon bibliothèque, jamais logs ; payload email temporaire chiffré | Invitation 7 jours ; challenge 10 min ; payload purgé à usage/expiration ; métadonnées minimales jusqu'à J+90 au plus |
| Sessions, facteurs, récupération / secrets critiques | Coffre | Bibliothèque, secrets hors logs ; aucun jeton au portail ; réauthentification et révocation | Révocation sur changement sensible ; durées exactes de session à fixer/tester en phase 3 ; facteurs supprimés avec compte |
| Manifeste, exclusions, consentements versionnés / données du groupe sans emails | Coffre | Visible aux seuls membres ; intégrité par empreinte canonique, autorisations et version | J+90 ; empreinte du manifeste autorisée, jamais empreinte de permutation |
| Souhaits, URLs, prix, notes, historique et révisions / privé | Coffre, enveloppes chiffrées | AES-256-GCM, clé événement enveloppée ; propriétaire et son acheteur autorisé | J+90, historique compris |
| Permutation, version manifeste / secret central | Coffre, SealedDraw | Permutation complète chiffrée, aucun recipient_id en clair ; aucune copie portail, outbox ou audit | J+90, y compris après clôture ; jamais publication automatique après fête |
| Identifiants événement/job, ciphertext, nonce, key_id, clé enveloppée, schéma / technique coffre | Coffre, SealedDraw et registre d'enveloppes | En clair dans coffre pour autorisation/routage ; nonces 96 bits uniques par clé ; données associées type/identifiants/version | Vie de l'objet puis purge J+90 ; registre ne doit pas permettre réemploi sous une clé vivante |
| Choix de souhait, révision choisie, note et suivi d'achat / privé donneur | Coffre | Choix/note chiffrés ; accès donneur seul ; aucun index relationnel révélant le destinataire ; état stocké au coffre | J+90 |
| Outbox, email destinataire, payload, ID fournisseur, webhooks / personnel et secrets temporaires | Coffre et fournisseur email | Tokens/codes chiffrés, messages neutres ; signature brute webhook ; accès worker ; aucun corps dans logs | Payload à usage/expiration ; suivi fournisseur 30 jours après état terminal, plafonné à J+90 ; politique fournisseur à vérifier phase 7 |
| Jobs, baux, idempotence, reçus de durabilité / technique sensible | Coffre | Pas de résultat dans le job ; références et preuve backup seulement ; registre durable contre replay | Jusqu'à purge de l'événement ; identifiant purgé non réutilisable et replay refusé |
| Clés maîtresses versionnées / secret critique | Gestionnaire indépendant, jamais base/dépôt/image/backup portail | Accès opérateur coffre ; clés sauvegardées séparément ; rotation sans nouveau tirage | Tant qu'une donnée ou sauvegarde autorisée en dépend, puis destruction contrôlée |
| Logs/événements de sécurité / technique personnel minimisé | Chaque service séparément | Catégories et corrélations opaques, pas de corps HTTP, email, secret, liste ou attribution ; IP complète uniquement si besoin documenté | 30 jours proposés ; pas de conservation distincte plus longue sans décision documentée |
| Métriques / agrégats non personnels | Chaque service | Aucun label de personne, association ou souhait ; aucune télémétrie privée chez organisateur | 90 jours proposés, à mesurer ; aucune identité conservée après purge |
| Backups / même sensibilité que source | Stockages indépendants par service | Chiffrés ; clés séparées ; coffre inaccessible au portail | Fenêtre glissante 30 jours, donc copies résiduelles jusqu'à 30 jours après purge primaire |
| Registre minimal de suppression / identifiants techniques personnels | Coffre et portail pour leurs données | Identifiant opaque + date/type de purge, aucun contenu ; accessible au processus de restauration | Jusqu'à expiration de tout backup concerné + marge proposée de 7 jours ; ensuite purge du registre |

## Flux et minimisation

1. Organisateur → portail : données de préparation, aucun souhait ou résultat.
2. Portail → coffre : commandes autorisées signées/versionnées, jamais session privée ou demande de lecture d'attribution.
3. Participant → coffre directement : vérification, souhaits, consentement, révélation personnelle et achat. Aucun proxy organisateur.
4. Coffre → portail : exclusivement projection fermée ; noms/pays/emails du roster déjà saisis ne justifient pas de champs supplémentaires.
5. Coffre → fournisseur : email individuel neutre et secrets d'accès temporaires nécessaires ; fournisseur traite des données personnelles, compte indépendant. Paramètres de rétention, suivi d'ouverture/réécriture de liens et suppression fournisseur à vérifier/configurer, sans supposer une maîtrise non prouvée.
6. Navigateur → marchand : lien volontaire, no-referrer/noopener/noreferrer, aucune récupération serveur ni adresse ou paiement transmis par l'application.

Données interdites à collecter : adresses postales, cartes bancaires, graine de tirage, hash public de permutation, logs de choix aléatoires, copie des associations au portail. Les identifiants propriétaires de souhaits restent seulement au coffre pour autorisation ; les attributions ne doivent pas être reconstituables par un index achat/souhait en clair.

## Purge et restauration

À J+90, supprimer associations, souhaits/historiques, achats, invitations/payloads, appartenances et projections nominatives ; ne garder qu'un résumé non personnel. Comptes sans autre événement actif traités selon demande/politique annoncée. Une annulation n'allonge pas la conservation ; une demande anticipée suit d'abord retrait/annulation pour préserver l'intégrité.

La suppression primaire n'est pas la suppression immédiate des backups. Ne pas annoncer un effacement cryptographique total si une clé subsiste en sauvegarde. Toute restauration démarre en maintenance, suspend envois/tirages, applique le registre de suppression et les échéances avant réouverture, puis réconcilie les notifications. Résultat scellé déjà divulgué introuvable : incident et annulation, jamais recalcul sous le même événement. Tests T18/T20/T26/C15 à exécuter aux phases 9–10.

## Stockage livré en phase 5

DrawJob ne garde que le manifeste public immuable, son empreinte, état et bail/tentative.
SealedDraw contient uniquement les métadonnées techniques, ciphertext AES-GCM et clé de données
enveloppée ; aucune association en clair. DrawNonce réserve les nonces sous clé, sans membre.
DrawNotification relie un avis neutre à son destinataire de courrier, jamais à une attribution.
Le résultat et les avis restent retenus jusqu'à confirmation de sauvegarde restaurée.
Le reçu de backup privé référence l'archive chiffrée et son intégrité, sans hash de permutation.
Les purges et échéances décrites plus haut restent à implémenter/qualifier en phase 10.

## Stockage livré en phase 6

EventDataKey contient seulement version maîtresse, nonce et clé de données enveloppée par événement.
WishlistRevision v2 protège l'historique sous cette clé ; les révisions v1 restent migrables et les
anciennes clés requises par les archives sont conservées. PrivatePurchaseState est lié uniquement
au donneur, avec révision technique en clair ; choix de souhait, révision choisie, état et note
sont chiffrés ensemble, sans index d'association cadeau/destinataire. La comparaison ne déchiffre
que l'historique de la liste attribuée au membre autorisé. recipient_viewed est un booléen, sans
horodatage individuel. Seuls ce booléen et ready_count périodique sont conservés au portail.
Les registres de nonces sont conservés pour toutes les clés encore autorisées et leurs archives.
Les cibles de purge et rétention ci-dessus restent à qualifier en phase 10.

## Stockage livré en phase 7

AuthMail est propre au portail et ne contient que ses messages d'identité chiffrés. PendingMail /
NotificationOutbox garde au coffre ses payloads chiffrés, FK de destinataire légitime et clés métier,
jamais une association cadeau en clair. HMAC de contenu et fingerprint de credential sont secrets,
sans hash brut de code court ou permutation. Le payload est purgé à succès, expiration ou état terminal.
ScheduledNotification contient type neutre, membre à rappeler et échéance/version, aucun choix d'achat.
Le champ wish_digest_day est un bucket de groupe, pas une date d'action d'un propriétaire de liste.
DeliveryReceipt conserve seulement ID/fait fournisseur, date technique, corrélation opaque et HMAC
pour déduplication, sans corps, email, erreur brute, pixel ou lien marchand. Les échéances de rétention
et suppression de ces données et de leurs copies fournisseur restent à finaliser en phase 10.


Phase 8 : PortalSubmission conserve seulement UUID de demande, propriétaire, événement et empreinte
de contenu public pour dédupliquer une création/copie. OwnershipTransfer contient les deux rôles
portail, nom public annoncé, version, expiration et état ; aucune identité ou attribution du coffre.
Les liens vers l’événement permettent leur suppression dans la future purge de cet événement.
Le coffre reçoit uniquement une référence de transfert et un nom public pour son avis neutre.
Les captures de recette sont synthétiques, locales et exclues des distributions de production.


Phase 9 : la route personnelle de disponibilité ne retourne que l’état d’événement et un booléen
de disponibilité. Son GET ne marque pas de consultation et n’ajoute aucune table ni télémétrie.
L’onglet privé interroge ce statut pour retirer l’affichage après annulation ; une connaissance
déjà acquise par l’utilisateur ne peut pas être révoquée. Les rapports de qualification contiennent
noms de tests, hashes de sources/preuves et mesures agrégées synthétiques, jamais de permutation
ou de secret. Les preuves brutes restent dans `.local/qualification`, hors production.

## Conservation et récupération livrées en phase 10

`DeletionTombstone` garde UUID d'événement et date, sans FK vers une personne ni contenu
privé. Le registre opérateur externe authentifié conserve ces suppressions, les identifiants
et fingerprints de résultats scellés (jamais leur permutation), et les demandes de comptes
supprimés sous identifiant/empreinte HMAC. Il survit à une restauration SQL ancienne.
`OperationsState` ne contient que maintenance/vérification, sans donnée métier.

La purge à J+90 retire l'événement et ses dépendances privées/publiques. Les comptes vérifiés
restent selon le choix du titulaire ; une future invitation réutilise le même compte vérifié
sans reprendre l'ancienne adhésion. La suppression de compte sur demande refuse les échanges
et transferts encore liés. Les données de session expirées, métadonnées de sécurité et reçus
de plus de 30 jours et messages expirés anciens sont nettoyés pendant l'entretien.

Les nouveaux backups par rôle expirent après 30 jours avec la commande opérateur dédiée.
Les copies anciennes et externes exigent leur propre inventaire. Le registre minimal reste
au moins 120 jours et tant qu'un backup rejouable existe ; sa réduction exige une revue des
copies détruites, sans expiration automatique non prouvée. Les nonces de clés encore
utilisables restent réservés. Voir [politique et limites](runbooks/operations.md).

## Accès sans email — données ajoutées

- VerifiedIdentity.email et RosterProposal.email peuvent être null lorsque le mode est activé ;
  compte sans mot de passe utilisable, aucune fausse adresse et aucun EmailAddress vérifié factice.
- EnrollmentClaim : invitation, UUID, empreinte du secret navigateur, comparaison, dates et
  référence du rôle approbateur ; aucune session authentifiée avant activation. Demande 24 heures
  au maximum, activation dans les 15 minutes de l'approbation ; les lignes expirées ne donnent
  aucun accès et sont supprimées avec l'événement à J+90.
- AccessCredential : empreinte SHA-256 d'un code aléatoire de 160 bits, génération et enabled ;
  jamais de code récupérable. Affichage à usage unique côté participant ; copie volontaire hors
  application sous sa responsabilité. Suppression avec l'identité d'événement et le compte sans email.
- EnrollmentVerifier : UUID de rôle, clé publique, rôle fixe et enabled ; aucune nomination créée
  automatiquement. Clé privée de signature hors serveur/SQL, détenue par le vérificateur nommé.
- Registre opérateur : reçus minimaux d'approbation et d'attribution/révocation de rôle, sans
  comparaison, secret navigateur, code, souhait, nom/contact personnel ou association. Même
  protection externe que le registre de rétention ; politique de conservation opérateur à qualifier.
- Sans email, aucune outbox vers un fournisseur. Sessions toujours chiffrées ; code absent des
  URL, logs, localStorage et projections. Restauration : codes/rôles/demandes restaurés désactivés
  avant reprise, puis nouvelle attribution/vérification indépendante selon le runbook.
