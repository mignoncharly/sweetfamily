import json

import pytest
import qualify
import tasks


def test_unexecuted_qualification_never_becomes_pass():
    matrix = qualify.matrix([])
    assert matrix["T01"]["status"] == "BLOCKED"
    assert matrix["T20"]["status"] == "BLOCKED"
    assert matrix["T23"]["status"] == "BLOCKED"
    assert matrix["T01"]["missing"]


def test_failure_cannot_be_hidden_by_manual_qualification_condition():
    row = qualify.matrix(
        [
            {
                "test": "browser-vault.xml::test_browser",
                "status": "FAILED",
                "evidence": "browser-vault.xml",
            }
        ]
    )["T22"]
    assert row["status"] == "FAILED"


def test_test_facts_read_real_pass_fail_skip_outcomes(tmp_path):
    (tmp_path / "root.xml").write_text(
        '<testsuite><testcase classname="a" name="pass"/>'
        '<testcase classname="a" name="failure"><failure/></testcase>'
        '<testcase name="skip"><skipped/></testcase></testsuite>'
    )
    assert [row["status"] for row in qualify.test_facts(tmp_path)] == ["PASS", "FAILED", "BLOCKED"]


def test_release_gate_rejects_changed_evidence_and_never_approves_production(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "LOCAL", tmp_path)
    monkeypatch.setattr(qualify, "source_digest", lambda: "snapshot")
    root = tmp_path / "qualification"
    directory = root / "run"
    directory.mkdir(parents=True)
    evidence = directory / "root.xml"
    evidence.write_text("synthetic evidence")
    result = {
        "source_sha256": "snapshot",
        "local_status": "PASS",
        "release_blockers": [],
        "evidence_sha256": {"root.xml": qualify.sha(evidence)},
    }
    path = directory / "result.json"
    path.write_text(json.dumps(result))
    (root / "latest.json").write_text(
        json.dumps({"run": "run", "report_sha256": qualify.sha(path)})
    )
    with pytest.raises(tasks.Blocked, match="Phase 10"):
        qualify.verify_release()
    evidence.write_text("modified")
    with pytest.raises(tasks.Blocked, match="changed evidence"):
        qualify.verify_release()
    path.write_text("modified")
    with pytest.raises(tasks.Blocked, match="report changed"):
        qualify.verify_release()


def test_release_gate_cli_reports_blocked_without_traceback():
    import subprocess

    result = subprocess.run(
        [str(tasks.PYTHON), "scripts/tasks.py", "verify-release"],
        cwd=tasks.ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stderr
    assert "BLOCKED:" in result.stderr and "Traceback" not in result.stderr
