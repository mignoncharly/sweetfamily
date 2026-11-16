# Notifications natives — phase 7

## Modes et preuve

Le mode par défaut est Mailpit local : « Simulation ». Il prouve une remise au serveur local,
jamais une livraison réelle. Le transport Resend et le transport Zoho EU sont implémentés,
mais aucun compte réel n'est déclaré opérationnel sans preuve externe.

Demande reçue pour cette installation : boîte Zoho info@gestionatech.de, domaine fourni
sweetfamily.gestionatech.de, réutilisation autorisée des paramètres email du projet gtech.
Le checkout trouvé C:/tmp/github-cleanup/repos/gtech ne contient pas de .env. L'utilisateur
fournira son chemin plus tard. Aucun mot de passe n'a été copié, aucun email réel envoyé,
aucune modification du projet gtech, DNS ou déploiement effectuée.

Les tests automatisés forcent Mailpit et retirent les credentials réels de leurs subprocessus,
même après configuration de l'opérateur. Les deux services emploient des expéditeurs de
simulation distincts : leurs codes d'authentification ne peuvent être confondus dans le smoke.

## Zoho EU sans déplacer la boîte

Zoho peut rester la boîte de réception habituelle. Le compte existant peut envoyer les messages
neutres via SMTP TLS si cet accès est autorisé ; cela reste à vérifier avec les paramètres gtech. Avec ce transport, une réponse positive prouve seulement l'acceptation
par le relais SMTP : le statut reste SUBMITTED. Il n'y a pas de webhook Resend à simuler pour
Zoho, ni de faux statut DELIVERED. Une coupure ambiguë ou un worker mort pendant SMTP donne
DELIVERY_UNKNOWN, sans nouvelle tentative automatique : Message-ID ne prouve pas une déduplication.
Un échec SMTP explicitement négatif et temporaire peut être repris avec délai et borne.

Quand le .env gtech sera disponible, copier uniquement ses paramètres SMTP autorisés dans le
.env ignoré de Noël, sans afficher le secret, sans copier ses autres clés et sans modifier gtech.
Les noms ci-dessous sont préfixés CONTROL_ ou VAULT_ dans le runner local :

| Variable de processus | Valeur / règle |
|---|---|
| MAIL_PROVIDER | zoho |
| MAIL_LIVE_ENABLED | true seulement après configuration explicite |
| SMTP_HOST | Le serveur EU indiqué par la configuration Zoho : smtp.zoho.eu ou smtppro.zoho.eu |
| SMTP_PORT / SMTP_USE_SSL / SMTP_USE_TLS | 465 / true / false, ou 587 / false / true |
| SMTP_USERNAME / SMTP_PASSWORD | Adresse complète et mot de passe d'application autorisés |
| NOTIFICATION_FROM_EMAIL | Adresse authentifiée ; pas d'alias non vérifié supposé |
| MAIL_TEST_RECIPIENTS | info@gestionatech.de pour cet essai autorisé |

Aucun port clair, certificat ignoré ou autre hôte SMTP n'est accepté par l'adaptateur Zoho.
Le domaine sweetfamily.gestionatech.de n'est pas automatiquement un alias d'expéditeur Zoho :
le rôle de ce domaine dans l'hébergement sera à confirmer au déploiement. Les origines locales
restent loopback jusqu'à cette étape. La boîte info@gestionatech.de peut recevoir l'essai,
indépendamment du domaine choisi pour l'application.

Le partage du même compte SMTP entre services est demandé pour l'essai local. Il ne prouve pas
la séparation de production contre l'administrateur du portail : conserver le coffre, son
identité d'envoi et ses accès sous un opérateur indépendant avant de revendiquer cette garantie.

## Resend avec une boîte Zoho conservée

