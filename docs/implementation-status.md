# État de l'implémentation

Mise à jour : 16 novembre 2026. Phases 1 à 9 et travaux locaux de phase 10 implémentés ; recette email externe différée.
Adaptation explicite : aucun Docker, GitHub Actions ou CI/CD. Remise dans le dépôt GitHub fourni.

| Phase | État | Preuves / conditions |
|---|---|---|
| 1 — Produit, accès, invariants | Livrée | product-spec.md, permissions.md, threat-model.md, data-map.md et ADR |
| 2 — Socle et environnements | Livrée et testée sur Windows et Ubuntu | Locks, deux bases/processus, outils vérifiés, distributions, runner manuel ; qualification/phase-2.md |
| 3 — Identité et invitations | Livrée et testée localement | Modèles/migrations, email/MFA/sessions allauth, commandes/projections signées, invitations, profils ; qualification/phase-3.md |
| 4 — Souhaits et pays | Livrée et testée localement | Éditeur/API, budgets entiers, marchands approuvés, historiques AES-GCM et conflits ; qualification/phase-4.md |
| 5 — Tirage et états | Livrée et testée localement | Manifeste/consentements, moteur exact, baux, scellement et backup restauré ; qualification/phase-5.md |
| 6 — Protection et espaces privés | Livrée et testée localement | Révélation personnelle, achats chiffrés, migration/enveloppes, rotation et dump portail sans canaris ; qualification/phase-6.md |
| 7 — Notifications et suivi | Code livré / essais locaux PASS ; recette externe différée | Outbox/baux, Resend + Zoho EU, webhooks, rappels et préférences ; chemin .env gtech à fournir plus tard ; qualification/phase-7.md |
| 8 — Interfaces et cas de vie | Livrée et testée localement, recette assistive complémentaire en phase 9 | Deux espaces HTML, reprise, masquage, transfert, copie annuelle, Chromium + 32 scans Axe ; archivage/purge lié à phase 10 ; qualification/phase-8.md |
| 9 — Qualification du produit complet | Requalification locale PASS ; sortie globale BLOCKED | Run Ubuntu : 74 cas racine, 51 portail/164 coffre imbriqués, Chromium/Axe ; T18/T20 PASS_LOCAL. P95 282,695/327,425 ms en mode 2 × 2, PASS_LOCAL ; performance de production, T22/T23 et indépendance ouverts ; qualification/ubuntu-2026-11-16.md. Le rapport phase 9 conserve ses mesures historiques. |
| 10 — Exploitation et remise | Travaux locaux livrés ; sortie production BLOCKED | Maintenance, purge J+90, registre externe, replay/restauration native, backups par rôle, supervision et guides ; qualification/phase-10.md. Déploiement, indépendance, RPO/RTO et recettes externes restent ouverts. |

## Périmètre réellement livré

Le workspace initial contenait seulement le plan. Le contrat produit distingue exigences,
hypothèses et garanties de production. Les services utilisent des groupes de dépendances,
configurations, bases PostgreSQL, comptes SQL, migrations, sessions et clés distincts.
Le choix sans conteneurs et sans pipeline est consigné dans ADR-0004.

La phase 3 livre le portail/API de préparation et l'identité du coffre : email vérifié,
MFA organisateur, invitation personnelle et usage unique, correction avant revendication,
profil personnel, sessions chiffrées et révocation. Les formulaires d'authentification viennent
de django-allauth ; les modèles domain utilisent des UUID, les sessions utilisent les modèles
maintenus d'allauth.usersessions. L'acceptation du manifeste et le tirage sont désormais livrés
en phase 5, après la validation des souhaits.

## Vérifications et limites

Les rapports de qualification indiquent commandes et résultats effectivement exécutés, y compris
la chaîne locale de vrais processus, PostgreSQL et SMTP Mailpit. Aucune livraison à une vraie
boîte, aucun matériel WebAuthn et aucune restauration indépendante de production ne sont revendiqués.
Le parcours Ubuntu est désormais vérifié indépendamment ; voir [recette du 16 novembre](qualification/ubuntu-2026-11-16.md). Une infrastructure de production et un opérateur indépendants restent non qualifiés.

Dans l'ancienne session Windows, le dossier .git avait un problème de propriétaire. Ce blocage
ne s'applique pas au clone Ubuntu fourni. Le remote a été inspecté avant les modifications ;
la remise utilise un commit/push normal, sans force et sans configuration Git globale.

La garantie contre l'administrateur du portail reste NON VALIDÉE en production : elle exige
un opérateur indépendant du coffre, les domaines/comptes/récupérations/accès réellement isolés,
la restauration des clés et une revue de sécurité indépendante. Les ressources externes manquantes
ne bloquent pas le travail local de phase 8. Aucun secret de production n'est demandé dans la conversation.

