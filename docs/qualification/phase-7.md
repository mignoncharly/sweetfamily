# Qualification de phase 7

Date : 15 novembre 2026. Windows x64, PostgreSQL 17.12, Django 5.2.19, Resend SDK 2.53.2.
Code livré et vérifié localement, en exécution native sans Docker, GitHub Actions ou CI/CD.
**La recette email externe est différée à la demande de l'utilisateur.**

## Livraison

NotificationOutbox est le proxy métier de PendingMail, pour conserver la base et les FK des
phases précédentes. La table contient clés métier uniques, payloads chiffrés, baux, tentatives,
HMAC de contenu, fingerprint secret de transport et états techniques minimaux. AuthMail est
séparée dans le portail pour ses codes, avec un worker propre. La création d'avis est atomique
avec le gel, scellement ou annulation ; le tirage crée maintenant une vraie outbox HELD et sa
libération durable ouvre ces mêmes lignes, sans nouveau résultat.

Resend est intégré par HTTPS borné sans redirection, clé d'idempotence stable et corps figé.
Le SDK officiel vérifie corps brut/timestamp/signature des webhooks. Les reçus minimaux sont
persistés avant ACK et les faits de livraison restent distincts, sans régression d'une remise
confirmée vers acceptation. Les erreurs brutes, adresses, corps, ouvertures et clics ne sont pas
conservés. Les reprises sont bornées et expirent avant la fenêtre fournisseur ; la réconciliation
ne renvoie aucun courrier. Un nouveau credential ne permet pas une reprise cachée dans un autre compte.

Zoho EU SMTP TLS est aussi implémenté, à la demande de l'utilisateur. Sa réponse positive est
SUBMITTED, pas DELIVERED. Une ambiguïté ou mort du worker pendant SMTP donne DELIVERY_UNKNOWN
sans nouvelle tentative automatique. Message-ID stable n'est pas présenté comme déduplication.
La clé et les valeurs SMTP gtech n'étant pas encore disponibles, aucun essai externe n'est effectué.

Rappels explicites J-7/J-2 des listes et J-7/J-1 du réveillon, à 18:00 locale, préférences
personnelles, versions et utilité sont revérifiés. Les anciens jobs sont invalidés après changement
de date ; les tâches expirées après panne sont ignorées. Les changements de souhaits après tirage
produisent seulement un digest quotidien neutre au groupe. Les avis contiennent les liens du
coffre et des consignes générales, jamais une attribution, un souhait, une note ou un achat.

## Résultats locaux

| Contrôle | Résultat |
|---|---|
| Migrations des deux services et rattachement de métadonnées historiques | PASS |
| Déclenchement unique, corps/sender immuables et credential différent | PASS : absence de nouvelle soumission cachée |
| Deux workers, bail, crash après acceptation et reprise Resend | PASS avec fournisseur simulé : même message logique, une seule réservation de bail |
| Expiration de code, cinq tentatives et fenêtre 23 h 55 | PASS : aucun vieux code soumis, inconnu honnête au-delà de la fenêtre |
| Erreurs permanentes, timeout ambigu, HTTP429/Retry-After | PASS : bornes et classification testées, sans réponse brute journalisée |
| HTTPS fixe, timeout et refus de redirection | PASS |
| Vraie vérification SDK de signatures fraîches | PASS : corps modifié, signature forgée, timestamp périmé refusés |
| Webhooks dupliqués, conflit de corps, désordre et ACK perdu | PASS : faits commités et dédupliqués, DELIVERED non écrasé par ACCEPTED |
| Reçu avant réponse d'envoi / avant association locale | PASS : rapprochement par provider_id ou tag opaque |
| Réconciliation manuelle et automatique | PASS : lectures uniquement ; un ID inconnu nécessite un tag prouvant la notification |
| SMTP Zoho EU : TLS/hôte/adresse limités et ACK neutre | PASS simulé : un destinataire, SUBMITTED uniquement |
| SMTP Zoho ambigu ou worker mort | PASS : aucun second envoi automatique, état inconnu |
| Suppression d'une ligne pendant I/O | PASS : ni résurrection ni renvoi |
| Activation explicite avec dates confirmées | PASS : aucun rappel par défaut, propositions visibles dans le portail |
| Calendrier local et transitions heure été/hiver Europe/Berlin | PASS |
| Préférence, retrait, liste terminée, version/date changée et panne longue | PASS : rappels devenus inutiles non envoyés |
| Tâche déjà en vol après changement de dates | PASS : ancienne version ne redémarre pas un rappel |
| Deux ordonnanceurs | PASS : une seule ligne d'outbox pour la tâche |
| Digest quotidien au groupe | PASS : une échéance commune, ni propriétaire de changement ni acheteur dans le contenu |
| Renvoi idempotent et borné | PASS : même ciphertext scellé, aucun nouveau job de tirage |
| Annulation et changement d'email | PASS : révocation de travaux périmés et notices neutres |
| Préférences personnelles / CSRF / mode Simulation | PASS |
| Suites de service finales | PASS : 33 cas portail (8 + 25 livraison) ; 142 coffre (19 identité + 43 souhaits + 16 tirage + 22 privé + 25 livraison + 17 notifications) |
| test-integration | PASS : 8 tests racine en 250,11 s ; jeux de service imbriqués |
| Smoke processus/SMTP étendu | PASS : 59,22 s dans la passe ciblée ; code portail de sa vraie queue → worker → Mailpit → MFA, puis parcours coffre/durabilité/achat/projection |
| test-draw et suites de service | PASS : 18 tests racine ; régressions et moteurs des phases 3–7, complétés par les suites ciblées finales |
| test-unit | PASS : 51 tests racine, 8 d'intégration exclus |
| test-privacy | PASS : 29 tests racine, avec recouvrement entre suites |
| check | PASS : Ruff/formatage, TypeScript, assets, checks Django et migrations synchronisées |
| check-security | PASS : scan source et secrets locaux, pip-audit, npm audit et checks Django stricts |
| build-prod / build-test / check-prod-artifact | PASS : archives distinctes, sans tests/probe/secrets/service étranger en production |

