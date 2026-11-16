# Noël Secret — contrat produit

Version 1.0 — 15 novembre 2026. Source : [plan des dix phases](../Plan_implementation_Noel_Secret_10_phases.md). Ce contrat couvre la phase 1. Les tests ci-dessous sont des cibles à implémenter, jamais des résultats déjà obtenus.

## Périmètre et hypothèses

Webapp responsive entièrement française, plusieurs événements indépendants, un propriétaire par événement, 4 à 20 participants actifs. L'organisateur peut participer sans privilège privé supplémentaire. Une boîte email personnelle distincte par membre d'un événement ; UUID comme identifiant, jamais le prénom. Les prénoms identiques sont possibles avec noms d'affichage distincts.

L'acheteur commande hors application, reçoit chez lui et apporte le cadeau au réveillon. Aucun paiement ni adresse postale collectés. Les liens servent de référence ; conseils de boutique selon le pays de l'acheteur, sans garantir stock ou livraison ni remplacer automatiquement une fiche étrangère.

Hypothèses proposées, à confirmer avant ouverture : frais de port hors plafond, Europe/Berlin configurable, purge à J+90 du réveillon, sauvegardes glissantes de 30 jours. Dates, noms, pays, emails et exclusions réels restent à saisir. Aucun réveillon imposé, aucune donnée fictive en production. Ces choix ne constituent pas une conclusion juridique. L'opérateur indépendant, les domaines et comptes d'envoi ne sont pas encore disponibles ni vérifiés.

## Exigences et traçabilité

Les phases indiquent la réalisation ; la qualification globale relève de la phase 9. T01–T26 renvoient à la matrice du plan. C01–C16 sont précisés plus bas. Chaque ligne est normative.

