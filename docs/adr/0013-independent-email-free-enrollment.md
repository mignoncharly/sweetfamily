# ADR-0013 — Accès sans email et vérification indépendante

Date : 16 novembre 2026. Décision utilisateur : invitation WhatsApp privée, session mémorisée,
code personnel sauvegardé, maintien de la protection contre l'organisateur. Rôle de vérification
**NON ATTRIBUÉ**. Implémentation soumise à qualification ; aucune indépendance de production déclarée.

Cette décision complète ADR-0005. Le parcours email/allauth existant reste disponible. Le portail
organisateur conserve son authentification forte existante ; cette modification ne lui fournit
ni connexion simplifiée ni moyen de devenir un participant à la place d'un autre.

## Frontière d'identité

Un lien détenu par l'organisateur ne peut pas être une preuve d'identité contre cet organisateur.
Le lien partageable est donc une référence d'inscription, jamais un bearer token de connexion.
Un GET, y compris un aperçu WhatsApp, n'inscrit et n'authentifie personne. Un POST explicite ouvre
une demande liée à un secret aléatoire du navigateur, conservé dans sa session Django chiffrée ;
seule son empreinte est dans EnrollmentClaim. Plusieurs demandes concurrentes n'usurpent pas le
compte ; l'approbation vise une demande exacte, pas « la prochaine personne qui clique ».

Le rôle distinct **Independent vault operator** autorise uniquement une approbation signée d'une
demande précise après vérification humaine. EnrollmentVerifier contient une référence UUID, une
clé publique et enabled ; les migrations ne créent aucune attribution. La clé Ed25519 privée
est générée/conservée hors du portail, du coffre web et des sauvegardes SQL. Elle est distincte
de la clé de commandes de l'organisateur ; cette dernière ne peut pas approuver. L'outil hors
ligne n'a besoin d'aucune connexion SQL, clé de souhait/tirage ou clé de session.

Un opérateur technique du coffre, lui aussi hors du contrôle de l'organisateur, enregistre la
clé publique après nomination et vérification de son empreinte. Il importe ensuite le fichier
d'approbation signé. Ce chemin opérateur n'est exposé par aucun endpoint web. Il demande les
credentials/journal opérateur, absents des processus web et workers. Le serveur vérifie rôle,
clé activée, origine du coffre, signature, comparaison et expiration. Le reçu externe minimal
est synchronisé sur disque avant le commit d'approbation. La signature vaut cinq minutes pour
l'import ; le navigateur approuvé dispose ensuite d'au plus quinze minutes pour activer l'accès.
Une révocation du rôle interdit aussi l'activation des approbations encore inutilisées.

L'activation atomique ne fonctionne que dans le navigateur demandeur. Elle consomme l'invitation,
revendique l'appartenance et révoque les demandes concurrentes. Le code personnel possède 160 bits
aléatoires (32 symboles répartis en huit groupes), reste dans le coffre et n'est affiché qu'à ce
moment. Sa base conserve une empreinte SHA-256, sans version en clair ou récupérable. Un code
choisi par l'utilisateur ou court n'est pas accepté. La copie peut être stockée volontairement
par le participant dans son gestionnaire de mots de passe ; l'application ne la place pas dans
localStorage, une URL, les logs ou le portail.

## Sessions et récupération

Django gère la connexion, la rotation de session et les cookies HttpOnly/SameSite/Secure hors
local. Le backend de code s'ajoute aux backends existants. Une session est limitée à la fermeture
du navigateur par défaut ; l'option explicite propose 30 jours sur un appareil personnel.
Le navigateur peut lui-même restaurer des sessions à sa réouverture : se déconnecter sur un
appareil partagé reste nécessaire. Une génération de credential vérifiée à chaque requête
invalide les anciennes sessions après remplacement du code. Le code actuel est requis pour
le remplacer ; le portail ne reçoit pas de fonction « réinitialiser ».

Perte du code : nouvelle invitation de récupération créée uniquement par l'opérateur technique
indépendant, nouvelle demande liée au navigateur et nouvelle vérification signée. Le même compte
et la même appartenance sont conservés. Aucun nouveau tirage, réaffectation ou suppression de
souhait ne se produit. Une demande seule ne remplace pas un code encore utilisable.

Après restauration SQL, recover(restored=True) désactive tous les codes et rôles de vérification
restaurés, révoque les demandes et invitations sans email en attente et supprime les sessions.
Ainsi une ancienne sauvegarde ne réactive ni code remplacé, ni signature de rôle révoqué.
Le rétablissement des clés publiques et des accès requiert une nouvelle décision indépendante.
La vérification courante recover(restored=False) n'effectue pas ces révocations. Les journaux de
rétention, contrôles du résultat scellé, gates de maintenance et reprise restent obligatoires.

## Email et protection annoncée

La vérification email prouve le contrôle d'une boîte, pas l'identité humaine annoncée. Si cette
boîte est déjà liée indépendamment à la bonne personne, elle empêche un voleur d'invitation
qui ne contrôle pas la boîte de terminer le premier accès. Si l'organisateur choisit seul
l'adresse associée à « Alex », il peut proposer sa propre boîte sous ce nom : vérifier cette
boîte ne règle pas ce risque de substitution initiale. Le parcours historique ne constituait
pas à lui seul une preuve universelle du lien humain/boîte contre un organisateur malveillant.
Le nouveau parcours exige explicitement cette vérification indépendante ; un simple lien privé,
une mention « C'est moi », une adresse saisie ou un code généré par l'organisateur ne la remplacent pas.

## Conséquences produit

L'email peut être null seulement avec WHATSAPP_ENROLLMENT_ENABLED activé dans chaque rôle.
Une identité sans email est propre à son inscription d'événement, avec mot de passe inutilisable
et sans fausse adresse ou EmailAddress vérifiée. Le portail copie un lien nommé vers le coffre
pour un message WhatsApp privé manuel ; aucun envoi WhatsApp n'est automatisé. Ce lien cesse de
permettre l'inscription une fois celle-ci activée. Avant cela, son invitation interne expire
après sept jours et peut être renouvelée dans les limites existantes.

Les commandes/projections gardent leur schéma fermé ; email=null est l'extension du roster.
Aucun code, secret navigateur, clé de vérification ou état d'approbation détaillé n'est projeté.
L'organisateur reçoit seulement les statuts publics déjà définis. Les identités sans email ne
créent pas de courrier sortant ; les avis de tirage restent HELD jusqu'à la preuve de durabilité,
puis IN_APP. Les confirmations, listes, consentements exacts et autorisations privées restent
exigés. Les annonces de groupe sont générales, sans accès personnel. Les écrans de migration
email/passkey des comptes par code sont fermés tant qu'un parcours dédié n'a pas été qualifié.

## Limite non levée

Deux domaines et deux bases sur le même serveur, sous le même compte Unix et le même contrôle
administratif, ne satisfont pas l'indépendance. Aucun vérificateur réel n'est nommé. Les signatures
du rôle utilisées par les tests sont synthétiques et temporaires. Le flag reste désactivé par
défaut ; aucune donnée réelle, famille réelle ou approbation réelle n'est autorisée par cette ADR.
Voir le [runbook](../runbooks/independent-enrollment.md) et le rapport de préparation à la production.
