# Noël Secret: plan complet d'implémentation en 10 phases

Version: 1.0. Date: 15 novembre 2026. Langue du produit: français.

Ce document est le cahier d'exécution d'un agent de développement. Il décrit une application complète destinée à une utilisation réelle, avec exploitation, sécurité, tests, reprise après panne et documentation. Il ne constitue pas une application déjà développée ni une certification de sécurité.

## Résultat attendu

Un organisateur crée un échange de cadeaux pour un réveillon, ajoute les participants et suit leur préparation sans connaître les attributions des autres. Chaque participant accède à son espace personnel, propose exactement trois cadeaux à moins de 50 € chacun, découvre la personne à qui offrir un cadeau et choisit normalement un cadeau parmi ses trois souhaits.

La personne qui offre commande et reçoit le cadeau chez elle, puis l'apporte au réveillon. Le pays utile pour choisir une boutique est donc celui de l'acheteur. Les liens proposés par le destinataire identifient les articles souhaités; ils ne constituent pas une obligation d'acheter sur la version nationale initiale du site.

Le suivi des notifications reste disponible en production. La consultation des associations pour déboguer n'existe que dans un environnement de test contenant des données fictives.

## Décisions de conception et hypothèses explicites

Ces choix donnent à l'agent un point de départ exécutable. Ils doivent être consignés, pas présentés comme des informations déjà confirmées par la famille.

| Sujet | Décision de référence |
|---|---|
| Produit | Webapp responsive, accessible sur téléphone et ordinateur, utilisable sans installation. |
| Nom de travail | Noël Secret, remplaçable sans modifier les règles métier. |
| Participants | 4 à 20 par événement. Limite technique explicite pour le tirage uniforme exact et le contrôle des déductions. Aucun dépassement silencieux. |
| Organisation | Un propriétaire par événement; il peut aussi participer avec son identité personnelle. Plusieurs événements indépendants sont possibles. |
| Contact | Email personnel distinct pour chaque participant d'un événement. Prénom et pays seuls ne permettent pas un envoi automatique. |
| Invitation | Lien personnel pour rejoindre, puis vérification de la boîte email. Le lien d'invitation ne suffit pas à voir une attribution. |
| Budget | Prix indicatif de chaque souhait strictement inférieur à 50 €, donc au plus 49,99 €. |
| Livraison | Chez celui qui commande, puis remise au réveillon. Aucune adresse postale collectée. |
| Frais de port | Hors plafond par défaut, clairement affichés. L'organisateur peut choisir un plafond frais compris avant la confirmation des règles. Ce choix n'est pas déjà confirmé par l'utilisateur. |
| Devises | Référence en EUR. Pour un article dans une autre devise, estimation EUR renseignée et signalée comme indicative; aucune conversion automatique inventée. |
| Souhaits | Exactement trois à la validation, avec titre, lien HTTPS, prix EUR et précision éventuelle. |
| Achat | Effectué sur le site marchand par le participant. L'application ne commande rien et ne reçoit aucun paiement. |
| Langues | Interface et emails français complets; architecture traduisible, sans traductions partielles présentées comme terminées. |
| Dates | Date du réveillon et échéance saisies lors de la création. Fuseau proposé Europe/Berlin, configurable; stockage UTC. Aucune date de Noël imposée. |
| Tirage | Déclenchement explicite par l'organisateur après validation; un résultat définitif par événement. |
| Exclusions | Possibles avant le gel des règles. Par défaut, aucune exclusion hors interdiction de se tirer soi-même. |
| Couples | Une exclusion réciproque crée deux interdictions dirigées. Les liens de couple ne sont pas déduits des noms. |
| Confidentialité après la fête | Pas de publication automatique de la liste des associations, même après le réveillon. |
| Conservation proposée | Suppression des données privées 90 jours après le réveillon, sauvegardes glissantes 30 jours; politique ajustable avant ouverture. Ce sont des choix produit, pas une conclusion juridique. |

### Confidentialité: garantie exacte et condition de déploiement

La garantie visée est la suivante: l'organisateur, même administrateur du portail d'organisation, ne peut obtenir les attributions des autres depuis l'interface, les API, sa base, ses journaux, ses sauvegardes ou son compte d'envoi.

Elle nécessite une frontière de confiance réelle. L'architecture de référence sépare:

1. **Le portail d'organisation**, que l'organisateur peut administrer et héberger.
2. **Le coffre privé**, service qui héberge les espaces participants, l'authentification, les souhaits, le tirage et les notifications. En production, son exploitation relève d'une personne ou entité de confiance indépendante de l'organisateur et idéalement extérieure au tirage.

Le coffre possède son propre domaine, son infrastructure, sa base, ses clés, ses accès de déploiement, son compte d'envoi et ses sauvegardes. L'organisateur n'a pas de moyen de récupération ou d'escalade vers ces accès. Deux conteneurs sur un serveur dont l'organisateur est root ne constituent pas cette séparation. Deux comptes dont il peut réinitialiser les mots de passe non plus.

Le service coffre traite nécessairement les associations en mémoire. Son exploitant et son infrastructure sont donc des acteurs de confiance. Ce plan ne promet ni chiffrement de bout en bout du tirage, ni absence absolue de confiance, ni résistance à un exploitant du coffre malveillant. Une telle exigence demanderait un autre protocole, évalué séparément, et ne doit pas être improvisée par l'agent.

Si le propriétaire conserve tous les accès techniques, l'application peut fonctionner mais la garantie contre ce propriétaire n'est pas satisfaite. L'agent doit le signaler et laisser le critère de confidentialité de production non validé. Il doit continuer les travaux indépendants, sans remplacer discrètement la garantie par un simple masquage d'écran.

Le secret ne protège pas contre les participants qui se communiquent leurs résultats, une boîte email compromise, les révélations lors du réveillon, les observations des achats ou la collecte de données par un marchand. Le contrôle combinatoire ci-dessous réduit certaines déductions imposées par les règles; il ne prouve pas un anonymat absolu.

### Architecture retenue

| Composant | Choix et responsabilité |
|---|---|
| Backend | Python 3.13, Django 5.2 LTS, dernier correctif de sécurité compatible vérifié au démarrage. |
| Authentification | django-allauth, versions stables compatibles figées; codes email et MFA existants adaptés plutôt que protocole d'authentification maison. |
| Interface | Templates Django, CSS local et TypeScript léger compilé. HTML utilisable sans animations; améliorations progressives. |
| Données | PostgreSQL 17 maintenu, dernier correctif vérifié. Bases et identifiants séparés pour portail et coffre. |
| Calcul et tâches | Workers Python dédiés; tâches et outbox durables dans PostgreSQL, prise de travail avec verrouillage et bail. Pas de dépendance à une mémoire de processus pour la fiabilité. |
| Chiffrement | Bibliothèque PyCA cryptography; enveloppes AES-256-GCM, clés versionnées. Aucune primitive cryptographique inventée. |
| Emails | Adaptateur Resend réel en production; Mailpit exclusivement en local. Les accès Resend du coffre ne sont pas remis à l'organisateur. |
| Déploiement | Images OCI/Docker distinctes, reverse proxy HTTPS, deux déploiements indépendants. Compose pour développement et recette; ressources de production isolées. |
| Tests | pytest, pytest-django, Hypothesis, Playwright et contrôles d'accessibilité. PostgreSQL réel pour concurrence et intégrité. |
| Exploitation | Journaux structurés minimisés, métriques sans données privées, sauvegardes et exercice de restauration. |

Le choix de Django 5.2 LTS est cohérent avec le socle Python et sa période de maintenance publiée. Les versions exactes des dépendances et images doivent être enregistrées dans des fichiers de verrouillage au moment de l'implémentation, puis mises à jour de manière contrôlée. [S1]

## Phase 1. Spécifier le produit, les accès et les invariants

**Objectif:** rendre les comportements et les garanties vérifiables avant d'écrire les parcours.

### Travaux

