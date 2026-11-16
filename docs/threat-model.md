# Modèle de menace

Version 1 — conception, sans audit ni preuve de déploiement. Références : [produit](product-spec.md), [permissions](permissions.md), [données](data-map.md), [ADR](adr/0001-frontiere-de-confiance.md).

## Garantie et frontière

Objectif : l'organisateur, même administrateur du portail, ne peut obtenir les attributions des autres via interface, API, SQL, logs, sauvegardes ou compte d'envoi. Comme participant, il peut connaître sa seule attribution. Le coffre traite nécessairement la permutation en mémoire : son opérateur indépendant et son infrastructure sont de confiance. Aucun chiffrement de bout en bout ou anonymat absolu n'est promis.

Portail : interface organisateur, roster proposé, base/projections sûres, logs et sauvegardes propres. Coffre : origine HTTPS distincte, sessions personnelles, identités, souhaits, tirage, achats, outbox, email, base, clés et backups. Navigateur participant → coffre directement ; portail → commandes limitées signées ; coffre → projection fermée signée ; coffre → fournisseur email neutre. Marchands externes hors frontière.

Le coffre exige comptes, récupération, DNS, terminaison TLS, accès root, CI, images, secrets, supervision, email et sauvegardes indépendants de l'organisateur. Deux conteneurs sous le même root ou deux comptes récupérables par lui ne suffisent pas. Un proxy contrôlé par lui ne termine jamais HTTPS du coffre. En l'absence de cette séparation, le logiciel peut fonctionner mais la garantie contre le propriétaire reste NON VALIDÉE. L'agent peut développer le socle sans déclarer la production conforme.

## Acteurs et actifs

Adversaires : inconnu avec lien volé, participant curieux, organisateur malveillant ou portail compromis, faux assistant, attaquant réseau/serveur. Actifs : permutation, listes, achats, boîtes et sessions, intégrité du manifeste/consentement, unicité/durabilité du résultat. Opérateur coffre et fournisseur d'infrastructure ont une capacité technique réelle ; un coffre compromis est un incident de confidentialité, pas un cas résolu par le masquage d'écran.

| Menace | Mesure exigée | Preuve cible / risque résiduel |
|---|---|---|
| Email d'un inscrit remplacé par organisateur | Identité revendiquée immuable par commande portail ; changement personnel réauthentifié et vérifié | T24, C05 ; boîte compromise hors garantie |
| Invitation interceptée | Usage unique/expiration/empreinte ; vérification de boîte distincte du lien | T06, C03 ; accès à boîte + lien permet attaque |
| Assistance usurpée | Facteur préenregistré ou preuve indépendante ; aucun transfert sur demande organisateur | C05 ; procédure humaine à qualifier en phase 3 |
| Lecture SQL, backups ou export du portail | Aucune donnée privée, projection fermée ; pas de clés coffre | T15, C11 ; roster public au groupe reste observable |
| Logs, APM, queues trop détaillés | Aucun corps HTTP/secret/association, champs autorisés, télémétrie séparée | T15 ; scan canari complété par revue humaine |
| Règles/exclusions ou faux membre imposés | Manifeste accepté par chacun ; reconsentement et contrôle combinatoire conditionnel | T04, T24, C09, C10 ; email vérifié ne prouve pas identité réelle |
| Double clic, replay ou workers concurrents | Unicité événement/job, idempotence, verrouillage, bail et tentative monotone | T08–T10 ; tests PostgreSQL réel nécessaires |
| Ancienne sauvegarde restaurée | Maintenance, envois suspendus, point sûr/durabilité, réconciliation et registre de suppression | T18, T20, T26 ; perte irréparable = incident/annulation |
| Serveur portail compromis | Coffre refuse commandes interdites ; accès service sans lecture privée ; DNS/CI indépendants | T07, T24, C11 ; phishing du portail reste possible |
| Serveur coffre compromis | Accès minimaux, secrets séparés, patchs, supervision, revue indépendante et incident | C11, C16 ; pas de résistance promise à l'opérateur malveillant |
| IDOR et onglets multiévénements | Session détermine membre et événement autorisé par requête | T02, T07 ; appareil partagé nécessite déconnexion/masquage |
| XSS, URL malveillante ou fuite marchand | Texte échappé, CSP, pas de fetch, marchands approuvés, liens protégés | T16 ; suivi du marchand hors garantie |
| Robot email / prévisualisation | GET sans effet, révélation par POST personnel | T13 ; observation d'écran non couverte |
| Fausse livraison ou webhook falsifié | Vérification signature brute, déduplication, faits distincts et timeout inconnu | T11, T12, T23 ; boîte principale/lecture non garanties |
| Rejeu de ciphertext ou corruption | AEAD avec identifiants/type/version en données associées, nonces uniques | C12 ; clés/opérateur restent de confiance |
| Fuite par corrélation des notifications | Message neutre, pas de digest ciblé exposé au portail, projections regroupées | T15, T25 ; informations externes/coalitions hors garantie |
| Diagnostics synthétiques activés en production | Module absent de l'image et contrôle bloquant build/démarrage | T17 ; chaîne de déploiement doit être indépendante |

## Limites et critères de production

Le contrôle combinatoire refuse les configurations où connaître sa propre attribution force celle d'un autre ; il ne protège pas contre coalitions, confidences, achats observés, révélations au réveillon, boîte compromise ou marchand. Chiffrer la base ne retire pas les capacités du service qui déchiffre. Python ne garantit pas l'effacement mémoire.

Avant de revendiquer la garantie : preuve d'isolation des comptes et chemins de récupération, tests de fuite/autorisation/concurrence/restauration, exercice avec données synthétiques et revue indépendante de sécurité. Aucun de ces critères n'est validé en phase 1. Manque actuel : infrastructure, opérateur, domaines, comptes email, implémentation et preuves. La phase 2 reste possible.
