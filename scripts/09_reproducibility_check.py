#!/usr/bin/env python3

"""
09_reproducibility_check.py

Stage 3 — Laravel reproducibility check.

Workflow:

    Frozen candidates
          |
    Select pilot
          |
    Clone repository
          |
    Checkout exact SHA
          |
    Inspect composer.json
          |
    Detect PHP extensions
          |
    Detect test command
          |
    Composer install
          |
    Prepare test environment
          |
    Prepare SQLite database
          |
    Run tests
          |
    Classify result
          |
    Export CSV / Excel / manifest

This script is intended to run both:

1. On HPC for inspection / baseline checks.
2. On GitHub Actions where PHP + Composer are available.

The script does NOT modify the frozen candidate dataset.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = (
    ROOT / "data/interim/cross_os_candidates.csv"
)

DEFAULT_PILOT = (
    ROOT / "data/interim/reproducibility_pilot20.csv"
)

DEFAULT_OUTPUT = (
    ROOT / "data/interim/reproducibility_results.csv"
)

DEFAULT_XLSX = (
    ROOT / "data/interim/reproducibility_results.xlsx"
)

DEFAULT_MANIFEST = (
    ROOT / "data/interim/reproducibility_results.manifest.json"
)

DEFAULT_WORKSPACE = (
    ROOT / "data/interim/reproducibility_workspace"
)


# ============================================================
# GENERAL UTILITIES
# ============================================================

def command_exists(command: str) -> bool:
    """
    Return True if command is available in PATH.
    """
    return shutil.which(command) is not None


def run_command(
    command,
    cwd=None,
    timeout=900,
):
    """
    Execute a command safely.

    Returns:
        return_code
        output
        duration_seconds
    """

    started = time.time()

    try:

        process = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )

        output = process.stdout or ""

        return (
            process.returncode,
            output[-12000:],
            round(time.time() - started, 2),
        )

    except subprocess.TimeoutExpired as exc:

        output = exc.stdout or ""

        if isinstance(output, bytes):
            output = output.decode(
                errors="replace"
            )

        return (
            124,
            str(output)[-12000:],
            round(time.time() - started, 2),
        )

    except Exception as exc:

        return (
            125,
            repr(exc),
            round(time.time() - started, 2),
        )


def sanitize_excel_value(value):
    """
    Remove XML control characters that openpyxl rejects.

    This prevents errors such as:

        openpyxl.utils.exceptions.IllegalCharacterError

    when PHPUnit/Laravel output contains control characters.
    """

    if value is None:
        return value

    if not isinstance(value, str):
        return value

    return re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        value,
    )


def sanitize_dataframe_for_excel(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Remove illegal Excel characters from all object columns.
    """

    dataframe = dataframe.copy()

    for column in dataframe.select_dtypes(
        include=["object"]
    ).columns:

        dataframe[column] = dataframe[
            column
        ].map(
            sanitize_excel_value
        )

    return dataframe


# ============================================================
# PILOT SELECTION
# ============================================================

def select_pilot(
    dataframe: pd.DataFrame,
    number: int = 20,
) -> pd.DataFrame:

    """
    Deterministic pilot selection.

    Priority:
        1. Cover environment groups.
        2. Fill remaining slots using higher-star repositories.

    This is only a reproducibility pilot.
    It is not the final Cross-OS sample.
    """

    df = dataframe.copy()

    df = df.drop_duplicates(
        subset=["repo_full_name"]
    ).reset_index(drop=True)

    if number <= 0:
        return df.iloc[0:0].copy()

    selected = []

    # --------------------------------------------------------
    # Environment coverage
    # --------------------------------------------------------

    if "environment_group" in df.columns:

        groups = (
            df[
                "environment_group"
            ]
            .fillna("UNKNOWN")
            .astype(str)
        )

        df = df.assign(
            _environment_group=groups
        )

        for _, group in df.groupby(
            "_environment_group",
            sort=True,
        ):

            if len(selected) >= number:
                break

            selected.append(
                group.iloc[0]
            )

        selected_repos = {
            row["repo_full_name"]
            for row in selected
        }

        remaining = df[
            ~df["repo_full_name"].isin(
                selected_repos
            )
        ].copy()

    else:

        remaining = df.copy()

    # --------------------------------------------------------
    # Fill remaining slots
    # --------------------------------------------------------

    if "stars" in remaining.columns:

        remaining["_stars_numeric"] = pd.to_numeric(
            remaining["stars"],
            errors="coerce",
        ).fillna(0)

        remaining = remaining.sort_values(
            [
                "_stars_numeric",
                "repo_full_name",
            ],
            ascending=[
                False,
                True,
            ],
        )

    else:

        remaining = remaining.sort_values(
            "repo_full_name"
        )

    for _, row in remaining.iterrows():

        if len(selected) >= number:
            break

        selected.append(row)

    if not selected:
        return df.iloc[0:0].copy()

    result = pd.DataFrame(
        selected
    ).drop(
        columns=[
            "_environment_group",
            "_stars_numeric",
        ],
        errors="ignore",
    )

    return result.reset_index(
        drop=True
    )


