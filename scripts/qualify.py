"""Manual phase-9 evidence collector. Successful local checks never imply release approval."""

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import tasks

# Select actual executed test names, not prose assertions of coverage.
SCENARIOS = {
    "T01": ["test_T01_eight_fr_de_members", "test_real_local_web_worker_and_mailpit_processes"],
    "T02": [
        "test_real_local_web_worker_and_mailpit_processes",
        "test_each_member_only_receives_own_assignment",
    ],
    "T03": ["test_T03_small_group_refused"],
    "T04": [
        "test_forced_edge_and_fully_excluded_group_are_rejected",
        "test_incomplete_lists_and_privacy_violating_exclusions_cannot_freeze",
    ],
    "T05": [
        "test_exact_integer_budget_rejects_bad_amount",
        "test_validation_requires_exactly_three",
    ],
    "T06": ["test_invitation_get_has_no_side_effect_and_interception_cannot_claim"],
    "T07": [
        "test_foreign_session_service_credentials_and_csrf_are_rejected",
        "test_nonowner_and_service_credential_cannot_read_wishes",
    ],
    "T08": ["test_twenty_simultaneous_same_signed_requests_and_two_workers"],
    "T09": ["test_stale_lease_cannot_seal_and_attempts_increase"],
    "T10": [
        "test_atomic_failure_never_leaves_partial_result_or_outbox",
        "test_retry_after_commit_does_not_reroll_even_if_worker_loses_reply",
    ],
    "T11": [
        "test_crash_after_provider_acceptance_retries_same_logical_message",
        "test_reconciliation_reads_provider_fact_and_never_resends",
    ],
    "T12": [
        "test_forged_stale_modified_and_conflicting_webhooks_rejected",
        "test_real_sdk_verifies_raw_signature_deduplicates_and_preserves_delivered_fact",
    ],
    "T13": [
        "test_get_never_marks_reveal_and_page_requires_explicit_post",
        "test_T21_availability_is_safe_get",
    ],
    "T14": ["test_purchase_ciphertext_and_history_comparison_survive_wishlist_edit"],
    "T15": [
        "test_real_local_web_worker_and_mailpit_processes",
        "test_ready_projection_only_has_aggregate_and_reveal_boolean",
        "test_html_creation_idempotent_bound_errors_and_csv_formula",
        "test_logs_omit_payloads_and_exceptions",
    ],
    "T16": [
        "test_bad_urls_rejected_without_fetch",
        "test_private_html_escapes_notes_and_keeps_title_neutral",
    ],
    "T17": [
        "test_nested_diagnostic_route_refused",
        "test_invalid_configuration_refused",
        "test_private_process_refuses_debugger_in_nonlocal_mode",
    ],
    "T18": [
        "test_real_encrypted_native_backup_restores_before_release_and_is_idempotent",
        "test_reconciliation_reads_provider_fact_and_never_resends",
        "test_native_restore_repurges_deleted_event_preserves_sealed_draw_and_holds_mail",
    ],
    "T19": [
        "test_withdrawal_under_four_blocks_freeze_and_withdrawal_during_draw_cancels_everyone",
        "test_cancel_sealed_preserves_ciphertext_and_reopen_is_for_unsealed_failure_only",
    ],
    "T20": [
        "test_native_restore_repurges_deleted_event_preserves_sealed_draw_and_holds_mail",
        "test_deletion_journal_survives_database_rollback_and_prevents_recreation",
    ],
    "T21": [
        "test_T21_availability_is_safe_get_and_cancellation_blocks_old_session",
        "browser-vault.xml::",
    ],
    "T22": ["browser-control.xml::", "browser-vault.xml::"],
    "T23": [],
    "T24": [
        "test_claimed_email_cannot_be_changed_by_signed_organizer",
        "test_rule_changes_invalidate_all_consents_and_never_reuse_manifest_version",
    ],
    "T25": [
        "test_scheduler_skips_obsolete_or_unneeded_jobs",
        "test_stale_inflight_reminder_cannot_restart_after_dates_changed",
    ],
    "T26": [
        "test_pending_durability_cancelled_and_archived_reject_reads_and_writes",
        "test_real_encrypted_native_backup_restores_before_release_and_is_idempotent",
    ],
}
CONDITIONAL = {
    "T22": (
        "PARTIAL",
        (
            "Automated Chromium/Axe/keyboard/reflow only; real phone, assistive technology "
            "and manual zoom review not executed."
        ),
    ),
    "T23": (
        "BLOCKED",
        (
            "Live Zoho/Resend delivery deferred by user. Configure secrets locally, verify "
            "authorised sender domain and run staging_mail probe to authorised inbox, "
            "retaining delivery facts."
        ),
    ),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest():
    digest = hashlib.sha256()
    for folder in ("services", "scripts", "tests", "packages", "frontend", "infra"):
        for path in sorted((tasks.ROOT / folder).rglob("*")):
            if any(
                part in {"node_modules", "__pycache__", "staticfiles", "dist"}
                for part in path.parts
            ):
                continue
            if path.is_file() and path.suffix in {".py", ".ts", ".css", ".html", ".mjs", ".json"}:
                digest.update(path.relative_to(tasks.ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    for name in ("pyproject.toml", "uv.lock", ".env.example", "Makefile"):
        digest.update(name.encode())
        digest.update((tasks.ROOT / name).read_bytes())
    return digest.hexdigest()


def test_facts(directory):
    facts = []
    for path in sorted(Path(directory).glob("*.xml")):
        for case in ET.parse(path).iter("testcase"):
            status = (
                "FAILED"
                if case.find("failure") is not None or case.find("error") is not None
                else "BLOCKED"
                if case.find("skipped") is not None
                else "PASS"
            )
            facts.append(
                {
                    "test": path.name
                    + "::"
                    + case.get("classname", "")
                    + "."
                    + case.get("name", ""),
                    "status": status,
                    "evidence": path.name,
                }
            )
    return facts


def matrix(facts):
    result = {}
    for scenario, selectors in SCENARIOS.items():
        matched = [
            fact for fact in facts if any(selector in fact["test"] for selector in selectors)
        ]
        missing = [
            selector
            for selector in selectors
            if not any(selector in fact["test"] for fact in facts)
        ]
        status = (
            "FAILED"
            if any(fact["status"] == "FAILED" for fact in matched)
            else "BLOCKED"
            if missing or not matched or any(fact["status"] == "BLOCKED" for fact in matched)
            else "PASS_LOCAL"
        )
        reason = "" if not missing else "Unexecuted selectors: " + ", ".join(missing)
        if scenario in CONDITIONAL and status != "FAILED":
            override, note = CONDITIONAL[scenario]
            status = override if not missing else "BLOCKED"
            reason = (reason + " " + note).strip()
        result[scenario] = {
            "status": status,
            "reason": reason,
            "missing": missing,
            "tests": matched,
        }
    return result


def verify_release():
    pointer = json.loads((tasks.LOCAL / "qualification/latest.json").read_text())
    directory = (tasks.LOCAL / "qualification" / pointer["run"]).resolve()
    if directory.parent != (tasks.LOCAL / "qualification").resolve():
        raise tasks.Blocked("Invalid evidence path")
    path = directory / "result.json"
    if sha(path) != pointer["report_sha256"]:
        raise tasks.Blocked("Evidence report changed")
    report = json.loads(path.read_text())
    if report["source_sha256"] != source_digest():
        raise tasks.Blocked("Source changed; run qualify again")
    for name, expected in report["evidence_sha256"].items():
        evidence = (directory / name).resolve()
        if evidence.parent != directory or not evidence.is_file() or sha(evidence) != expected:
            raise tasks.Blocked("Missing or changed evidence")
    blockers = report["release_blockers"]
    if report["local_status"] != "PASS" or blockers:
        raise tasks.Blocked(
            "Release not qualified: " + "; ".join(blockers or ["local checks failed"])
        )
    raise tasks.Blocked("Phase 10 operator deployment/recovery qualification still required")


def main():
    tasks.db_up()
    tasks.migrate()
    directory = (
        tasks.LOCAL
        / "qualification"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    )
    directory.mkdir(parents=True)
    env = os.environ.copy() | {
        "NOEL_TEST_MAILPIT": "true",
        "NOEL_HTTP_ONLY": "false",
        "NOEL_HTTP_PROFILE": "false",
        "NOEL_QUALIFICATION_DIR": str(directory),
    }
    source = source_digest()
    stages = []
    commands = [
        ("checks", [tasks.PYTHON, "scripts/tasks.py", "check"]),
        ("security", [tasks.PYTHON, "scripts/tasks.py", "check-security"]),
        ("artifacts", [tasks.PYTHON, "scripts/tasks.py", "build-prod"]),
        (
            "tests",
            [tasks.PYTHON, "-m", "pytest", "-q", "--junitxml=" + str(directory / "root.xml")],
        ),
        ("browser-load", [tasks.PYTHON, "scripts/tasks.py", "test-e2e"]),
        ("engine-timing", [tasks.PYTHON, "tests/engine_measurement.py", directory]),
    ]
    for name, args in commands:
        print("Qualification: " + name, flush=True)
        started = time.perf_counter()
        result = subprocess.run(
            [str(arg) for arg in args],
            cwd=tasks.ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            errors="replace",
        )
        (directory / (name + ".log")).write_text(
            result.stdout + "\n" + result.stderr, encoding="utf8"
        )
        stages.append(
            {
                "stage": name,
                "status": "PASS" if result.returncode == 0 else "FAILED",
                "returncode": result.returncode,
                "seconds": round(time.perf_counter() - started, 3),
            }
        )
        print(name + ": " + stages[-1]["status"], flush=True)
    scenarios = matrix(test_facts(directory))
    blockers = [
        key + ": " + row["reason"]
        for key, row in scenarios.items()
        if row["status"] != "PASS_LOCAL"
    ]
    blockers.append(
        "Independent security review and genuinely separated operator/domains/keys/"
        "recovery not demonstrated"
    )
    blockers.append(
        "Email-free enrollment: independent vault operator remains UNASSIGNED; "
        "synthetic verifier signatures do not establish independent production operation."
    )
    for name in ("http-control.json", "http-vault.json", "engine.json"):
        if not (directory / name).exists() or not json.loads((directory / name).read_text()).get(
            "target_met"
        ):
            blockers.append("Performance target missing or unmet: " + name)
    if source_digest() != source:
        blockers.append("Source changed while qualification was running")
    report = {
        "schema": 1,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "postgresql": tasks.run(
                [tasks.executable("postgres"), "--version"], capture_output=True, text=True
            ).stdout.strip(),
            "node": tasks.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
            "db_ports": tasks.DB_PORTS,
            "web_threads_per_process": tasks.WEB_THREADS,
            "web_processes": tasks.WEB_PROCESSES,
        },
        "created_at": datetime.now(UTC).isoformat(),
        "source_sha256": source,
        "local_status": "PASS"
        if all(stage["status"] == "PASS" for stage in stages)
        and all(row["status"] != "FAILED" and not row["missing"] for row in scenarios.values())
        and source_digest() == source
        else "FAILED",
        "release_status": "BLOCKED",
        "release_blockers": blockers,
        "stages": stages,
        "scenarios": scenarios,
        "evidence_sha256": {
            path.name: sha(path) for path in sorted(directory.iterdir()) if path.is_file()
        },
    }
    (directory / "result.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    pointer = {"run": directory.name, "report_sha256": sha(directory / "result.json")}
    (directory.parent / "latest.json").write_text(json.dumps(pointer, indent=2), encoding="utf8")
    print("Local qualification: " + report["local_status"] + "; release: BLOCKED", flush=True)
    print("Evidence: " + str(directory), flush=True)
    return 0 if report["local_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