## Livraison de phase 4

Les listes privées, validations, historique chiffré et conseils par pays sont disponibles.
Les conflits concurrents sont vérifiés avec PostgreSQL réel. Dans la qualification historique de
phase 4, les tests d'édition après DRAWN utilisaient une fixture d'état, sans attribution.
Le lecteur de liste attribuée et la comparaison au moment de l'achat sont désormais livrés en phase 6.

## Livraison de phase 5

Le coffre gèle le groupe public, recueille les consentements exacts et calcule un couplage
uniforme sans déduction forcée selon le contrôle défini. Job unique, baux, tentatives et
scellement atomique empêchent les doubles résultats. Retrait et annulation ne recollent jamais
les associations. La commande opérateur native sauvegarde et restaure effectivement le commit
avant disponibilité et avis neutres. La qualification historique de phase 5 n'ouvrait aucune attribution privée ;
ce parcours est maintenant livré en phase 6. La sauvegarde indépendante, archivage et purge restent en phase 10.

## Livraison de phase 6

Le coffre ouvre uniquement sa propre attribution après confirmation de durabilité, avec révélation
explicite, trois souhaits et conseils selon le pays de l'acheteur. La préparation personnelle
conserve choix, révision, état et note chiffrés, avec comparaison historique et conflits explicites.
Les souhaits historiques sont migrés vers les enveloppes par événement ; la rotation maîtresse
ne change pas les associations ou ciphertexts métier. Le portail ne reçoit qu'un booléen de
consultation et un total périodique. Les essais incluent dump complet du portail et vraie
sauvegarde/restauration locale ; KMS, politique OS et infrastructure indépendante de production
restent non qualifiés. Les adaptateurs email et notifications sont maintenant livrés en phase 7 ; leur recette externe reste différée.

## Livraison de phase 7

Queues chiffrées séparées, baux/tentatives, idempotence Resend, arrêt honnête des ambiguïtés,
reçus de webhook vérifiés/dédupliqués, réconciliation sans renvoi, messages neutres et renvois
limités sont livrés. Les rappels sont proposés à 18:00 locale avec activation/date confirmées,
préférences, vérifications de version et rattrapage limité. Un digest neutre au groupe remplace
toute notification de changement ciblée vers l'acheteur. Mailpit est toujours une simulation.

L'utilisateur souhaite Zoho EU avec info@gestionatech.de et a fourni le domaine
sweetfamily.gestionatech.de. Il fournira plus tard le chemin .env gtech autorisé pour les valeurs
SMTP. Aucun mot de passe copié, envoi réel, DNS ou déploiement n'a été effectué. Zoho peut être
utilisé sans compte Resend, avec seulement preuve de soumission SMTP ; les webhooks/API Resend
restent disponibles si ce fournisseur est configuré. Aucun statut de livraison externe ou
d'indépendance de production n'est inventé. La phase 8 peut progresser sur le mode local.


## Livraison de phase 8

Les formulaires des deux espaces, le tableau de suivi et l’export limité sont disponibles.
Les erreurs réseau conservent la saisie sans stockage persistant ; une session expirée propose
la reconnexion puis le renouvellement du seul jeton CSRF. Le masquage retire le cadeau du DOM.
La copie annuelle repart d’un brouillon public neuf. Le transfert n’accorde que l’organisation,
avec réauthentification des deux comptes, réservation de commande et avis neutre au groupe.

Recette native : 8 tests racine d’intégration, 51 unitaires et 29 de confidentialité passent
(ensembles avec recouvrement, cas de service imbriqués). Les parcours Chromium et 32 scans Axe
passent, sans violation signalée dans ce périmètre. Les captures synthétiques des quatre largeurs
et les rapports restent dans `.local/ui-results`, hors production.

Cela ne vaut pas conformité WCAG 2.2 AA : lecteur d’écran, téléphone réel, zoom manuel et
équipements de connexion restent à qualifier en phase 9. Le reflow automatisé représente
la largeur CSS équivalente à un zoom de 200 %, sans manipulation du menu du navigateur.
La clôture et l’annulation sont opérationnelles. L’archivage avec résumé non personnel et purge
reste attaché à la phase 10 ; l’interface ne présente pas une suppression fictive.
L’envoi Zoho réel demeure différé à la demande de l’utilisateur, sans nouvelle demande de secret.


## Livraison de phase 9

Rapport, matrice T01–T26, liens exigences/tests, revue de confidentialité, accessibilité, mesures
et défauts sont dans docs/qualification. Le runner `qualify` conserve des preuves versionnées ;
`verify-release` vérifie leur fraîcheur/intégrité puis bloque la mise en service sur les critères ouverts.

