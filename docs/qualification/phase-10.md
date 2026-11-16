# Qualification de phase 10 — exploitation locale

Historique Windows : 16 novembre 2026. Windows x64, PostgreSQL natif, deux services séparés,
sans Docker, GitHub Actions, dépôt distant ou CI/CD.

## Périmètre livré

- Maintenance SQL par rôle et forçage indépendant par environnement lors d'une restauration.
  Verrous partagés pour requêtes/ticks, transition exclusive sans modifier les transactions
  métier d'envoi ou de scellement. Vivacité neutre, autres accès refusés en maintenance.
- Purge à J+90 des dépendances privées/publiques ; métadonnées anciennes, messages expirés
  et sessions nettoyés. Registre externe authentifié écrit avant le commit de suppression.
- Suppression de compte sur demande vérifiée, avec refus si échange/transfert encore lié,
  réapplication après ancien backup et révocation des sessions concernées.
- Conservation d'un compte vérifié permettant une nouvelle invitation annuelle après purge
  de son ancienne identité, sans nouvelle copie de compte, souhait ou attribution.
- Backups chiffrés propres à chaque rôle, restauration vers une nouvelle base isolée,
  expiration des archives préfixées de plus de 30 jours et inventaire des copies résiduelles.
- Récupération : tombstones rejoués avant accès, tirages connus/fingerprints/bijection inchangés,
  déchiffrement des souhaits/achats/facteurs, jobs anciens retenus et sessions révoquées.
  Les messages même anciennement QUEUED sont retenus en DELIVERY_UNKNOWN et ne repartent pas.
- Commandes et guides d'exploitation, déploiement, restauration, incident, organisateur et participant.

## Preuves

`python scripts/tasks.py backup-drill` : PASS pour les deux rôles. Onze cas par rôle dans
la suite d'opérations, dont une vraie chaîne pg_dump/pg_restore et récupération en second
processus. Les données sont synthétiques ; aucun envoi réel. Les cas propres au coffre
ne prétendent pas exercer une fonction correspondante du portail.

Le drill restaure un événement encore présent dans le backup mais supprimé ensuite de la
source, ainsi qu'un compte dont la suppression est postérieure au snapshot. Les deux sont
repurgés avant reprise. Un autre événement conserve son tirage scellé ; les clés de facteurs
TOTP et des souhaits restaurés sont effectivement utilisées. Les files restaurées ne sont
pas éligibles à l'envoi, y compris par le vrai dispatcher. La répétition de récupération passe.

Les autres tests couvrent rollback SQL après reçu externe, retry direct de purge, absence
ou corruption du registre, tirage connu absent, clés maîtresses/authentification erronées,
refus de suppression d'un compte actif, distinction entretien/restauration et expiration
des archives limitée au rôle et à la fenêtre attendus.

La requalification complète est enregistrée sous
[20261116T105107Z-7d6abc4f](../../.local/qualification/20261116T105107Z-7d6abc4f/result.json).
SHA-256 des sources : `6a6a32640c35a8a53f1c5ff0b930e7341bac0d5a3a4c0eeb68786a929b006b72`.

| Contrôle de la version finale | Résultat |
|---|---|
| Ruff/format, TypeScript, assets, Django, migrations | PASS |
| Secrets, pip-audit, npm audit, paramètres stricts | PASS dans le périmètre automatisé |
| Distributions de production et séparation des rôles | PASS |
| Tests racine | PASS : 69 cas |
| Suite portail / coffre imbriquée | PASS : 51 / 162 cas ; ne pas additionner comme preuves indépendantes |
| Chromium et Axe, deux rôles | PASS |
| Trois tirages de 20 membres | PASS : 2,505 / 2,227 / 2,237 secondes, plafond 60 secondes |
| HTTP p95 portail / coffre, même protocole local | 725,169 / 1 401,162 ms ; cible 500 ms NON ATTEINTE |
| Reconnexion après terminaison SQL | PASS : cinq backends par rôle puis requête authentifiée |
| `qualify` | PASS local ; release BLOCKED |
| `verify-release` | BLOCKED attendu : T22, T23, indépendance/revue externe et p95 |

