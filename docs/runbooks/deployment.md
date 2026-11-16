# Conditions de déploiement et remise

La production est bloquée. Les distributions natives se construisent avec
`python scripts/tasks.py build-prod` et se contrôlent avec `check-prod-artifact`.
Elles contiennent requirements à hashes, code, migrations, assets et commandes opérateur
du seul rôle, sans données de test ni secrets. Installer les versions verrouillées dans
un environnement isolé et utiliser `serve.py` avec le superviseur de l'hôte.

Avant ouverture, l'opérateur doit fournir deux ressources/comptes/bases indépendants,
TLS PostgreSQL `verify-full`, reverse proxy HTTPS supprimant les en-têtes transmis non
fiables, secrets distincts, domaine propre au coffre hors DNS contrôlé par l'organisateur,
compte email du coffre, sauvegardes et récupération indépendantes. N'exposer ni SQL,
ni Mailpit, ni registres, ni accès opérateur. L'administrateur portail ne peut modifier
seul le code exécuté, ses secrets ou les procédures de récupération du coffre.

Utiliser `APP_ENV=production`, le bon `SERVICE_ROLE`, `DEBUG=false`, les hôtes/origines
explicites et diagnostics désactivés. Exécuter migrations, `bind_environment`, `check_runtime`,
les checks Django `--deploy`, initialisation du registre et un premier backup restauré.
Configurer le superviseur pour les serveurs, workers, rétention et alertes ; les commandes
locales ne constituent pas un planificateur ni un pipeline installé en production.

La qualification doit porter sur les artefacts exacts : tests et sécurité, revue externe,
latence cible sur l'hôte de référence, téléphone/lecteur d'écran/zoom, boîtes de recette
réelles, sender/domaine et restauration hors site. La recette Zoho/Resend reste différée.
Le domaine proposé `sweetfamily.gestionatech.de` ne prouve pas l'indépendance du coffre.

La remise comprend README, état des phases, contrats, matrice T01–T26, rapports et hashes
de preuves, dépendances verrouillées, artefacts de chaque rôle, procédures et guides.
Une répétition synthétique réelle doit précéder la création sans fixtures de l'événement
familial. Ne jamais déclencher un tirage réel ni afficher une attribution pour illustrer
un guide. `verify-release` demeure bloqué tant que les critères essentiels sont ouverts.
