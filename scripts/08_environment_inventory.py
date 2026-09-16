#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime, timezone
import json
import re

import pandas as pd


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "data/interim/cross_os_candidates.csv"

OUTPUT_CSV = (
    ROOT / "data/interim/cross_os_environment_inventory.csv"
)

OUTPUT_XLSX = (
    ROOT / "data/interim/cross_os_environment_inventory.xlsx"
)

MANIFEST = (
    ROOT / "data/interim/cross_os_environment_inventory.manifest.json"
)


# ============================================================
# VERSION PARSING
# ============================================================

VERSION_RE = re.compile(
    r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?"
)


def extract_versions(value):

    if pd.isna(value):
        return []

    text = str(value).strip()

    if not text:
        return []

    matches = VERSION_RE.findall(text)

    versions = []

    for major, minor, patch in matches:

        versions.append(
            (
                int(major),
                int(minor or 0),
                int(patch or 0),
            )
        )

    return sorted(set(versions))


def version_to_string(version):

    if version is None:
        return None

    major, minor, patch = version

    return f"{major}.{minor}.{patch}"


def major_minor(version):

    if version is None:
        return None

    return f"{version[0]}.{version[1]}"


# ============================================================
# CONSTRAINT INFORMATION
# ============================================================

def constraint_info(value):

    versions = extract_versions(value)

    if not versions:

        return {
            "min": None,
            "max": None,
            "count": 0,
            "multi": False,
        }

    return {
        "min": version_to_string(
            min(versions)
        ),
        "max": version_to_string(
            max(versions)
        ),
        "count": len(versions),
        "multi": len(versions) > 1,
    }


def php_environment_group(value):

    versions = extract_versions(value)

    if not versions:
        return "PHP-Unknown"

    groups = sorted(
        {
            major_minor(v)
            for v in versions
        }
    )

    if len(groups) == 1:
        return f"PHP-{groups[0]}"

    return (
        "PHP-Multi["
        + ",".join(groups)
        + "]"
    )


def laravel_environment_group(value):

    versions = extract_versions(value)

    if not versions:
        return "Laravel-Unknown"

    groups = sorted(
        {
            str(v[0])
            for v in versions
        },
        key=int,
    )

    if len(groups) == 1:
        return f"Laravel-{groups[0]}"

    return (
        "Laravel-Multi["
        + ",".join(groups)
        + "]"
    )


# ============================================================
# TESTING MECHANISM
# ============================================================

