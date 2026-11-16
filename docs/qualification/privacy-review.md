# Revue de confidentialité — phase 9

## Frontières examinées

Le portail stocke propositions publiques (nom, pays, email proposé), règles, commandes métier,
consentements/listes/notification/consultation sous forme de drapeaux et un total de cadeaux prêts.
Il ne possède ni clé de déchiffrement de tirage, ni souhait, choix d’achat ou note privée. Les
commandes signées ne permettent aucun export d’attribution. Le coffre déduit le membre de la
session vérifiée et contrôle l’événement dans chaque requête personnelle. Une clé de service
ne donne pas accès à une route de lecture privée. Les routes d’export portail lisent l’allowlist
publique ; les formules de tableur sont neutralisées.

Les listes, révisions, achats, sessions/MFA et résultats privés utilisent les enveloppes prévues.
Les nonces et données associées empêchent la substitution entre membres/événements. L’absence
ou l’altération d’une clé échoue sans générer un autre tirage. Un backup vérifié est obligatoire
avant la disponibilité du résultat et des notifications ; la clé de backup et les clés de tirage
restent des secrets du coffre. La machine locale de développement peut accéder aux deux rôles :
aucune résistance à son administrateur OS n’est revendiquée.

## Canaris et examen des surfaces

Les tests vérifient le dump PostgreSQL complet du portail après révélation/achat dans les vrais
services, les projections fermées, les réponses non autorisées, le CSV, les sorties du formateur
de logs et les titres/URL de l’espace privé. Les contenus d’email restent neutres ; les outbox
privées sont chiffrées et les payloads sont effacés après traitement. Les sources de tests et leurs
preuves locales peuvent volontairement contenir des canaris synthétiques : elles sont exclues
des distributions de production et ne sont pas un export familial.

Le scan complète l’examen des champs, du code et des autorisations ; il ne démontre pas à lui seul
une absence de fuite. Les sauvegardes de production, comptes de supervision et accès réels doivent
être inspectés par l’opérateur indépendant. Aucun secret réel n’est copié dans les preuves.

## Navigateur et annulation

Les pages privées/API imposent no-store/no-referrer et CSP restrictive, sans analytics, cache
applicatif persistant, worker hors ligne ni association dans l’URL ou le titre. Les formulaires
natifs de connexion/invitation et l’accueil neutre utilisent same-origin pour rester compatibles
avec CSRF ; aucune origine null n’est approuvée. Les liens marchands utilisent noreferrer/noopener.

La nouvelle route de disponibilité renvoie seulement état et disponibilité pour le membre courant.
Son GET ne marque pas de consultation. Un onglet visible interroge cet état toutes les 15 secondes,
au retour de focus et au retour de visibilité ; une annulation retire le contenu privé et l’action
de révélation. Un délai réseau est borné à 10 secondes. Les mutations restent refusées immédiatement
par le serveur après annulation. En cas de panne réseau, le navigateur ne prétend pas connaître le
nouvel état et affiche un avertissement. Il est impossible de faire oublier un cadeau déjà vu,
photographié ou copié ; aucune révocation de cette connaissance n’est promise.

## Limites ouvertes

T18 reste partiel jusqu’à la reprise en maintenance de phase 10. T20 exige la purge et le registre
appliqué aux restaurations. La durée effective des backups et des copies chez le fournisseur email,
le cloisonnement matériel/organisationnel et la revue indépendante restent non qualifiés.
Les résultats exécutés et leurs références exactes figurent dans report.md et matrix.md.