1. Créer `docs/product-spec.md`, `docs/threat-model.md`, `docs/data-map.md`, `docs/permissions.md` et les décisions d'architecture dans `docs/adr/`.
2. Attribuer un identifiant aux exigences: invitations, pays, trois souhaits, budget, tirage, notification, confidentialité, livraison chez l'acheteur, exploitation.
3. Distinguer les rôles: organisateur, participant, worker du coffre, opérateur technique du coffre. Le rôle organisateur n'accorde aucun accès privé supplémentaire au participant qui le possède.
4. Documenter les attaques pertinentes: changement d'email d'un inscrit, lien d'invitation intercepté, usurpation via assistance, lecture SQL du portail, logs trop détaillés, changement de règles pour forcer une association, double clic, restauration d'une ancienne sauvegarde, serveur compromis.
5. Définir la liste fermée des informations transmissibles du coffre au portail. Aucun champ sensible ne doit être ajouté par sérialisation automatique d'un modèle.
6. Définir le vocabulaire utilisateur: "personne à qui tu offres", "tes trois souhaits", "à recevoir chez toi", "à apporter au réveillon". Éviter "ton destinataire de livraison" pour la personne qui reçoit finalement le cadeau.
7. Définir une politique de retrait avant et après tirage, de récupération de compte, de conservation et de suppression.

### Invariants non négociables

- Chaque participant actif offre à exactement une autre personne et reçoit d'exactement une autre personne.
- Aucune attribution à soi-même, aucun destinataire oublié, aucun doublon de réception.
- Chaque liste validée contient exactement trois souhaits valides.
- Les prénoms ne sont jamais des identifiants techniques; deux prénoms identiques sont possibles avec un nom d'affichage distinct.
- Les règles, participants et exclusions sont gelés avant le tirage et acceptés par tous.
- Un renvoi d'email, une reconnexion, un retry ou une restauration ne doit pas créer une nouvelle attribution.
- L'API privée détermine l'utilisateur depuis sa session, pas depuis un `participant_id` choisi par le navigateur.
- Le portail ne possède pas la table des associations, ni une copie dans un export, une tâche, un cache ou un événement analytique.
- Une lecture de page ou un robot de prévisualisation email ne déclenche ni tirage ni confirmation de consultation.
- Les données fictives et les données réelles ne partagent pas d'environnement de test.

### Matrice minimale des permissions

| Action ou donnée | Organisateur | Participant | Service coffre |
|---|---|---|---|
| Créer et modifier l'événement avant gel | Oui, pour ses événements | Non | Vérifie les commandes |
| Voir les noms, pays et états de préparation | Oui | Roster nécessaire à la confirmation | Oui |
| Voir les emails du groupe | Ceux qu'il a saisis | Son email uniquement | Oui |
| Lire une liste de souhaits | La sienne; celle de la personne tirée s'il participe | La sienne et celle de sa personne tirée | Accès technique contrôlé |
| Lire une attribution | La sienne uniquement, comme participant | La sienne uniquement | Calcul et consultation autorisée |
| Voir qui lui offre | Non | Non | Accès technique contrôlé |
| Voir le choix de cadeau d'un autre | Non | Non | Stockage privé contrôlé |
| Renvoyer une notification neutre | Oui, commande limitée | Pour son accès | Oui, sans nouveau tirage |
| Réinitialiser l'accès privé d'un autre | Non | Non | Procédure de récupération vérifiée |
| Exporter toutes les associations | Jamais | Jamais | Aucun endpoint ou écran métier |

**Validation:** toutes les exigences ont une phase et un test cible; la frontière de confiance est écrite; les hypothèses ne sont pas transformées en faits. Cette phase produit un contrat, pas seulement des maquettes.

## Phase 2. Installer le dépôt, les environnements et les contrôles automatiques

**Dépendance:** phase 1.

**Objectif:** obtenir une base reproductible avec deux services réellement séparables.

### Travaux

1. Créer un dépôt privé et un monorepo avec `services/control/`, `services/vault/`, `packages/contracts/`, `frontend/`, `tests/`, `infra/` et `docs/`.
2. Partager uniquement les contrats de messages, primitives de validation non sensibles et styles. Le portail n'importe pas les modèles privés du coffre.
3. Séparer paramètres, fichiers de verrouillage ou groupes de dépendances, migrations, comptes SQL, cookies, clés Django et secrets d'environnement.
4. Créer trois environnements: local, staging synthétique, production. Déclarer `APP_ENV` et `SERVICE_ROLE` dans la configuration et en base; vérifier leur cohérence au démarrage.
5. Fournir Compose local: deux apps, deux bases, workers, Mailpit. Les ports SQL et Mailpit ne doivent pas être exposés en production.
6. Créer deux cibles d'image: production et tests. Le module permettant d'inspecter un tirage fictif est absent de l'image de production.
7. Installer les dépendances réelles, verrouiller versions et intégrité, construire les assets localement et servir polices/scripts sans CDN tiers sur le coffre.
8. Créer CI: contrôles Python/TypeScript, tests unitaires, migrations sur PostgreSQL vierge, tests d'intégration, scans de secrets et dépendances, build des images.
9. Produire `.env.example` avec noms et explications, jamais des secrets fonctionnels. Générer les secrets dans le gestionnaire de secrets ou l'environnement de déploiement, sans les afficher.
10. Implémenter les cibles `make` définies dans l'annexe de ce document. Une cible absente ou qui ne fait qu'afficher un succès est un défaut.

### Livrables

- Images reproductibles, lockfiles, `Makefile`, configurations locales et CI.
- Endpoints de santé sans informations internes: vivacité et disponibilité distinctes.
- `docs/local-development.md` et inventaire des variables de configuration.
- Build de production échouant si des routes de diagnostic sont enregistrées.

**Validation:** un clone propre démarre avec les commandes documentées; migrations réversibles quand c'est approprié; les deux services ne peuvent pas lire leurs bases respectives; aucun envoi réel depuis la CI.

## Phase 3. Construire les événements, l'identité et les invitations

**Dépendance:** phase 2.

**Objectif:** identifier chaque personne sans donner à l'organisateur un accès à son espace privé.

### Modèles et intégrité

| Base | Modèles principaux | Contraintes |
|---|---|---|
| Portail | `Organizer`, `EventDraft`, `RosterProposal`, `SafeParticipantStatus`, `ControlCommand`, `ControlAudit` | Propriétaire obligatoire; isolation par événement; versions de commande; projection sûre seulement. |
| Coffre | `PrivateEvent`, `Membership`, `VerifiedIdentity`, `Invitation`, `RosterConsent`, `PrivateSession`, `SecurityEvent` | Un membre par identité vérifiée et événement; jeton d'invitation unique; consentement lié à une version précise des règles. |

L'identité interne est un UUID aléatoire. Les noms d'affichage sont des chaînes bornées et échappées. Les adresses email sont normalisées par les règles de la bibliothèque; ne pas inventer une normalisation des points ou du suffixe `+` commune à tous les fournisseurs.

### Parcours organisateur

1. Connexion et MFA obligatoire avant gestion d'un événement réel.
2. Création: titre, date du réveillon, échéance des listes, fuseau, règle de frais, consigne de remise et participants.
3. Saisie prénom ou nom d'affichage, pays ISO et email. Prévisualisation des erreurs sans envoi immédiat.
4. Publication de la proposition au coffre via une commande signée, versionnée et idempotente.
5. Le coffre vérifie la commande, crée les invitations et envoie lui-même les messages. L'organisateur ne récupère pas les jetons privés.
6. Consultation des états d'invitation; correction d'une adresse non encore revendiquée selon la procédure, avec révocation de l'invitation précédente.

### Parcours participant

1. Ouverture de l'invitation: présentation de l'événement et du domaine du coffre, sans résultat privé.
2. Vérification de la boîte email et création d'une session personnelle.
3. Confirmation de son nom et pays, renseignement des souhaits, puis confirmation ultérieure de la liste du groupe et des règles gelées.
4. Nouvelle connexion par code email; possibilité d'enregistrer une passkey avec les fonctionnalités de la bibliothèque retenue.
5. Déconnexion, révocation des autres sessions et indication claire pour un appareil partagé.

