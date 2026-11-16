# Qualification de phase 6

Date : 15 novembre 2026. Windows x64, PostgreSQL 17.12, Django 5.2.19, cryptography 50.0.2.
Réalisation native, vérifications manuelles ; aucun Docker, GitHub Actions ou pipeline.

## Livraison

Les endpoints fixes du coffre résolvent le donneur depuis la session vérifiée et event_id,
sans identifiant de personne fourni par le navigateur. Seul le résultat AVAILABLE est lisible,
avec état DRAWN ou CLOSED. La réponse contient une personne et trois souhaits, pas la permutation
ou « qui m'offre ». Le portail et les credentials de service ne donnent aucun accès personnel.
GET ne marque aucune consultation ; seul le POST explicite avec CSRF la marque. Le GET HTML
est un écran neutre, avec titre/URL sans destinataire, no-store, no-referrer et CSP anti-iframe.

PrivatePurchaseState conserve choix, révision choisie, état et note dans un ciphertext, sans
index d'association. Les états sont NOT_STARTED, ORDERED, RECEIVED, READY, GIVEN. Une référence
choisie reste comparable après remplacement de l'article ; les nouveaux choix exigent la liste
courante et les écritures sont versionnées. Aucune commande ou livraison commerciale n'est exécutée.

EventDataKey enveloppe une clé AES-256 par événement pour souhaits et préparation. Le résultat
garde sa clé événement de phase 5. Création des enveloppes et nonces est centralisée ; contexte
associé lié au type, événement, propriétaire et révision. Les révisions v1 sont migrées sous
verrou, sans changer leurs numéros utilisateur. La rotation rewrappe les clés sans changer les
ciphertexts métier ni attributions. L'ancien chiffrement reste lisible pour les archives autorisées.
Une clé manquante n'est pas remplacée si des données chiffrées existent ; erreur contrôlée et
alerte locale neutre, aucun nouveau tirage. Aucun KMS n'est configuré.

La projection reste fermée : recipient_viewed booléen et ready_count périodique seulement.
Aucune mutation d'achat ou révélation ne force une projection fine individuelle. Le total
READY/GIVEN n'est accompagné d'aucun statut individuel d'achat, UUID de souhait ou note.

## Contrôles exécutés

| Contrôle | Résultat local |
|---|---|
| Migrations coffre/portail et conversion historique native | PASS |
| Tests de service PostgreSQL jetables | PASS : 8 cas portail ; 19 identité, 43 souhaits, 16 tirage et 22 espaces privés dans le coffre |
| Attribution correcte pour chaque membre, seulement ses trois souhaits | PASS : comparaison interne au résultat synthétique, aucune permutation dans la réponse |
| Session étrangère, credential de service, identifiants additionnels et CSRF | PASS : accès refusé |
| GET neutre / POST reveal idempotent / pas de projection immédiate | PASS |
| PENDING_DURABILITY et annulation bloquent lecture/écriture, CLOSED est en lecture seule | PASS |
| Choix limité à sa liste attribuée, champs fermés, révisions et note bornée | PASS |
| Deux mises à jour concurrentes d'achat | PASS : une 200 et une 409, sans écrasement silencieux |
| Note et choix absents du ciphertext lisible et de l'espace du destinataire | PASS |
| Modification de souhait après choix, ancien article conservé et comparaison | PASS |
| Enveloppes substituées entre membres/événements et ciphertexts altérés | PASS : intégrité rejetée ; réponse neutre 503 et alerte locale |
| Clé d'événement supprimée | PASS : refus, aucune régénération ni remplacement de tirage |
| Collision de nonce simulée | PASS : réservation renouvelée avant chiffrement du nouveau contenu |
| Rotation deux fois, ancienne version autorisée et version retirée | PASS : mêmes attributions/ciphertexts ; ancienne archive lisible avec sa clé, refus sans elle |
| Staging/activation locale de versions maîtresses | PASS : ancien secret non remplacé, aucun secret imprimé |
| Migration v1 vers v2 répétée | PASS : aucun nouveau numéro de révision, mêmes contenus |
| HTML, notes échappées, titre neutre et headers privés | PASS |
| Projection réelle et dump complet du portail | PASS : booléen/total reçus, aucun canari souhait/choix/note dans le dump PostgreSQL |
| test-integration | PASS : 8 tests racine en 211,42 s, avec smoke HTTP étendu |
| test-draw | PASS : 18 tests racine en 85,69 s ; inclut les suites de service et les régressions phases 3–6 |
| test-unit | PASS : 48 tests racine ; 8 cas d'intégration exclus |
| test-privacy | PASS : 26 tests racine, avec recouvrement des suites |
| check | PASS : Ruff/formatage, TypeScript, assets, checks Django et migrations synchronisées |
| check-security | PASS : scanner de secrets/maps JSON, pip-audit, npm audit et checks Django stricts |
| build-prod / build-test / check-prod-artifact | PASS : distributions séparées, imports/routes isolés vérifiés, sans tests, secrets ou service étranger dans la production |