# ============================================================
# COMPOSER
# ============================================================

def load_composer_json(
    repository_directory: Path,
):

    composer_file = (
        repository_directory
        / "composer.json"
    )

    if not composer_file.exists():
        return None

    try:

        return json.loads(
            composer_file.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return None


def detect_php_extensions(
    repository_directory: Path,
):

    composer_data = load_composer_json(
        repository_directory
    )

    if composer_data is None:
        return ""

    requirements = composer_data.get(
        "require",
        {},
    )

    extensions = []

    for package_name in requirements:

        if str(
            package_name
        ).lower().startswith("ext-"):

            extensions.append(
                str(package_name)
            )

    return ", ".join(
        sorted(extensions)
    )


# ============================================================
# TEST COMMAND DETECTION
# ============================================================

def detect_test_command(
    repository_directory: Path,
):

    composer_data = load_composer_json(
        repository_directory
    )

    if composer_data is None:

        return (
            "",
            "composer.json missing",
        )

    scripts = composer_data.get(
        "scripts",
        {},
    )

    # --------------------------------------------------------
    # Explicit test scripts
    # --------------------------------------------------------

    preferred_scripts = [
        "test",
        "tests",
        "test:unit",
        "test:feature",
    ]

    for script_name in preferred_scripts:

        if script_name in scripts:

            value = scripts[
                script_name
            ]

            if isinstance(
                value,
                list,
            ):

                value = " && ".join(
                    str(x)
                    for x in value
                )

            return (
                f"composer run {script_name}",
                str(value),
            )

    # --------------------------------------------------------
    # Any script containing "test"
    # --------------------------------------------------------

    for script_name, value in scripts.items():

        if "test" in str(
            script_name
        ).lower():

            if isinstance(
                value,
                list,
            ):

                value = " && ".join(
                    str(x)
                    for x in value
                )

            return (
                f"composer run {script_name}",
                str(value),
            )

    # --------------------------------------------------------
    # PHPUnit binary
    # --------------------------------------------------------

    phpunit = (
        repository_directory
        / "vendor/bin/phpunit"
    )

    if phpunit.exists():

        return (
            "vendor/bin/phpunit",
            "vendor/bin/phpunit detected",
        )

    # --------------------------------------------------------
    # Pest binary
    # --------------------------------------------------------

    pest = (
        repository_directory
        / "vendor/bin/pest"
    )

    if pest.exists():

        return (
            "vendor/bin/pest",
            "vendor/bin/pest detected",
        )

    # --------------------------------------------------------
    # Artisan test
    # --------------------------------------------------------

    artisan = (
        repository_directory
        / "artisan"
    )

    if artisan.exists():

        return (
            "php artisan test",
            "artisan detected",
        )

    return (
        "",
        "No test command detected",
    )


# ============================================================
# STAGE 3 — TEST ENVIRONMENT PREPARATION
# ============================================================

def prepare_test_environment(
    repository_directory: Path,
):

    """
    Prepare a Laravel repository for test execution.

    This function intentionally avoids destructive changes.

    It performs common test-environment preparation:

        1. Create .env from .env.example when available.
        2. Ensure APP_KEY exists.
        3. Clear Laravel configuration/cache.
        4. Configure testing environment where possible.

    Returns:

        environment_ok
        environment_detail
    """

    details = []

    env_file = (
        repository_directory
        / ".env"
    )

    env_example = (
        repository_directory
        / ".env.example"
    )

    # --------------------------------------------------------
    # .env
    # --------------------------------------------------------

    if not env_file.exists():

        if env_example.exists():

            try:

                shutil.copy2(
                    env_example,
                    env_file,
                )

                details.append(
                    ".env created from .env.example"
                )

            except Exception as exc:

                return (
                    False,
                    "Failed to create .env: "
                    + repr(exc),
                )

        else:

            # Some repositories do not require .env.
            details.append(
                ".env.example not found"
            )

    else:

        details.append(
            ".env already exists"
        )

    # --------------------------------------------------------
    # APP_ENV
    # --------------------------------------------------------

    if env_file.exists():

        try:

            text = env_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

            if re.search(
                r"^APP_ENV=",
                text,
                flags=re.MULTILINE,
            ):

                text = re.sub(
                    r"^APP_ENV=.*$",
                    "APP_ENV=testing",
                    text,
                    flags=re.MULTILINE,
                )

            else:

                text += (
                    "\nAPP_ENV=testing\n"
                )

            env_file.write_text(
                text,
                encoding="utf-8",
            )

            details.append(
                "APP_ENV=testing"
            )

        except Exception as exc:

            details.append(
                "APP_ENV update skipped: "
                + repr(exc)
            )

    # --------------------------------------------------------
    # APP_KEY
    # --------------------------------------------------------

    if env_file.exists() and command_exists("php"):

        try:

            env_text = env_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

            app_key_match = re.search(
                r"^APP_KEY=(.*)$",
                env_text,
                flags=re.MULTILINE,
            )

            app_key = (
                app_key_match.group(1).strip()
                if app_key_match
                else ""
            )

            if not app_key:

                return_code, output, _ = (
                    run_command(
                        [
                            "php",
                            "artisan",
                            "key:generate",
                            "--force",
                        ],
                        cwd=repository_directory,
                        timeout=120,
                    )
                )

                if return_code == 0:

                    details.append(
                        "APP_KEY generated"
                    )

                else:

                    details.append(
                        "APP_KEY generation failed: "
                        + output
                    )

            else:

                details.append(
                    "APP_KEY already present"
                )

        except Exception as exc:

            details.append(
                "APP_KEY preparation skipped: "
                + repr(exc)
            )

    # --------------------------------------------------------
    # Laravel config clear
    # --------------------------------------------------------

    if (
        command_exists("php")
        and
        (
            repository_directory
            / "artisan"
        ).exists()
    ):

        return_code, output, _ = (
            run_command(
                [
                    "php",
                    "artisan",
                    "config:clear",
                ],
                cwd=repository_directory,
                timeout=120,
            )
        )

        if return_code == 0:

            details.append(
                "Laravel config cleared"
            )

        else:

            details.append(
                "Laravel config clear returned "
                f"{return_code}"
            )

    return (
        True,
        "; ".join(details),
    )


# ============================================================
# STAGE 3 — SQLITE DATABASE PREPARATION
# ============================================================

def prepare_sqlite_database(
    repository_directory: Path,
):

    """
    Prepare SQLite for Laravel tests when the repository
    already uses SQLite or can safely use SQLite for testing.

    This function does NOT overwrite an existing database.

    Returns:

        sqlite_ok
        sqlite_detail
    """

    database_directory = (
        repository_directory
        / "database"
    )

    database_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    sqlite_candidates = [
        database_directory
        / "database.sqlite",

        database_directory
        / "testing.sqlite",
    ]

    existing_sqlite = [
        path
        for path in sqlite_candidates
        if path.exists()
    ]

    details = []

    env_file = (
        repository_directory
        / ".env"
    )

    if env_file.exists():

        try:

            env_text = env_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

            # ------------------------------------------------
            # Detect existing SQLite configuration
            # ------------------------------------------------

            db_connection = re.search(
                r"^DB_CONNECTION=(.*)$",
                env_text,
                flags=re.MULTILINE,
            )

            connection = (
                db_connection.group(1).strip()
                if db_connection
                else ""
            )

            connection = connection.strip(
                "\"'"
            ).lower()

            # ------------------------------------------------
            # Existing sqlite database
            # ------------------------------------------------

            if existing_sqlite:

                details.append(
                    "SQLite database already exists"
                )

            elif connection == "sqlite":

                sqlite_file = (
                    database_directory
                    / "database.sqlite"
                )

                sqlite_file.touch(
                    exist_ok=True
                )

                details.append(
                    "SQLite database created"
                )

            else:

                # Do not force SQLite on repositories
                # explicitly configured for another database.
                details.append(
                    "Repository is not configured "
                    "for SQLite; existing database "
                    "configuration preserved"
                )

        except Exception as exc:

            return (
                False,
                "SQLite preparation failed: "
                + repr(exc),
            )

    else:

        details.append(
            ".env unavailable; SQLite not forced"
        )

    # --------------------------------------------------------
    # Laravel migrate for SQLite
    # --------------------------------------------------------

    if env_file.exists():

        try:

            env_text = env_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

            connection_match = re.search(
                r"^DB_CONNECTION=(.*)$",
                env_text,
                flags=re.MULTILINE,
            )

            connection = (
                connection_match.group(1).strip()
                if connection_match
                else ""
            )

            connection = connection.strip(
                "\"'"
            ).lower()

        except Exception:

            connection = ""

    else:

        connection = ""

    if (
        connection == "sqlite"
        and
        command_exists("php")
        and
        (
            repository_directory
            / "artisan"
        ).exists()
    ):

        return_code, output, _ = (
            run_command(
                [
                    "php",
                    "artisan",
                    "migrate",
                    "--force",
                ],
                cwd=repository_directory,
                timeout=300,
            )
        )

        if return_code == 0:

            details.append(
                "SQLite migrations completed"
            )

        else:

            # Migration failures should not immediately
            # be converted into a repository failure here.
            # The actual test run is the final evidence.
            details.append(
                "SQLite migration returned "
                f"{return_code}"
            )

    return (
        True,
        "; ".join(details),
    )


# ============================================================
# FAILURE CLASSIFICATION
# ============================================================

def classify_failure(
    output: str,
    stage: str = "test",
):

    text = (
        output or ""
    ).lower()

    # --------------------------------------------------------
    # Private package authentication
    # --------------------------------------------------------

    if any(
        phrase in text
        for phrase in [
            "authentication required",
            "could not authenticate",
            "private repository",
            "github token",
            "oauth token",
            "authentication.json",
        ]
    ):

        return (
            "PRIVATE_PACKAGE_AUTHENTICATION"
        )

    # --------------------------------------------------------
    # Invalid composer package
    # --------------------------------------------------------

    if (
        "invalid package name" in text
        or
        "invalid package names" in text
        or
        "package name" in text
        and "invalid" in text
    ):

        return (
            "INVALID_COMPOSER_PACKAGE_NAME"
        )

    # --------------------------------------------------------
    # Lockfile / PHP version
    # --------------------------------------------------------

    if (
        "lock file" in text
        and
        (
            "php version" in text
            or
            "requires php" in text
            or
            "does not satisfy" in text
        )
    ):

        return (
            "LOCKFILE_PHP_VERSION_MISMATCH"
        )

    if (
        "requires php" in text
        and
        "your php version" in text
    ):

        return (
            "LOCKFILE_PHP_VERSION_MISMATCH"
        )

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    if (
        "database.sqlite" in text
        and
        (
            "does not exist" in text
            or
            "sqlite" in text
        )
    ):

        return (
            "DATABASE_CONFIGURATION_OR_DATABASE_FAILURE"
        )

    if (
        "connection refused" in text
        and
        (
            "database" in text
            or
            "mysql" in text
            or
            "pgsql" in text
            or
            "sqlsrv" in text
        )
    ):

        return (
            "DATABASE_CONNECTION_REFUSED"
        )

    if (
        "sqlstate" in text
        or
        "queryexception" in text
    ):

        return (
            "DATABASE_CONFIGURATION_OR_DATABASE_FAILURE"
        )

    # --------------------------------------------------------
    # Cryptographic configuration
    # --------------------------------------------------------

    if (
        "supported ciphers" in text
        or
        "cipher" in text
        and
        "key length" in text
    ):

        return (
            "CRYPTOGRAPHIC_CONFIGURATION"
        )

    # --------------------------------------------------------
    # Application configuration
    # --------------------------------------------------------

    if any(
        phrase in text
        for phrase in [
            "undefined index",
            "undefined variable",
            "application configuration",
            "no application encryption key",
            "app_key",
            "application key",
            "class not found",
            "target class",
            "bootstrap",
            "environment file",
            "vite manifest not found",
            "configuration",
        ]
    ):

        if "bootstrap" in text:

            return (
                "APPLICATION_BOOTSTRAP_FAILURE"
            )

        return (
            "APPLICATION_CONFIGURATION"
        )

    # --------------------------------------------------------
    # Test command mismatch
    # --------------------------------------------------------

    if (
        "invalidpestcommand" in text
        or
        "please run [./vendor/bin/pest]" in text
    ):

        return (
            "TEST_COMMAND_MISMATCH"
        )

    # --------------------------------------------------------
    # Composer dependency
    # --------------------------------------------------------

    if (
        "composer" in text
        and
        (
            "dependency" in text
            or
            "could not resolve" in text
            or
            "install" in text
            or
            "memory" in text
        )
    ):

        return "COMPOSER"

    # --------------------------------------------------------
    # Test failure
    # --------------------------------------------------------

    if (
        "phpunit" in text
        or
        "pest" in text
        or
        "tests failed" in text
        or
        "failed tests" in text
        or
        "failure" in text
    ):

        return "TEST_FAILURE"

    # --------------------------------------------------------
    # Permission
    # --------------------------------------------------------

    if (
        "permission denied" in text
        or
        "operation not permitted" in text
    ):

        return "INFRASTRUCTURE"

    # --------------------------------------------------------
    # Network
    # --------------------------------------------------------

    if (
        "could not resolve host" in text
        or
        "network is unreachable" in text
        or
        "connection timed out" in text
    ):

        return "INFRASTRUCTURE"

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return "OTHER_TEST_FAILURE"


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run Stage 3 reproducibility "
            "checks on frozen Laravel candidates."
        )
    )

    parser.add_argument(
        "--input",
        default=str(
            DEFAULT_INPUT
        ),
    )

    parser.add_argument(
        "--pilot",
        default=str(
            DEFAULT_PILOT
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Run reproducibility check for one exact repository.",
    )

    parser.add_argument(
        "--workspace",
        default=str(
            DEFAULT_WORKSPACE
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
    )

    parser.add_argument(
        "--output",
        default=str(
            DEFAULT_OUTPUT
        ),
    )

    parser.add_argument(
        "--xlsx",
        default=str(
            DEFAULT_XLSX
        ),
    )

    parser.add_argument(
        "--manifest",
        default=str(
            DEFAULT_MANIFEST
        ),
    )

    parser.add_argument(
        "--skip-install",
        action="store_true",
        help=(
            "Inspect repositories only; "
            "do not run composer install or tests."
        ),
    )

    args = parser.parse_args()

    input_file = Path(
        args.input
    )

    pilot_file = Path(
        args.pilot
    )

    workspace = Path(
        args.workspace
    )

    output_file = Path(
        args.output
    )

    xlsx_file = Path(
        args.xlsx
    )

    manifest_file = Path(
        args.manifest
    )

    # ========================================================
    # CHECK INPUT
    # ========================================================

    if not input_file.exists():

        raise FileNotFoundError(
            f"Input file not found: {input_file}"
        )

    # ========================================================
    # LOAD CANDIDATES
    # ========================================================

    dataframe = pd.read_csv(
        input_file
    )

    dataframe = dataframe.drop_duplicates(
        subset=["repo_full_name"]
    ).reset_index(drop=True)

    # ========================================================
    # LOAD / CREATE PILOT
    # ========================================================

    if args.repo:

        repo_name = args.repo.strip()

        matches = dataframe[
            dataframe["repo_full_name"].astype(str).str.strip()
            == repo_name
        ].copy()

        if len(matches) == 0:

            raise ValueError(
                f"Repository not found in input dataset: "
                f"{repo_name}"
            )

        if len(matches) > 1:

            raise ValueError(
                f"Repository appears multiple times: "
                f"{repo_name}"
            )

        pilot = matches.reset_index(
            drop=True
        )

        print(
            f"Exact repository mode: {repo_name}"
        )

    elif pilot_file.exists():

        pilot = pd.read_csv(
            pilot_file
        )

    else:

        pilot = select_pilot(
            dataframe,
            args.limit,
        )

        pilot_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        pilot.to_csv(
            pilot_file,
            index=False,
        )

    if not args.repo and args.limit > 0:

        pilot = pilot.head(
            args.limit
        ).copy()

    # ========================================================
    # WORKSPACE
    # ========================================================

    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # ENVIRONMENT CHECK
    # ========================================================

    php_available = command_exists(
        "php"
    )

    composer_available = command_exists(
        "composer"
    )

    git_available = command_exists(
        "git"
    )

    print(
        "=" * 70
    )

    print(
        "REPRODUCIBILITY CHECK — STAGE 3"
    )

    print(
        "=" * 70
    )

    print(
        "Frozen candidates:",
        len(dataframe),
    )

    print(
        "Pilot repositories:",
        len(pilot),
    )

    print(
        "PHP available:",
        php_available,
    )

    print(
        "Composer available:",
        composer_available,
    )

    print(
        "Git available:",
        git_available,
    )

    print(
        "Timeout:",
        args.timeout,
        "seconds",
    )

    print(
        "Workspace:",
        workspace,
    )

    if not git_available:

        raise RuntimeError(
            "Git is required but was not found."
        )

    # ========================================================
    # RESULTS
    # ========================================================

    results = []

    # ========================================================
    # LOOP
    # ========================================================

    for index, row in pilot.iterrows():

        repo_full_name = str(
            row.get(
                "repo_full_name",
                "",
            )
        )

        url = str(
            row.get(
                "url",
                f"https://github.com/{repo_full_name}.git",
            )
        )

        latest_sha = str(
            row.get(
                "latest_sha",
                "",
            )
        )

        environment_group = str(
            row.get(
                "environment_group",
                "",
            )
        )

        php_constraint = str(
            row.get(
                "php_version_constraint",
                "",
            )
        )

        laravel_constraint = str(
            row.get(
                "laravel_version_constraint",
                "",
            )
        )

        result = {
            "repo_full_name": repo_full_name,
            "url": url,
            "latest_sha": latest_sha,
            "environment_group": environment_group,
            "php_version_constraint": php_constraint,
            "laravel_version_constraint": laravel_constraint,
            "clone_status": "",
            "checkout_status": "",
            "composer_json": False,
            "php_extensions": "",
            "test_command": "",
            "test_command_source": "",
            "php_available": php_available,
            "composer_available": composer_available,
            "composer_install": "",
            "test_environment_preparation": "",
            "sqlite_preparation": "",
            "test_execution": "",
            "failure_category": "",
            "failure_detail": "",
            "reproducibility_status": "",
            "tested_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        print()
        print(
            f"[{index + 1}/{len(pilot)}] "
            f"{repo_full_name}"
        )

        # ====================================================
        # REPOSITORY WORKSPACE
        # ====================================================

        safe_name = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            repo_full_name,
        )

        repository_directory = (
            workspace / safe_name
        )

        # ----------------------------------------------------
        # Remove previous clone
        # ----------------------------------------------------

        if repository_directory.exists():

            shutil.rmtree(
                repository_directory,
                ignore_errors=True,
            )

        # ====================================================
        # CLONE
        # ====================================================

        clone_code, clone_output, _ = (
            run_command(
                [
                    "git",
                    "clone",
                    "--no-tags",
                    url,
                    str(repository_directory),
                ],
                timeout=args.timeout,
            )
        )

        if clone_code != 0:

            result[
                "clone_status"
            ] = "FAIL"

            result[
                "failure_category"
            ] = "INFRASTRUCTURE"

            result[
                "failure_detail"
            ] = clone_output

            result[
                "reproducibility_status"
            ] = "FAILED"

            results.append(
                result
            )

            continue

        result[
            "clone_status"
        ] = "PASS"

        # ====================================================
        # CHECKOUT EXACT SHA
        # ====================================================

        if latest_sha:

            checkout_code, checkout_output, _ = (
                run_command(
                    [
                        "git",
                        "checkout",
                        "--detach",
                        latest_sha,
                    ],
                    cwd=repository_directory,
                    timeout=120,
                )
            )

            if checkout_code != 0:

                result[
                    "checkout_status"
                ] = "FAIL"

                result[
                    "failure_category"
                ] = "REPOSITORY"

                result[
                    "failure_detail"
                ] = checkout_output

                result[
                    "reproducibility_status"
                ] = "FAILED"

                results.append(
                    result
                )

                continue

            result[
                "checkout_status"
            ] = "PASS"

        else:

            result[
                "checkout_status"
            ] = "SKIPPED_NO_SHA"

        # ====================================================
        # COMPOSER.JSON
        # ====================================================

        composer_file = (
            repository_directory
            / "composer.json"
        )

        result[
            "composer_json"
        ] = composer_file.exists()

        if not composer_file.exists():

            result[
                "failure_category"
            ] = "REPOSITORY"

            result[
                "failure_detail"
            ] = (
                "composer.json was not found "
                "at tested commit."
            )

            result[
                "reproducibility_status"
            ] = "FAILED"

            results.append(
                result
            )

            continue

        # ====================================================
        # PHP EXTENSIONS
        # ====================================================

        result[
            "php_extensions"
        ] = detect_php_extensions(
            repository_directory
        )

        # ====================================================
        # TEST COMMAND
        # ====================================================

        (
            test_command,
            test_source,
        ) = detect_test_command(
            repository_directory
        )

        result[
            "test_command"
        ] = test_command

        result[
            "test_command_source"
        ] = test_source

        # ====================================================
        # INSPECTION ONLY
        # ====================================================

        if args.skip_install:

            result[
                "composer_install"
            ] = "SKIPPED"

            result[
                "test_environment_preparation"
            ] = "SKIPPED"

            result[
                "sqlite_preparation"
            ] = "SKIPPED"

            result[
                "test_execution"
            ] = "SKIPPED"

            result[
                "reproducibility_status"
            ] = "NOT STARTED"

            results.append(
                result
            )

            continue

        # ====================================================
        # PHP / COMPOSER AVAILABILITY
        # ====================================================

        if (
            not php_available
            or
            not composer_available
        ):

            missing = []

            if not php_available:
                missing.append(
                    "php"
                )

            if not composer_available:
                missing.append(
                    "composer"
                )

            result[
                "composer_install"
            ] = "BLOCKED"

            result[
                "test_environment_preparation"
            ] = "BLOCKED"

            result[
                "sqlite_preparation"
            ] = "BLOCKED"

            result[
                "test_execution"
            ] = "BLOCKED"

            result[
                "failure_category"
            ] = "INFRASTRUCTURE"

            result[
                "failure_detail"
            ] = (
                "Required command(s) unavailable: "
                + ", ".join(missing)
                + ". This is an HPC environment "
                "limitation, not a repository failure."
            )

            result[
                "reproducibility_status"
            ] = (
                "PARTIALLY REPRODUCIBLE"
            )

            results.append(
                result
            )

            continue

        # ====================================================
        # COMPOSER INSTALL
        # ====================================================

        (
            return_code,
            output,
            duration,
        ) = run_command(
            [
                "composer",
                "install",
                "--no-interaction",
                "--prefer-dist",
                "--no-progress",
            ],
            cwd=repository_directory,
            timeout=args.timeout,
        )

        if return_code != 0:

            result[
                "composer_install"
            ] = "FAIL"

            result[
                "test_execution"
            ] = "BLOCKED"

            result[
                "failure_category"
            ] = classify_failure(
                output,
                "composer",
            )

            result[
                "failure_detail"
            ] = output

            result[
                "reproducibility_status"
            ] = "FAILED"

            results.append(
                result
            )

            continue

        result[
            "composer_install"
        ] = "PASS"

        # ====================================================
        # STAGE 3 TEST ENVIRONMENT PREPARATION
        # ====================================================

        (
            environment_ok,
            environment_detail,
        ) = prepare_test_environment(
            repository_directory
        )

        result[
            "test_environment_preparation"
        ] = environment_detail

        if not environment_ok:

            result[
                "test_execution"
            ] = "BLOCKED"

            result[
                "failure_category"
            ] = "APPLICATION_CONFIGURATION"

            result[
                "failure_detail"
            ] = environment_detail

            result[
                "reproducibility_status"
            ] = "FAILED"

            results.append(
                result
            )

            continue

        # ====================================================
        # SQLITE PREPARATION
        # ====================================================

        (
            sqlite_ok,
            sqlite_detail,
        ) = prepare_sqlite_database(
            repository_directory
        )

        result[
            "sqlite_preparation"
        ] = sqlite_detail

        if not sqlite_ok:

            result[
                "test_execution"
            ] = "BLOCKED"

            result[
                "failure_category"
            ] = (
                "DATABASE_CONFIGURATION_OR_DATABASE_FAILURE"
            )

            result[
                "failure_detail"
            ] = sqlite_detail

            result[
                "reproducibility_status"
            ] = "FAILED"

            results.append(
                result
            )

            continue

        # ====================================================
        # TEST COMMAND CHECK
        # ====================================================

        if not test_command:

            result[
                "test_execution"
            ] = "NO TEST COMMAND"

            result[
                "failure_category"
            ] = "TEST_COMMAND_MISMATCH"

            result[
                "failure_detail"
            ] = test_source

            result[
                "reproducibility_status"
            ] = (
                "PARTIALLY REPRODUCIBLE"
            )

            results.append(
                result
            )

            continue

        # ====================================================
        # BUILD TEST COMMAND
        # ====================================================

        if test_command.startswith(
            "composer run "
        ):

            script_name = (
                test_command.replace(
                    "composer run ",
                    "",
                    1,
                )
            )

            command = [
                "composer",
                "run",
                script_name,
            ]

        else:

            command = (
                test_command.split()
            )

        # ====================================================
        # RUN TESTS
        # ====================================================

        (
            return_code,
            output,
            duration,
        ) = run_command(
            command,
            cwd=repository_directory,
            timeout=args.timeout,
        )

        if return_code == 0:

            result[
                "test_execution"
            ] = "PASS"

            result[
                "failure_category"
            ] = "NONE"

            result[
                "failure_detail"
            ] = ""

            result[
                "reproducibility_status"
            ] = "REPRODUCIBLE"

        else:

            result[
                "test_execution"
            ] = "FAIL"

            result[
                "failure_category"
            ] = classify_failure(
                output,
                "test",
            )

            result[
                "failure_detail"
            ] = output

            result[
                "reproducibility_status"
            ] = "FAILED"

        results.append(
            result
        )

    # ========================================================
    # RESULTS DATAFRAME
    # ========================================================

    results_df = pd.DataFrame(
        results
    )

    # ========================================================
    # SANITIZE EXCEL VALUES
    # ========================================================

    results_df = (
        sanitize_dataframe_for_excel(
            results_df
        )
    )

    # ========================================================
    # CREATE OUTPUT DIRECTORIES
    # ========================================================

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    xlsx_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # CSV
    # ========================================================

    results_df.to_csv(
        output_file,
        index=False,
    )

    # ========================================================
    # EXCEL
    # ========================================================

    try:

        results_df.to_excel(
            xlsx_file,
            index=False,
        )

    except Exception as exc:

        print()
        print(
            "WARNING: Excel export failed:"
        )

        print(
            repr(exc)
        )

        # Re-sanitize all strings and retry.
        results_df = (
            sanitize_dataframe_for_excel(
                results_df
            )
        )

        results_df.to_excel(
            xlsx_file,
            index=False,
        )

    # ========================================================
    # MANIFEST
    # ========================================================

    status_counts = {}

    if (
        "reproducibility_status"
        in results_df.columns
    ):

        status_counts = {
            str(k): int(v)
            for k, v in results_df[
                "reproducibility_status"
            ]
            .value_counts(
                dropna=False
            )
            .items()
        }

    failure_counts = {}

    if (
        "failure_category"
        in results_df.columns
    ):

        failure_counts = {
            str(k): int(v)
            for k, v in results_df[
                "failure_category"
            ]
            .fillna("")
            .value_counts(
                dropna=False
            )
            .items()
        }

    manifest = {
        "stage": "Stage 3",
        "script": (
            "scripts/09_reproducibility_check.py"
        ),
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "input": str(
            input_file
        ),
        "pilot": str(
            pilot_file
        ),
        "output_csv": str(
            output_file
        ),
        "output_xlsx": str(
            xlsx_file
        ),
        "workspace": str(
            workspace
        ),
        "frozen_candidate_count": int(
            len(dataframe)
        ),
        "pilot_count": int(
            len(pilot)
        ),
        "php_available": bool(
            php_available
        ),
        "composer_available": bool(
            composer_available
        ),
        "git_available": bool(
            git_available
        ),
        "timeout_seconds": int(
            args.timeout
        ),
        "status_counts": status_counts,
        "failure_category_counts": (
            failure_counts
        ),
    }

    manifest_file.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        "STAGE 3 REPRODUCIBILITY SUMMARY"
    )

    print(
        "=" * 70
    )

    if (
        "reproducibility_status"
        in results_df.columns
    ):

        print(
            results_df[
                "reproducibility_status"
            ].value_counts(
                dropna=False
            )
        )

    print()
    print(
        "FAILURE CATEGORIES"
    )

    if (
        "failure_category"
        in results_df.columns
    ):

        print(
            results_df[
                "failure_category"
            ]
            .fillna("")
            .replace(
                "",
                "NONE",
            )
            .value_counts()
        )

    print()
    print(
        "OUTPUTS"
    )

    print(
        "CSV:",
        output_file,
    )

    print(
        "Excel:",
        xlsx_file,
    )

    print(
        "Manifest:",
        manifest_file,
    )


if __name__ == "__main__":
    main()
