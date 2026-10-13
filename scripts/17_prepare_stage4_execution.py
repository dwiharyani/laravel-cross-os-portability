#!/usr/bin/env python3

import csv
import json
import re
import sys
from pathlib import Path


ASSIGNMENT = Path(
    "data/interim/stage4_two_person_execution_assignment_921.csv"
)

RUNTIME_EVIDENCE = Path(
    "data/interim/stage4_php_runtime_evidence_921.csv"
)

STUDY_DEFAULT_PHP = "8.2"

OS_MATRIX = [
    {
        "os": "linux",
        "runner": "ubuntu-22.04",
    },
    {
        "os": "windows",
        "runner": "windows-2022",
    },
    {
        "os": "macos",
        "runner": "macos-15",
    },
]


# ================================================================
# PHP VERSION RESOLUTION
# ================================================================

def normalize_php_version(value):
    """
    Convert a version-like value into major.minor.

    Examples:
        8.2       -> 8.2
        8.2.4     -> 8.2
        ^8.2      -> 8.2
        >=8.1     -> 8.1
    """

    if not value:
        return None

    m = re.search(
        r"\b(7|8)\.(\d+)(?:\.\d+)?\b",
        str(value)
    )

    if not m:
        return None

    return f"{m.group(1)}.{m.group(2)}"


def resolve_from_constraint(constraint):
    """
    Infer a requested PHP runtime from composer.php.

    IMPORTANT:
    This is recorded as an INFERENCE, not as explicit
    runtime evidence.

    Examples:
        ^8.2              -> 8.2
        ^7.3|^8.0         -> 8.0
        ^8.2|^8.3|^8.4   -> 8.4
        >=5.6.4           -> 5.6.4 cannot be used by this resolver,
                             therefore fallback is used.
    """

    if not constraint:
        return None

    versions = []

    for m in re.finditer(
        r"(?:^|[\s|,=~><^*])"
        r"((?:7|8)\.\d+)(?:\.\d+)?",
        constraint,
    ):
        try:
            major, minor = m.group(1).split(".")
            versions.append(
                (int(major), int(minor))
            )
        except Exception:
            continue

    if not versions:
        return None

    # Use the highest explicitly declared 7.x/8.x minor.
    major, minor = max(versions)

    return f"{major}.{minor}"


def load_runtime_evidence():
    """
    Load the 921-repository runtime evidence audit.

    The audit is AUXILIARY information.
    It NEVER determines sampling eligibility.
    """

    if not RUNTIME_EVIDENCE.exists():
        return {}

    with RUNTIME_EVIDENCE.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:
        rows = list(csv.DictReader(f))

    return {
        r["repo_full_name"]: r
        for r in rows
        if r.get("repo_full_name")
    }


def choose_php(row, runtime_evidence):
    """
    Resolve execution PHP while NEVER excluding a repository.

    Priority:

    1. Runtime evidence audit with a resolved runtime.
    2. Explicit/inferred composer.php constraint.
    3. Study default PHP 8.2.

    Every resolution path is recorded in the matrix.
    """

    repo = row["repo_full_name"]

    evidence = runtime_evidence.get(repo)

    # ------------------------------------------------------------
    # 1. Runtime evidence
    # ------------------------------------------------------------

    if evidence:

        runtime = (
            evidence.get("php_runtime") or ""
        ).strip()

        status = (
            evidence.get("runtime_status") or ""
        ).strip()

        if runtime and status == "RESOLVED":
            return {
                "php_runtime_requested": runtime,
                "php_runtime_resolution": "RUNTIME_EVIDENCE",
                "php_runtime_source": (
                    evidence.get("runtime_source") or ""
                ),
                "php_runtime_confidence": (
                    evidence.get("runtime_confidence") or "HIGH"
                ),
                "php_runtime_audit_status": status,
            }

    # ------------------------------------------------------------
    # 2. Composer constraint
    # ------------------------------------------------------------

    constraint = (
        row.get("php_version_constraint") or ""
    ).strip()

    inferred = resolve_from_constraint(constraint)

    if inferred:
        return {
            "php_runtime_requested": inferred,
            "php_runtime_resolution": (
                "COMPOSER_CONSTRAINT_INFERRED"
            ),
            "php_runtime_source": (
                "composer.json require.php"
            ),
            "php_runtime_confidence": "MEDIUM",
            "php_runtime_audit_status": (
                evidence.get("runtime_status", "")
                if evidence else ""
            ),
        }

    # ------------------------------------------------------------
    # 3. Study default
    # ------------------------------------------------------------

    return {
        "php_runtime_requested": STUDY_DEFAULT_PHP,
        "php_runtime_resolution": "STUDY_DEFAULT",
        "php_runtime_source": (
            "study_protocol_default"
        ),
        "php_runtime_confidence": "LOW",
        "php_runtime_audit_status": (
            evidence.get("runtime_status", "")
            if evidence else ""
        ),
    }