| ID | Exigence vérifiable | Phases | Tests cibles |
|---|---|---|---|
| EVT-01 | Propriétaire obligatoire ; isolation interévénements ; UUID, noms distincts et effectif de 4 à 20 | 3, 5 | T01, T03, T07, C01 |
| EVT-02 | Dates saisies, fuseau configurable, stockage UTC ; aucun tirage automatique | 3, 5 | C02, T08 |
| INV-01 | Invitation personnelle, usage unique, au moins 32 octets aléatoires, empreinte seule stockée, expiration 7 jours ; réémission révoque l'ancien jeton | 3 | T06, C03 |
| IDN-01 | Email personnel vérifié et distinct par événement ; lien seul insuffisant ; aucune inscription libre par identifiant deviné | 3 | T06, T07, C03 |
| IDN-02 | Authentification par bibliothèque existante ; challenge 10 minutes, 5 essais maximum, limites compte/IP, réponses uniformes, rotation session et cookies propres au coffre | 3 | C04, T07 |
| IDN-03 | MFA organisateur pour événement réel ; réauthentification et récupération indépendante ; aucune substitution d'identité revendiquée par l'organisateur | 3 | T24, C05 |
| CTY-01 | Pays ISO de commande/réception ; pays acheteur dans les conseils ; changement avant tirage invalide le manifeste, après tirage conserve l'attribution | 3, 4 | T01, T14, T24, C06 |
| WSH-01 | Brouillon de zéro à trois souhaits ; validation exactement trois emplacements complets : titre, URL HTTPS, prix, note facultative | 4 | T05 |
| BUD-01 | Centimes entiers de 1 à 4 999 ; rejet des valeurs ambiguës et arrondis silencieux ; frais explicités avant consentement | 4 | T05, C07 |
| WSH-02 | Prix étranger estimé en EUR et signalé, date du prix déclaré, doublons évidents corrigés ; aucun scraping ni conversion inventée | 4 | C07, T16 |
| WSH-03 | Révisions privées et contrôle concurrent ; après tirage trois souhaits conservés, changement visible à son acheteur sans changer le tirage | 4, 6 | T14, C08 |
| URL-01 | Marchands approuvés extensibles ; refus URL locale, raccourcie, schéma actif ou credentials ; texte échappé, domaine lisible, ouverture protégée, aucun fetch arbitraire | 4 | T16 |
| DLV-01 | Achat externe, réception chez l'acheteur puis remise au réveillon ; aucune adresse ou donnée bancaire collectée | 4, 8 | C06 |
| CNS-01 | Même manifeste canonique accepté par tous : événement, membres, noms, pays, règles, exclusions, version ; changement structurel invalide les consentements | 3, 5 | T24, C09 |
| DRW-01 | Bijection sans auto-attribution ; exclusions dirigées, couple explicite = deux interdictions ; cycles de deux autorisés si compatibles | 5 | T01, T04, C10 |
| DRW-02 | Avant tirage : couplage parfait et, pour chaque arête réalisable fixée, chaque autre donneur garde au moins deux destinataires réalisables ; sinon refus | 5 | T03, T04, C10 |
| DRW-03 | Échantillonnage uniforme exact par DP et source cryptographique ; aucune graine conservée ou empreinte publique de permutation | 5 | C10 |
| DRW-04 | Un job par événement, verrouillage/idempotence, baux avec tentative monotone, scellement atomique sans révélation partielle | 5 | T08, T09, T10 |
| DRW-05 | Résultat scellé définitif ; retry, renvoi, reconnexion et restauration ne le changent pas ; sauvegarde confirmée avant lectures et envois | 5, 10 | T10, T18, T26 |
| PRV-01 | Frontière indépendante portail/coffre, sans récupération possible par l'organisateur ; projections fermées, aucune donnée privée au portail | 2, 6, 10 | T02, T15, C11 |
| PRV-02 | Session détermine le membre ; événement explicitement sélectionné et autorisé par requête ; seule attribution personnelle et souhaits associés, aucun donneur ni export global | 3, 6 | T02, T07 |
| PRV-03 | Enveloppes authentifiées pour permutation, souhaits et achats ; clés hors base ; nonces uniques par clé et données associées ; corruption sans nouveau tirage | 6 | C12, T15 |
| PRV-04 | Aucun résultat dans URL, titre, cache, logs, métriques ou analytics ; no-store, no-referrer, CSP/anti-iframe ; GET et robots sans mutation | 6, 8 | T13, T15 |
| PUR-01 | Choix/révision et note privés du donneur ; états NOT_STARTED, ORDERED, RECEIVED, READY, GIVEN ; total prêt uniquement au portail | 6, 8 | C13, T15 |
| NTF-01 | Emails neutres individuels, jamais association/souhait/achat ; outbox durable et payload sensible chiffré, retries bornés et registre local | 7 | T11, T15, T23 |
| NTF-02 | Webhooks signés/dédupliqués tolérant le désordre ; soumis/accepté/livré/différé/rejeté/échec/inconnu distincts ; livré ne signifie pas lu | 7 | T12, T23 |
| NTF-03 | Renvoi limité sans tirage ; timeout hors fenêtre fournisseur = DELIVERY_UNKNOWN à réconcilier ; aucune promesse exactement une fois | 7 | T11, C14 |
| NTF-04 | Rappels activés explicitement, préférences respectées, revalidation état/version/échéance ; pas de rafale après panne ; digest de souhaits neutre au groupe | 7 | T25 |
| LIF-01 | Retrait avant tirage invalide confirmations ; après scellement annulation explicite sans réparation de permutation | 5, 8 | T19, T21 |
| RET-01 | Purge privée et projections à J+90, backups expirant sous 30 jours ; registre minimal rejoué avant réouverture après restauration | 10 | T20, C15 |
| OPS-01 | Services/bases/secrets/environnements séparés ; diagnostics synthétiques absents de production ; aucun email réel en CI/local | 2, 10 | T17, C11 |
| OPS-02 | Backups chiffrés séparés, restauration en maintenance sans envoi ; résultat perdu déjà divulgué = incident puis annulation, jamais nouveau tirage | 10 | T18, T26, C15 |
| OPS-03 | Santé/métriques minimisées, alertes neutres, runbooks et revue indépendante avant garantie de production | 2, 9, 10 | T15, C16 |
| UX-01 | Interface/emails français, vocabulaire cohérent, clavier/mobile/lecteur d'écran/zoom ; objectif WCAG 2.2 AA, animations facultatives | 8, 9 | T22 |
| API-01 | Commandes signées/versionnées avec nonce/fraîcheur/idempotence ; refus replay ; CSRF web ; erreurs stables sans détails privés, conflits explicites | 3, 6 | T07, T08, T24, C08 |

## États et invariants

DRAFT → OPEN → CONFIRMING → READY → DRAWING → DRAWN → CLOSED → ARCHIVED. Annulation explicite possible depuis un état actif vers CANCELLED. Le coffre fait autorité. READY nécessite toutes les identités vérifiées, trois souhaits valides par membre et tous les consentements au même manifeste. Une modification structurelle avant DRAWING ramène à OPEN et invalide les consentements. DRAWING interdit ces modifications.

Le job a ses propres états PENDING, RUNNING, FAILED_RETRYABLE, FAILED_FINAL, SEALED. Une panne ne remet pas automatiquement READY. Après FAILED_FINAL sans résultat, l'opérateur peut clôturer la tentative, révoquer les baux et rouvrir la préparation avec nouveau manifeste et consentements. Si un résultat existe, seule reprise ou annulation est possible.

DRAWN possède release_state=PENDING_DURABILITY puis AVAILABLE. Avant AVAILABLE, lectures et notifications restent retenues (« Finalisation du tirage »). Commit atomique du résultat chiffré et de l'outbox retenue. Une panne de sauvegarde ou de déchiffrement ne crée jamais un nouveau tirage. CLOSED autorise seulement les lectures personnelles jusqu'à purge. ARCHIVED conserve un résumé non personnel. CANCELLED refuse révélation, achat et rappels même depuis un ancien onglet ; l'information d'annulation reste accessible avant purge. Pendant DRAWING, l'annulation révoque le bail et le worker revérifie l'état sous verrou avant scellement.

