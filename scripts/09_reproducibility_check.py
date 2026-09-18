#!/usr/bin/env python3

"""
09_reproducibility_check.py

Purpose:
    Check whether frozen Laravel candidates can be reproduced
    from a clean repository checkout.

Workflow:

    Frozen candidates
          ↓
    Select pilot
          ↓
    Clone repository
          ↓
    Checkout exact SHA
          ↓
    Inspect composer.json
          ↓
    Detect PHP extensions
          ↓
    Detect test command
          ↓
    Composer install
          ↓
    Run tests
          ↓
    Classify result

IMPORTANT:
    This is NOT the final Cross-OS experiment.

    A missing PHP or Composer installation on the HPC is classified
    as an infrastructure limitation, not as a repository failure.
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
    ROOT / "data/work/reproducibility"
)


# ============================================================
# COMMAND UTILITIES
# ============================================================

def command_exists(command: str) -> bool:
    """
    Check whether a command exists in PATH.
    """
    return shutil.which(command) is not None


def run_command(
    command,
    cwd=None,
    timeout=900,
):
    """
    Run a shell command safely.

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

        return (
            process.returncode,
            process.stdout[-12000:],
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


# ============================================================
# PILOT SELECTION
# ============================================================

def select_pilot(
    dataframe: pd.DataFrame,
    number: int = 20,
) -> pd.DataFrame:

    """
    Select a deterministic pilot.

    Priority:
        1. Cover major environment groups.
        2. Then fill remaining slots using higher-star projects.

    This is only a reproducibility pilot.
    It is NOT the final Cross-OS experimental sample.
    """

    df = dataframe.copy()

    # --------------------------------------------------------
    # Remove duplicate repositories
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=["repo_full_name"]
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # Create environment_group if necessary
    # --------------------------------------------------------

    if "environment_group" not in df.columns:

        if (
            "php_environment_group" in df.columns
            and
            "laravel_environment_group" in df.columns
        ):

            df["environment_group"] = (
                df["php_environment_group"].astype(str)
                + "__"
                + df["laravel_environment_group"].astype(str)
            )

        else:

            df["environment_group"] = "Unknown"

    selected = []

    used_repositories = set()

    # --------------------------------------------------------
    # First pass:
    # one representative from each major environment group
    # --------------------------------------------------------

    groups = (
        df["environment_group"]
        .value_counts()
        .index
        .tolist()
    )

    for group in groups:

        candidates = df[
            df["environment_group"] == group
        ].copy()

        if candidates.empty:
            continue

        candidates = candidates.sort_values(
            by=[
                "stars_github",
                "repo_full_name",
            ],
            ascending=[
                False,
                True,
            ],
            na_position="last",
        )

        row = candidates.iloc[0]

        repository = row["repo_full_name"]

        if repository not in used_repositories:

            selected.append(row)

            used_repositories.add(
                repository
            )

        if len(selected) >= number:
            break

    # --------------------------------------------------------
    # Second pass:
    # fill remaining slots
    # --------------------------------------------------------

    if len(selected) < number:

        remaining = df[
            ~df["repo_full_name"].isin(
                used_repositories
            )
        ].copy()

        remaining = remaining.sort_values(
            by=[
                "stars_github",
                "repo_full_name",
            ],
            ascending=[
                False,
                True,
            ],
            na_position="last",
        )

        remaining_needed = (
            number - len(selected)
        )

        for _, row in remaining.head(
            remaining_needed
        ).iterrows():

            selected.append(row)

    return pd.DataFrame(
        selected
    ).reset_index(drop=True)


# ============================================================
# COMPOSER INSPECTION
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

        with open(
            composer_file,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    except Exception:

        return None


# ============================================================
# PHP EXTENSIONS
# ============================================================

def detect_php_extensions(
    repository_directory: Path,
) -> str:

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

        if str(package_name).lower().startswith(
            "ext-"
        ):

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

    if (
        repository_directory
        / "vendor/bin/phpunit"
    ).exists():

        return (
            "vendor/bin/phpunit",
            "vendor/bin/phpunit detected",
        )

    # --------------------------------------------------------
    # PHPUnit configuration
    # --------------------------------------------------------

    if (
        (
            repository_directory
            / "phpunit.xml"
        ).exists()
        or
        (
            repository_directory
            / "phpunit.xml.dist"
        ).exists()
    ):

        return (
            "vendor/bin/phpunit",
            "PHPUnit configuration detected",
        )

    return (
        "",
        "No test command detected",
    )


# ============================================================
# FAILURE CLASSIFICATION
# ============================================================

def classify_failure(
    output: str,
    stage: str,
) -> str:

    text = (
        output or ""
    ).lower()

    # --------------------------------------------------------
    # Infrastructure
    # --------------------------------------------------------

    if stage == "infrastructure":

        return "INFRASTRUCTURE"

    # --------------------------------------------------------
    # Network
    # --------------------------------------------------------

    if (
        "could not resolve host" in text
        or
        "network" in text
    ):

        return "NETWORK"

    # --------------------------------------------------------
    # PHP version
    # --------------------------------------------------------

    if (
        "requires php" in text
        or
        "your php version" in text
    ):

        return "PHP VERSION"

    # --------------------------------------------------------
    # PHP extension
    # --------------------------------------------------------

    if (
        "ext-" in text
        or
        "extension" in text
    ):

        return "PHP EXTENSION"

    # --------------------------------------------------------
    # Dependency
    # --------------------------------------------------------

    if (
        "dependency" in text
        or
        "class not found" in text
    ):

        return "DEPENDENCY"

    # --------------------------------------------------------
    # Composer
    # --------------------------------------------------------

    if (
        "composer" in text
        and
        (
            "memory" in text
            or
            "dependency" in text
        )
    ):

        return "COMPOSER"

    # --------------------------------------------------------
    # PHPUnit / tests
    # --------------------------------------------------------

    if (
        "phpunit" in text
        or
        "test" in text
    ):

        return "TEST FAILURE"

    # --------------------------------------------------------
    # Permission
    # --------------------------------------------------------

    if "permission denied" in text:

        return "INFRASTRUCTURE"

    return "UNKNOWN"


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run reproducibility checks "
            "on frozen Laravel candidates."
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
        "--workspace",
        default=str(
            DEFAULT_WORKSPACE
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
    )

    parser.add_argument(
        "--skip-install",
        action="store_true",
        help=(
            "Only inspect repositories. "
            "Do not run composer install "
            "or tests."
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

    # ========================================================
    # CHECK INPUT
    # ========================================================

    if not input_file.exists():

        raise FileNotFoundError(
            f"Input file not found: "
            f"{input_file}"
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
    # CREATE / LOAD PILOT
    # ========================================================

    if pilot_file.exists():

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
        "REPRODUCIBILITY CHECK"
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
        "Workspace:",
        workspace,
    )

    print()

    results = []

    # ========================================================
    # PROCESS PILOT
    # ========================================================

    for index, row in pilot.iterrows():

        repository_name = str(
            row["repo_full_name"]
        )

        repository_url = str(
            row.get(
                "url",
                f"https://github.com/"
                f"{repository_name}.git",
            )
        )

        latest_sha = str(
            row.get(
                "latest_sha",
                "",
            )
        ).strip()

        safe_name = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            repository_name,
        )

        repository_directory = (
            workspace / safe_name
        )

        # ----------------------------------------------------
        # Result structure
        # ----------------------------------------------------

        result = {

            "repo_full_name":
                repository_name,

            "url":
                repository_url,

            "latest_sha":
                latest_sha,

            "environment_group":
                row.get(
                    "environment_group",
                    "",
                ),

            "php_version_constraint":
                row.get(
                    "php_version_constraint",
                    "",
                ),

            "laravel_version_constraint":
                row.get(
                    "laravel_version_constraint",
                    "",
                ),

            "clone_status":
                "NOT STARTED",

            "checkout_status":
                "NOT STARTED",

            "composer_json":
                False,

            "php_extensions":
                "",

            "test_command":
                "",

            "test_command_source":
                "",

            "php_available":
                php_available,

            "composer_available":
                composer_available,

            "composer_install":
                "NOT STARTED",

            "test_execution":
                "NOT STARTED",

            "failure_category":
                "",

            "failure_detail":
                "",

            "reproducibility_status":
                "NOT STARTED",

            "tested_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
        }

        print(
            f"[{index + 1}/{len(pilot)}] "
            f"{repository_name}"
        )

        # ====================================================
        # GIT AVAILABILITY
        # ====================================================

        if not git_available:

            result[
                "clone_status"
            ] = "BLOCKED"

            result[
                "failure_category"
            ] = "INFRASTRUCTURE"

            result[
                "failure_detail"
            ] = (
                "git command is not "
                "available on this machine."
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
        # CLEAN OLD REPOSITORY
        # ====================================================

        if repository_directory.exists():

            shutil.rmtree(
                repository_directory
            )

        # ====================================================
        # CLONE
        # ====================================================

        return_code, output, duration = (
            run_command(
                [
                    "git",
                    "clone",
                    "--no-tags",
                    repository_url,
                    str(
                        repository_directory
                    ),
                ],
                timeout=args.timeout,
            )
        )

        if return_code != 0:

            result[
                "clone_status"
            ] = "FAIL"

            result[
                "failure_category"
            ] = classify_failure(
                output,
                "clone",
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
            "clone_status"
        ] = "PASS"

        # ====================================================
        # CHECKOUT EXACT SHA
        # ====================================================

        if latest_sha:

            (
                return_code,
                output,
                duration,
            ) = run_command(
                [
                    "git",
                    "checkout",
                    "--detach",
                    latest_sha,
                ],
                cwd=repository_directory,
                timeout=120,
            )

            if return_code != 0:

                result[
                    "checkout_status"
                ] = "FAIL"

                result[
                    "failure_category"
                ] = "REPOSITORY"

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
            "checkout_status"
        ] = "PASS"

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
                "composer.json was not "
                "found at tested commit."
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
                "test_execution"
            ] = "BLOCKED"

            result[
                "failure_category"
            ] = "INFRASTRUCTURE"

            result[
                "failure_detail"
            ] = (
                "Required command(s) "
                "unavailable: "
                + ", ".join(missing)
                + ". This is an HPC "
                "environment limitation, "
                "not a repository failure."
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
        # TEST COMMAND
        # ====================================================

        if not test_command:

            result[
                "test_execution"
            ] = "NO TEST COMMAND"

            result[
                "failure_category"
            ] = "REPOSITORY"

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
                test_command
                .replace(
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
    # OUTPUT DIRECTORY
    # ========================================================

    DEFAULT_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # CSV
    # ========================================================

    results_df.to_csv(
        DEFAULT_OUTPUT,
        index=False,
    )

    # ========================================================
    # EXCEL
    # ========================================================

    with pd.ExcelWriter(
        DEFAULT_XLSX,
        engine="openpyxl",
    ) as writer:

        results_df.to_excel(
            writer,
            sheet_name=(
                "Reproducibility Results"
            ),
            index=False,
        )

        status_summary = (
            results_df[
                "reproducibility_status"
            ]
            .value_counts(
                dropna=False
            )
            .rename_axis(
                "Status"
            )
            .reset_index(
                name="Projects"
            )
        )

        status_summary.to_excel(
            writer,
            sheet_name="Status Summary",
            index=False,
        )

        failure_summary = (
            results_df[
                "failure_category"
            ]
            .value_counts(
                dropna=False
            )
            .rename_axis(
                "Failure Category"
            )
            .reset_index(
                name="Projects"
            )
        )

        failure_summary.to_excel(
            writer,
            sheet_name="Failure Summary",
            index=False,
        )

    # ========================================================
    # MANIFEST
    # ========================================================

    manifest = {

        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "input":
            str(input_file),

        "pilot":
            str(pilot_file),

        "frozen_candidate_count":
            len(dataframe),

        "pilot_count":
            len(pilot),

        "php_available":
            php_available,

        "composer_available":
            composer_available,

        "git_available":
            git_available,

        "output_csv":
            str(DEFAULT_OUTPUT),

        "output_excel":
            str(DEFAULT_XLSX),

        "workspace":
            str(workspace),

        "important_note": (
            "Infrastructure limitations "
            "must not be interpreted as "
            "repository portability failures."
        ),
    }

    with open(
        DEFAULT_MANIFEST,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            manifest,
            file,
            indent=2,
        )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        "REPRODUCIBILITY SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        results_df[
            "reproducibility_status"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()
    print(
        "FAILURE CATEGORIES"
    )

    print(
        results_df[
            "failure_category"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()
    print(
        "OUTPUTS"
    )

    print(
        "CSV:",
        DEFAULT_OUTPUT,
    )

    print(
        "Excel:",
        DEFAULT_XLSX,
    )

    print(
        "Manifest:",
        DEFAULT_MANIFEST,
    )


if __name__ == "__main__":

    main()
