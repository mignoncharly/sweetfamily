# Récupération d'accès et changement d'email

Périmètre : phase 3, comptes indépendants de portail/coffre. Aucun outil d'usurpation ni
endpoint organisateur de transfert de compte n'est fourni. Ne jamais demander de code,
facteur, clé ou lien privé dans une conversation d'assistance.

## Boîte accessible

Se connecter sur l'origine du coffre, ouvrir /accounts/email/, accomplir la réauthentification
allauth demandée (code à la boîte actuelle ou facteur déjà enregistré), saisir la nouvelle
adresse puis vérifier le code reçu dans cette nouvelle boîte. Une authentification simple
récente ne remplace pas la réauthentification explicite des opérations sensibles.
Le code expire après dix minutes et cinq erreurs interrompent le challenge.

La première vérification d'une identité invitée n'est pas un changement d'adresse :
elle ne révoque pas l'invitation en cours. Un vrai changement conserve l'UUID d'identité et
les appartenances, actualise uniquement le coffre, révoque les anciennes invitations non
consommées et tous les challenges/sessions anciens. La personne doit se reconnecter.
Les notifications neutres allauth informent les boîtes concernées ; aucun nouvel email privé
n'est renvoyé dans le suivi organisateur.

## Boîte perdue, facteur préenregistré disponible

Utiliser l'authentification passkey de django-allauth lorsqu'elle avait été configurée,
puis une réauthentification par facteur disponible et la vérification de la nouvelle boîte.
Les codes de récupération allauth servent à remplacer un second facteur dans un parcours
d'authentification établi ; ils ne constituent pas un lien universel de transfert de compte.
Tester son facteur et conserver ses codes personnels hors de l'application avant usage réel.
La recette matérielle passkey sur navigateurs/appareils réels reste à effectuer.

## Plus aucun moyen de preuve disponible

L'opérateur indépendant peut expliquer les options et vérifier la présence de facteurs,
sans afficher ni transmettre leurs secrets. Un nom, un pays, la possession d'un lien
d'invitation ou une demande de l'organisateur ne constituent jamais une preuve suffisante.
Aucune réinitialisation par SQL, changement d'email forcé ou désactivation de MFA n'est
autorisée par ce guide pour résoudre une demande non prouvée.

Sans preuve via un moyen déjà enregistré, refuser le transfert. Appliquer le retrait
avant tirage ou l'annulation explicite après tirage lorsque ces parcours seront disponibles
en phase 5. En phase 3, ne pas ouvrir un événement réel nécessitant ces parcours encore absents.
Une éventuelle procédure humaine exceptionnelle exige une décision de sécurité distincte,
une revue indépendante et un journal minimal ; elle n'est pas implémentée comme raccourci.

## Appareil partagé et incident

La page /accounts/sessions/ révoque les autres sessions ; /accounts/logout/ présente une confirmation,
puis la déconnexion est effectuée par POST. Fermer ensuite les onglets privés.
En cas de boîte compromise, sécuriser la boîte et révoquer les sessions depuis un facteur
sûr ; signaler l'incident à l'opérateur indépendant, jamais transférer les droits à l'organisateur.

Les clés AUTH_DATA_KEY protègent sessions et secrets MFA. Les perdre n'est pas une procédure
de récupération utilisateur : cela peut rendre les facteurs illisibles. La sauvegarde/rotation
et la restauration de ces clés doivent être qualifiées avant production (phases 6 et 10).
