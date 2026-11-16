# ADR-0011 — Réutilisation bornée des connexions SQL WSGI

Date : 16 novembre 2026. Statut : implémenté et testé localement ; cible p95 non atteinte.

Le premier test HTTP a mesuré un p95 de 2 528 ms au portail et 3 592 ms au coffre sous
40 requêtes concurrentes. Les paramètres fermaient la connexion SQL après chaque requête.
Un diagnostic local de dix nouvelles connexions par rôle a observé une médiane de 150 à 163 ms
pour connexion + SELECT 1. La création de backends PostgreSQL Windows est donc une hypothèse
concrète de coût important, à confirmer par la mesure après changement.

Les deux serveurs natifs WSGI utilisent désormais DB_CONN_MAX_AGE=60 secondes et les health checks
Django. L’opérateur peut choisir de 0 à 300 secondes ; zéro désactive la réutilisation, une valeur
invalide refuse le démarrage. Les variables locales sont CONTROL_DB_CONN_MAX_AGE et
VAULT_DB_CONN_MAX_AGE. Aucun pool ou credential commun n’est ajouté et les transactions,
autorisations, sessions et requêtes restent contrôlées par utilisateur/événement.

La durée est bornée. Chaque thread a sa connexion ; prévoir les threads de requête, workers,
connexions de démarrage et marge opérateur dans le budget PostgreSQL. Le worker ferme ses
connexions anciennes/inutilisables entre itérations. Aucun paramètre SQL de rôle, fuseau ou
identité n’est modifié par requête. Une future exécution ASGI devra désactiver cette stratégie
et être qualifiée séparément. Ajuster la durée en dessous d’un éventuel timeout idle du serveur.

La recette termine réellement les backends d’une base jetable après charge, puis vérifie une
requête authentifiée réussie et les parcours suivants. Ce test est local, utilise un nom de base
strictement réservé aux tests, et n’est ni embarqué ni exposé en production.

Référence primaire : [Django 5.2 — persistent connections, connection management et caveats](https://docs.djangoproject.com/en/5.2/ref/databases/#persistent-connections).
La mesure du premier run reste conservée ; seule une nouvelle qualification peut valider la version modifiée.
