# Préparation aux vrais utilisateurs

16 novembre 2026. **PRODUCTION BLOCKED.** Le HTTPS staging est accessible ; cela ne signifie
pas que la confidentialité contre l'organisateur ou l'exploitation réelle sont validées.
Le parcours sans email est défini par ADR-0013 et son
[runbook de vérification](../runbooks/independent-enrollment.md).

| Critère | État réel / preuve manquante |
|---|---|
| Authentification participant sans email | Code, tests PostgreSQL, sessions et récupération implémentés. Flag désactivé par défaut ; recette uniquement synthétique. Voir le rapport email-free-enrollment-2026-11-16.md. |
| Rôle Independent vault operator | **NON ATTRIBUÉ**. Aucun vérificateur réel inventé ou nommé. Modèle/clé de signature distincts, attribution explicite requise. Les clés temporaires de tests ne sont pas une nomination. |
| Vérification du premier accès | Procédure précise documentée : identité reconnue par un contact indépendant, bon événement/personne, comparaison UUID + phrase depuis le navigateur du participant. Exercice humain avec la personne nommée non effectué. |
| Protection contre l'organisateur | **NON DÉMONTRÉE en production** : même hôte/contrôle Unix ; le sous-domaine du coffre dépend de la même zone parente. Hébergement, root, déploiement, DNS/registrar, clés, SQL, backup, récupération et facteurs doivent être hors de son contrôle. |
| Organisateur et email réel | MFA maintenu. La simplification concerne les participants ; elle ne supprime pas le besoin de qualifier le parcours organisateur existant et les emails optionnels utilisés. Envoi réel toujours bloqué ; aucune recette de boîte autorisée. |
| Performance | Référence locale 40 clients/400 GET avec 2 processus × 2 threads testée. Les résultats exacts du dernier run sont dans le rapport sans email. Charge HTTPS authentifiée et dimensionnement/quotas prévus de production restent à qualifier, y compris le parcours par code. |
| Accessibilité et appareil réel | Chromium/Axe/clavier/reflow automatisés ; téléphone réel, lecteur d'écran et zoom manuel 200 % non exécutés. Tester aussi sauvegarde/saisie du code et appareil partagé. Aucune conformité WCAG globale déclarée. |
| HTTPS / supervision | Deux HTTPS staging validés, six unités utilisateur et linger actifs, renouvellement Certbot configuré. Redémarrage réel, pannes, alertes externes, rotation SQL/certificats/clés et exploitation par l'opérateur nommé restent à qualifier. |
| Maintenance / sauvegardes | Gates, registre externe, purge et backups chiffrés/drills locaux livrés. Planification réelle, copie indépendante, alertes et inventaire des copies restent ouverts. |
| Restauration indépendante | Drill PostgreSQL local inclut révocation des codes/rôles restaurés et préservation des tirages. Exercice indépendant RPO proposé 15 min / RTO 4 h non effectué ; inclure la réinscription des participants. |
| Patchs et revue externe | PostgreSQL 17.11 conservé pour ne pas remplacer les services partagés ; ne valide pas le minimum 17.12 enregistré. Revue de sécurité indépendante de la version exacte requise. |

Les tests peuvent établir qu'une signature étrangère ou le mauvais navigateur sont refusés.
Ils ne prouvent ni l'identité de l'opérateur réel, ni la bonne exécution de sa vérification
humaine, ni que l'organisateur ne peut reprendre un compte fournisseur ou modifier le serveur.
`verify-release` reste bloquant ; aucun critère n'est fermé par la seule présence d'une clé en base.