### Paramètres de sécurité à implémenter

- Invitation: jeton aléatoire d'au moins 32 octets, stockage uniquement de son empreinte, expiration de 7 jours, usage unique pour l'inscription. Les invitations réémises invalident les anciennes.
- Authentification email: expiration de 10 minutes, au plus 5 essais par challenge; configuration de la bibliothèque vérifiée et testée. Les secrets de challenge ne doivent pas apparaître en clair dans les journaux ou données de diagnostic. [S6]
- Limites de fréquence sur demandes, validations et renvois, avec protection par compte et par IP. Prévoir plusieurs membres derrière la même connexion familiale.
- Réponses de connexion uniformes pour réduire l'énumération des emails.
- Cookies host-only, Secure, HttpOnly et SameSite approprié. Pas de cookie partagé entre portail et coffre. Rotation de session à l'authentification.
- Réauthentification récente pour changer l'email, ajouter un facteur ou consulter les paramètres de récupération.
- Après inscription vérifiée, l'organisateur ne peut plus changer l'adresse liée à une identité. Le changement par la personne vérifie les boîtes concernées lorsque disponibles et révoque les anciennes sessions.
- Si la boîte est perdue, récupération par facteur déjà enregistré ou procédure documentée de l'opérateur indépendant; jamais par simple demande de l'organisateur.
- Pas d'inscription publique libre permettant à un inconnu de rejoindre un événement en devinant son identifiant.

**Validation:** même prénom pour deux personnes, invitation expirée, lien intercepté sans accès email, brute force, changement d'email, boîte partagée refusée pour deux membres du même événement, accès interévénements et cumul organisateur/participant.

## Phase 4. Implémenter les souhaits, les pays et la préparation des achats

**Dépendance:** phase 3.

**Objectif:** obtenir des listes utilisables dans les différents pays sans promettre une disponibilité commerciale non vérifiée.

### Modèles

- `Wishlist`: membre propriétaire, état brouillon/validé, révision, date de validation.
- `GiftWish`: trois emplacements stables numérotés 1 à 3, identifiant aléatoire, titre, prix indicatif EUR, URL, note, contrainte de modèle exact.
- `WishlistRevision`: historique privé des modifications, selon la même durée de conservation que l'événement.

Les montants sont stockés en centimes entiers. La validation du budget s'effectue côté serveur. Les données privées résident dans le coffre et sont chiffrées au repos selon la phase 6.

### Règles et interface

1. Sauvegarde d'un brouillon de zéro à trois idées; validation uniquement avec trois idées complètes.
2. Chaque idée exige un titre, une URL HTTPS et un prix de 1 à 4 999 centimes. Refuser les formats ambigus, `NaN`, valeurs négatives et montants obtenus par arrondi silencieux.
3. Notes: taille, couleur, édition, compatibilité ou "modèle exact". L'utilisateur peut préciser si un article équivalent lui convient.
4. Détecter les doublons évidents de liens et demander correction avant validation; ne pas prétendre identifier tous les doublons produits entre marchands.
5. Afficher le pays du participant dans son profil et le pays de l'acheteur dans les conseils de commande.
6. Pour un lien étranger, afficher: "Ce lien sert de référence. Vérifie le même article sur une boutique qui livre chez toi."
7. Fournir un bouton pour copier le nom/référence de l'article et, pour les marchands pris en charge, un lien de recherche explicite dans la boutique du pays de l'acheteur. Ne pas remplacer automatiquement le domaine en prétendant que la fiche existe.
8. Indiquer que prix, frais et disponibilité sont indicatifs; afficher la date du prix déclaré. Une estimation n'est jamais étiquetée "prix vérifié".
9. La personne qui offre achète hors application. Son adresse et ses données bancaires ne transitent pas par le produit.

### Sécurité des liens

- URL bornée, sans schéma exécutable, identifiants intégrés ni adresse locale; validation du nom d'hôte normalisé.
- Domaine marchand lisible avant ouverture; `rel="noopener noreferrer"`; pas de redirection ouverte de l'application.
- Supprimer les paramètres de suivi connus seulement lorsque cela ne casse pas la référence produit; conserver les paramètres nécessaires aux variantes.
- Pas de récupération automatique de HTML, d'image distante ou de métadonnées dans cette version complète du produit. Elle fonctionne avec les champs saisis, ce qui évite de dépendre d'un scraping fragile et d'introduire un fetch réseau arbitraire.
- Les liens raccourcis et domaines non marchands identifiés sont refusés. Prévoir une liste de marchands approuvés extensible par l'opérateur et une demande d'ajout sans fetch automatique. Ne pas limiter le produit à Amazon.
- Les titres et notes sont du texte, jamais du HTML fourni par le participant.
- Aucune garantie d'anonymat n'est annoncée une fois sur un site marchand externe.

### Modifications et pays

La validation d'un roster inclut les pays. Avant tirage, toute modification du pays ou des règles invalide les consentements concernés par le manifeste gelé. Après tirage, un changement de pays met à jour les recommandations d'achat du membre sans modifier son attribution.

Après tirage, les souhaits restent modifiables en conservant trois emplacements et le budget, avec numéro de révision et indication du changement. L'acheteur voit la liste courante et peut comparer avec la version consultée au moment de son choix. Les modifications ne changent jamais le tirage et ne révèlent pas l'identité de l'acheteur. Éviter des notifications ciblées visibles du portail qui permettraient de corréler un propriétaire de liste avec son acheteur.

**Validation:** deux pays différents, souhait à 49,99 € accepté, 50 € refusé, trois idées obligatoires, modification concurrente avec conflit explicite, URL malveillante, prix étranger indicatif, article épuisé remplacé sans nouveau tirage.

## Phase 5. Construire le moteur de tirage et la machine d'états

**Dépendances:** phases 3 et 4.

**Objectif:** produire un tirage valide, équitable selon les règles, non manipulable par des retries et récupérable après panne.

### États de l'événement

| État | Entrée et opérations autorisées | Transition |
|---|---|---|
| `DRAFT` | Organisateur prépare le groupe | Ouverture explicite vers `OPEN` |
| `OPEN` | Inscriptions, souhaits et exclusions | Gel de proposition vers `CONFIRMING` |
| `CONFIRMING` | Chaque membre vérifie le roster, les règles et exclusions | Tous valides vers `READY`; modification structurelle vers `OPEN` |
| `READY` | Manifeste gelé, trois souhaits valides par personne, consentements complets | Déclenchement explicite vers `DRAWING` |
| `DRAWING` | Calcul asynchrone; édition structurelle interdite | Résultat scellé vers `DRAWN`; erreur technique récupérable dans le même job |
| `DRAWN` | Consultation, achat, préparation, rappels | Clôture vers `CLOSED` |
| `CLOSED` | Événement terminé, lectures personnelles selon conservation | Archivage puis purge |
| `ARCHIVED` | Résumé non sensible; données privées purgées selon calendrier | Pas de nouveau tirage |
| `CANCELLED` | Participants informés; aucune nouvelle activité métier | Purge selon politique |

Le job de tirage possède ses propres états `PENDING`, `RUNNING`, `FAILED_RETRYABLE`, `FAILED_FINAL`, `SEALED`. Une erreur ne remet pas automatiquement l'événement à `READY`. Les mises à jour du portail reflètent l'état du coffre, qui fait autorité.

Un résultat scellé possède aussi `release_state=PENDING_DURABILITY` puis `AVAILABLE`. Tant que la sauvegarde durable de son commit n'est pas confirmée, les lectures privées et les notifications de tirage restent bloquées. L'interface affiche "Finalisation du tirage". Une panne de sauvegarde donne lieu à une alerte et une reprise de la sauvegarde, jamais à un autre tirage.

### Prévalidation et protection contre les déductions forcées