Un compte Resend peut gérer seulement l'envoi transactionnel, tandis que les boîtes restent chez
Zoho. Utiliser un domaine/sous-domaine d'envoi dédié ; ajouter les enregistrements exacts retournés
par Resend pour ce domaine, sans remplacer les MX de réception Zoho à la racine. Ne pas activer
la réception Resend sur le domaine existant. Ne pas copier une valeur DNS d'exemple générique.
Vérifier SPF, DKIM et la politique DMARC réelle. Le coffre exige ses propres comptes et secrets.

Configurer, séparément par service : MAIL_PROVIDER=resend, RESEND_API_KEY, RESEND_DOMAIN_ID,
RESEND_WEBHOOK_SECRET, NOTIFICATION_FROM_EMAIL et MAIL_TEST_RECIPIENTS. Le webhook HTTPS est
POST /webhooks/resend sur l'origine du service concerné. Le secret du portail n'est pas celui
du coffre. Le fournisseur doit pouvoir joindre ce domaine ; un localhost ne constitue pas une
recette externe des webhooks.

Dans le dashboard/API de domaine Resend, désactiver open_tracking et click_tracking.
La commande native manage.py check_mail_provider vérifie le domaine, SPF/DKIM et ces deux
réglages via une lecture fournisseur ; elle n'envoie pas de message. Avec Zoho, elle vérifie
TLS et authentification sans envoi. DMARC, rétention fournisseur, absence de réécriture des
liens et une boîte de test autorisée restent à vérifier effectivement.
MAIL_DNS_VERIFIED=true et MAIL_TRACKING_DISABLED=true sont des confirmations de l'opérateur,
pas une preuve créée par le code. Sans les confirmations, la clé, le secret webhook et
MAIL_LIVE_ENABLED=true, Resend reste bloqué. En local/staging, l'adresse doit aussi être dans
MAIL_TEST_RECIPIENTS. Ne jamais coller de clé API ou mot de passe dans un ticket/conversation.

## Essai explicite, hors distribution de production

Le script opérateur de test n'est pas dans les archives de production. Une fois les paramètres
réels fournis et vérifiés, la commande suivante crée un unique message neutre autorisé, puis
affiche seulement son identifiant opaque et ses états techniques :

~~~powershell
python scripts/staging_mail.py --role vault --to info@gestionatech.de --confirm-authorised
python scripts/staging_mail.py --role vault --notification UUID_AFFICHE
~~~

Le premier ordre est un vrai envoi ; ne pas le répéter pour simplement consulter l'état.
Le second lit/réconcilie sans renvoyer. L'option --configured-environment utilise un environnement
staging explicitement fourni, avec le bon SERVICE_ROLE et PYTHONPATH, plutôt que le runner local.
Le script refuse la production. Le même parcours peut ensuite qualifier le portail séparément.
Ne jamais utiliser les adresses de vrais participants pour une recette.

Avec Zoho, vérifier le message dans la boîte autorisée et consigner la preuve sans recopier le
corps d'un code ou des headers sensibles. Le statut applicatif SMTP ne devient pas « livré »
par supposition. Avec Resend, vérifier acceptation, webhook de remise au serveur et arrivée dans
la boîte. « Livré » n'est ni lu ni forcément en boîte principale. Une recette de bounce doit être
identifiée comme simulation lorsqu'elle n'est pas une vraie réponse externe. Aucun pixel ne
marque la consultation du tirage ; seul le POST authentifié de l'application la marque.

## Reprise, inconnus et renvois

Chaque notification possède un identifiant durable, un HMAC secret du contenu et un fingerprint
secret du transport. Après une première tentative, changer le corps, l'expéditeur ou le compte
ne provoque jamais une réexpédition cachée. Une rotation de credential pendant un état ambigu
exige réconciliation ; ne pas changer de compte pour contourner la déduplication.

