# Qualification de phase 5

Date : 15 novembre 2026. Windows x64, PostgreSQL 17.12, Django 5.2.19, cryptography 50.0.2.
Exécution native et manuelle, sans Docker, GitHub Actions ou pipeline.

## Livraison

Moteur de couplage parfait uniforme exact pour 4–20 personnes, exclusions dirigées et refus
conditionnel des attributions forcées. La programmation dynamique utilise des entiers Python
et secrets.randbelow. Les cycles de deux sont possibles ; aucun cycle unique n'est imposé.
Les comptes restent en mémoire ; aucune graine, trace des choix ou empreinte de permutation.

Manifeste public complet, sans emails, confirmé individuellement dans le coffre. Les règles,
pays, noms ou exclusions modifiés avant calcul invalident tous les consentements. Les numéros
de manifeste ne sont jamais réutilisés. Une modification des frais exige aussi de revalider
les souhaits. Après calcul, le nom est gelé ; le pays peut évoluer sans changer l'attribution.

Un seul DrawJob par événement ; calcul hors transaction, bail/tentative monotone, snapshot
vérifié et scellement atomique. Le résultat AES-GCM possède une clé de données aléatoire
enveloppée sous une clé maîtresse indépendante. Les avis sont créés HELD, sans association.

La confirmation opérateur produit réellement une archive PostgreSQL chiffrée, la relit,
la déchiffre et la restaure dans une base neuve isolée, sans app ni worker. Les octets scellés,
clés enveloppées, schéma et manifeste restaurés doivent correspondre avant AVAILABLE.
Le reçu ne contient qu'une empreinte de l'archive chiffrée, jamais celle de la permutation.
Une erreur garde PENDING_DURABILITY ; la commande de backup ne recalcule pas de résultat.

## Contrôles exécutés

| Contrôle | Résultat local |
|---|---|
| Migrations des deux services, synchronisation des états/versions publics | PASS |
| Tous les 4 096 graphes dirigés à quatre personnes | PASS : comptes, supports et confidentialité conditionnelle comparés aux permutations de référence |
| Hypothesis, 35 graphes de quatre à huit personnes | PASS : comparaison indépendante, y compris graphes sans couplage |
| Comptes de dérangements exacts, quatre à huit et vingt personnes | PASS |
| Probabilité de chaque chemin avec fractions exactes | PASS : chaque couplage complet reçoit 1/count ; contrôle des tickets pondérés |
| Configuration forcée, exclusions impossibles, groupes hors 4–20 | PASS : refus avant création d'un résultat |
| Groupe de vingt, sans exclusion | PASS : échantillonnage mesuré à 4,472 s sur cette machine ; budget worker 60 s |
| Manifeste sans emails/souhaits, consentement exact, nouveau numéro après modification | PASS |
| Accès personnel, étranger, authentification, CSRF et payload fermé | PASS |
| Vingt requêtes simultanées, même commande et commandes distinctes | PASS : un seul job/résultat ; reçu idempotent |
| Deux workers, bail expiré, ancienne tentative et snapshot modifié | PASS : seul le propriétaire courant peut sceller |
| Résultat invalide, interruption avant commit, réponse perdue après commit | PASS : rollback complet ou reprise du même ciphertext, aucun second tirage |
| Chiffrement intègre, clé indépendante, absence de champs d'attribution en clair | PASS |
| Retrait sous quatre personnes, annulation pendant/après calcul | PASS : blocage ou annulation globale ; ciphertext conservé |
| Réouverture opérateur FAILED_FINAL | PASS : seulement sans résultat ; consentements supprimés |
| Backup indisponible puis vrai pg_dump/pg_restore chiffré | PASS : résultat retenu en échec, puis vérification avant libération et quatre avis neutres |
| Confirmation de durabilité répétée et clôture | PASS : aucun nouvel avis, clôture seulement après AVAILABLE |
| Suites de service sur bases jetables | PASS : 8 cas portail ; 19 identité + 43 souhaits + 16 tirage dans le coffre |
| test-unit / test-privacy | PASS : 46 et 24 tests racine, suites avec recouvrement |
| test-integration | PASS : 8 tests racine ; le smoke de transport étendu est qualifié séparément ci-dessous |
| test-draw, dernière passe | PASS : 18 tests racine, dont les deux runners de service ; 80,52 s |
| Smoke HTTP/processus de phase 5 | PASS : 58,29 s, résultat retenu et projection FINALIZING |
| check | PASS : Ruff/formatage, TypeScript, assets, Django et migrations synchronisées |
| check-security | PASS : scan secrets, audits Python/npm et checks Django stricts |
| build-prod / build-test / check-prod-artifact | PASS ; archives finales rafraîchies à la livraison |

Les nombres des suites de service sont imbriqués dans les runners racine, pas des scénarios
supplémentaires à additionner. Les données sont synthétiques et les boîtes en .invalid.

Le smoke étendu réutilise le vrai login email/MFA de l'organisateur et la vraie inscription
SMTP du premier membre. Trois autres identités/listes sont préparées comme fixtures explicites.
Les quatre consentements passent ensuite par le vrai HTTP avec sessions de fixtures et CSRF ;
la demande portail traverse le vrai transport signé, le processus worker scelle, puis sa
projection publie DRAWN/FINALIZING. Cette recette n'est pas quatre parcours de login indépendants.

Les premières passes ont révélé des problèmes de fixtures (sélection d'un membre d'un autre
groupe, répertoire temporaire Windows de l'ancienne session et reprise des cookies de test).
Les fixtures sont maintenant isolées par événement et leurs fichiers restent sous .local.
Le helper TOTP produit un code du compteur courant, plutôt que du bord antérieur de tolérance,
pour éviter un échec de test lorsqu'une requête traverse une frontière de période. Aucun bypass
TOTP n'a été ajouté à l'application.

## Portée et limites

Aucun véritable groupe familial, achat, attribution affichée ou email externe. La lecture privée,
les achats, migration des souhaits vers enveloppes et rotation des clés restent en phase 6.
Le fournisseur email réel et sa réconciliation restent en phase 7 ; interfaces complètes et
accessibilité en phase 8. La clôture est livrée, l'archivage/purge reste en phase 10.

La copie chiffrée locale et sa restauration effective ne démontrent pas la survie à la perte
de la machine ni la restauration indépendante des clés. La sauvegarde hors machine, la rétention,
la procédure de restauration avec registre de suppression, l'alerte/supervision et l'indépendance
réelle de l'opérateur sont à qualifier en phase 10. La commande de durabilité en échec retourne
un code d'échec neutre ; aucune supervision de production n'est revendiquée.
La confidentialité conditionnelle ne couvre ni coalitions ni informations externes.

## Références

- [Contrats](../api-contracts.md), [ADR-0007](../adr/0007-tirage-exact-et-durabilite.md).
- [Guide de reprise](../runbooks/draw-recovery.md).
- [Django : verrouillage select_for_update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).
- [PyCA : AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