Chaque actif offre et reçoit exactement une fois, jamais à soi-même. Aucun destinataire oublié ou dupliqué. Aucune table, copie, queue, cache, export ou analytique du portail ne contient les associations. Le rôle organisateur n'ajoute aucun accès privé. Aucun GET, robot ou renvoi ne déclenche tirage ou marqueur de consultation. Données réelles et fictives ne partagent pas l'environnement de test.

## Retrait, récupération et suppression

Avant DRAWING, retrait = révocation des accès à l'événement/invitations, retrait du prochain manifeste, nouvelle confirmation et vérification d'effectif/faisabilité. Pendant DRAWING, aucune suppression sauvage : annulation coordonnée sous verrou. Après scellement, aucune réattribution ; annuler et informer tout le groupe si l'échange devient impossible. Un nouvel échange a un nouvel identifiant et de nouveaux consentements. Les achats et révélations antérieurs ne sont pas effaçables.

Avant revendication : correction email versionnée avec révocation de l'ancienne invitation. Après vérification : aucun changement par l'organisateur. Changement personnel = réauthentification récente, vérification des boîtes concernées lorsqu'elles sont disponibles, révocation des anciennes sessions. Boîte perdue = facteur préenregistré ou procédure de l'opérateur indépendant sans impersonation. Ni demande de l'organisateur, ni prénom/pays ne suffisent. Sans preuve suffisante, accès refusé ; traiter retrait/annulation plutôt que transférer le compte. Procédure détaillée de preuve et qualification à livrer en phase 3.

Suppression pendant échange : expliquer les conséquences, traiter retrait/annulation puis supprimer selon la politique annoncée. Annulation ne prolonge pas le calendrier J+90 initial ; suppression anticipée traitée par l'opérateur. Compte sans autre événement actif supprimable à la demande. Voir la carte des données pour backups et registre de suppression.

## Vocabulaire

Employer « personne à qui tu offres », « tes trois souhaits », « à recevoir chez toi », « à apporter au réveillon ». Éviter « ton destinataire de livraison ». « Attribution consultée » vient d'un POST authentifié, jamais d'un pixel email. Prix « indicatif », Mailpit « Simulation ». Aucun anonymat promis sur un site marchand externe.

## Tests complémentaires cibles

| ID | Résultat attendu |
|---|---|
| C01 | 20 acceptés, 21 refusés ; prénoms identiques distingués ; email partagé refusé |
| C02 | Dates UTC, fuseaux/changements d'heure et absence de tirage sur GET |
| C03 | Invitations expirées/réutilisées/réémises et identifiant deviné refusés ; jeton brut absent du stockage |
| C04 | Challenge expiré et sixième essai refusés ; limites compte/IP ; cookies et réponses non énumérantes |
| C05 | MFA obligatoire ; changement email vérifié ; sessions révoquées ; assistance frauduleuse refusée |
| C06 | Pays acheteur utilisé ; aucune adresse collectée ou fausse fiche substituée ; changement de pays sans nouveau tirage |
| C07 | Montants ambigus/étrangers, frais inclus/exclus et doublons traités ; aucune fausse vérification de prix |
| C08 | Deux onglets : version obsolète en conflit ; clé idempotente avec corps différent refusée |
| C09 | Manifeste altéré/confirmation ancienne refusés ; READY impossible sans tous les consentements |
| C10 | DP et arêtes conditionnelles comparées à énumération indépendante ; propriétés, bornes et poids de sélection |
| C11 | Comptes SQL croisés refusés ; audit DNS/CI/comptes/récupération ; production sans diagnostics |
| C12 | Substitution ciphertext refusée, collision nonce simulée, rotation clé et restauration ancienne clé autorisée |
| C13 | Achat visible au donneur seul ; total prêt sans choix ni statut individuel au portail |
| C14 | Renvoi borné et timeout ambigu hors fenêtre ; retry avec payload identique ; attribution inchangée |
| C15 | Purge de chaque famille ; suppressions rejouées après ancien backup ; clés restaurables séparément |
| C16 | Alertes neutres, sauvegarde ancienne détectée ; RPO/RTO mesurés ; revue indépendante consignée |

## Décision utilisateur du 16 novembre — participation sans email

Pour un participant sans boîte personnelle, une invitation privée WhatsApp peut ouvrir une
demande d'inscription. Le lien seul ne connecte personne. Le rôle indépendant du coffre doit
vérifier le vrai participant et sa demande précise ; seul son navigateur reçoit ensuite son
code personnel. L'option de session mémorisée et le code sauvegardé permettent les retours sans
email ni création manuelle de compte. Le code n'est affiché qu'à sa création/remplacement et
n'est jamais visible dans le tableau de bord organisateur. Une perte requiert une nouvelle
vérification indépendante, sans modification du tirage. Les messages de groupe restent généraux.

Les conditions d'identité email des phases historiques sont donc complétées par cette méthode
explicite ; elles ne deviennent pas une connexion par nom/lien possédé par l'organisateur.
Le rôle de vérification est **NON ATTRIBUÉ**. L'authentification forte de l'organisateur reste
celle du parcours existant. Détails, limites et portes d'activation : ADR-0013 et son runbook.