1. Construire un graphe biparti: à gauche les donneurs, à droite les destinataires possibles.
2. Supprimer les boucles personnelles et les exclusions. Vérifier qu'un couplage parfait existe.
3. Refuser les événements de moins de quatre personnes: à deux, tout est évident; à trois, un participant peut déduire tout le tirage à partir de sa propre attribution.
4. Pour chaque arête possible `g -> r` appartenant à au moins un couplage parfait, fixer hypothétiquement cette attribution, puis vérifier que chaque autre donneur conserve au moins deux destinataires possibles parmi les couplages restants.
5. Si une attribution d'un autre devient forcée pour un participant connaissant la sienne, refuser cette configuration avec une explication sur les règles, sans résultat de tirage puisque celui-ci n'a pas encore eu lieu.
6. Implémenter ce contrôle sur les couplages possibles, pas sur le simple nombre d'arêtes initiales. Une optimisation possible consiste à utiliser un couplage et les composantes fortement connexes du graphe des cycles alternants pour identifier les arêtes utilisables.
7. Valider l'algorithme optimisé contre une énumération exhaustive sur les petits graphes. Ce contrôle ne couvre pas les coalitions, les indiscrétions ou les informations externes.

Le manifeste accepté contient les identités d'événement, noms d'affichage, pays, règles, exclusions et version. Les emails ne sont pas publiés au groupe. Chaque membre confirme la même empreinte canonique. Une modification invalide les consentements; le portail ne peut pas substituer une version au coffre. La famille doit pouvoir repérer un participant inconnu dans le roster: la vérification d'un email ne prouve pas à elle seule une identité réelle.

### Échantillonnage uniforme exact

Pour la limite de 20 personnes, utiliser une programmation dynamique sur les ensembles de destinataires déjà choisis. Ordre des donneurs déterministe, entier Python pour les comptes, source aléatoire `secrets.randbelow`. [S7]

```text
count(mask):
    i = nombre de bits de mask
    si i == n: retourner 1
    retourner la somme de count(mask avec r ajouté)
        pour chaque destinataire r autorisé et encore libre pour le donneur i

sample(mask):
    i = nombre de bits de mask
    pour chaque r autorisé et libre:
        poids[r] = count(mask avec r ajouté)
    choisir r avec une probabilité poids[r] / somme(poids)
    enregistrer i -> r en mémoire et continuer
```

Chaque couplage complet valide a la même probabilité. Cela ne signifie pas que chaque destinataire a la même probabilité marginale lorsqu'il existe des exclusions. Ne pas utiliser `random`, un tri par nombre aléatoire, une graine issue d'un horodatage ou un simple premier couplage trouvé. Ne pas imposer un seul cycle: les cycles de deux personnes sont autorisés lorsque les règles le permettent.

Les tables de comptage restent en mémoire et portent seulement sur les règles publiques; la graine ou un journal des choix du véritable tirage ne sont pas conservés. Ne pas publier de hash non secret de la permutation: son espace est trop petit pour en faire une preuve de confidentialité.

### Atomicité, verrouillage et reprise

1. `POST draw` reçoit un `Idempotency-Key` et la version attendue. Verrouiller l'événement avec `SELECT FOR UPDATE`, revérifier l'état et créer un seul `DrawJob` unique par événement. [S8]
2. Le worker acquiert un bail et un numéro de tentative monotone. Il calcule hors transaction longue sur un snapshot immuable.
3. Une seconde transaction reprend le verrou, vérifie snapshot, bail, tentative et absence de résultat scellé. Un ancien worker ne peut plus écrire après perte de son bail.
4. Valider tous les invariants, chiffrer le résultat et écrire atomiquement le tirage scellé, l'état `DRAWN` et les notifications dans l'outbox.
5. Aucune attribution n'est consultable ou envoyée avant ce commit. Le contrôleur de santé et la projection ne transportent pas le résultat.
6. Crash avant commit: nouvelle tentative possible, puisqu'aucun résultat n'a été révélé. Crash après commit: reprendre uniquement les notifications du même résultat.
7. Une clé d'idempotence réutilisée avec une autre requête retourne un conflit. Un double clic avec une autre clé ne peut pas contourner l'unicité par événement.

8. L'outbox créée au scellement est initialement retenue. Le passage à `AVAILABLE`, autorisé uniquement par la confirmation de durabilité, libère les notifications. Le worker email et les endpoints privés vérifient cette condition indépendamment.

En cas de `FAILED_FINAL` sans aucun résultat scellé, l'opérateur peut clôturer la tentative avec un motif neutre puis réouvrir la préparation sous une nouvelle version de manifeste. Cette opération révoque les anciens baux et nécessite de nouveaux consentements. Si un résultat existe, elle est interdite: seule sa reprise ou l'annulation de l'événement est possible.

### Retrait et annulation

Avant tirage, retirer un membre réouvre la confirmation et revérifie les contraintes. Après tirage, ne pas enlever une personne et recoller silencieusement les associations. Annuler explicitement l'événement si l'échange ne peut plus se tenir, notifier tous les inscrits et, si nécessaire, créer un nouvel événement lié avec de nouveaux consentements. L'annulation ne peut pas effacer ce que des participants ont déjà vu ou acheté.

**Validation:** exactitude exhaustive sur petits groupes; propriétés sur graphes variés; zéro résultat forcé selon le contrôle défini; double requête; deux workers; bail expiré; crash avant/après commit; vérification que les renvois ne modifient pas le résultat. Les tests statistiques sont indicatifs, pas une preuve unique d'uniformité.

## Phase 6. Protéger les données, sceller le résultat et ouvrir les espaces privés

**Dépendance:** phase 5, avec modèles et règles des phases précédentes.

**Objectif:** faire de la séparation une propriété de l'application et du déploiement, pas seulement de l'interface.

### Stockage et clés

1. Stocker le résultat dans `SealedDraw`: identifiants non secrets de l'événement et du job, version de schéma, ciphertext, nonce, identifiant de clé et clé de données enveloppée.
2. Le contenu chiffré contient la permutation complète et la version du manifeste. Aucun `recipient_id` en clair dans une table de résultats, un index, une outbox ou un audit.
3. Générer une clé de données AES-256 par événement et l'envelopper avec une clé maîtresse du coffre. Chiffrer les objets privés avec nonce unique et données associées contenant type d'objet, identifiants et version. Une substitution de ciphertext entre événements doit échouer. [S2, S3]
4. Protéger de la même manière les souhaits, notes et choix d'achat. Les identifiants propriétaires nécessaires à l'autorisation peuvent rester en clair dans la seule base du coffre; leur classification figure dans `data-map.md`.
5. La clé maîtresse est absente de PostgreSQL, du dépôt, des images et des backups du portail. Utiliser un secret monté par l'exploitation indépendante; documenter rotation, sauvegarde séparée et restauration. Prévoir un adaptateur KMS si l'hébergement le fournit, sans prétendre qu'il est connecté avant configuration.
6. Limiter le déchiffrement aux traitements autorisés. Aucune donnée privée dans `__str__`, traces SQL, exceptions, traces APM, dumps de tâche ou métriques.
7. Désactiver core dumps et débogueurs en production. Ne pas promettre un effacement garanti de la mémoire dans Python; le service et son opérateur restent de confiance.
8. La corruption d'une enveloppe renvoie une erreur contrôlée et une alerte neutre. Ne jamais recréer un tirage pour masquer une erreur de déchiffrement.

Centraliser la création des enveloppes: nonces de 96 bits issus de la source cryptographique, contrôle d'unicité par clé dans le registre des enveloppes, génération à nouveau en cas de collision détectée. La réémission d'un ciphertext inchangé est permise; réutiliser son nonce pour un autre contenu ne l'est pas. Tester le chiffrement, l'intégrité, la rotation de clé maîtresse sans modification des associations et la restauration avec une ancienne version de clé autorisée.

### Consultation privée

