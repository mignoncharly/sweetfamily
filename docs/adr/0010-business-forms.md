# ADR-0011 — Formulaires locaux et parcours de secours

Date : 16 novembre 2026. Statut : accepté pour l’implémentation locale.

Les deux services rendent leurs propres formulaires Django. Le module public noel_ui ne contient
que labels, validation de date/fuseau, formulaires publics et un adaptateur HttpRequest pour appeler
les vues applicatives avec le même utilisateur et la même session. Le POST HTML passe CSRF avant
cet appel ; le portail ne récupère aucun contenu privé du coffre. Les mutations gardent les
versions et clés de demande. Les heures locales ambiguës ou inexistantes sont refusées.

L’amélioration JavaScript est limitée aux formulaires métier explicitement marqués. Une panne,
un délai ou une expiration de session conservent la saisie dans le DOM ; la reconnexion actualise
seulement le jeton CSRF. Les versions et clés ne sont pas actualisées silencieusement. Aucun
stockage local, sessionStorage, worker de cache, trace ou analytics n’est ajouté. Les formulaires de connexion et d’invitation restent natifs. Les soumissions métier sous
no-referrer exigent JavaScript, sans désactiver CSRF. Le masquage instantané exige aussi
JavaScript ; un avertissement le précise lorsque celui-ci est désactivé.

Le transfert du rôle organisateur nécessite deux comptes vérifiés/MFA et une authentification
code ou mot de passe + MFA de moins de cinq minutes pour chaque acceptation/proposition.
Une réservation APPLYING bloque les mutations de l’ancien propriétaire jusqu’à la réponse du coffre à la commande
signée, sur le transport authentifié existant. Une erreur non définitive conserve
la même commande ; un refus métier définitif impose une nouvelle proposition. La notification
au groupe est créée atomiquement dans le coffre, sans mutation d’attribution ni identité privée.

La copie annuelle crée un nouveau brouillon et de nouvelles propositions, avec remappage des
exclusions publiques. Toute personne doit être réinvitée, revendiquer, remplir et confirmer à nouveau.
Aucun résultat, achat ou état de notification n’est copié. L’export ne parcourt que l’allowlist du
suivi public ; les cellules commençant par un préfixe de formule sont neutralisées.

Le navigateur de recette utilise des sessions et événements synthétiques créés hors routes de
production, dans des bases jetables. La libération du tirage dans cette fixture est explicitement
une preuve simulée ; la restauration native réelle est couverte séparément par la recette métier.
Axe et la simulation de largeur ne prouvent pas une conformité WCAG ni l’usage sur téléphone réel.
L’archivage qui ne conserve qu’un résumé non personnel attend la purge de phase 10, et n’est pas
simulé par un simple changement d’étiquette laissant les données privées en place.


Chromium émet Origin:null pour un POST de navigation sous Referrer-Policy:no-referrer,
ce qui est correctement refusé par Django CSRF. Les pages d’authentification, d’invitation et
l’accueil neutre utilisent donc same-origin : aucun Referer vers un tiers. Les pages cadeau,
listes et API gardent no-referrer ; leurs formulaires métier utilisent fetch same-origin avec
le jeton CSRF standard. Aucun Origin:null n’est ajouté aux origines approuvées et aucune
vérification CSRF n’est contournée. La révélation sans JavaScript est signalée indisponible.
Les contrôles nommés action dans les formulaires ne sont jamais utilisés comme propriété
form.action : l’URL est lue via getAttribute pour éviter le masquage DOM de cette propriété.
