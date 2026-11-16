# ADR-0001 — Frontière de confiance indépendante

Date : 15 novembre 2026. Statut : retenu pour la conception ; déploiement non vérifié.

## Contexte

L'organisateur administrateur du portail ne doit pas connaître les attributions des autres, y compris via SQL, logs, sauvegardes et email. Un simple contrôle d'interface ne remplit pas ce besoin.

## Décision

Deux services séparables : portail d'organisation et coffre privé. Le coffre héberge identité, espace participant, souhaits, tirage et notifications. Son opérateur, ses comptes et moyens de récupération, domaine/DNS/TLS, infrastructure, CI/images, clés, email, logs et backups sont indépendants de l'organisateur. Les sessions personnelles vont directement au coffre. Communication limitée à commandes signées et projections fermées ; aucun modèle privé partagé.

## Alternatives écartées

Une base commune avec filtrage ou deux conteneurs sous le root de l'organisateur laissent ses capacités techniques intactes. Chiffrer la base avec une clé accessible au même administrateur ne suffit pas. Un protocole sans opérateur de confiance exigerait une conception et une évaluation séparées, non improvisées ici.

## Conséquences et validation

Le coffre et son infrastructure restent de confiance ; aucune promesse contre un opérateur malveillant, aucune garantie E2E. Sans séparation réelle, laisser la confidentialité de production non validée et poursuivre les travaux indépendants. Preuves futures : C11, T15, T24 et revue indépendante en phases 9–10. Voir [modèle de menace](../threat-model.md).