Les tests racine enveloppent les suites de service : leurs nombres ne s'additionnent pas comme
scénarios indépendants. Le smoke conserve les vrais processus apps/workers/Mailpit, le login
SMTP du premier acteur et le MFA organisateur. Trois autres identités et les sessions de révélation
sont des fixtures explicites. Il sauvegarde, chiffre et restaure effectivement le coffre dans une
base isolée, révèle via HTTP avec CSRF, enregistre une préparation READY, avance seulement le
calendrier de projection de sa fixture puis vérifie le portail et son dump complet. Aucune attribution
ou dump privé n'est affiché dans la console. Les acteurs/événement et bases jetables sont nettoyés.

La première passe a détecté une fixture conservant une date de projection antérieure à la libération
durable. La fixture recharge maintenant l'événement ; le POST reveal n'avance effectivement pas le
calendrier. Les anciens tests de collision ciblent désormais le registre central et vérifient le
nonce utilisé au chiffrement, sans contourner l'intégrité des enveloppes.

## Limites et suite

Données uniquement synthétiques, aucune famille réelle, aucun achat ni email externe. La phase 7
intégrera le fournisseur réel et ses notifications, baux/réconciliation et rappels. Les interfaces
complètes/accessibilité sont en phase 8. Le fournisseur local de clés a un contrat d'extension typé ;
aucun adaptateur KMS connecté n'est revendiqué.

Les anciennes clés restent conservées avec une sauvegarde distincte ; la compatibilité avec une
ancienne version est testée localement. La restauration indépendante des clés et la survie à la perte
de la machine restent non qualifiées. La sauvegarde hors machine, purge, registre de suppression et
qualification humaine des comptes/DNS/TLS/opérateur indépendants restent en phases 9–10.

Le garde non local refuse les debuggers Python et collectes de dumps Windows repérés ; Unix fixe
RLIMIT_CORE et Linux non-dumpable. Seul le refus d'un debugger Python est testé ici. Les branches
Unix et une configuration réelle de service Windows durcie ne sont pas qualifiées sur ce poste.
Le contrôle Django strict n'est pas une preuve de cette politique OS. L'opérateur doit vérifier
collecteurs de dumps, EDR/APM et privilèges d'attachement avant production. Aucune promesse d'effacement
mémoire garanti en Python, ni de confidentialité contre l'opérateur de confiance.
Les alertes SecurityEvent sont locales et neutres ; leur routage vers une supervision est en phase 10.

## Références

- [Contrats API](../api-contracts.md), [ADR-0008](../adr/0008-espaces-prives-et-enveloppes.md).
- [Guide de clés et processus](../runbooks/private-keys.md).
- [AESGCM PyCA](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
- [Django : transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/).
