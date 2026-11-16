# ADR-0005 — Identité et invitations dans le coffre

Date : 15 novembre 2026. Statut : appliquée en phase 3, qualifiée localement.

## Décision

Utiliser django-allauth 65.22.1 pour email-code, réauthentification, TOTP, récupération de second
facteur, WebAuthn et gestion des sessions. Les contraintes du produit sont des adaptateurs et
autorisations autour de ces flux, sans fabriquer de code de connexion ni de vérificateur OTP.
Les consultations des traces d'authentification internes d'allauth sont couvertes par les tests ;
réexaminer ces hooks à chaque mise à jour de version.

Le coffre prépare un compte à mot de passe inutilisable et une VerifiedIdentity UUID lors d'une
commande d'invitation signée. Une identité peut être préparée mais non encore vérifiée.
Membership est indépendante du rôle organisateur et n'est active pour l'accès personnel qu'après
revendication explicite par l'utilisateur authentifié avec sa boîte vérifiée et le bon lien.
Aucune inscription publique libre au coffre ; le portail garde sa propre inscription organisateur.

Stocker uniquement l'empreinte du jeton d'invitation. Le secret nécessaire au message est dans un
payload temporaire chiffré puis purgé. Le contexte signé de dix minutes permet de conserver le lien
entre invitation et parcours allauth ; ce cookie ne dispense d'aucune vérification d'identité.

Envelopper la sérialisation de session Django et les secrets MFA avec Fernet de cryptography,
avec une clé de service hors base. HMACer les clés du cache SQL de limitation, notamment pour ne
pas exposer un code TOTP dans une clé de cache upstream. Sérialiser les POST d'authentification
sous verrou de session jusqu'à sa sauvegarde pour préserver les compteurs de tentatives.

Exiger email vérifié, premier facteur code/mot de passe et MFA effectivement accompli dans la
session pour les API organisateur. Les facteurs seuls stockés en base ne suffisent pas.
Les limites d'ouverture/correction sont aussi vérifiées par compte/IP ; le coffre limite les
réémissions à trois invitations par membre et par heure, même face à un portail compromis.

Les commandes sont signées Ed25519 avec la clé privée du portail et vérifiées avec sa clé publique
dans le coffre. Une deuxième paire, dont la clé privée reste au coffre, signe les projections
fermées vers le portail. Les modèles privés, clés d'authentification et sessions ne sont pas partagés.
L'idempotence repose sur des reçus persistés, pas sur une mémoire de processus.

## Alternatives et conséquences

Le lien seul ne constitue pas une session. Une réinitialisation par l'organisateur ou un changement
d'identité revendiquée est refusé ; la correction avant revendication remplace uniquement la
proposition d'appartenance et révoque les anciens liens. Un vrai changement personnel d'email
nécessite les flux allauth de réauthentification et vérification de nouvelle boîte, puis révoque
les anciennes sessions et challenges. Les adresses déjà liées à une autre identité ne sont pas
fusionnées silencieusement.

La perte d'AUTH_DATA_KEY peut rendre les facteurs illisibles ; sauvegarde et rotation sont des
conditions de production à qualifier. Les opérateurs techniques restent de confiance.
Le dispatcher SQL local couvre les messages nécessaires à l'identité ; il ne remplace pas les
baux et la réconciliation fournisseur de phase 7. Les passkeys matérielles restent à recetter.
