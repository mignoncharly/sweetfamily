# Qualification — accès sans email, 16 novembre 2026

**Recette technique synthétique ; PRODUCTION BLOCKED ; vérificateur réel NON ATTRIBUÉ.**
Décision : [ADR-0013](../adr/0013-independent-email-free-enrollment.md).
Procédure/permissions : [runbook indépendant](../runbooks/independent-enrollment.md).
Critères réels : [préparation production](production-readiness.md).

## Source qualifiée et commandes

Run final `20261116T143006Z-ae8bc273`, source SHA-256
`880bbd1dde7ae4addfe14fb80cf58caf96ae89e260d3b977cb9a7e17646d6a74`.
Les commandes sont exécutées depuis `/home/mignon/apps/sweetfamily`, avec son Python 3.13.11.
Aucun bootstrap relancé, package système remplacé, secret gtech copié ou courrier réel envoyé.

```bash
.venv/bin/python scripts/tasks.py db-up
.venv/bin/python -m ruff check services packages tests scripts
.venv/bin/python -m ruff format --check services packages tests scripts
NOEL_WEB_PROCESSES=2 NOEL_WEB_THREADS=2 .venv/bin/python scripts/tasks.py qualify
.venv/bin/python scripts/tasks.py verify-release
```

Migrations générées puis appliquées au local : control 0011, vault 0013–0015. Migration séparée
et sans création de vérificateur ; dependances verrouillées existantes conservées. Aucun changement
de paquet n'est requis pour les venvs hébergées : leurs requirements restent identiques.

| Vérification finale | Résultat |
|---|---|
| Root | 76 PASS |
| Portail imbriqué | 52 PASS |
| Coffre imbriqué | 186 PASS |
| Navigateurs | 3 cas PASS ; 1 cas explicitement non applicable au rôle portail, SKIP |
| Axe natif | 11 portail + 22 coffre historique + 7 nouveau parcours ; zéro violation détectée |
| Checks/migrations/types/assets | PASS |
| Audits dépendances/sécurité | PASS |
| Distributions par rôle | PASS ; import depuis extraction sans fallback dépôt ajouté |
| Restore/purge PostgreSQL réel | PASS, y compris ancien backup de code remplacé / rôle activé |
| verify-release | BLOCKED attendu, code 2 ; critères humains/indépendance/revue/email ouverts |

Tests de confidentialité : invitation/aperçu sans authentification, demande non approuvée refusée,
mauvais navigateur et requête concurrente refusés, une seule activation en concurrence PostgreSQL,
clé organisateur incapable d'approuver, rôle absent/révoqué refusé, code affiché une fois et absent
des sessions/DB en clair, remplacement révoquant ancien code/autres sessions, limites/CSRF,
purge et restore ne réactivant ni code ni rôle. Une recette avec configuration staging,
Secure cookies et mail bloqué passe aussi dans le client de test HTTPS Django ; elle n'est pas
présentée comme une session réseau TLS. La recette publique ci-dessous est distincte.

Le parcours de tirage synthétique exige toujours listes validées, consentements au manifeste
exact et disponibilité après durabilité ; pas de mail sans email. Les tests utilisant un reçu
fixture l'identifient comme tel ; les drills de sauvegarde/restauration physique restent distincts.
Aucun tirage réel n'est lancé sur le staging hébergé.

## Performance de référence locale

Deux événements, 20 sessions par événement, 40 requêtes concurrentes, 40 warmups puis 400 GET,
2 processus × 2 threads par rôle. Portail p95 **231,411 ms** ; coffre p95 **411,940 ms**.
Cible locale < 500 ms atteinte. Reconnexion après terminaison de six backends par rôle PASS.
Ce benchmark authentifie les fixtures historiques email ; il ne qualifie pas sous charge les
sessions par code en HTTPS. HTTP loopback sans TLS et sans quotas de production, hôte partagé :
aucune promesse de capacité ni fermeture du critère de performance de production.

## Incident d'empaquetage et correction

