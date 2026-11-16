# ADR-0004 — Exécution locale sans Docker ni CI/CD

Date : 15 novembre 2026. Statut : décision utilisateur appliquée depuis la phase 2.

La demande utilisateur remplace les prescriptions Docker/Compose, images OCI, dépôt GitHub et CI/CD
du plan. Deux services Django fonctionnent comme processus indépendants, avec deux clusters
PostgreSQL, comptes, migrations, secrets et cookies distincts. Aucun dépôt distant ou pipeline créé.

Waitress est le serveur WSGI natif. uv.lock et package-lock.json verrouillent les dépendances ;
infra/tool-versions.json enregistre les versions et empreintes des outils téléchargés.
PostgreSQL 17.12 et Mailpit restent dans .local, sans changer les installations système.
Tous les ports locaux sont liés à loopback ; Mailpit porte le label Simulation.

Les contrôles s'exécutent manuellement via scripts/tasks.py ou Makefile. Les cibles production/tests
sont des archives distinctes, contrôlées et reproductibles, plutôt que des images OCI.
La production inclut le seul service concerné, contrats publics, assets et dépendances hachées ;
elle exclut tests, diagnostics et secrets locaux. Une cible future indisponible échoue avec BLOCKED.

L'exécution sur un même ordinateur ne prouve pas l'indépendance du coffre contre son administrateur.
La production exige toujours opérateur, domaines, accès système, récupération, clés, compte d'envoi,
sauvegardes et accès de déploiement indépendants, avec qualification de restauration et revue de sécurité.
