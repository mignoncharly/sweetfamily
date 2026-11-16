# Noël Secret

Phases 1 à 9 et travaux locaux de phase 10 livrés : portail et coffre privé séparés.
La mise en production reste bloquée par les critères de qualification externes et de performance.
[Avancement](docs/implementation-status.md) · [Contrat produit](docs/product-spec.md) ·
[Contrats API](docs/api-contracts.md).

## Recette hébergée active

[Portail](https://sweetfamily.gestionatech.de/) · [Coffre](https://vault.sweetfamily.gestionatech.de/)

Les deux sites sont accessibles en HTTPS et vérifiés dans Chromium, avec certificat valide.
Voir [état et exploitation](docs/runbooks/hosted-staging.md). L'email et la connexion email
restent désactivés ; seules des données fictives sont autorisées et la production reste non qualifiée.

## Démarrer sur Ubuntu

Lire [le runbook Ubuntu sur hôte partagé](docs/runbooks/ubuntu.md) avant tout bootstrap.
Il donne les commandes vérifiées, ports privés, environnement Python local, outils à empreintes,
recette synthétique et arrêt sans intervenir sur les autres applications.
Résultats : [qualification Ubuntu](docs/qualification/ubuntu-2026-11-16.md).

## Démarrer sur Windows

Prérequis : Python 3.13, uv et Node.js 24/npm. Aucun Docker, dépôt GitHub ou pipeline CI/CD requis.

~~~powershell
python scripts/tasks.py bootstrap
python scripts/tasks.py dev-up
~~~

bootstrap installe les dépendances verrouillées, PostgreSQL 17.12 et Mailpit vérifiés dans .local,
génère les secrets locaux sans les afficher et compile les assets. migrate complète les nouvelles
clés et migrations lorsqu'on reprend un environnement de phase 2.

Portail : http://127.0.0.1:8001/ ; coffre : http://127.0.0.1:8002/ ;
Mailpit « Simulation » : http://127.0.0.1:18025. Les endpoints /health/live et /health/ready
restent disponibles sur chacun des services.

Créer le compte organisateur, vérifier son email dans Mailpit, activer MFA puis se reconnecter
par code email et second facteur. Les API documentées permettent de préparer l'événement et le
groupe, puis d'envoyer explicitement les invitations. Les formulaires d'authentification sont
disponibles, avec les formulaires métier des deux espaces (phase 8).

Chaque invité ouvre son lien, demande un code email sur le coffre et confirme ensuite son
inscription. Le lien seul n'authentifie pas. Le worker coffre envoie les messages dans Mailpit
et regroupe les projections sûres vers le portail ; le worker portail reste un socle supervisé.
Aucune donnée familiale réelle n'est préremplie. Seuls les tests synthétiques exécutent des tirages.

Ctrl+C arrête applications, workers et Mailpit. Arrêter ensuite les bases sans supprimer les données :

~~~powershell
python scripts/tasks.py db-down
~~~

## Contrôles manuels

~~~powershell
python scripts/tasks.py check
python scripts/tasks.py test-unit
python scripts/tasks.py test-integration
python scripts/tasks.py test-draw
python scripts/tasks.py test-privacy
python scripts/tasks.py check-security
python scripts/tasks.py build-prod
python scripts/tasks.py build-test
python scripts/tasks.py check-prod-artifact
~~~

Alias Makefile disponibles si make est installé. Les tests de phase 3 utilisent des bases
PostgreSQL temporaires et une vraie chaîne locale HTTP/SMTP pour le scénario d'invitation.
Les cibles `test-e2e`, `check-accessibility` et `backup-drill` exécutent les parcours natifs
et la récupération PostgreSQL isolée. `verify-release` bloque sur les critères ouverts.

Voir [guide local](docs/local-development.md), [récupération](docs/runbooks/account-recovery.md),
[rapport phase 2](docs/qualification/phase-2.md) et [rapport phase 3](docs/qualification/phase-3.md).
Les envois externes, la recette matérielle passkey, la restauration et l'indépendance du coffre
en production ne sont pas validés par ces essais locaux. Les listes de souhaits sont maintenant disponibles sur le coffre.

## Phase 4 — mes trois souhaits

Dans le coffre, ouvrir « Mes trois souhaits » depuis son événement. Les brouillons peuvent être
incomplets ; la validation exige trois articles, chacun entre 0,01 € et 49,99 €. L'éditeur conserve
trois emplacements stables, date/prix indicatifs, devise d'origine, notes et préférence de modèle.
Les révisions sont chiffrées et les conflits entre fenêtres sont explicites.

Les recherches marchandes utilisent le pays de l'acheteur sans modifier les liens de référence.
Aucune fiche, image, conversion de devise ou disponibilité n'est récupérée automatiquement.
La consultation de la personne tirée est disponible en phase 6. Voir [contrats](docs/api-contracts.md)
et [qualification phase 4](docs/qualification/phase-4.md). Le moteur et les confirmations du groupe sont maintenant disponibles.

## Phase 5 — confirmer et tirer

L'organisateur gèle le groupe via l'API confirm-roster. Chaque membre consulte « Le groupe et
les règles » dans le coffre et confirme la même version, sans publication des emails.
Quand tous ont rejoint, validé trois souhaits et confirmé, l'API draw crée un unique job.
Les exclusions incompatibles ou permettant de déduire une autre attribution sont refusées.

Le worker scelle un résultat chiffré et retient les notifications. L'opérateur du coffre doit
ensuite sauvegarder, restaurer et vérifier ce commit :

~~~powershell
python scripts/noel_operator.py confirm-durability <event_uuid>
~~~

Les sauvegardes chiffrées locales sont dans .local/backups. Une erreur laisse le résultat en
finalisation ; relancer cette commande ne relance jamais le tirage. La consultation privée est
livrée en phase 6. Voir le [guide opérateur](docs/runbooks/draw-recovery.md) et la
[qualification phase 5](docs/qualification/phase-5.md). L'archivage/purge et la sauvegarde
indépendante de production restent à qualifier en phase 10.

## Phase 6 — mon cadeau à préparer

Depuis le coffre, ouvrir « Mon cadeau à préparer » puis révéler explicitement l'attribution.
L'espace affiche seulement ta personne tirée, ses trois souhaits et les recherches adaptées à
**ton** pays. Choix, note personnelle et avancement restent privés et chiffrés ; l'organisateur
reçoit un total de personnes prêtes, jamais les cadeaux ou avancements individuels.

Si la liste change, la référence choisie reste conservée pour comparaison. L'achat se fait
chez le marchand, à recevoir chez toi puis apporter au réveillon. La clôture permet encore la
lecture, sans modifier la préparation. Voir la [qualification phase 6](docs/qualification/phase-6.md)
et le [guide de clés/rotation](docs/runbooks/private-keys.md). Les adaptateurs de notification sont livrés en phase 7 ; Mailpit reste la simulation locale
par défaut tant que les paramètres et preuves externes ne sont pas fournis.

## Phase 7 — notifications et rappels

Le coffre met en queue des messages individuels neutres dans une outbox chiffrée, avec baux,
reprises bornées, idempotence et faits fournisseur. Le portail a sa propre queue de connexion.
Le worker propose des rappels à 18:00 dans le fuseau du réveillon, activés explicitement après
confirmation des dates ; chaque membre peut désactiver les facultatifs. Les changements de
souhaits produisent un digest groupé quotidien, jamais une alerte ciblée dévoilant l'acheteur.

Resend est disponible avec vérification des webhooks et réconciliation. Zoho EU SMTP est aussi
supporté à ta demande, en gardant la boîte info@gestionatech.de ; une soumission SMTP n'est
pas présentée comme une livraison vérifiée. La reprise de ses paramètres depuis gtech et
l'essai réel attendent le chemin du fichier .env, que tu fourniras plus tard. Aucun secret
n'a été copié, email externe envoyé, domaine connecté ou service déployé pendant cette phase.

Voir le [guide de configuration/reprise](docs/runbooks/notifications.md) et la
[qualification de phase 7](docs/qualification/phase-7.md). Le domaine fourni
sweetfamily.gestionatech.de reste à configurer au déploiement. Les interfaces complètes sont
la phase 8 ; l'indépendance et la qualification de production restent conditionnelles.


## Phase 8 — interfaces et cas de vie

Le portail propose création, participants, règles, exclusions, confirmations, lancement,
progression publique, renvois, annulation, clôture et export CSV protégé contre les formules.
Le transfert d’organisation exige un code et un second facteur récents des deux comptes ;
le destinataire accepte et le groupe reçoit un avis neutre. Les accès privés ne changent pas.
La prochaine édition reprend un brouillon public, de nouveaux UUID et des exclusions remappées,
sans consentement, invitation, attribution ou achat repris.

Le coffre dispose des formulaires de profil, souhaits, règles, retrait, boutique et rappels,
d’un guide d’aide et de la préparation privée. Le masquage retire le contenu sensible du DOM
par bouton, Échap ou sortie d’onglet. Enregistrer avant de quitter l’écran. Une erreur réseau
conserve la saisie dans la page sans stockage persistant ni confirmation de succès.

Commandes manuelles : `python scripts/tasks.py test-e2e` et
`python scripts/tasks.py check-accessibility` exécutent la même recette Chromium + Axe,
sur des bases PostgreSQL jetables et données synthétiques. Installer le navigateur natif
avec `$env:PLAYWRIGHT_BROWSERS_PATH='C:\noel\.local\pw-browsers'; npx --prefix frontend playwright install chromium`
après `npm --prefix frontend ci`. Aucun fichier de pipeline n’est nécessaire.
Les captures et rapports sont ignorés dans `.local/ui-results` et exclus de la production.
Voir [qualification de phase 8](docs/qualification/phase-8.md).

L’archivage avec purge et résumé non personnel reste lié à la conservation de phase 10 :
l’interface explique le recours à l’opérateur et n’annonce aucune suppression déjà effectuée.
Les essais sur téléphone réel, lecteur d’écran, passkey matérielle et la recette Zoho différée
restent à qualifier avant l’ouverture réelle.


## Phase 9 — qualification et critères de sortie

`python scripts/tasks.py qualify` rejoue les checks, audits, distributions, tests complets,
parcours Chromium, charge HTTP et trois tirages de 20 membres. Il crée un run unique sous
`.local/qualification` : JUnit racine et suites imbriquées, mesures sans contenu privé, journaux,
hash des sources et hashes des preuves. Les tests forcent Mailpit. Aucun pipeline n’est ajouté.

`python scripts/tasks.py verify-release` vérifie que ces preuves correspondent encore au code,
puis refuse la mise en service si les conditions essentielles restent ouvertes. Un succès des
commandes de test ne signifie pas que le produit est qualifié pour la production. Le gate exige
encore les travaux/opérations de phase 10 et les recettes externes/assistives indépendantes.

Le rapport [report.md](docs/qualification/report.md) et la [matrice T01–T26](docs/qualification/matrix.md)
distinguent PASS_LOCAL, PARTIAL et BLOCKED. Ils photographient le run nommé dans le rapport ;
un nouveau run écrit de nouvelles preuves JSON, sans réécrire automatiquement ces documents.
Voir aussi [confidentialité](docs/qualification/privacy-review.md),
[méthode de mesure](docs/qualification/performance-method.md) et
[recettes encore nécessaires](docs/qualification/manual-gates.md).

Le test de charge initial a révélé un coût important de nouvelles connexions PostgreSQL sous
Windows. La réutilisation WSGI est maintenant bornée à 60 secondes, avec health checks et essai
de reconnexion après terminaison de backends d’une base de test. Les résultats, y compris tout
dépassement de la cible p95 de 500 ms, restent visibles dans le rapport ; aucune capacité de
l’hôte de production proposé n’est déduite des mesures locales.

## Phase 10 — conservation et exploitation locale

`python scripts/tasks.py backup-drill` exerce une vraie restauration par rôle, la repurge
d'un événement supprimé après le backup, la suppression de compte et la rétention des envois.
Initialiser les registres opérateur avant toute nouvelle confirmation de durabilité :

```powershell
python scripts/noel_operator.py operations-init --role control
python scripts/noel_operator.py operations-init --role vault
```

Le registre doit rester indépendant de l'ancien backup restauré. Les nouvelles commandes
opérateur couvrent maintenance, purge à J+90, vérification, backup chiffré, restauration vers
une nouvelle base isolée, reprise, expiration des archives à 30 jours et supervision agrégée.
Le web/worker restauré doit démarrer avec `FORCE_MAINTENANCE=true` jusqu'à récupération vérifiée.

Voir [exploitation](docs/runbooks/operations.md), [restauration](docs/runbooks/restore.md),
[incident](docs/runbooks/incident.md), [déploiement et remise](docs/runbooks/deployment.md),
[guide organisateur](docs/user-guides/organizer.md) et [guide participant](docs/user-guides/participant.md).
Aucun déploiement, DNS, email réel ou qualification de l'indépendance n'est effectué par ces commandes.