Le run source précédent `20261116T142129Z-4de6cdaf` passait ses checks locaux. Lors des premières
recettes HTTPS hébergées (`synthetic-enrollment-20261116T142726Z` et `...142843Z`), l'import
opérateur d'approbation échouait : `noel_enrollment_approval.py` manquait à l'allowlist du ZIP
coffre. Les tests du dépôt disposaient du module via leur PYTHONPATH et ne détectaient pas cette
absence. Aucun accès privé n'était accordé après l'échec. Nettoyage, désactivation et readiness
réussis après chaque tentative ; la première trace avait un libellé RUNNING non final, et ne doit
pas être comptée comme succès. L'absence de module a été diagnostiquée explicitement.

Correction : module livré uniquement dans l'artéfact coffre ; chaque distribution est désormais
extraite et importée avec un répertoire courant/PYTHONPATH limité à l'extraction. Le run final
ci-dessus requalifie la correction. Les anciennes preuves locales ne sont pas réécrites comme
si elles avaient testé ce chemin réseau/opérateur.

## Hébergement et recette publique

Les deux bases hébergées étaient vides avant modification (0 événements/0 utilisateurs pour
chaque rôle). Les deux mises à niveau ont utilisé les scripts opérateur locaux reviewables :

```bash
.venv/bin/python .local/hosted/upgrade-email-free.py
.venv/bin/python .local/hosted/qualify-email-free.py
```

Ces exécutions ponctuelles et leurs journaux sont privés dans `.local/hosted`, pas des scripts
contenant des credentials à versionner. L'upgrade contrôle la qualification/source, extrait les
artéfacts par rôle, vérifie les requirements identiques, entre en maintenance, arrête seulement
les quatre unités web/worker Sweetfamily, produit un backup chiffré par rôle, conserve l'ancien
release, applique migrations/bind/check_runtime/check --deploy/operations verify, reprend et
redémarre uniquement ces unités. Les clusters ne sont pas remplacés. Readiness HTTPS et état
PID/NRestarts de gtech sont comparés après opération. Aucun changement nginx, DNS, certificat
public ou service d'une autre application n'est effectué.

La recette publique active temporairement le flag du seul coffre, attribue une clé de rôle
**synthétique temporaire**, crée quatre inscriptions sans email par commande signée et utilise
Chromium sur l'origine HTTPS réelle. Elle signe/importe une demande, active le code dans le bon
navigateur, teste session mémorisée, retour avec code, liste privée et remplacement révoquant
l'autre session. Aucun bypass TLS/hostname/DNS n'est configuré. Pas d'email ou tirage réel.
Ensuite maintenance, révocation du rôle test, purge de l'événement synthétique via le registre,
suppression de cette attribution test, retour au flag désactivé, vérification/reprise et HTTPS.
Le résultat effectivement obtenu, les empreintes et le répertoire final sont consignés dans
[email-free-enrollment-2026-11-16.json](email-free-enrollment-2026-11-16.json).

## Critères non fermés

Aucun vérificateur réel nommé ; contrôle du coffre/serveur/zone DNS/recovery encore commun à
l'organisateur. Aucune garantie de production contre ce contrôle n'est revendiquée. Téléphone,
lecteur d'écran, zoom manuel 200 %, procédure humaine de vérification, email autorisé du parcours
organisateur/notifications éventuelles, charge HTTPS/quotas, rotation/scheduled maintenance,
backups/alertes indépendants, restauration indépendante RPO/RTO et revue externe restent ouverts.
Le PostgreSQL partagé 17.11 n'a pas été remplacé et ne valide pas le minimum 17.12 de production.

### Résultat public final

`synthetic-enrollment-20261116T143416Z` : **PASS**, sept scans Axe sans violation, Chromium avec
validation TLS normale. Les empreintes des ZIP et toutes les entrées déployées correspondent
aux distributions du run final. Après purge : zéro événement, utilisateur, code, demande ou rôle
activé du coffre. Aucune nomination réelle ; flag sans email désactivé et route de connexion
par code renvoyant 404 comme attendu. Readiness HTTPS 200 sur les deux domaines. Les six unités
Sweetfamily sont actives ; gtech reste PID 1733623, NRestarts=0.

Deux backups par rôle ont été créés lors des deux promotions, avec anciennes releases conservées
sous `.local/hosted/upgrades/`. Les CA/secrets/configurations/bases n'ont pas été régénérés.
La requalification finale inclut la correction PACKAGE-01. Les premiers échecs réseau/opérateur
restent explicitement conservés dans le paragraphe d'incident, sans être comptés comme succès.
