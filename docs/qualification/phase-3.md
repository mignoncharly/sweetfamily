# Qualification de phase 3

Date : 15 novembre 2026. Environnement : Windows x64, Python 3.13.11, PostgreSQL 17.12,
Django 5.2.19 et django-allauth 65.22.1. Exécution native locale, sans Docker ni CI/CD.

## Livrables

- Portail : Organizer, EventDraft, RosterProposal, SafeParticipantStatus, ControlCommand,
  ControlAudit et migrations propres ; ownership et versions obligatoires.
- Coffre : PrivateEvent, Membership, VerifiedIdentity, Invitation, RosterConsent,
  InboundCommand, PendingMail, SecurityEvent et migrations propres.
- PrivateSession est réalisée par les modèles/flux maintenus d'allauth.usersessions,
  avec backend de session DB chiffré propre au service, sans protocole d'authentification maison.
- Identités métier UUID, emails normalisés par la bibliothèque, noms d'affichage distincts,
  pays ISO et dates avec offset/fuseau validés. Aucune donnée familiale réelle préremplie.
- Email-code et TOTP allauth, MFA obligatoire pour les API organisateur, profils personnels,
  changement d'email réauthentifié, déconnexion et révocation des autres sessions.
- Invitations 32 octets, empreinte seule dans Invitation, expiration sept jours et usage unique.
  Le contexte signé temporaire ne remplace jamais une session personnelle vérifiée.
- Commandes Ed25519 versionnées/idempotentes et projection signée par une autre paire de clés,
  schéma fermé et versions anciennes ignorées. Aucun jeton participant ne revient au portail.
- Dispatcher local SQL pour invitations/challenges, payloads chiffrés et purge après traitement.
  Limites de demandes compte/IP et réémissions côté coffre, signatures et contrôles CSRF.
- Templates d'accès français, scripts WebAuthn collectés localement, QR TOTP sous CSP.
  Les formulaires métier complets restent à construire en phase 8.

## Vérifications exécutées

| Contrôle | Résultat |
|---|---|
| uv lock / uv sync --locked avec groupes control/vault | PASS ; ajout explicite de pycountry et cryptography pour les contrats/authentification |
| Migrations séparées des deux services | PASS sur les clusters locaux |
| test-unit | PASS : 26 tests du socle, 8 tests d'intégration désélectionnés |
| test-integration | PASS : 8 tests racine, incluant les deux suites de service sur bases neuves |
| Suites de phase 3 dans ces deux bases | PASS : 7 cas portail et 19 cas coffre, y compris la variante d'expiration/essais |
| test-privacy | PASS : suite de frontières du socle ; ne constitue pas une preuve globale de production |
| check | PASS : Ruff/formatage, TypeScript, compilation/collectstatic, checks Django et absence de migration manquante |
| check-security | PASS : scan source/canaris, pip-audit et npm audit, deux checks Django --deploy stricts sans warning masqué |
| build-prod / check-prod-artifact | PASS : archives distinctes sans tests/diagnostics, avec contrats, templates et assets locaux |
| build-test | PASS : distribution de tests séparée, incluant ses templates et sources nécessaires |

Les comptes et bases temporaires emploient uniquement des adresses synthétiques .invalid.
Les comptes de tests de service sont dans des bases jetables noel_phase3_test_* ; les transactions
sont annulées par cas et les bases supprimées après la suite. Ne pas additionner les résultats
des suites qui se recouvrent.

Le scénario de processus réel démarre les deux apps, les deux workers et Mailpit.
Un compte organisateur accomplit la vraie connexion par email-code et TOTP, prépare quatre
personnes FR/DE et ouvre l'événement par l'API. Le portail envoie réellement la commande HTTP
signée au coffre. Le worker coffre expédie l'invitation et le code de connexion via SMTP.
Le test retrouve les deux messages par l'API Mailpit, authentifie le participant avec le code
généré par allauth, revendique l'invitation, vérifie ses seuls événements, puis constate la
projection signée sur le portail. Le compte organisateur utilise sa propre adresse comme un
participant, sans privilège privé supplémentaire. Seule l'horloge de lot de cet événement
synthétique est avancée pour ne pas attendre quinze minutes. Acteurs et événement sont ensuite
supprimés et les processus de test arrêtés. Aucun message externe ou tirage réel.

Les tests couvrent aussi l'expiration à dix minutes, cinq erreurs invalidant un challenge,
la séparation des limites par email derrière une IP familiale, le lien intercepté sans boîte,
la correction avant revendication, le refus après revendication, les doubles requêtes,
les références d'événement étrangères, le conflit de profil et les champs sensibles interdits
dans une projection. Le changement de boîte réalise une réauthentification sur l'ancienne boîte,
une vraie vérification de la nouvelle boîte par les vues allauth et la révocation des sessions.

## Défauts corrigés et portée

Les premières passes ont détecté un oubli de django.contrib.humanize pour la page de sessions,
un ordre d'applications empêchant la surcharge des templates et des dates non rechargées après
création avant composition du message. Ces points ont été corrigés avant les résultats finaux.
Le signal email_changed d'allauth est aussi émis à la première vérification : ce cas est désormais
distingué d'un véritable changement, afin de ne pas révoquer l'invitation ni la session en cours.
La réauthentification explicite requiert sa propre preuve allauth, pas simplement une connexion
récente ; le test et le guide suivent ce parcours réel.

Les scénarios d'indisponibilité du transport utilisent un double de panne clairement isolé dans
les tests portail. Ils ne remplacent pas la preuve HTTP/SMTP réelle décrite ci-dessus.

Les cas locaux valident des sous-ensembles d'INV-01, IDN-01/02/03, EVT-01/02, CTY-01,
PRV-01/02 et API-01. Ils ne valident pas globalement T01–T26 du produit complet.
La table RosterConsent est prête, mais le manifeste gelé et son acceptation ne sont pas
ouverts avant phase 5, après les trois souhaits de phase 4.

## Conditions restantes

Les authentificateurs passkey sont proposés par allauth et leurs scripts sont distribués localement ;
aucun matériel WebAuthn ou navigateur réel n'a encore été qualifié. TOTP a été réellement validé.
L'UI de préparation métier complète, l'accessibilité et la recette multiappareils restent en phase 8.
La procédure de récupération refuse tout transfert sans preuve préenregistrée ; aucun raccourci
organisateur/opérateur d'usurpation n'est ajouté.

Le dispatcher de phase 3 n'est pas l'outbox fournisseur complète de phase 7 : baux, reprise avec
réconciliation d'envoi ambigu, webhooks, rappels et envoi Resend ne sont pas validés.
Le backend hors local reste bloqué. Les archives ne sont pas une autorisation de production.
Rotation/restauration des clés d'authentification, rétention/purge globale et indépendance réelle
du coffre sont encore à qualifier. La limitation Windows des ACL .git reste documentée.
Le travail de phase 4 peut commencer.

## Références

- [Configuration django-allauth](https://docs.allauth.org/en/latest/account/configuration.html).
- [Configuration MFA](https://docs.allauth.org/en/latest/mfa/configuration.html).
- [Sessions utilisateur](https://docs.allauth.org/en/latest/usersessions/index.html).
- Les signatures/hooks ont aussi été vérifiés dans les sources installées de la version 65.22.1
  verrouillée : code login/reauth/email verification, MFA TOTP et usersessions.
- [Contrats locaux](../api-contracts.md), [récupération](../runbooks/account-recovery.md),
  [modèle de menace](../threat-model.md).
