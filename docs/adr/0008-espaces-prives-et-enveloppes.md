# ADR-0008 — Espaces personnels et enveloppes métier

Statut : accepté pour la phase 6 locale, 15 novembre 2026.

Le navigateur accède directement au coffre. Les routes fixes recipient, recipient/reveal et
purchase déduisent le donneur depuis sa session et event_id, sans accepter d'identifiant d'autrui.
Le coffre verrouille l'événement pour sérialiser accès, annulation, édition des souhaits et achat.
Il valide le résultat scellé et sa disponibilité, puis renvoie une seule personne et trois souhaits.
Aucun endpoint inverse, extraction globale ou usurpation de participant.

GET ne marque pas de consultation ; seul POST explicite avec CSRF la marque. La page GET de
révélation n'affiche aucune attribution. URL et titre restent neutres, avec no-store/no-referrer,
CSP, anti-iframe et sans service worker ou analytique. CLOSED autorise lectures personnelles,
DRAWN les écritures d'achat ; CANCELLED/ARCHIVED et finalisation refusent les deux.

Une enveloppe EventDataKey protège souhaits et achats avec AES-256-GCM, nonce central unique
par clé et contexte lié au type, événement, propriétaire et révision. Le résultat garde la clé
par événement de phase 5. La rotation rewrappe les deux clés, sans changer associations ou contenu.
Les anciennes révisions v1 sont migrées transactionnellement ; leurs anciennes clés restent
nécessaires aux archives. Un fournisseur local implémente le contrat typé prévu pour un futur KMS.

PrivatePurchaseState ne conserve en clair que le membre propriétaire et la révision technique.
Choix de souhait, révision choisie, état et note sont tous chiffrés. Le choix est limité aux trois
souhaits de l'attribution autorisée. Une référence historique déjà choisie reste comparable après
modification ; un nouveau choix exige la version courante. Les corrections d'avancement sont
explicites, sans transition automatique qui promettrait une commande ou livraison réelle.

Le portail reçoit uniquement recipient_viewed et ready_count aux projections regroupées habituelles.
Aucune sauvegarde d'achat ou révélation ne force une projection individuelle immédiate.
Les valeurs READY/GIVEN contribuent au total, aucun état individuel d'achat n'est transmis.
Les erreurs d'intégrité restent neutres, créent une alerte locale et ne réinitialisent jamais le tirage.
L'indépendance humaine de l'infrastructure, OS/collecteurs de dumps, rétention et restauration
hors machine restent à qualifier avant production aux phases 9–10.