Les nombres de service sont imbriqués dans les runners racine et ne s'additionnent pas comme
scénarios indépendants. Les derniers tests ciblés rejouent livraison/préférences sur des bases
jetables pour les deux rôles, après les corrections de versions/ambiguïtés. Toutes les données
sont synthétiques. Les SMTP de simulation et les fournisseurs HTTP simulés n'ont pas transmis
un message à une boîte réelle. Le probe explicite reste exclu des archives de production.

Le passage du code organisateur par SMTP a révélé que deux challenges (portail/coffre) pour
une même adresse synthétique pouvaient être confondus par le lecteur Mailpit du test. Les rôles
ont maintenant des expéditeurs de simulation distincts, et les lecteurs filtrent leur expéditeur.
Aucun contournement d'authentification n'a été ajouté. Les tests forcent Mailpit et retirent
les credentials réels, même si une future configuration Zoho/Resend est présente localement.

## Preuves externes différées

| Élément | État réel |
|---|---|
| Boîte autorisée | Fournie : info@gestionatech.de |
| Domaine souhaité | Fourni : sweetfamily.gestionatech.de ; aucun DNS/déploiement effectué |
| Source de configuration | gtech .env : chemin à fournir plus tard, demande explicite de l'utilisateur |
| Copie de mot de passe d'application | NON EFFECTUÉE ; aucune valeur trouvée/copée ou affichée |
| Authentification / soumission Zoho réelle | NON VÉRIFIÉE |
| Message reçu dans la boîte Zoho | NON VÉRIFIÉ |
| Domaine/API/webhook Resend réels | NON CONFIGURÉS / NON VÉRIFIÉS |
| SPF/DKIM/DMARC, tracking désactivé et rétention fournisseur | NON VÉRIFIÉS pour cette application |
| Comptes et infrastructure coffre indépendants | NON VALIDÉS en production ; phase 10 |

Zoho peut rester la boîte et le transport SMTP ; un compte Resend n'est pas nécessaire à ce
mode. Le suivi complet par webhook/idempotence fournisseur exige Resend ou un fournisseur aux
capacités équivalentes réellement configuré, et ne peut être déduit d'une acceptation SMTP.
La réutilisation demandée d'un même compte/app-password pour l'essai n'est pas une preuve
contre l'administrateur du portail : l'isolation de production devra être qualifiée séparément.

## Limites et suite

La phase 8 peut progresser sur les interfaces et cas de vie avec Mailpit. Les preuves ci-dessus
restent ouvertes jusqu'à réception du chemin de configuration et à la recette autorisée. Ne pas
présenter les emails réels comme opérationnels d'ici là. La planification de suppression prochaine
par la politique de purge, la rétention SQL/fournisseur, les alertes externes et la restauration
avec réconciliation sont en phase 10. Le texte de purge sait annoncer J+90 mais aucune purge
automatique n'est revendiquée. Le backend ne crée ni nouvel échange ni nouveau résultat pour
réparer une livraison, un bounce ou une enveloppe illisible.

## Références

- [Guide de configuration et reprise](../runbooks/notifications.md), [contrats API](../api-contracts.md).
- [ADR-0009](../adr/0009-notifications-et-faits-fournisseur.md).
- [Resend : fenêtre d'idempotence](https://resend.com/docs/dashboard/emails/idempotency-keys).
- [Resend : vérification webhook](https://resend.com/docs/webhooks/verify-webhooks-requests).
- [Resend : lecture de faits email](https://resend.com/docs/api-reference/emails/retrieve-email).
- [Zoho : SMTP](https://www.zoho.com/mail/help/zoho-smtp.html).