Les baux sont de 90 s, avec tentative monotone et vérification au commit. L'I/O est hors
transaction SQL, timeout 10 s. Les reprises sont bornées à cinq et utilisent backoff/Retry-After.
Resend reçoit la même clé SERVICE_ROLE/notification_uuid et le même corps. La rétention
fournisseur est de 24 h ; l'application arrête les tentatives à 23 h 55 pour garder une marge.
Au-delà, DELIVERY_UNKNOWN et réconciliation, jamais renvoi automatique en prétendant une
unicité garantie. Pour SMTP Zoho, aucune reprise après une ambiguïté, même dans les 24 heures.
Un code déjà expiré n'est jamais soumis au transport ; une arrivée tardive ne prolonge pas sa validité.

Les reçus de webhook vérifiés sont persistés avant ACK, dédupliqués par svix-id et HMAC de
corps, sans conserver corps, destinataires ou erreurs fournisseur. Des faits distincts sont
conservés pour acceptation, remise, report, rejet et échec. Une acceptation retardée ne remplace
pas une remise confirmée. Un webhook arrivé avant l'ACK d'envoi est réconcilié par l'identifiant
fournisseur ou le tag opaque de notification. Aucun fait d'ouverture/clic ne marque une révélation.

Le worker tente jusqu'à cinq lectures fournisseur pour les états à vérifier. Un opérateur peut
ensuite utiliser manage.py reconcile_mail NOTIFICATION_UUID [--provider-id UUID]. Fournir un
identifiant inconnu ne suffit pas : le tag Resend doit prouver qu'il appartient à cette notification.
La commande n'envoie aucun email et ne change pas un tirage. Avec SMTP, vérifier les traces du
relais/boîte et laisser l'état honnêtement inconnu sans inventer une API de réconciliation.

Un renvoi organisateur est une nouvelle notification neutre, sous MFA, version, signature et
idempotence ; au maximum trois par membre et heure, quarante par événement et heure.
Un renvoi d'invitation renouvelle seulement le token d'invitation non revendiquée. Un renvoi de
tirage exige AVAILABLE et réutilise strictement le même résultat. Un renvoi manuel après un
inconnu peut produire un doublon de courrier ; l'interface ne promet pas exactement une fois.

## Rappels et résumés

Aucun rappel automatique sans activation explicite par l'organisateur avec dates courantes
confirmées ; le participant peut désactiver les facultatifs. Les propositions sont J-7/J-2 de
l'échéance de liste et J-7/J-1 du réveillon, à 18:00 locale. Le calendrier utilise les dates
locales, pas des soustractions d'heures UTC à travers un changement d'heure. Après panne, les
jobs expirés sont ignorés ; état, membre, préférences, version et utilité sont revérifiés à la
mise en queue ET à l'envoi. Une modification des dates invalide les anciennes tâches.

Les modifications de souhaits après tirage programment un digest neutre au groupe, au plus une
fois par jour à 18:00, jamais un email ciblé vers l'acheteur ou un fait de changement individuel
au portail. Les avis de règles, tirage et annulation sont créés avec l'événement métier.
Le tirage possède une vraie outbox HELD jusqu'à confirmation de durabilité. Le texte de
suppression prochaine inclut la date annoncée J+90 ; son déclenchement par la politique de
purge sera intégré en phase 10, sans prétendre qu'une purge automatique existe déjà.

Les payloads de codes/tokens sont chiffrés puis purgés à succès, expiration ou état terminal.
Les données de rétention/suppression fournisseur, les alertes externes et la restauration avec
réconciliation restent à qualifier en phase 10. Ne pas restaurer une archive en redémarrant
immédiatement les workers : suspendre les envois jusqu'à réconciliation des reçus.

Sources officielles : [Zoho SMTP](https://www.zoho.com/mail/help/zoho-smtp.html),
[Resend et MX existants](https://resend.com/docs/knowledge-base/how-do-i-avoid-conflicting-with-my-mx-records),
[idempotence Resend](https://resend.com/docs/dashboard/emails/idempotency-keys),
[vérification webhook](https://resend.com/docs/webhooks/verify-webhooks-requests),
[domaine et tracking](https://resend.com/docs/api-reference/domains/get-domain).
