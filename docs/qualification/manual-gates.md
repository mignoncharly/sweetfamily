# Recettes restantes avant ouverture réelle

Ces recettes ne sont pas marquées PASS par le runner local. Consigner date, version exacte,
matériel/environnement, étapes, résultat observé et défauts. Ne jamais mettre de secret dans le rapport.

## T22 — téléphone, lecteur d’écran et zoom

Utiliser seulement des comptes synthétiques et un groupe de recette. Sur un téléphone réel,
ouvrir invitation/connexion, modifier le profil, compléter les trois souhaits, déclencher une erreur,
confirmer les règles puis révéler/masquer et enregistrer une préparation. Vérifier que le clavier
logiciel laisse les actions accessibles, que les champs et erreurs sont lisibles et que le masquage
retire réellement le cadeau de l’écran. Vérifier rotation, retour de navigation et changement d’onglet.

Sur Windows avec NVDA, puis si disponible VoiceOver/iOS, effectuer les mêmes parcours sans souris :
lien d’évitement, ordre et visibilité du focus, titre et régions, labels, aides, erreurs de champ,
annonce de sauvegarde et de session expirée, conflit entre deux fenêtres, boutons de masquage et
retour au bouton de révélation. Ne pas attribuer une réussite à partir de la seule arborescence Axe.
Tester le menu de zoom à 200 %, texte long et écran étroit ; vérifier contraste, focus et cibles
sur toutes les actions, y compris les formulaires d’authentification et les liens marchands.

Le reflow à 720 CSS pixels de la recette automatisée représente une fenêtre de 1440 pixels
zoomée à 200 %, sans prouver la manipulation du menu, la lecture audio ou le clavier d’un téléphone.
Tout défaut bloquant doit être corrigé puis rejoué avant de fermer T22.

## T23 — remise réelle Zoho EU ou Resend

Différé à la demande de l’utilisateur. Ne pas redemander la configuration gtech pendant cette attente.
Quand le chemin du fichier local est fourni, recopier uniquement les paramètres autorisés dans les
variables du rôle concerné, sans les afficher ni partager les secrets entre les deux services.
Utiliser `docs/runbooks/notifications.md` et `scripts/staging_mail.py --help` pour le probe neutre.

Vérifier le domaine réellement autorisé, SPF/DKIM, l’expéditeur et la boîte de test autorisée
info@gestionatech.de, puis réception/indésirables. Distinguer soumis au SMTP, accepté fournisseur,
remis au serveur, arrivé dans la boîte et lu. Zoho SMTP n’offre pas de preuve de remise webhook.
Ne pas ajouter de suivi de clic/ouverture. Conserver uniquement références techniques minimales
et observations manuelles, sans corps privé, mot de passe ou clé. Le sous-domaine proposé
sweetfamily.gestionatech.de ne prouve pas l’indépendance du coffre si son DNS est contrôlé par
l’organisateur ; le domaine et l’opérateur du coffre doivent être qualifiés séparément.

## T18/T20 — restauration, replay et purge (phase 10)

La restauration native du résultat scellé et la réconciliation simulée des envois sont testées.
Il reste à implémenter puis exercer la maintenance avant reprise, le registre de suppressions,
la repurge d’un backup ancien et la réconciliation des envois restaurés avant relance des workers.
Restaurer sur une base isolée, envois suspendus et SMTP de simulation ; vérifier une attribution
inchangée, les anciennes notifications ambiguës sans renvoi aveugle et les identifiants purgés
qui ne ressuscitent pas. Mesurer RPO/RTO sur cet exercice, sans les déduire du test de scellement.

## Indépendance et sécurité de production

Un opérateur distinct doit vérifier comptes, accès OS/SQL, DNS, clés, sauvegardes, récupération,
absence de droits de remplacement du coffre par le portail et limites d’accès aux journaux.
Une revue indépendante doit examiner les autorisations, primitives de tirage/chiffrement,
restauration et surface publique de la version exacte. Le runner local sur une seule machine
ne prouve pas cette indépendance, même si les comptes SQL et processus applicatifs sont séparés.
`verify-release` reste bloqué tant que les critères essentiels ne sont pas réellement satisfaits.
