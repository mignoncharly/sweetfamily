import os
import secrets
import subprocess

import pytest
import tasks


@pytest.mark.integration
@pytest.mark.parametrize("role", tasks.ROLES)
def test_phase3_service_cases_on_disposable_postgres(role):
    run_service_cases(role)


def run_service_cases(role, case_files=None):
    import psycopg
    from psycopg import sql

    name = "noel_phase3_test_" + secrets.token_hex(6)
    values = tasks.config()
    with psycopg.connect(
        host="127.0.0.1",
        port=tasks.DB_PORTS[role],
        dbname="postgres",
        user="noel_admin",
        password=values[f"{role.upper()}_DB_ADMIN_PASSWORD"],
        autocommit=True,
    ) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(name), sql.Identifier(f"noel_{role}")
            )
        )
        try:
            env = tasks.environment(role) | {"DB_NAME": name}
            env["PYTHONPATH"] = os.pathsep.join(
                [str(tasks.ROOT / "scripts"), str(tasks.ROOT / "tests/cases"), env["PYTHONPATH"]]
            )
            for args in (["migrate", "--noinput"], ["bind_environment"]):
                result = subprocess.run(
                    [str(tasks.PYTHON), str(tasks.ROOT / "services" / role / "manage.py"), *args],
                    env=env,
                    cwd=tasks.ROOT,
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, result.stderr
            report_args = []
            if os.environ.get("NOEL_QUALIFICATION_DIR"):
                from pathlib import Path

                report = Path(os.environ["NOEL_QUALIFICATION_DIR"]).resolve()
                assert report.is_relative_to(tasks.LOCAL.resolve())
                report.mkdir(parents=True, exist_ok=True)
                label = (
                    "browser"
                    if case_files and any("browser" in case for case in case_files)
                    else "service"
                )
                report_args = ["--junitxml=" + str(report / f"{label}-{role}.xml")]
            result = subprocess.run(
                [
                    str(tasks.PYTHON),
                    "-m",
                    "pytest",
                    *report_args,
                    "-q",
                    *(
                        case_files
                        or [
                            f"tests/cases/{role}_cases.py",
                            "tests/cases/delivery_cases.py",
                            "tests/cases/operations_cases.py",
                            *(
                                [
                                    "tests/cases/wishlist_cases.py",
                                    "tests/cases/draw_cases.py",
                                    "tests/cases/private_cases.py",
                                    "tests/cases/notification_cases.py",
                                    "tests/cases/participant_cases.py",
                                    "tests/cases/qualification_cases.py",
                                ]
                                if role == "vault"
                                else ["tests/cases/portal_cases.py"]
                            ),
                        ]
                    ),
                    "--tb=short",
                ],
                env=env,
                cwd=tasks.ROOT,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + "\n" + result.stderr
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
