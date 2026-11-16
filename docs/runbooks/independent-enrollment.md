# Opérateur indépendant — premier accès sans email

16 novembre 2026. **Rôle NON ATTRIBUÉ ; sortie production BLOCKED.** Ce guide décrit une
procédure à qualifier avec la personne nommée. Il ne la nomme pas, n'accorde rien à l'organisateur
et ne transforme pas la recette synthétique en exploitation indépendante.

## Vérification obligatoire, personne par personne

1. Utiliser son propre appareil et l'origine HTTPS du coffre connue à l'avance. Vérifier le
   domaine/certificat ; ne pas suivre une adresse d'approbation donnée par l'organisateur.
2. Rencontrer le participant, ou utiliser un contact privé déjà connu et vérifié indépendamment.
   Un nom WhatsApp, numéro nouvellement fourni par l'organisateur, screenshot ou transfert de
   message ne constitue pas cette preuve. L'opérateur doit savoir quelle personne il vérifie,
   son événement et son inscription attendue, sans déduire cette identité de la demande seule.
3. Le participant ouvre l'invitation sur son propre navigateur, confirme son nom/événement et
   « C'est bien moi ». Il lit **depuis ce navigateur** la référence UUID et les quatre groupes
   de comparaison affichés. Comparer tous les groupes, l'événement, la personne et la référence.
   Ne pas approuver une demande préparée dans le navigateur de l'organisateur. Ne demander ni
   code personnel, ni cookie, ni secret de navigateur ; ne prendre aucune copie du futur code.
4. Signer uniquement cette demande précise après cette vérification. Transmettre le fichier
   signé à l'opérateur technique indépendant du coffre par le canal convenu, hors du portail.
   Import dans les cinq minutes ; sinon refaire la vérification/signature. Ne pas signer en lot
   sur la seule base du roster fourni par l'organisateur.
5. Le participant actualise sa page sur **le même navigateur**, puis active dans les quinze
   minutes. Il conserve son code en privé et choisit lui-même de mémoriser la session. Une autre
   demande ou un autre appareil ne peut pas utiliser cette approbation. En cas de doute, refuser.

