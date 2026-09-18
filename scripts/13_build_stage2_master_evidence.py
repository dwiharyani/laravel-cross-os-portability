#!/usr/bin/env python3

import json
from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_ROOT = (
    ROOT / "data/interim/stage2_artifacts"
)

OUTPUT_DIR = (
    ROOT / "data/interim"
)

MASTER_OUTPUT = (
    OUTPUT_DIR / "stage2_reproducibility_evidence.csv"
)

FAILURE_OUTPUT = (
    OUTPUT_DIR / "stage2_failure_evidence.csv"
)

SUMMARY_OUTPUT = (
    OUTPUT_DIR / "stage2_summary.csv"
)


# ============================================================
# HELPERS
# ============================================================

def get_value(data, *keys, default=""):
    """
    Return the first available value from candidate keys.
    """

    for key in keys:

        if key in data:

            value = data[key]

            if value is None:
                return default

            return value

    return default


# ============================================================
# DISCOVER RESULT FILES
# ============================================================

result_files = sorted(
    ARTIFACT_ROOT.glob(
        "reproducibility-*/result.json"
    )
)


print("=" * 70)
print("STAGE 2 MASTER EVIDENCE")
print("=" * 70)

print(
    "Result files:",
    len(result_files)
)


if len(result_files) != 20:

    raise SystemExit(
        f"Expected 20 result.json files, "
        f"found {len(result_files)}"
    )


# ============================================================
# LOAD RESULTS
# ============================================================

records = []


for result_file in result_files:

    with result_file.open(
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    record = {

        # ----------------------------------------------------
        # Identity
        # ----------------------------------------------------

        "artifact":
            result_file.parent.name,

        "repo_full_name":
            get_value(
                data,
                "repo_full_name",
                "repository",
            ),

        "commit_sha":
            get_value(
                data,
                "commit_sha",
                "latest_sha",
            ),

        # ----------------------------------------------------
        # Runtime
        # ----------------------------------------------------

        "requested_php":
            get_value(
                data,
                "requested_php",
                "php_version",
                "selected_php_runtime",
            ),

        "operating_system":
            get_value(
                data,
                "operating_system",
                "os",
            ),

        "runtime_available":
            get_value(
                data,
                "runtime_available",
                "php_available",
            ),

        # ----------------------------------------------------
        # Composer
        # ----------------------------------------------------

        "composer_available":
            get_value(
                data,
                "composer_available",
            ),

        "composer_install":
            get_value(
                data,
                "composer_install",
            ),

        "composer_exit_code":
            get_value(
                data,
                "composer_exit_code",
            ),

        # ----------------------------------------------------
        # Testing
        # ----------------------------------------------------

        "test_command":
            get_value(
                data,
                "test_command",
            ),

        "test_exit_code":
            get_value(
                data,
                "test_exit_code",
            ),

        "test_timeout":
            get_value(
                data,
                "test_timeout",
            ),

        # ----------------------------------------------------
        # Classification
        # ----------------------------------------------------

        "failure_stage":
            get_value(
                data,
                "failure_stage",
            ),

        "failure_category":
            get_value(
                data,
                "failure_category",
            ),

        "reproducibility_status":
            get_value(
                data,
                "reproducibility_status",
                "runtime_status",
            ),

        # ----------------------------------------------------
        # Timing
        # ----------------------------------------------------

        "started_at":
            get_value(
                data,
                "started_at",
            ),

        "completed_at":
            get_value(
                data,
                "completed_at",
            ),

        "duration_seconds":
            get_value(
                data,
                "duration_seconds",
            ),
    }

    records.append(record)


# ============================================================
# DATAFRAME
# ============================================================

df = pd.DataFrame(records)


# ============================================================
# BASIC VALIDATION
# ============================================================

if df["repo_full_name"].isna().any():

    print(
        "WARNING: Missing repository names:"
    )

    print(
        df[
            df["repo_full_name"].isna()
        ]
    )


duplicate_repositories = (
    df["repo_full_name"]
    .duplicated()
    .sum()
)


if duplicate_repositories:

    raise SystemExit(
        "Duplicate repositories detected: "
        f"{duplicate_repositories}"
    )


# ============================================================
# SORT
# ============================================================

df = df.sort_values(
    by="repo_full_name"
).reset_index(
    drop=True
)


# ============================================================
# FAILURE EVIDENCE
# ============================================================

failure_df = df[
    df["reproducibility_status"]
    != "REPRODUCIBLE"
].copy()


# ============================================================
# SUMMARY
# ============================================================

summary_rows = []


def add_summary(
    metric,
    value,
):

    summary_rows.append(
        {
            "metric": metric,
            "value": value,
        }
    )


add_summary(
    "total_repositories",
    len(df),
)

add_summary(
    "reproducible",
    (
        df[
            df["reproducibility_status"]
            == "REPRODUCIBLE"
        ].shape[0]
    ),
)

add_summary(
    "non_reproducible",
    (
        df[
            df["reproducibility_status"]
            == "NON_REPRODUCIBLE"
        ].shape[0]
    ),
)

add_summary(
    "partially_reproducible",
    (
        df[
            df["reproducibility_status"]
            == "PARTIALLY_REPRODUCIBLE"
        ].shape[0]
    ),
)

add_summary(
    "unique_failure_categories",
    (
        failure_df[
            "failure_category"
        ]
        .replace("", pd.NA)
        .dropna()
        .nunique()
    ),
)


# ------------------------------------------------------------
# Failure category counts
# ------------------------------------------------------------

category_counts = (
    failure_df[
        "failure_category"
    ]
    .replace("", pd.NA)
    .dropna()
    .value_counts()
)


for category, count in (
    category_counts.items()
):

    add_summary(
        f"failure_category__{category}",
        count,
    )


# ------------------------------------------------------------
# Failure stage counts
# ------------------------------------------------------------

stage_counts = (
    failure_df[
        "failure_stage"
    ]
    .replace("", pd.NA)
    .dropna()
    .value_counts()
)


for stage, count in (
    stage_counts.items()
):

    add_summary(
        f"failure_stage__{stage}",
        count,
    )


summary_df = pd.DataFrame(
    summary_rows
)


# ============================================================
# SAVE
# ============================================================

df.to_csv(
    MASTER_OUTPUT,
    index=False,
)

failure_df.to_csv(
    FAILURE_OUTPUT,
    index=False,
)

summary_df.to_csv(
    SUMMARY_OUTPUT,
    index=False,
)


# ============================================================
# REPORT
# ============================================================

print()
print(
    "Master evidence:",
    len(df)
)

print(
    "Failure evidence:",
    len(failure_df)
)

print()
print("Reproducibility:")
print(
    df[
        "reproducibility_status"
    ].value_counts(
        dropna=False
    )
)

print()
print("Failure categories:")
print(
    failure_df[
        "failure_category"
    ].value_counts(
        dropna=False
    )
)

print()
print("Failure stages:")
print(
    failure_df[
        "failure_stage"
    ].value_counts(
        dropna=False
    )
)

print()
print("Files created:")

print(
    "-",
    MASTER_OUTPUT
)

print(
    "-",
    FAILURE_OUTPUT
)

print(
    "-",
    SUMMARY_OUTPUT
)

print()
print(
    "=" * 70
)

print(
    "STAGE 2 MASTER EVIDENCE CREATED"
)

print(
    "=" * 70
)
