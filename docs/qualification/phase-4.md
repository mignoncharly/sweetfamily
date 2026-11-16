# Qualification de phase 4

Date : 15 novembre 2026. Windows x64, PostgreSQL 17.12, Django 5.2.19, cryptography 50.0.2.
Périmètre : souhaits, pays et préparation des achats, en exécution native sans Docker ni CI/CD.

## Livraison

Modèles Wishlist, GiftWish, WishlistRevision, WishlistNonce et MerchantRequest dans le coffre,
avec migrations séparées. GiftWish contient les UUID/slots ; titres, URLs, prix EUR en centimes,
date déclarée, devise, notes et préférences de modèle sont dans les snapshots AES-256-GCM.
Le portail ne reçoit que wishlist_complete dans sa table de suivi et son API de statut.

L'éditeur HTML « Mes trois souhaits » fonctionne sans JavaScript pour sauvegarder/valider.
Le script local ajoute seulement la copie de référence. Les brouillons peuvent être incomplets ;
la validation exige trois souhaits complets, de 1 à 4 999 centimes, avec URLs approuvées.
Une liste validée garde trois souhaits valides lors des éditions, avec UUID stables et historique.
Une écriture concurrente obsolète reçoit 409 et conserve le formulaire saisi.

Les recherches proposées utilisent le pays de l'acheteur, sans transformer un lien étranger en
fiche prétendument équivalente. Les prix sont toujours déclaratifs, les prix non EUR sont des
estimations manuelles et les frais suivent la règle d'événement. Aucune adresse ou donnée bancaire.

## Contrôles exécutés

| Contrôle | Résultat local |
|---|---|
| Migrations des deux bases, y compris le booléen de suivi portail | PASS |
| Suites de service sur bases PostgreSQL temporaires | PASS : 7 cas portail, 19 cas identité coffre et 43 cas souhaits |
| Prix 49,99 €, 50 €, négatifs, booléens, floats et saisies ambiguës | PASS : validation entière sans arrondi silencieux |
| Deux/quatre souhaits, validation d'un brouillon, révision périmée | PASS |
| Deux transactions PostgreSQL concurrentes | PASS : une réponse 200 et une 409, aucune révision perdue |
| UUID stables et lecture des anciennes révisions par leur propriétaire | PASS |
| Ciphertext sans canaris titre/domaine, contenu substitué et collision nonce simulée | PASS : erreur d'intégrité ou nouvelle réservation de nonce avant chiffrement |
| URLs dangereuses/locales/raccourcies, doublons et variantes | PASS ; tests sans récupération réseau arbitraire |
| Session personnelle, accès étranger et CSRF | PASS |
| HTML échappé, liens noopener/noreferrer, formulaire sauvegardé ou conservé en conflit | PASS |
| Pays FR/DE, référence FR conservée et recherches DE | PASS ; aucune disponibilité commerciale revendiquée |
| test-integration | PASS : les 8 tests racine incluent les suites de service et le smoke HTTP/SMTP |
| test-unit / test-privacy | PASS : 26 et 20 tests du socle, avec recouvrement entre suites |
| check | PASS : Ruff/formatage, TypeScript, assets, checks Django, migrations synchronisées |
| check-security | PASS : scan source/canaris, pip-audit, npm audit et contrôles Django stricts |
| build-prod / build-test / check-prod-artifact | PASS : distributions locales séparées, sans secrets |

Les suites de service sont appelées par le runner d'intégration ; leurs nombres ne s'ajoutent
pas aux tests racine comme des scénarios entièrement distincts. Le smoke de processus réel
étend celui de phase 3 : après l'inscription, il sauvegarde et valide trois souhaits via le
vrai serveur HTTP du coffre avec cookie/CSRF, puis constate la projection de suivi au portail.
Les titres privés ne font pas partie des commandes stockées par le portail.

Les premières passes ont détecté une erreur de rendu d'un brouillon dont le prix était encore
vide ; le formateur utilise maintenant des centimes entiers et accepte explicitement ce cas.
Les erreurs de validation inattendues sont converties en message français générique, sans
trace interne. Les collisions de nonce sont testées avant chiffrement, pas après publication.

## Portée et conditions restantes

Le test d'édition après DRAWN utilise une fixture d'état. Aucun moteur, permutation ou tirage
réel n'est créé pour ce test. L'accès de l'acheteur à la liste de sa personne tirée et la
comparaison avec la version de son choix d'achat restent en phase 6 ; le lecteur de snapshots
et l'aide pays sont prêts pour cette autorisation future, sans nouvel endpoint public étranger.

Les prix, stocks, frais finaux et résultats des recherches chez les marchands ne sont pas
vérifiés par le produit. Le registre de domaines est maintenu par l'opérateur ; l'ajout demandé
n'est pas automatique. Les paramètres originaux sont conservés ; la déduplication reste une
heuristique limitée, pas une identification universelle de produits.

Les enveloppes par événement, rotation et restauration des clés, purge globale, tests matériels
passkey, accessibilité complète et qualification indépendante de production restent à leurs
phases. La clé dédiée de phase 4 n'est pas une preuve d'exploitation indépendante du coffre.
Aucune notification externe, aucun paiement ni achat n'est effectué. La phase 5 peut commencer.

## Références

- [Contrats phase 4](../api-contracts.md).
- [ADR-0006](../adr/0006-souhaits-revisions-et-liens.md).
- [PyCA : chiffrement authentifié AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