- Session participant établie directement sur le domaine du coffre.
- Endpoint fixe `/api/me/recipient`: il résout le membre depuis la session et l'événement autorisé, déchiffre dans le coffre puis renvoie seulement la personne concernée et ses trois souhaits.
- Aucun endpoint donnant "qui m'offre", aucune liste globale, aucun mode d'usurpation de participant.
- La page de révélation nécessite une action explicite. Un `POST /api/me/recipient/reveal` marque la consultation; une prévisualisation ou un `GET` technique ne la marque pas.
- Cache-Control `no-store`, Referrer-Policy `no-referrer`, CSP restrictive, protection anti-iframe, aucun script analytique ni service worker stockant les pages privées.
- Titres d'onglet, notifications et URL ne contiennent pas le prénom de la personne tirée.
- L'organisateur participant utilise le même parcours et voit uniquement sa propre attribution.

### Communication portail-coffre

Mettre en place des identifiants de service limités et des messages signés avec identifiant, version de schéma, horodatage, nonce et empreinte du corps. Refuser relecture et conflit de contenu. Le contrat n'autorise que création/proposition, gel, déclenchement, annulation et demandes limitées de notification. Il n'autorise ni lecture des souhaits, ni extraction du résultat, ni changement d'une identité déjà confirmée.

La projection vers le portail est une liste blanche: identifiant opaque de membre, inscription confirmée, liste complète ou non, consentement reçu, état de notification, consultation oui/non. Les timestamps fins, références de souhaits, identifiants de destinataires, erreurs détaillées et journaux privés n'en font pas partie.

Le coffre doit appliquer les règles même si le portail est compromis. Les participants sont dirigés directement vers le domaine du coffre à partir des messages envoyés par celui-ci. Aucun reverse proxy sous contrôle de l'organisateur ne doit terminer le HTTPS du coffre. Son domaine et son pipeline de déploiement doivent être indépendants; contrôler le DNS ou la CI permettrait de remplacer le service.

### Données d'achat

Créer `PrivatePurchaseState` lié au donneur et à l'événement: souhait choisi et révision, état `NOT_STARTED`, `ORDERED`, `RECEIVED`, `READY`, `GIVEN`, note privée facultative. Le choix et la note sont chiffrés. Le destinataire ne voit ni le choix ni l'état. Le portail peut recevoir uniquement un total de personnes prêtes, par projection périodique, sans détail de cadeau.

**Validation:** essais d'accès depuis chaque rôle; dump complet du portail sans association; endpoint privé inaccessible avec credential de service; remplacement de ciphertext détecté; consultation d'une autre personne refusée; absence de résultat dans les logs et headers; vérification humaine de l'indépendance des comptes d'infrastructure.

## Phase 7. Intégrer les notifications réelles et le suivi des envois

**Dépendance:** phase 6. L'adaptateur peut être préparé plus tôt, mais aucun scénario réel n'est validé avant la protection des données.

**Objectif:** délivrer des notifications vérifiables sans divulguer le tirage ni promettre une livraison certaine.

### Messages à produire

| Type | Contenu autorisé |
|---|---|
| Invitation | Événement, échéance, lien d'inscription, consigne générale. |
| Code de connexion | Code court et expiration, sans autre donnée privée. |
| Liste à compléter | Rappel individuel de compléter ses propres souhaits. |
| Règles à confirmer | Demande de vérifier la version du roster et des règles. |
| Tirage prêt | "Ton tirage est prêt. Connecte-toi à ton espace pour découvrir à qui offrir ton cadeau." |
| Rappel avant réveillon | "Pense à recevoir le cadeau chez toi et à l'apporter au réveillon." |
| Modification de souhaits | Digest neutre au groupe, au plus quotidien, invitant à vérifier les souhaits avant achat. Pas de lien de corrélation acheteur/destinataire exposé au portail. |
| Annulation | Événement annulé; consigne de ne plus utiliser ce tirage. |
| Suppression prochaine | Date prévue et procédure d'accès à ses propres données avant purge. |

Le corps des messages de tirage ne contient ni association, ni souhait, ni achat. L'email invite à se connecter; il n'est pas une session permanente permettant de contourner la vérification personnelle.

### Outbox et acheminement

1. Écrire `NotificationOutbox` dans la même transaction que l'événement métier. Clé d'unicité métier: événement, membre, type et version logique.
2. Le payload de message contenant un code ou un jeton est chiffré dans l'outbox et purgé après son usage ou son expiration. Les workers de rendu ne journalisent pas le HTML ni le texte des messages d'authentification.
3. Worker avec bail, retries bornés et backoff. Les erreurs permanentes vont dans un état terminal visible; les erreurs temporaires restent récupérables.
4. Adapter Resend avec clé d'idempotence stable et payload identique pour une tentative logique. La déduplication du fournisseur a une fenêtre de 24 heures; conserver aussi le registre local durable. [S5]
5. Après timeout ambigu, réessayer dans la fenêtre d'idempotence. Au-delà, passer à `DELIVERY_UNKNOWN` et réconcilier avec les informations disponibles; ne pas réexpédier automatiquement en prétendant garantir "exactement une fois".
6. Un renvoi explicite crée une nouvelle notification neutre avec compteur de renvoi et limitation de fréquence. Il ne crée jamais un nouveau tirage.
7. Ne pas envoyer de code de connexion après son expiration; produire un nouveau challenge à la demande.

### Planification des rappels

Implémenter `ScheduledNotification` et un ordonnanceur qui ne fait qu'insérer des notifications idempotentes dans l'outbox. Proposer, sans les imposer, des rappels de liste à J-7 et J-2 de l'échéance, puis des rappels de préparation à J-7 et J-1 du réveillon, à 18:00 dans le fuseau de l'événement. L'organisateur valide les échéances et active les rappels lors de la création; le participant peut désactiver les rappels facultatifs.

À l'exécution, revérifier état de l'événement, version des règles, préférence du membre et utilité du message. Ne pas envoyer un rappel de liste déjà terminée, à un membre retiré ou pour un événement annulé. Un changement d'échéance invalide les jobs devenus obsolètes. Après une longue panne, regrouper ou ignorer les rappels périmés au lieu de tous les envoyer. Tester changements d'heure, fuseaux et reprise concurrente de l'ordonnanceur.

### Retours fournisseur et statuts

- Vérifier la signature du webhook sur les octets bruts, la fraîcheur et l'identifiant fournisseur avec l'outil officiel compatible. [S4]
- Dédupliquer par identifiant de webhook, persister l'événement avant accusé de réception, supporter les événements en désordre.
- Conserver les faits distincts: soumis, accepté, livré au serveur email, différé, rejeté, échec, inconnu. Ne pas écraser une livraison confirmée par un événement plus ancien d'acceptation.
- "Livré" signifie livré au serveur email, pas nécessairement en boîte principale ou lu. [S4]
- "Attribution consultée" vient du `POST` authentifié de l'application, pas d'un pixel email.
- Désactiver suivi d'ouverture et réécriture de liens si le fournisseur le permet. Ne pas utiliser les ouvertures pour évaluer la participation.
- Aucun destinataire multiple en CC/BCC pour les messages individuels.

### Mode test et preuve d'envoi

Mailpit prouve qu'un message a été remis à la boîte locale de test, pas à une personne réelle. L'interface doit afficher "Simulation" sans ambiguïté.

En staging, réaliser une recette réelle avec des boîtes de test autorisées, des noms fictifs, les domaines vérifiés et les webhooks configurés. Le diagnostic synthétique peut comparer une attribution attendue et le contenu de la page privée; le message de production restant neutre, il ne prétend pas contenir le nom du destinataire.

Valider SPF, DKIM et la politique DMARC du domaine d'envoi au déploiement. Les étapes exactes dépendent du domaine réellement choisi et doivent suivre les valeurs retournées par le fournisseur. Ne jamais déclarer l'envoi opérationnel sans preuve réelle.

**Validation:** acceptation fournisseur, livraison à une boîte de test, bounce simulé documenté, webhook falsifié, doublon et désordre, timeout ambigu, crash du worker, renvoi manuel, aucun nom de destinataire de cadeau dans le tableau d'organisation.

## Phase 8. Finaliser les interfaces, le réveillon et les cas de vie

**Dépendances:** phases 3 à 7.

**Objectif:** livrer un produit cohérent et confortable, avec tous les états et les parcours de secours.

