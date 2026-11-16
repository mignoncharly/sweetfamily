# ADR-0002 — Socle et contrats minimaux

Date : 15 novembre 2026. Statut : retenu pour la conception ; versions exactes à vérifier en phase 2.

## Contexte et décision

Suivre le socle du plan : Python 3.13, Django 5.2 LTS, django-allauth pour email/MFA, PostgreSQL 17, templates Django, CSS local et TypeScript léger ; cryptography pour les enveloppes AES-256-GCM. Ne pas inventer de protocole d'authentification ou de primitive cryptographique. Les correctifs compatibles et versions/images exactes seront vérifiés puis verrouillés lors de l'installation ; ce document ne prétend pas les avoir vérifiés aujourd'hui.

Deux configurations, bases, comptes SQL, migrations, cookies, secrets, images et déploiements séparés. Partage limité aux contrats, validations non sensibles et styles. Workers et outbox durables dans PostgreSQL avec baux ; Resend réel en production et recette autorisée, Mailpit uniquement local, aucun envoi réel en CI. Local, staging synthétique et production explicitement identifiés ; diagnostics de tirage fictif absents des images de production.

Contrats fermés et versionnés selon [permissions](../permissions.md), refus des champs inconnus, signatures/nonce/fraîcheur/idempotence, erreurs minimisées. Construire les assets localement, sans analytics ou CDN tiers au coffre.

## Alternatives et conséquences

Un monolithe avec modèles communs faciliterait les fuites et empêcherait l'exploitation indépendante. Une queue mémoire perdrait les tâches après panne. Un écran simulant des envois ne prouverait pas la livraison. Le coût assumé est une exploitation de deux services et des intégrations réelles à qualifier. Cibles : OPS-01, API-01, T17, T23, C11.
