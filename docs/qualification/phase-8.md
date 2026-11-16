# Qualification de phase 8 — interfaces et cas de vie

Date : 16 novembre 2026, Europe/Berlin. Windows x64, PostgreSQL 17.12 natif,
Django 5.2.19, TypeScript, Playwright 1.65.1 / Chromium 159, Axe 4.14.0.
Exécution manuelle sans Docker, GitHub Actions, dépôt distant ni CI/CD.

## Périmètre livré

- Portail : accueil, création, propositions de participants, correction avant revendication,
  dates/fuseau/frais/consigne, exclusions, confirmation de groupe, déclenchement sans animation
  d’attribution, progression publique et indisponibilité, renvois neutres, annulation, clôture.
- CSV : allowlist explicite du suivi public, cellules de formule neutralisées, aucune lecture
  de souhait, attribution, choix d’achat ou note. Le titre et le nom du fichier restent neutres.
- Coffre : profil, listes et conflits de révision, consentement, attente, préférences, retrait,
  demande de boutique et aide aux cas de vie. Les dates de rendez-vous respectent le fuseau affiché.
- Révélation explicite puis masquage par bouton/Échap, sortie de page/onglet et retour bfcache ;
  contenu privé retiré du DOM, réponse tardive ignorée après masquage. Aucun stockage persistant.
- Erreur réseau/délai/HTTP5xx : saisie et identifiant de demande conservés dans la page ; aucun
  succès supposé. Session expirée : lien de reconnexion séparé et renouvellement du seul CSRF.
  Les versions obsolètes restent des conflits à résoudre, sans écrasement silencieux.
- Transfert du seul rôle d’organisation : deux comptes vérifiés/MFA et réauthentification de
  moins de cinq minutes ; acceptation du destinataire, commande signée persistée et avis neutre
  atomique au groupe. Un résultat réseau inconnu garde la réservation et la même commande.
  Aucun transfert pendant un tirage en cours, aucune attribution ni identité du coffre modifiée.
- Copie annuelle : règles publiques, propositions actives, nouveaux UUID et exclusions remappées.
  Aucun résultat, état de liste, consentement, invitation ou achat repris. Nouvelles dates à choisir.

## Résultats exécutés

| Contrôle | Résultat |
|---|---|
| test-unit | PASS : 51 tests racine, 8 d’intégration exclus |
| test-integration | PASS : 8 tests racine ; inclut suites de service, processus HTTP/worker/SMTP et vraie restauration native du tirage |
| Cas ciblés phase 8 | PASS : formulaires, idempotence, CSV, copie annuelle, transfert/reprise, profils et préparation en conflit, avis de propriétaire et exclusions copiées |
| test-privacy | PASS : 29 tests racine, avec recouvrement entre suites |
| test-e2e | PASS : deux rôles dans Chromium natif, bases PostgreSQL jetables et sessions synthétiques |
| Axe WCAG 2 A/AA, 2.1 A/AA, 2.2 AA | PASS : 11 scans portail et 21 scans coffre, aucune violation signalée dans les écrans scannés |
| Responsive | PASS : 360, 390, 768, 1440 CSS pixels, texte long et prénoms accentués, absence de débordement horizontal ; reflow équivalent 200 % à 720 CSS pixels |
| Clavier | PASS automatisé : accès direct au contenu avec focus effectif, formulaires, focus d’erreur et masquage Échap avec retour au bouton de révélation |
| Erreurs dans Chromium | PASS : réseau indisponible, vraie absence de session puis reprise, règles modifiées depuis une seconde fenêtre, souhaits modifiés depuis une seconde fenêtre, note privée conservée après panne |
| Vérification visuelle | Captures portail et espace privé à 390 pixels inspectées ; cartes et actions lisibles, sans pied fixe masquant les champs |
| check | PASS : Ruff/formatage, TypeScript, assets, checks Django et absence de migrations manquantes |
| check-security | PASS : scan source/secrets, pip-audit, npm audit et checks Django stricts |
| build-prod / build-test / check-prod-artifact | PASS : distributions séparées, assets et module de formulaires public présents ; aucun test, secret ou service étranger en production |

Les comptes sont synthétiques. Les fixtures navigateur ne contournent aucun endpoint de production :
elles créent les sessions hors serveur, dans une base jetable, puis les vrais middleware et CSRF
s’appliquent aux requêtes du navigateur. La libération du tirage de cette fixture utilise une preuve
explicitement simulée ; le test d’intégration séparé vérifie réellement pg_dump/pg_restore et la
barrière de durabilité. Les nombres de tests imbriqués ne s’additionnent pas aux tests racine.
`check-accessibility` utilise le même runner que `test-e2e`, ce n’est pas une seconde preuve indépendante.

## Corrections issues de la recette

Le lien d’évitement reçoit désormais le focus. Les contrôles nommés action masquaient la propriété
DOM form.action : la soumission lit maintenant l’attribut explicitement. Les conflits conservent
ancienne révision, choix, état et note. Les reprises d’ouverture/correction reconstruisent la bonne
forme d’appel tout en gardant la commande initiale.

Chromium envoie Origin:null pour une navigation POST sous no-referrer. Les formulaires métier
privés utilisent fetch same-origin avec le CSRF standard ; les pages de connexion/invitation et
l’accueil neutre utilisent Referrer-Policy:same-origin, sans transmission vers un tiers. Les pages
cadeau/liste/API gardent no-referrer. Aucun Origin:null n’est approuvé et CSRF reste actif. Les
soumissions métier et le masquage nécessitent JavaScript ; une information est affichée sans JS.

## Limites et suites prévues

Aucune conformité WCAG globale n’est annoncée sur la base d’Axe. Un lecteur d’écran (NVDA/VoiceOver),
un téléphone réel avec clavier logiciel, le zoom manuel du navigateur, les contrastes et parcours
assistifs complets restent à qualifier en phase 9. Les captures simulées et le reflow ne les remplacent pas.
Les captures et rapports sont ignorés dans `.local/ui-results` et exclus de production.

L’archivage qui ne conserve qu’un résumé non personnel exige la purge et sa politique de sauvegardes :
il reste en phase 10. Le parcours de conservation explique le recours à l’opérateur et ne prétend pas
avoir supprimé les données. Aucun état ARCHIVED artificiel gardant toutes les données privées n’est ajouté.

La recette externe Zoho/Resend et la remise à info@gestionatech.de sont différées à la demande de
l’utilisateur. Aucun secret gtech n’a été copié, aucun email réel ni changement DNS ou déploiement
n’a été effectué. L’indépendance et la qualification de production restent non démontrées.