La matrice issue de ces preuves passe T18 et T20 à PASS_LOCAL. T22 reste PARTIAL et T23
BLOCKED ; tous les autres scénarios T01–T26 sont PASS_LOCAL dans le périmètre local.
Les guides et rapports Markdown restent distincts des fichiers de preuve hashés. Les deux
registres opérateur locaux ont été initialisés sans données personnelles et les commandes
`status` ont été vérifiées sur les deux bases locales, sans envoi ni changement d'événement.

Le run précédent `20261116T104251Z-48103341` est conservé mais invalide pour cette version :
toutes ses étapes passent, cependant les sources ont changé pendant son exécution.

## Conditions de production ouvertes

Aucun déploiement, changement DNS ou email réel n'a été effectué. Performance p95, téléphone,
lecteur d'écran et zoom manuel, boîtes de recette Zoho/Resend, revue externe et indépendance
du coffre restent des critères essentiels. RPO 15 minutes / RTO 4 heures et récupération
hors site ne sont pas prouvés par ce poste local.

Le registre doit être le plus récent, conservé hors de la restauration SQL et protégé contre
rollback/effacement par le stockage de l'opérateur. Les anciens backups sans préfixe et copies
externes nécessitent inventaire ; la réduction du registre après 120 jours reste une revue
manuelle conditionnée par la disparition des copies rejouables. Les logs et planificateurs
de production relèvent du superviseur à configurer. Ces limites empêchent de déclarer la
phase 10 globale terminée ou le produit « prêt pour la famille ».

## Requalification indépendante Ubuntu — même journée

Le [rapport Ubuntu](ubuntu-2026-11-16.md) et son [résumé JSON](ubuntu-2026-11-16.json) portent
les résultats de la source remise depuis le clone Linux. Le run final est
`20261116T121211Z-59ab2e86`, source
`ac0ff2f302731eb99aa67cb448da9ff1dfe7206643188fccef90b73627786daf`.

PASS local : 74 tests racine, 51/164 cas imbriqués, deux parcours Chromium et 33 scans Axe
sans violation, sécurité, migrations, recovery/purge et distributions natives. P95 portail
282,695 ms / coffre 327,425 ms avec deux processus × deux threads par rôle ; cible locale
atteinte sans TLS et sans quotas de production. Reconnexion après terminaison de six backends
par rôle PASS. Trois calculs de vingt membres : 1,346 / 1,399 / 1,376 secondes.
Les registres opérateur ont été initialisés et leurs états vérifiés séparément.

L'installation et l'exploitation Ubuntu sont dans [le runbook](../runbooks/ubuntu.md).
Le mode Windows historique 1 × 4 reste disponible ; il n'a pas été rejoué sur Windows pendant
cette session. `verify-release` reste BLOCKED, code 2. La performance sous limites/HTTPS,
matériel assistif, email réel, indépendance, supervision/entretien/backups/alertes et
restauration indépendante RPO/RTO restent non validés. PostgreSQL 17.11 local ne valide pas
le minimum 17.12 enregistré pour la production. Aucun déploiement ni tirage réel n'est exécuté.

## Complément sans email — 16 novembre 2026

Le [rapport du parcours sans email](email-free-enrollment-2026-11-16.md) et
[ADR-0013](../adr/0013-independent-email-free-enrollment.md) complètent ces résultats historiques.
Le restore révoque aussi les codes et rôles d'approbation restaurés pour ne pas ressusciter
une clé/code révoqué après le snapshot. Maintenance, registre externe, scellement/durabilité
et contrôle des sauvegardes restent requis. Le rôle réel **Independent vault operator est
NON ATTRIBUÉ** ; ses clés synthétiques n'établissent aucune nomination ni indépendance.
Voir [les critères de production actuels](production-readiness.md), toujours BLOCKED.