# ================================================================
# MAIN
# ================================================================

def main():

    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/17_prepare_stage4_execution.py A01"
        )

    batch = sys.argv[1]

    if not ASSIGNMENT.exists():
        raise FileNotFoundError(
            f"Missing assignment file: {ASSIGNMENT}"
        )

    with ASSIGNMENT.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:
        rows = list(csv.DictReader(f))

    runtime_evidence = load_runtime_evidence()

    required = [
        "execution_id",
        "execution_owner",
        "execution_batch",
        "repo_full_name",
        "project_id",
        "docker_status",
        "popularity_quartile",
        "stars_github",
        "forks_count",
        "latest_sha",
        "default_branch",
        "url",
        "php_version_constraint",
        "laravel_version_constraint",
    ]

    missing_columns = [
        c for c in required
        if c not in rows[0]
    ]

    if missing_columns:
        raise RuntimeError(
            "Missing assignment columns: "
            + ", ".join(missing_columns)
        )

    batch_rows = [
        r for r in rows
        if r["execution_batch"] == batch
    ]

    if not batch_rows:
        raise RuntimeError(
            f"No repositories found for batch {batch}"
        )

    include = []

    resolution_counts = {}

    # ============================================================
    # Every repository stays in the matrix.
    # ============================================================

    for row in batch_rows:

        php = choose_php(
            row,
            runtime_evidence
        )

        resolution = php[
            "php_runtime_resolution"
        ]

        resolution_counts[resolution] = (
            resolution_counts.get(resolution, 0) + 1
        )

        for os_cfg in OS_MATRIX:

            execution = {
                # ------------------------------------------------
                # Execution identity
                # ------------------------------------------------

                "execution_id": row[
                    "execution_id"
                ],

                "execution_owner": row[
                    "execution_owner"
                ],

                "execution_batch": row[
                    "execution_batch"
                ],

                "project_id": row[
                    "project_id"
                ],

                "repo_full_name": row[
                    "repo_full_name"
                ],

                # ------------------------------------------------
                # Repository
                # ------------------------------------------------

                "url": row["url"],

                "latest_sha": row[
                    "latest_sha"
                ],

                "default_branch": row[
                    "default_branch"
                ],

                # ------------------------------------------------
                # Sampling
                # ------------------------------------------------

                "stars_github": row[
                    "stars_github"
                ],

                "forks_count": row[
                    "forks_count"
                ],

                "popularity_score": row.get(
                    "popularity_score",
                    ""
                ),

                "popularity_quartile": row[
                    "popularity_quartile"
                ],

                "docker_status": row[
                    "docker_status"
                ],

                # ------------------------------------------------
                # Laravel / PHP
                # ------------------------------------------------

                "laravel_version_constraint": row[
                    "laravel_version_constraint"
                ],

                "php_version_constraint": row[
                    "php_version_constraint"
                ],

                "php_runtime_requested": php[
                    "php_runtime_requested"
                ],

                "php_runtime_resolution": php[
                    "php_runtime_resolution"
                ],

                "php_runtime_source": php[
                    "php_runtime_source"
                ],

                "php_runtime_confidence": php[
                    "php_runtime_confidence"
                ],

                "php_runtime_audit_status": php[
                    "php_runtime_audit_status"
                ],

                # ------------------------------------------------
                # OS
                # ------------------------------------------------

                "os": os_cfg["os"],

                "runner": os_cfg[
                    "runner"
                ],

                # ------------------------------------------------
                # Existing repository metadata
                # ------------------------------------------------

                "tests_directory_present": row.get(
                    "tests_directory_present",
                    ""
                ),

                "phpunit_config_present": row.get(
                    "phpunit_config_present",
                    ""
                ),

                "composer_json_present": row.get(
                    "composer_json_present",
                    ""
                ),

                "composer_lock_present": row.get(
                    "composer_lock_present",
                    ""
                ),

                "composer_test_script_present": row.get(
                    "composer_test_script_present",
                    ""
                ),

                "composer_test_scripts": row.get(
                    "composer_test_scripts",
                    ""
                ),

                "test_command_declared": row.get(
                    "composer_test_scripts",
                    ""
                ),

                # ------------------------------------------------
                # Execution placeholders
                # These will be filled by GitHub Actions.
                # ------------------------------------------------

                "clone_status": "",

                "checkout_status": "",

                "composer_validate_status": "",

                "composer_install_status": "",

                "composer_install_duration": "",

                "platform_check_status": "",

                "environment_preparation_status": "",

                "database_preparation_status": "",

                "test_discovery_status": "",

                "test_execution_status": "",

                "exit_code": "",

                "duration_seconds": "",

                "tests_passed": "",

                "tests_failed": "",

                "tests_skipped": "",

                "tests_errors": "",

                # ------------------------------------------------
                # Failure fields
                # ------------------------------------------------

                "failure_present": "",

                "failure_stage": "",

                "failure_category": "",

                "failure_subcategory": "",

                "failure_os_specific": "",

                "failure_message": "",

                "failure_error_type": "",

                "failure_command": "",

                "failure_exit_code": "",

                "failure_raw_output": "",

                "failure_raw_stderr": "",

                "failure_log_path": "",

                # ------------------------------------------------
                # Environment
                # ------------------------------------------------

                "os_name": "",

                "os_version": "",

                "kernel_version": "",

                "architecture": "",

                "php_version_actual": "",

                "php_extensions": "",

                "composer_version": "",

                "git_version": "",

                "node_version": "",

                "npm_version": "",

                # ------------------------------------------------
                # Application
                # ------------------------------------------------

                "artisan_present": "",

                "env_example_present": "",

                "env_created": "",

                "app_key_generation_status": "",

                "config_clear_status": "",

                # ------------------------------------------------
                # Final status
                # ------------------------------------------------

                "reproducibility_status": "",

                "cross_os_comparable": "",

                "execution_complete": "",

                "artifact_complete": "",

            }

            include.append(execution)

    # ============================================================
    # Validate matrix
    # ============================================================

    expected = len(batch_rows) * 3

    assert len(include) == expected

    assert len({
        x["execution_id"]
        for x in include
    }) == len(batch_rows)

    os_counts = {}

    for x in include:
        os_counts[x["os"]] = (
            os_counts.get(x["os"], 0) + 1
        )

    import contextlib

    # Diagnostic output must go to stderr.
    # stdout is reserved exclusively for the JSON matrix consumed
    # by GitHub Actions.
    with contextlib.redirect_stdout(sys.stderr):

        print("=" * 70)
        print("STAGE 4 EXECUTION MATRIX")
        print("=" * 70)

        print("Batch:", batch)
        print("Repositories:", len(batch_rows))
        print("OS executions:", len(include))

        print()
        print("OS distribution:")

        for os_name, count in sorted(
            os_counts.items()
        ):
            print(
                f"  {os_name}: {count}"
            )

        print()
        print("PHP resolution:")

        for key, value in sorted(
            resolution_counts.items()
        ):
            print(
                f"  {key}: {value}"
            )


    # ============================================================
    # IMPORTANT:
    # JSON output is consumed by GitHub Actions.
    # ============================================================

    print()
    print(json.dumps(
        {
            "include": include
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