def testing_mechanism(row):

    phpunit = bool(
        row.get(
            "phpunit_config_present",
            False
        )
    )

    composer_test = bool(
        row.get(
            "composer_test_script_present",
            False
        )
    )

    if phpunit and composer_test:
        return "PHPUnit + Composer test"

    if phpunit:
        return "PHPUnit"

    if composer_test:
        return "Composer test script"

    return "Unknown"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("CROSS-OS ENVIRONMENT INVENTORY")
    print("=" * 70)

    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    if not INPUT.exists():

        raise FileNotFoundError(
            f"Input file not found: {INPUT}"
        )

    df = pd.read_csv(INPUT)

    print("Input rows:", len(df))

    required = [
        "repo_full_name",
        "php_version_constraint",
        "laravel_version_constraint",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
        )

    # --------------------------------------------------------
    # DEDUPLICATION
    # --------------------------------------------------------

    original_rows = len(df)

    df = (
        df
        .drop_duplicates(
            subset=["repo_full_name"]
        )
        .reset_index(drop=True)
    )

    duplicates_removed = (
        original_rows - len(df)
    )

    print(
        "Duplicates removed:",
        duplicates_removed
    )

    # --------------------------------------------------------
    # PHP
    # --------------------------------------------------------

    php_info = df[
        "php_version_constraint"
    ].apply(constraint_info)

    df["php_min_version"] = php_info.apply(
        lambda x: x["min"]
    )

    df["php_max_version"] = php_info.apply(
        lambda x: x["max"]
    )

    df["php_constraint_count"] = php_info.apply(
        lambda x: x["count"]
    )

    df["php_multi_version"] = php_info.apply(
        lambda x: x["multi"]
    )

    df["php_environment_group"] = df[
        "php_version_constraint"
    ].apply(
        php_environment_group
    )

    # --------------------------------------------------------
    # LARAVEL
    # --------------------------------------------------------

    laravel_info = df[
        "laravel_version_constraint"
    ].apply(constraint_info)

    df["laravel_min_version"] = (
        laravel_info.apply(
            lambda x: x["min"]
        )
    )

    df["laravel_max_version"] = (
        laravel_info.apply(
            lambda x: x["max"]
        )
    )

    df["laravel_constraint_count"] = (
        laravel_info.apply(
            lambda x: x["count"]
        )
    )

    df["laravel_multi_version"] = (
        laravel_info.apply(
            lambda x: x["multi"]
        )
    )

    df["laravel_environment_group"] = df[
        "laravel_version_constraint"
    ].apply(
        laravel_environment_group
    )

    # --------------------------------------------------------
    # COMBINED ENVIRONMENT
    # --------------------------------------------------------

    df["environment_group"] = (
        df["php_environment_group"]
        + "__"
        + df["laravel_environment_group"]
    )

    # --------------------------------------------------------
    # COMPLEXITY
    # --------------------------------------------------------

    def complexity(row):

        php_multi = row[
            "php_multi_version"
        ]

        laravel_multi = row[
            "laravel_multi_version"
        ]

        if php_multi and laravel_multi:
            return "Multi-PHP + Multi-Laravel"

        if php_multi:
            return "Multi-PHP"

        if laravel_multi:
            return "Multi-Laravel"

        return "Single constraint"

    df["environment_complexity"] = df.apply(
        complexity,
        axis=1
    )

    # --------------------------------------------------------
    # TESTING
    # --------------------------------------------------------

    df["testing_mechanism"] = df.apply(
        testing_mechanism,
        axis=1
    )

    # --------------------------------------------------------
    # ACTIVITY YEAR
    # --------------------------------------------------------

    if "pushed_at" in df.columns:

        pushed = pd.to_datetime(
            df["pushed_at"],
            errors="coerce",
            utc=True
        )

        df["activity_year"] = (
            pushed.dt.year
        )

    # --------------------------------------------------------
    # SAVE CSV
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    # --------------------------------------------------------
    # SAVE EXCEL
    # --------------------------------------------------------

    with pd.ExcelWriter(
        OUTPUT_XLSX,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Environment Inventory",
            index=False
        )

        (
            df["php_environment_group"]
            .value_counts()
            .rename_axis("PHP Environment")
            .reset_index(name="Count")
            .to_excel(
                writer,
                sheet_name="PHP Distribution",
                index=False
            )
        )

        (
            df["laravel_environment_group"]
            .value_counts()
            .rename_axis("Laravel Environment")
            .reset_index(name="Count")
            .to_excel(
                writer,
                sheet_name="Laravel Distribution",
                index=False
            )
        )

        (
            df["environment_group"]
            .value_counts()
            .rename_axis("Environment Group")
            .reset_index(name="Count")
            .to_excel(
                writer,
                sheet_name="Environment Groups",
                index=False
            )
        )

        (
            df["testing_mechanism"]
            .value_counts()
            .rename_axis("Testing Mechanism")
            .reset_index(name="Count")
            .to_excel(
                writer,
                sheet_name="Testing Mechanism",
                index=False
            )
        )

        (
            df["environment_complexity"]
            .value_counts()
            .rename_axis("Complexity")
            .reset_index(name="Count")
            .to_excel(
                writer,
                sheet_name="Constraint Complexity",
                index=False
            )

        )

    # --------------------------------------------------------
    # MANIFEST
    # --------------------------------------------------------

    manifest = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "input_file": str(INPUT),

        "output_csv": str(
            OUTPUT_CSV
        ),

        "output_excel": str(
            OUTPUT_XLSX
        ),

        "input_rows": original_rows,

        "duplicates_removed": duplicates_removed,

        "final_rows": len(df),

        "unique_repositories": int(
            df["repo_full_name"].nunique()
        ),

        "purpose": (
            "Environment inventory for "
            "the frozen Cross-OS Laravel "
            "candidate dataset."
        ),

        "interpretation_note": (
            "Parsed version values are "
            "descriptive summaries of explicit "
            "versions in the repository "
            "constraints. They do not prove "
            "complete dependency compatibility."
        ),
    }

    with open(
        MANIFEST,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            manifest,
            file,
            indent=2
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL INVENTORY")
    print("=" * 70)

    print(
        "Projects:",
        len(df)
    )

    print(
        "Unique repositories:",
        df["repo_full_name"].nunique()
    )

    print()
    print("PHP ENVIRONMENT GROUPS")
    print(
        df[
            "php_environment_group"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("LARAVEL ENVIRONMENT GROUPS")
    print(
        df[
            "laravel_environment_group"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("TOP ENVIRONMENT GROUPS")
    print(
        df[
            "environment_group"
        ]
        .value_counts()
        .head(30)
        .to_string()
    )

    print()
    print("TESTING MECHANISM")
    print(
        df[
            "testing_mechanism"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("CONSTRAINT COMPLEXITY")
    print(
        df[
            "environment_complexity"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("OUTPUTS")
    print(
        "CSV:",
        OUTPUT_CSV
    )

    print(
        "Excel:",
        OUTPUT_XLSX
    )

    print(
        "Manifest:",
        MANIFEST
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