### Écrans organisateur

1. Liste de ses événements et création.
2. Participants: saisie, erreurs, invitation, réponse, correction avant revendication et retrait avant tirage.
3. Règles, budget, pays, exclusions et échéances.
4. Tableau de préparation: invitations, listes complètes, consentements, notifications et consultation oui/non.
5. Validation du gel: avertissement pour toute modification invalidant des consentements.
6. Déclenchement: récapitulatif des règles publiques, puis progression technique du job, jamais une animation affichant les noms attribués.
7. Après tirage: renvoi de notification, total de cadeaux prêts, annulation explicite, clôture et archivage.
8. Export de suivi limité aux champs autorisés, sans liste de souhaits ni association. Neutraliser les formules de tableur si export CSV.

### Écrans participant

1. Invitation et connexion.
2. Profil et pays de commande/réception.
3. Mes trois souhaits, brouillon, validation, erreurs et confirmation de sauvegarde.
4. Groupe et règles à accepter.
5. Attente du tirage et rappel de la date.
6. Révélation privée de la personne à qui offrir, avec bouton de masquage immédiat pour un écran partagé.
7. Trois souhaits, notes utiles, version de la liste et aide au choix de boutique dans son propre pays.
8. Suivi personnel: "Commandé", "Reçu chez moi", "Prêt pour le réveillon", "Offert".
9. Aide pour lien inaccessible, produit épuisé, changement de souhait, email perdu et annulation.
10. Préférences de rappels, sessions, facteurs de connexion et données personnelles.

### Design et accessibilité

Créer un design chaleureux et sobre: fond clair, vert profond ou bordeaux, contraste suffisant, typographie lisible, cartes de cadeaux simples. Les animations sont facultatives, courtes et désactivables avec `prefers-reduced-motion`. Aucun son automatique.

Contrôler navigation clavier, focus visible, labels, messages associés aux champs, lecture d'écran, zoom à 200 %, contraste et tailles de cibles. Viser WCAG 2.2 AA sur les parcours livrés; ne pas annoncer la conformité sur la seule base d'un scan automatique. [S9]

Tester au minimum largeurs 360, 390, 768 et 1440 pixels, textes longs et prénoms accentués. Les boutons d'action ne sont pas masqués par le clavier mobile. Les erreurs réseau conservent le formulaire en mémoire de la page sans promettre une sauvegarde réussie. Aucun cache persistant de données privées hors ligne.

### Cas de vie obligatoires

- Une personne n'a pas terminé: l'organisateur voit le blocage, peut relancer ou retirer avant gel avec nouvelle confirmation du groupe.
- L'email n'arrive pas: statut honnête, vérification de l'adresse, renvoi limité, accès à l'aide sans fuite de compte.
- Deux fenêtres modifient les souhaits: conflit de version expliqué, pas d'écrasement silencieux.
- Le cadeau devient indisponible: l'acheteur consulte les autres souhaits; le propriétaire peut modifier sa liste. Aucune messagerie anonyme improvisée n'est nécessaire pour remplir la fonction demandée.
- La commande arrive après le réveillon: une note privée et le suivi personnel sont possibles; le produit ne prétend pas contrôler les délais du marchand.
- Un participant n'est plus disponible après tirage: procédure d'annulation ou maintien convenu hors application, jamais remaniement secret.
- Le propriétaire change: transfert du seul rôle organisation sous réauthentification, notification au groupe, sans accès supplémentaire aux attributions.
- Un nouvel événement annuel reprend seulement les paramètres et participants proposés, avec nouvelles invitations et confirmations; il ne réutilise pas les anciennes associations.

**Validation:** parcours complet réalisable au clavier et sur téléphone; état vide, chargement, erreur, délai dépassé et session expirée traités; aucun résultat privé dans un écran organisateur, titre d'onglet ou export.

## Phase 9. Qualifier la sécurité, la fiabilité et l'expérience réelle

**Dépendance:** phase 8 et intégration de toutes les fonctionnalités.

**Objectif:** réunir des preuves de fonctionnement et détecter les fuites avant tout usage familial réel.

### Matrice de tests obligatoires

| ID | Scénario | Résultat attendu |
|---|---|---|
| T01 | Groupe de 8 personnes fictives, pays FR/DE | Chaque membre offre et reçoit exactement une fois. |
| T02 | Organisateur également participant | Accès uniquement à sa propre attribution. |
| T03 | 2 ou 3 participants | Refus expliqué pour confidentialité insuffisante. |
| T04 | Exclusions impossibles ou forçant une attribution après connaissance de la sienne | Refus avant tirage, aucune donnée privée produite. |
| T05 | Prix 49,99 €, 50 €, négatif; deux ou quatre souhaits | Validation exacte côté serveur. |
| T06 | Lien volé sans boîte email | Aucune session ni attribution accessible. |
| T07 | Accès interpersonnes et interévénements | Réponse sans fuite et refus d'accès. |
| T08 | Double clic et 20 requêtes de lancement concurrentes | Un seul job métier et un seul résultat scellé. |
| T09 | Deux workers, bail expiré, worker ancien encore actif | Seul le propriétaire du bail courant peut sceller. |
| T10 | Crash avant/après commit du tirage | Aucun résultat partiel; résultat scellé conservé. |
| T11 | Envoi accepté puis timeout et redémarrage | Réconciliation/idempotence, pas de nouveau tirage. |
| T12 | Webhooks répétés, falsifiés, retardés | Validation, déduplication et états cohérents. |
| T13 | Consultation par prévisualisation ou robot email | Aucun marqueur "consulté" sans action authentifiée. |
| T14 | Modification de souhait après tirage | Attribution stable, révision visible de son acheteur seulement. |
| T15 | Inspection portail, backups, logs, métriques, exports | Aucune association ou donnée privée interdite. |
| T16 | URL ou note malveillante | Aucun script, fetch arbitraire ou redirection ouverte. |
| T17 | Activation forcée des diagnostics en production | Démarrage refusé ou fonctionnalité absente de l'image. |
| T18 | Restauration sauvegarde et replay des jobs | Résultat scellé préservé, envois réconciliés avant reprise. |
| T19 | Retrait avant/après tirage | Invalidation des consentements ou procédure d'annulation, jamais réparation silencieuse. |
| T20 | Purge et restauration d'un backup ancien | Données expirées repurgées avant réouverture du service. |
| T21 | Événement annulé mais ancien onglet ouvert | Lecture mise à jour et actions refusées; information claire. |
| T22 | Mobile, clavier, lecteur d'écran et zoom | Parcours essentiels réalisables et erreurs compréhensibles. |
| T23 | Boîtes email réelles de test et domaine d'envoi vérifié | Acceptation/livraison documentées avec distinction des statuts. |
| T24 | Roster ou email modifié par portail compromis | Refus du coffre ou nouveau cycle de confirmation. |
| T25 | Rappel après changement d'échéance, panne ou annulation | Aucun message obsolète ni rafale de rattrapage. |
| T26 | Résultat scellé mais sauvegarde non confirmée | Consultation et notification retenues jusqu'à preuve de durabilité. |

### Tests du moteur

- Énumération exhaustive pour les tailles compatibles avec le temps CI, typiquement jusqu'à 8 pour le comptage et moins si toutes les configurations de graphes sont explorées.
- Comparer comptes DP avec énumération indépendante, et arêtes possibles avec la référence exhaustive.
- Tests Hypothesis: graphes valides/invalides, exclusions dirigées, noms identiques, ordres d'entrée différents et limites.
- Tester la sélection pondérée avec un générateur contrôlé seulement en tests; vérifier bornes et cumul des poids.
- La configuration de production utilise toujours la source cryptographique, jamais une graine de test.

### Tests d'intégration et sécurité

Utiliser PostgreSQL réel, les vrais services dans des processus distincts, un serveur Mailpit réel pour le local, l'adaptateur Resend réel sur boîtes de recette. Les doubles de panne sont permis en tests et clairement identifiés; ils ne remplacent pas les essais d'intégration.