Les 70 cas racine et les suites imbriquées passent, ainsi que Chromium et 33 scans Axe sans violation.
L’ancien onglet retire le cadeau après connaissance de l’annulation. La réutilisation SQL est bornée,
avec reconnexion testée après terminaison de backends. Le p95 s’améliore mais reste au-dessus de
500 ms sur la charge locale : PERF-01 est ouvert, sans revendication de capacité de production.
T18 est partiel, T20 bloqué jusqu’à phase 10 ; T22 manuel et T23 réel restent non exécutés.
L’indépendance et la revue externe restent à démontrer. Aucune sortie production n’est déclarée.

## Livraison locale de phase 10

Les commandes opérateur couvrent initialisation du registre, maintenance drainant requêtes et
workers, purge, vérification d'entretien, backup chiffré, restauration isolée, récupération,
reprise, expiration d'archives et suivi agrégé. Un web/worker restauré démarre sous
`FORCE_MAINTENANCE=true`. Une reprise SQL ancienne réapplique le registre externe avant accès,
contrôle les tirages, déchiffre les données privées et facteurs de connexion, et retient les
anciens messages/commandes/jobs ambigus. Elle ne recalcule aucune attribution.

La purge à J+90 enlève données privées et projections nominatives de l'événement. Une demande
de compte supprimé est aussi rejouée ; elle est refusée si un échange dépend encore du compte.
Le compte vérifié conservé peut rejoindre une nouvelle année après suppression de son ancienne
identité d'événement, sans duplication ni reprise d'attributions. Les copies connues par rôle
expirent à 30 jours ; copies anciennes/externes et réduction du registre nécessitent inventaire.

Le drill PostgreSQL réel passe pour les deux rôles. Les procédures de déploiement, exploitation,
restauration, incident et guides participant/organisateur sont livrés. Le rapport
[phase-10.md](qualification/phase-10.md) porte les preuves de requalification de cette version.
Les résultats historiques de phase 9 ci-dessus restent ceux de leur ancien run.

Aucun hébergement, DNS, email réel ou planificateur de production n'a été activé. L'objectif
p95, le matériel assistif, les boîtes de recette, l'opérateur indépendant, le stockage externe
et RPO/RTO de production restent à qualifier. La phase 10 globale n'est pas déclarée terminée.

## Requalification Ubuntu et performance locale

Le [rapport Ubuntu](qualification/ubuntu-2026-11-16.md) et son résumé JSON remplacent les mesures
Windows comme preuve de cette source sur Linux. Setup local avec Python 3.13.11 et locks,
deux clusters SCRAM privés 55431/55433, Mailpit vérifié, ports configurables et wrappers
opérateur portables. Le [runbook Ubuntu](runbooks/ubuntu.md) donne les commandes exécutées.

Le coffre passe d'un p95 initial 1 174,947 ms à 327,425 ms lors du run final ; le portail
mesure 282,695 ms. Optimisations de rendu et relations SQL, puis deux processus natifs × deux
threads par rôle, avec cycle d'arrêt et panne d'enfant testés. Quatre threads au total comme
avant ; aucune donnée privée mise en cache, aucun contrôle de maintenance/scellement retiré.
La cible loopback locale est atteinte. Le défaut compatible Windows reste un processus × quatre
threads ; il faut sélectionner le mode Ubuntu explicitement. Ce résultat n'est pas une mesure
HTTPS ni une promesse de capacité avec limites CPU/RAM de production.

Qualification finale : 74 tests racine, 51/164 cas de service imbriqués, deux parcours Chromium
et 33 scans Axe sans violation, recovery/purge, audits et distributions PASS. `verify-release`
reste BLOCKED. PostgreSQL système 17.11 est conservé pour le local et ne valide pas le minimum
17.12 enregistré pour la production. Aucun service partagé, DNS ou email réel n'est activé.
Téléphone/lecteur d'écran/zoom, email autorisé, indépendance, HTTPS/supervision/maintenance
planifiée/backups/alertes, restauration indépendante RPO/RTO et revue externe restent ouverts.

## Préparation des domaines hébergés — 16 novembre 2026

L'utilisateur demande le portail sweetfamily.gestionatech.de et confirme le coffre
vault.sweetfamily.gestionatech.de. Six services staging privés sont préparés et actifs sur
bases/credentials/venvs neufs, SQL TLS verify-full, artefacts de rôles, unités utilisateur,
backups initiaux et proxy nginx testé en privé. La source passe 76 tests racine, 51/164 cas
imbriqués, navigateurs/Axe et audits ; voir [rapport hébergé](qualification/hosted-staging-2026-11-16.md).

L'activation publique reste BLOQUÉE : record A du coffre absent, sudo requérant une
authentification pour installer nginx et obtenir les certificats. Le [runbook](runbooks/hosted-staging.md)
et le script administrateur sont prêts ; aucune réussite publique ou production n'est
revendiquée. L'email et la connexion email restent désactivés. gtech n'est pas modifié.