La vérification humaine et la résistance à la manipulation du vérificateur ne sont pas démontrées
par les tests. Il faut recetter la procédure avec l'opérateur réellement nommé. L'email seul
prouve une boîte, sans prouver la bonne personne lorsque l'organisateur a choisi cette boîte ;
voir [ADR-0013](../adr/0013-independent-email-free-enrollment.md#email-et-protection-annoncée).

## Permissions minimales et attribution

| Acteur | Droit nécessaire | Ce qu'il ne reçoit pas |
|---|---|---|
| Organisateur | Préparer noms/pays/email facultatif, copier une référence d'invitation privée, suivi public | Approbation d'identité, clés du coffre, code permanent, reset d'un compte revendiqué |
| Participant | Sa demande liée à son navigateur, son code, ses sessions et données autorisées | Approbation des autres demandes, associations globales |
| Vérificateur « Independent vault operator » | Clé de signature dédiée et possibilité de vérifier une demande précise ; clé publique activée dans EnrollmentVerifier | SQL, shell serveur, Django admin, secret de session, clé de tirage/souhait, sauvegardes, codes personnels |
| Opérateur technique indépendant | Gestion contrôlée des clés publiques du rôle et import des approbations, journal, maintenance et récupération | Aucun droit à déléguer ces accès à l'organisateur ; aucune console métier d'associations |

Le dernier rôle conserve une capacité technique de confiance sur le coffre. Il ne doit pas être
confondu avec le minimum accordé au vérificateur. L'import se fait par commande opérateur,
jamais par une API de l'organisateur. Le modèle de rôle est un principal de signature distinct,
pas un compte organisateur/allauth partagé. Aucune ligne d'attribution n'est créée automatiquement.

Après nomination seulement, le vérificateur génère les clés sur une machine qu'il contrôle :

```bash
python scripts/enrollment_verifier.py init --directory /chemin/prive/verifier
```

Le Python doit avoir les dépendances verrouillées du projet. Répertoire 0700, fichiers 0600 sur
Ubuntu, refus d'écraser un existant. Sur Windows, appliquer une ACL privée au répertoire/fichiers.
Transmettre **public.json uniquement** à l'opérateur technique par le canal indépendant et
comparer l'empreinte de clé. Ne pas copier private.json sur le serveur/portail ni dans une sauvegarde SQL.

Avec l'environnement opérateur du coffre chargé séparément, après vérification de la nomination
et de cette clé publique :

```bash
python services/vault/manage.py enrollment_verifier grant --public-key-file /chemin/public.json
```

La commande nécessite OPERATIONS_DIRECTORY/OPERATIONS_KEY et les credentials du coffre ; ne pas
les injecter dans web/worker. Ne jamais utiliser les credentials de gtech. La CLI refuse la clé
de commande du portail comme clé du rôle. Une clé techniquement distincte ne prouve pas qu'elle
est détenue par une autre personne : cette attribution est une preuve opérateur à conserver hors portail.

Après les cinq vérifications ci-dessus, sur l'appareil du vérificateur :

```bash
python scripts/enrollment_verifier.py sign \
  --key-file /chemin/prive/verifier/private.json \
  --claim-id UUID_LU_SUR_L_APPAREIL_DU_PARTICIPANT \
  --comparison AAAA-BBBB-CCCC-DDDD \
  --vault-origin https://ORIGINE_INDEPENDANTE_DU_COFFRE \
  --identity-verified --output /chemin/prive/approval.json
```

La comparaison n'est pas un mot de passe. Aucun code personnel n'est produit par cet outil.
La clé privée n'est pas affichée ; le fichier doit rester privé. L'option identity-verified est
une attestation de l'opérateur, pas une vérification automatique. L'importateur technique exécute :

```bash
python services/vault/manage.py approve_enrollment --approval-file /chemin/prive/approval.json
```

Le fichier signé est lié au rôle, à l'origine exacte du coffre, à la demande, à sa comparaison
et à une expiration. Rejeu après utilisation, mauvaise signature, clé non attribuée/désactivée,
ancienne invitation ou mauvais navigateur sont refusés. Supprimer les copies d'approbation après
traitement selon la politique opérateur ; ne pas les versionner ni les publier.

Révocation d'une clé du rôle :

```bash
python services/vault/manage.py enrollment_verifier revoke --verifier-id UUID_DU_ROLE
```

Cela bloque les nouvelles approbations et l'activation d'approbations inutilisées. Les comptes
déjà activés gardent leur accès propre. En cas de compromission, enregistrer une nouvelle clé
indépendante après nouvelle vérification de son détenteur ; ne pas réactiver aveuglément l'ancienne.

## Récupération d'un participant

Avec le seul environnement opérateur technique indépendant :

```bash
python services/vault/manage.py recover_personal_access UUID_DU_MEMBRE
```

Cette commande crée une nouvelle référence d'inscription non authentifiante, valable un jour.
Elle ne montre/remplace aucun code. Refaire toute la vérification sur une nouvelle demande ;
l'activation remplace ensuite le credential et révoque les autres sessions. Elle conserve
compte, appartenance, souhaits et éventuelle attribution scellée. Le portail ne peut pas initier
ce reset d'un compte revendiqué. Aucune récupération basée sur la seule affirmation de l'organisateur.

Après restauration SQL, suivre d'abord restore.md : maintenance obligatoire, registre externe,
contrôle des tirages et déchiffrement, anciens envois retenus. Tous les codes, sessions, rôles
et approbations restaurés sont bloqués avant reprise. Réattribuer les clés publiques après examen
indépendant, puis rétablir chaque participant avec la cérémonie ci-dessus. Le drill local ne
vaut pas exercice indépendant RPO 15 minutes / RTO 4 heures.

## Accès devant rester hors du contrôle de l'organisateur

- Compte d'hébergement/console, facturation et récupération fournisseur du coffre ; root/sudo,
  shell, comptes Unix, unités web/worker, déploiement/code et toute voie de mise à jour.
- Bases, rôles SQL, sockets, credentials, fichiers de configuration, sessions et clés de données,
  signature de projections, clés de chiffrement des souhaits/tirages et clés opérateur/journal.
- Domaine du coffre, registrar, DNS autoritatif et récupération de ces comptes, émission et clés
  TLS. Un sous-domaine dépend encore de l'administrateur de sa zone parente ; délégation DNS et
  certificat séparés ne suffisent pas si l'organisateur peut reprendre la zone/registrar.
- Registre externe, stockage/chiffrement des backups, restauration et inventaire des copies,
  clés du vérificateur, canal de vérification d'identité, supervision et destinataires d'alertes.
- Identités MFA, passkeys, boîtes/numéros de récupération et comptes de secours de tous ces accès.
  Aucun compte partagé, reset par l'organisateur ou secret commun avec le portail/gtech.

Actuellement les deux services sont sur cet hôte sous le même contrôle administratif, et le coffre
est vault.sweetfamily.gestionatech.de sous la zone de l'organisateur. C'est une recette technique ;
ces faits ne prouvent pas la séparation ci-dessus. Aucun vérificateur réel n'est attribué.

## Activation et recette technique

Par défaut WHATSAPP_ENROLLMENT_ENABLED=false pour chaque service. En local, les deux options
CONTROL_WHATSAPP_ENROLLMENT_ENABLED et VAULT_WHATSAPP_ENROLLMENT_ENABLED du .env peuvent être
activées seulement pour une recette synthétique. Les tests utilisent leurs bases jetables,
clés temporaires et attributions synthétiques, jamais une vraie famille.

Déployer les migrations et artefacts qualifiés de chaque rôle avec backup/maintenance/reprise
selon les guides existants avant d'activer le flag dans les configurations indépendantes.
Cette modification du dépôt ne remplace pas à elle seule les releases immuables déjà hébergées.
Ne pas lancer prepare ou bootstrap sur un environnement hébergé existant pour tenter une mise à jour.
