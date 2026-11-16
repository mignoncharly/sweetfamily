# Matrice T01–T26 — requalification de phase 10

Run : `20261116T105107Z-7d6abc4f`. PASS_LOCAL vaut uniquement pour le périmètre exécuté.
Les fonctions listées sont retrouvées dans les preuves JUnit du run ; les cas paramétrés sont inclus.
Un critère partiel ou bloqué ne devient pas PASS parce que ses sous-tests locaux passent.

| ID | Scénario | Statut | Cas exécutés / condition |
|---|---|---|---|
| T01 | Huit membres FR/DE, bijection | **PASS_LOCAL** | `test_T01_eight_fr_de_members`<br>`test_real_local_web_worker_and_mailpit_processes` |
| T02 | Organisateur participant | **PASS_LOCAL** | `test_real_local_web_worker_and_mailpit_processes`<br>`test_each_member_only_receives_own_assignment` |
| T03 | Groupe de deux/trois | **PASS_LOCAL** | `test_T03_small_group_refused` |
| T04 | Exclusions impossibles/déductibles | **PASS_LOCAL** | `test_forced_edge_and_fully_excluded_group_are_rejected`<br>`test_incomplete_lists_and_privacy_violating_exclusions_cannot_freeze` |
| T05 | Budget et trois souhaits | **PASS_LOCAL** | `test_exact_integer_budget_rejects_bad_amount`<br>`test_validation_requires_exactly_three` |
| T06 | Invitation volée sans boîte | **PASS_LOCAL** | `test_invitation_get_has_no_side_effect_and_interception_cannot_claim` |
| T07 | Accès entre personnes/événements | **PASS_LOCAL** | `test_foreign_session_service_credentials_and_csrf_are_rejected`<br>`test_nonowner_and_service_credential_cannot_read_wishes` |
| T08 | Vingt lancements concurrents | **PASS_LOCAL** | `test_twenty_simultaneous_same_signed_requests_and_two_workers` |
| T09 | Deux workers et bail ancien | **PASS_LOCAL** | `test_stale_lease_cannot_seal_and_attempts_increase` |
| T10 | Crash avant/après commit | **PASS_LOCAL** | `test_atomic_failure_never_leaves_partial_result_or_outbox`<br>`test_retry_after_commit_does_not_reroll_even_if_worker_loses_reply` |
| T11 | Acceptation puis timeout provider | **PASS_LOCAL** | `test_crash_after_provider_acceptance_retries_same_logical_message`<br>`test_reconciliation_reads_provider_fact_and_never_resends` |
| T12 | Webhooks falsifiés/répétés/retardés | **PASS_LOCAL** | `test_forged_stale_modified_and_conflicting_webhooks_rejected`<br>`test_real_sdk_verifies_raw_signature_deduplicates_and_preserves_delivered_fact` |
| T13 | GET/robot sans marqueur consulté | **PASS_LOCAL** | `test_get_never_marks_reveal_and_page_requires_explicit_post`<br>`test_T21_availability_is_safe_get` |
| T14 | Révision après tirage stable | **PASS_LOCAL** | `test_purchase_ciphertext_and_history_comparison_survive_wishlist_edit` |
| T15 | Portail/SQL/logs/CSV sans canari privé | **PASS_LOCAL** | `test_real_local_web_worker_and_mailpit_processes`<br>`test_ready_projection_only_has_aggregate_and_reveal_boolean`<br>`test_html_creation_idempotent_bound_errors_and_csv_formula`<br>`test_logs_omit_payloads_and_exceptions` |
| T16 | URL/note malveillante | **PASS_LOCAL** | `test_bad_urls_rejected_without_fetch`<br>`test_private_html_escapes_notes_and_keeps_title_neutral` |
| T17 | Diagnostics forcés en production | **PASS_LOCAL** | `test_nested_diagnostic_route_refused`<br>`test_invalid_configuration_refused`<br>`test_private_process_refuses_debugger_in_nonlocal_mode` |
| T18 | Restauration et replay opérationnel | **PASS_LOCAL** | `test_real_encrypted_native_backup_restores_before_release_and_is_idempotent`<br>`test_reconciliation_reads_provider_fact_and_never_resends`<br>`test_native_restore_repurges_deleted_event_preserves_sealed_draw_and_holds_mail` ; maintenance, clés restaurées, résultat inchangé, envois retenus et dispatcher sans renvoi. |
| T19 | Retrait avant/après tirage | **PASS_LOCAL** | `test_withdrawal_under_four_blocks_freeze_and_withdrawal_during_draw_cancels_everyone`<br>`test_cancel_sealed_preserves_ciphertext_and_reopen_is_for_unsealed_failure_only` |
| T20 | Purge puis ancien backup | **PASS_LOCAL** | `test_native_restore_repurges_deleted_event_preserves_sealed_draw_and_holds_mail`<br>`test_deletion_journal_survives_database_rollback_and_prevents_recreation` ; registre externe, pg_restore réel, suppression d'événement et compte réappliquées avant reprise. |
| T21 | Ancien onglet après annulation | **PASS_LOCAL** | `test_T21_availability_is_safe_get_and_cancellation_blocks_old_session`<br>`browser-vault.xml::` |
| T22 | Mobile/clavier/lecteur/zoom | **PARTIAL** | `browser-control.xml::`<br>`browser-vault.xml::`<br>Automated Chromium/Axe/keyboard/reflow only; real phone, assistive technology and manual zoom review not executed. |
| T23 | Boîtes et expéditeur réels | **BLOCKED** | <br>Live Zoho/Resend delivery deferred by user. Configure secrets locally, verify authorised sender domain and run staging_mail probe to authorised inbox, retaining delivery facts. |
| T24 | Portail modifiant roster/email | **PASS_LOCAL** | `test_claimed_email_cannot_be_changed_by_signed_organizer`<br>`test_rule_changes_invalidate_all_consents_and_never_reuse_manifest_version` |
| T25 | Rappel obsolète/panne/annulation | **PASS_LOCAL** | `test_scheduler_skips_obsolete_or_unneeded_jobs`<br>`test_stale_inflight_reminder_cannot_restart_after_dates_changed` |
| T26 | Scellement sans backup confirmé | **PASS_LOCAL** | `test_pending_durability_cancelled_and_archived_reject_reads_and_writes`<br>`test_real_encrypted_native_backup_restores_before_release_and_is_idempotent` |

Le PASS_LOCAL de T15 s’appuie sur le dump complet du portail et les contrôles de champs/permissions,
sans qualifier les sauvegardes/comptes réels de production. T17 inclut l’inspection des distributions.
T18/T20 qualifient la reprise et repurge locales ; stockage indépendant, copies externes,
réconciliation réelle du fournisseur et RPO/RTO restent des conditions de production.
T21 n’affirme pas faire oublier ce qui a été vu. T22 ne constitue pas une conformité WCAG globale.
T23 n’a envoyé aucun message réel. PERF-01 et IND-01 sont des critères ouverts supplémentaires.

Voir [report.md](report.md), [requirements.md](requirements.md) et [manual-gates.md](manual-gates.md).