Rechercher les canaris synthétiques de confidentialité dans les réponses, logs, queues, erreurs et exports. Ce scan complète la revue des champs et autorisations; il ne constitue pas à lui seul une preuve d'absence de fuite.

Exécuter les contrôles Django de déploiement, la revue CSRF/CSP, les tests d'accès direct aux objets, la limitation d'authentification, les scans de secrets et la vérification des dépendances. Corriger ou documenter explicitement chaque résultat; ne pas masquer un contrôle en le désactivant. [S10]

### Objectifs mesurables proposés

- Configuration de référence documentée: portail 1 vCPU/1 Go et coffre 2 vCPU/4 Go au départ, à ajuster sur mesures.
- Pages usuelles: réponse serveur p95 inférieure à 500 ms hors fournisseur email, sur la charge de recette définie.
- Tirage et contrôle de confidentialité pour 20 participants: objectif inférieur à 60 secondes, limite de job et comportement de dépassement testés. Aucune réduction silencieuse du contrôle pour atteindre le délai.
- Envoi: mise en traitement de l'outbox sous 60 secondes en fonctionnement normal; le délai de livraison externe n'est pas garanti.
- Tests de charge: 20 connexions simultanées par événement et plusieurs événements actifs; mesurer plutôt que revendiquer une capacité sans essai.

### Livrables et sortie

Créer `docs/qualification/report.md`, matrice exigences/tests, rapport de confidentialité, résultats d'accessibilité, mesures, défauts restants et limites. Ne pas inscrire "PASS" pour un test non exécuté. Un test nécessitant un compte externe absent porte "BLOCKED", avec procédure précise pour le débloquer.

**Validation:** aucun défaut critique de confidentialité, intégrité de tirage, authentification ou perte de données; scénarios métier terminés; tout écart important est visible. Une revue de sécurité indépendante du coffre est requise avant de revendiquer la garantie de production contre l'administrateur du portail.

## Phase 10. Déployer, restaurer, exploiter et remettre le produit

**Dépendance:** phase 9; ne pas déclarer la production prête avec des critères essentiels bloqués.

**Objectif:** rendre le service réellement utilisable et maintenable pour la famille.

### Préparation de production

1. Déployer portail et coffre sur des ressources, comptes et domaines séparés selon le modèle de confiance. Le coffre n'est pas hébergé sous un domaine dont l'organisateur maîtrise le DNS.
2. L'opérateur indépendant configure ses secrets, son compte email, ses sauvegardes et son pipeline. Fournir les noms des paramètres et procédures, sans demander de secrets collés dans une conversation.
3. Protéger les branches et images du coffre. L'organisateur peut proposer du code, mais ne doit pas pouvoir remplacer seul la version exécutée en production, modifier le pipeline ou récupérer ses secrets.
4. Activer HTTPS, en-têtes de sécurité, règles réseau et contrôle d'accès aux opérations. PostgreSQL reste privé.
5. Appliquer migrations, vérifier santé, workers, tâches planifiées, domaine d'envoi et réception des webhooks.
6. Refuser le démarrage si environnement incohérent, secrets absents, debug actif ou configuration de diagnostic présente.

### Sauvegarde et restauration

- Sauvegardes chiffrées et isolées par service. Clés du coffre sauvegardées séparément, accessibles à l'opérateur indépendant, jamais au propriétaire du portail.
- Proposer RPO de 15 minutes et RTO de 4 heures comme objectifs d'exploitation, à confirmer par la solution et l'exercice. Mettre en place archivage WAL/PITR si nécessaire pour le RPO retenu.
- Après scellement d'un tirage, confirmer sa protection par la chaîne de sauvegarde avant d'ouvrir sa consultation et de libérer les notifications. Cet état de sauvegarde est un sous-état de disponibilité du résultat, pas un nouveau tirage.
- Pour PostgreSQL avec archivage WAL, enregistrer une barrière WAL après le commit scellé, déclencher si nécessaire la fermeture du segment, puis confirmer son archivage durable avec une sauvegarde de base exploitable. Un simple "backup démarré" ne suffit pas. Une sauvegarde complète ponctuelle vérifiée est une autre procédure valable à cette échelle. Le reçu de durabilité est conservé dans le coffre et corrélé au résultat, sans sa permutation.
- En cas de restauration: démarrer en maintenance, suspendre tous les envois et nouveaux tirages, récupérer jusqu'au point sûr, contrôler les résultats scellés, réconcilier les notifications puis rouvrir.
- Si un tirage déjà divulgué ne peut pas être récupéré, ne pas en générer un autre sous la même identité. Déclarer l'incident et appliquer l'annulation explicite si la récupération échoue.
- Exercer une restauration dans un environnement isolé sans émission réelle d'emails. Vérifier les clés, les associations inchangées, les consentements, les suppressions et la reprise des baux.

### Journaux et supervision

Surveiller: disponibilité, profondeur et âge de l'outbox, jobs bloqués, expirations de bail, taux d'erreurs, bounces, absence de webhooks et sauvegardes trop anciennes. Les alertes de l'organisateur portent sur l'état du service ou l'action à accomplir; elles ne contiennent aucune association.

Les journaux gardent des catégories d'erreur et identifiants techniques minimisés. Les logs privés du coffre ne sont pas envoyés au compte de supervision de l'organisateur. La rétention proposée est de 30 jours pour l'exploitation; les métadonnées de sécurité utiles peuvent avoir une durée distincte documentée. Éviter tout enregistrement systématique de corps HTTP ou d'IP complète au-delà du besoin de sécurité.

### Conservation, suppression et fermeture

1. À J+90 après le réveillon, purger associations, souhaits, choix d'achat, invitations, contenus de notification et identités propres à l'événement selon la politique annoncée.
2. Supprimer les comptes sans autre événement actif selon le choix utilisateur et les règles documentées.
3. Purger aussi les projections nominatives devenues inutiles du portail. Conserver uniquement les métriques non personnelles nécessaires.
4. Les sauvegardes expirent au plus tard selon leur fenêtre de 30 jours. Ne pas présenter une suppression de clé active comme une suppression immédiate de toutes les copies si une clé reste dans un backup.
5. Maintenir un registre minimal de suppression et l'appliquer après restauration, avant remise en service. L'expiration des identifiants du registre suit elle-même une politique.
6. Pour une demande de suppression pendant un échange actif, appliquer d'abord le parcours de retrait/annulation nécessaire à l'intégrité, expliquer la conséquence, puis supprimer selon la politique.

### Mise en service et remise

- Répétition complète avec un événement synthétique distinct, tous les rôles et de vraies boîtes de recette.
- Création de l'événement familial réel sans données fictives préremplies. Les noms, pays, emails, dates et exclusions réels doivent être fournis ou saisis par l'organisateur.
- Aucun vrai tirage exécuté par l'agent à l'insu du groupe: le parcours produit attend les inscriptions, confirmations et action prévue.
- Guide organisateur, guide participant, guide d'exploitation, guide de récupération et procédure d'incident.
- Remise du dépôt, des commandes, des artefacts de release, des versions de dépendances et du rapport de qualification.
- Test après déploiement: connexion, création contrôlée, notification de recette, consultation privée et contrôle du tableau organisateur. Ne pas utiliser une vraie attribution pour un screenshot de documentation.

**Critères de fin:** application déployée et vérifiée, domaine et emails opérationnels, restauration démontrée, isolation du coffre constatée, aucun diagnostic de tirage réel, documentation utilisable, limites clairement indiquées. Si une ressource externe manque, livrer tout le travail exécutable et nommer exactement le blocage; ne pas annoncer "prêt pour la famille".

## Contrats techniques transversaux

### Endpoints à livrer

Les chemins ci-dessous sont les contrats cibles à créer. Ils ne désignent pas des services déjà existants. Toutes les mutations web utilisent CSRF; toutes les requêtes de service utilisent leur authentification dédiée. Les routes privées sont sur l'origine du coffre uniquement.

