# Méthode de mesure locale — phase 9

Le runner `python scripts/tasks.py qualify` écrit ses preuves dans un répertoire unique sous
`.local/qualification`, avec résultats JSON/XML, journaux des étapes, hash des sources et hashes
des preuves. Les tests forcent Mailpit et retirent les credentials d’envoi réel. `verify-release`
refuse des preuves absentes/modifiées ou devenues obsolètes après modification du code, puis
signale les conditions essentielles encore bloquées. Ce contrôle local n’est pas une attestation
signée d’un auditeur externe.

## HTTP

Un processus Waitress natif par rôle, quatre threads chacun, PostgreSQL natif par rôle, sur
loopback sans TLS. Les rôles sont mesurés successivement et les workers sont arrêtés pendant
ce benchmark ; la chaîne des vrais services/workers/SMTP est une recette séparée. La mesure d’un rôle utilise deux événements et 20 sessions synthétiques par
événement, jusqu’à 40 requêtes concurrentes. Quarante requêtes de chauffe sont exclues, puis
400 requêtes sont mesurées. Côté portail : suivi de brouillons avec 20 et 8 propositions ; côté
coffre : éditeurs de listes d’événements scellés de 4 et 8 membres. Chaque requête crée une connexion
HTTP et lit la réponse, qui n’est pas conservée. Les sessions portail sont des copies de fixture
d’une vraie session code/MFA ; cette mesure ne prétend pas effectuer 40 cérémonies de connexion.

Une requête supplémentaire de récupération, hors échantillon, suit la terminaison réelle des
backends PostgreSQL de la base jetable. La requête authentifiée doit réussir ; les reconnexions
réutilisent les contrôles de santé Django. La réutilisation est bornée à 60 secondes.

Le p95 est le rang ceil(0,95 × N) de la durée HTTP complète, incluant file d’attente serveur,
requêtes SQL et loopback. La cible proposée est 500 ms ; un dépassement est conservé comme écart,
jamais transformé en succès en changeant le seuil. Cette mesure est plus large que le seul temps
serveur, mais exclut le réseau réel, TLS et tout fournisseur email.

## Tirage et envoi

Trois tirages de 20 membres sans exclusions sont calculés avec la source cryptographique de
production, validation de confidentialité et validation de résultat incluses. Seules les durées
sont écrites, jamais les permutations, graines ou empreintes du résultat. Le plafond est 60 s.
Les tests séparés de timeout, baux expirés et absence de scellement partiel restent nécessaires.

La recette SMTP utilise réellement le worker et Mailpit. Le délai observé du poll de boîte locale
après mise en file est enregistré, avec borne de 60 s. Il inclut le traitement et la remise SMTP
locale ; aucun délai fournisseur externe ou arrivée en boîte réelle n’en est déduit.

## Portée

Aucune limite de CPU/RAM n’est appliquée à ces processus locaux. Les propositions de production
(portail 1 vCPU/1 Go, coffre 2 vCPU/4 Go) restent à mesurer sur leur propre hôte. Les résultats de
cette machine ne prouvent ni dimensionnement, ni latence Internet, ni capacité multi-familles
non mesurée. Les chiffres réellement observés sont dans report.md et les JSON du run référencé.