| Surface | Méthode et chemin | Règle principale |
|---|---|---|
| Portail | `POST /api/events` | Crée un brouillon appartenant à l'utilisateur. |
| Portail | `PATCH /api/events/{id}` | Version attendue et propriétaire vérifiés. |
| Portail | `POST /api/events/{id}/participants` | Ajoute une proposition avant gel. |
| Portail | `POST /api/events/{id}/open` | Commande d'invitation idempotente. |
| Portail | `POST /api/events/{id}/confirm-roster` | Fige une version à faire accepter. |
| Portail | `POST /api/events/{id}/draw` | Version et idempotence requises; réponse sans résultat. |
| Portail | `GET /api/events/{id}/status` | Projection sûre uniquement. |
| Portail | `POST /api/events/{id}/reminders` | Type autorisé et fréquence limitée. |
| Portail | `POST /api/events/{id}/cancel` | Confirmation de conséquence et notification globale. |
| Coffre | `GET /join/{token}` | Présentation et vérification, jamais authentification complète seule. |
| Coffre | Routes allauth personnalisées | Authentification, MFA et récupération sans duplications maison. |
| Coffre | `GET /api/me/events` | Uniquement les événements de l'identité vérifiée. |
| Coffre | `GET/PATCH /api/me/profile` | Pays et nom de la personne connectée. |
| Coffre | `GET/PUT /api/me/wishlist` | Événement autorisé et révision attendue. |
| Coffre | `POST /api/me/wishlist/validate` | Exactement trois souhaits valides. |
| Coffre | `GET /api/me/roster` | Manifeste à accepter, sans emails des autres. |
| Coffre | `POST /api/me/roster-consent` | Version et empreinte du manifeste requises. |
| Coffre | `POST /api/me/recipient/reveal` | Action personnelle, résultat scellé disponible. |
| Coffre | `GET /api/me/recipient` | Projection de sa seule attribution. |
| Coffre | `GET/PATCH /api/me/purchase` | Choix et statut privés du donneur. |
| Coffre | `POST /api/me/withdrawal` | Procédure liée à l'état, pas de suppression sauvage. |
| Coffre | `POST /webhooks/resend` | Signature brute, déduplication, aucun effet sur le tirage. |
| Service | `POST /internal/commands` | Schéma fermé, signature, nonce, horodatage et idempotence. |
| Portail | `POST /internal/status-projections` | Projection signée; ignorer les anciennes versions. |

L'événement courant des routes `/api/me/` est sélectionné explicitement par un identifiant d'événement, puis autorisé côté serveur. Ne pas utiliser un contexte de session global mutable qui mélangerait deux onglets ouverts sur des événements différents. L'identifiant de membre reste dérivé de l'identité authentifiée, jamais fourni pour choisir une autre personne.

Réponses d'erreur: code stable, message compréhensible, identifiant de corrélation opaque. Utiliser notamment 400/422 pour validation selon contrat choisi, 401/403 ou 404 uniforme pour accès refusé, 409 pour version/idempotence, 429 pour fréquence et 503 pour service temporairement indisponible. Aucun détail de base, traceback ou contenu privé.

### Commandes de référence à implémenter et vérifier

```bash
make bootstrap
make dev-up
make migrate
make test-unit
make test-integration
make test-draw
make test-privacy
make test-e2e
make check-accessibility
make check-security
make build-prod
make check-prod-artifact
make backup-drill
make verify-release
```

`make verify-release` orchestre les contrôles de release sur une configuration de recette. Les contrôles exigeant des identifiants externes doivent retourner un état bloqué explicite, pas un succès silencieux. `make check-security` inclut notamment les contrôles Django avec les paramètres de production valides fournis par l'environnement. Aucun script ne déploie ou ne tire au sort des participants réels par défaut.

### Fichiers de remise attendus dans le dépôt développé

| Fichier ou dossier | Usage |
|---|---|
| `README.md` | Démarrage, architecture et commandes réellement testées. |
| `docs/implementation-status.md` | État des 10 phases avec preuves et blocages. |
| `docs/product-spec.md` | Règles métier et hypothèses. |
| `docs/threat-model.md` | Garantie exacte, acteurs de confiance et limites. |
| `docs/permissions.md` | Matrice de visibilité et autorisations. |
| `docs/data-map.md` | Données, propriétaire, chiffrement, stockage et rétention. |
| `docs/adr/` | Décisions d'architecture, alternatives écartées et raisons utiles. |
| `docs/api-contracts.md` | Contrats, idempotence, erreurs et exemples synthétiques. |
| `docs/qualification/` | Résultats réels, mesures et écarts. |
| `docs/runbooks/` | Déploiement, sauvegarde, restauration, incident, rotation et suppression. |
| `docs/user-guides/` | Guides courts organisateur et participant. |
| `infra/` | Configurations séparées et contrôles de production. |
| `tests/` | Tests unitaires, intégration, confidentialité et parcours. |

## Instruction finale à l'agent chargé de l'implémentation

Exécute ce plan dans l'ordre de ses dépendances. Construis le produit complet décrit ici. Ne remplace pas une intégration réelle par un écran de démonstration, une statistique codée en dur ou un succès simulé. Les doubles de test doivent rester explicitement confinés aux tests.

Commence par lire les consignes du dépôt et inventorier l'existant. Réutilise les composants pertinents sans écraser le travail local de l'utilisateur. Si un choix technique existant diffère du plan mais remplit les mêmes garanties, documente l'adaptation et ses preuves plutôt que réécrire inutilement le projet.

Pour chaque phase, livre le code, les migrations, la documentation et les tests nécessaires, puis indique: modifications, commandes exécutées, résultats, risques résiduels et conditions de passage. Ne demande pas de confirmation pour les travaux réversibles déjà couverts par le plan. Ne demande jamais de secrets dans la conversation.

Continue les phases indépendantes lorsqu'un service externe manque. En revanche, ne déclare pas validées la livraison email réelle, l'indépendance du coffre, une restauration ou une sécurité qui n'ont pas été vérifiées. La disponibilité d'un coffre indépendant, des domaines, des boîtes de recette et des credentials configurés est une dépendance de mise en service, pas une justification pour fabriquer un résultat.

Le produit est terminé lorsque les critères de la phase 10 sont démontrés. Le nombre de fichiers, de tests ou de lignes de code n'est pas un critère de succès à lui seul.

## Sources techniques et portée

Sources officielles consultées le 15 novembre 2026. Les règles métier, la séparation portail/coffre et les algorithmes proposés sont des décisions de conception de ce document. Ces liens documentent les composants et principes utilisés; ils ne certifient pas l'architecture entière. Revérifier versions, options et comportements lors de l'implémentation.

- **S1. Django:** [versions et maintenance](https://www.djangoproject.com/download/), [Django 5.2 LTS](https://docs.djangoproject.com/en/5.2/releases/5.2/).
- **S2. OWASP:** [Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html), séparation des clés et données et modèle de menace.
- **S3. PyCA cryptography:** [chiffrement authentifié](https://cryptography.io/en/stable/hazmat/primitives/aead/), nonces, données associées et erreurs d'intégrité.
- **S4. Resend:** [types d'événements](https://resend.com/docs/webhooks/event-types), [gestion et vérification des webhooks](https://resend.com/changelog/managing-webhooks-via-api).
- **S5. Resend:** [clés d'idempotence et fenêtre de 24 heures](https://resend.com/docs/dashboard/emails/idempotency-keys).
- **S6. django-allauth:** [configuration des comptes](https://docs.allauth.org/en/latest/account/configuration.html), [configuration MFA](https://docs.allauth.org/en/latest/mfa/configuration.html), [limites de fréquence](https://docs.allauth.org/en/latest/account/rate_limits.html).
- **S7. Python:** [module secrets](https://docs.python.org/3.13/library/secrets.html).
- **S8. PostgreSQL:** [verrouillage explicite](https://www.postgresql.org/docs/17/explicit-locking.html).
- **S9. W3C:** [WCAG 2.2](https://www.w3.org/TR/WCAG22/).
- **S10. Django:** [checklist de déploiement](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
