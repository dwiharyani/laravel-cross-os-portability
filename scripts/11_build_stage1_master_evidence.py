import json
import re
from pathlib import Path

import pandas as pd


# ============================================================
# STAGE 1 — MASTER RUNTIME EVIDENCE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERIM = PROJECT_ROOT / "data" / "interim"

PRIMARY_RUN_ID = 35220810757
REPEAT_RUN_A = 35269909018
REPEAT_RUN_B = 35314890357

PRIMARY_JOBS = INTERIM / "runtime_pilot_jobs.json"
REPEAT_A_JOBS = INTERIM / f"jobs_{REPEAT_RUN_A}.json"
REPEAT_B_JOBS = INTERIM / f"jobs_{REPEAT_RUN_B}.json"

OUT = INTERIM / "stage1_runtime_evidence.csv"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def load_jobs(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return data["jobs"]


def parse_job_name(name):
    """
    Expected:

    repository / OS / PHP version

    Example:
    404NotFoundIndonesia/raktrek / macos-14 / PHP 8.1
    """

    pattern = (
        r"(.+?) / "
        r"(ubuntu-22\.04|windows-2022|macos-14) / "
        r"PHP (.+)$"
    )

    match = re.match(pattern, name)

    if not match:
        return None

    repo, os_name, php = match.groups()

    return {
        "repo_full_name": repo,
        "os": os_name,
        "requested_php": php,
    }


def runtime_jobs(jobs):
    result = []

    for job in jobs:
        parsed = parse_job_name(job["name"])

        if parsed is None:
            continue

        row = {
            "job_id": job["id"],
            "repo_full_name": parsed["repo_full_name"],
            "os": parsed["os"],
            "requested_php": parsed["requested_php"],
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "job_url": job.get("html_url"),
        }

        result.append(row)

    return result


def make_key(row):
    return (
        row["repo_full_name"],
        row["os"],
        str(row["requested_php"]),
    )


# ------------------------------------------------------------
# Load data
# ------------------------------------------------------------

print("=" * 80)
print("STAGE 1 — BUILD MASTER RUNTIME EVIDENCE")
print("=" * 80)

primary = runtime_jobs(load_jobs(PRIMARY_JOBS))
repeat_a = runtime_jobs(load_jobs(REPEAT_A_JOBS))
repeat_b = runtime_jobs(load_jobs(REPEAT_B_JOBS))

print()
print("Primary run :", PRIMARY_RUN_ID)
print("Repeat A    :", REPEAT_RUN_A)
print("Repeat B    :", REPEAT_RUN_B)

print()
print("Primary runtime jobs :", len(primary))
print("Repeat A jobs       :", len(repeat_a))
print("Repeat B jobs       :", len(repeat_b))


# ------------------------------------------------------------
# Index repeat runs
# ------------------------------------------------------------

repeat_a_map = {
    make_key(row): row
    for row in repeat_a
}

repeat_b_map = {
    make_key(row): row
    for row in repeat_b
}


# ------------------------------------------------------------
# Load PHP runtime matrix
# ------------------------------------------------------------

matrix_path = INTERIM / "php_runtime_matrix.csv"

if not matrix_path.exists():
    raise FileNotFoundError(
        f"Missing runtime matrix: {matrix_path}"
    )

matrix = pd.read_csv(matrix_path)

matrix_map = {}

for _, row in matrix.iterrows():

    key = (
        row["repo_full_name"],
        None,
        str(row["selected_php_runtime"]),
    )

    matrix_map.setdefault(
        (row["repo_full_name"], str(row["selected_php_runtime"])),
        row.to_dict()
    )


# ------------------------------------------------------------
# Build master table
# ------------------------------------------------------------

records = []

for row in primary:

    key = make_key(row)

    repo = row["repo_full_name"]
    os_name = row["os"]
    php = str(row["requested_php"])

    # -----------------------------------------
    # Primary result
    # -----------------------------------------

    primary_conclusion = row["conclusion"]

    # -----------------------------------------
    # Repeat A
    # -----------------------------------------

    a = repeat_a_map.get(key)

    if a:
        repeat_a_conclusion = a["conclusion"]
        repeat_a_job_id = a["job_id"]
        repeat_a_url = a["job_url"]
    else:
        repeat_a_conclusion = ""
        repeat_a_job_id = ""
        repeat_a_url = ""

    # -----------------------------------------
    # Repeat B
    # -----------------------------------------

    b = repeat_b_map.get(key)

    if b:
        repeat_b_conclusion = b["conclusion"]
        repeat_b_job_id = b["job_id"]
        repeat_b_url = b["job_url"]
    else:
        repeat_b_conclusion = ""
        repeat_b_job_id = ""
        repeat_b_url = ""

    # -----------------------------------------
    # Repeatability
    # -----------------------------------------

    repeat_values = [
        x for x in [
            repeat_a_conclusion,
            repeat_b_conclusion
        ]
        if x
    ]

    if len(repeat_values) == 2:

        if repeat_values[0] == "success" and repeat_values[1] == "success":
            repeat_status = "STABLE_SUCCESS"

        elif (
            repeat_values[0] == "failure"
            and repeat_values[1] == "failure"
        ):
            repeat_status = "STABLE_FAILURE"

        else:
            repeat_status = "VARIABLE"

    else:
        repeat_status = "INSUFFICIENT_REPEAT_DATA"

    # -----------------------------------------
    # Runtime status
    # -----------------------------------------

    if primary_conclusion == "success":
        runtime_status = "AVAILABLE"
    else:
        runtime_status = "UNAVAILABLE"

    # -----------------------------------------
    # Failure stage
    # -----------------------------------------

    if primary_conclusion == "failure":

        failure_stage = "runtime_provisioning"

        failure_category = (
            "PHP runtime provisioning failure"
        )

    else:

        failure_stage = ""
        failure_category = ""

    # -----------------------------------------
    # Portability outcome
    # -----------------------------------------

    if repeat_status == "STABLE_SUCCESS":

        portability_outcome = "REPRODUCIBLE"

    elif repeat_status == "VARIABLE":

        portability_outcome = "PARTIALLY_REPRODUCIBLE"

    elif repeat_status == "STABLE_FAILURE":

        portability_outcome = "NON_REPRODUCIBLE"

    else:

        portability_outcome = ""

    # -----------------------------------------
    # Evidence source
    # -----------------------------------------

    if primary_conclusion == "failure":

        evidence_source = (
            "GitHub Actions job log / runtime evidence artifact"
        )

    else:

        evidence_source = (
            "GitHub Actions job result / runtime evidence artifact"
        )

    # -----------------------------------------
    # Record
    # -----------------------------------------

    records.append({

        "primary_run_id":
            PRIMARY_RUN_ID,

        "primary_job_id":
            row["job_id"],

        "repo_full_name":
            repo,

        "os":
            os_name,

        "requested_php":
            php,

        "primary_conclusion":
            primary_conclusion,

        "runtime_status":
            runtime_status,

        "repeat_run_a":
            REPEAT_RUN_A,

        "repeat_a_conclusion":
            repeat_a_conclusion,

        "repeat_a_job_id":
            repeat_a_job_id,

        "repeat_run_b":
            REPEAT_RUN_B,

        "repeat_b_conclusion":
            repeat_b_conclusion,

        "repeat_b_job_id":
            repeat_b_job_id,

        "repeat_status":
            repeat_status,

        "failure_stage":
            failure_stage,

        "failure_category":
            failure_category,

        "portability_outcome":
            portability_outcome,

        "primary_job_url":
            row["job_url"],

        "repeat_a_job_url":
            repeat_a_url,

        "repeat_b_job_url":
            repeat_b_url,

        "evidence_source":
            evidence_source,
    })


# ------------------------------------------------------------
# DataFrame
# ------------------------------------------------------------

df = pd.DataFrame(records)

df = df.sort_values(
    [
        "repo_full_name",
        "os",
        "requested_php"
    ]
).reset_index(drop=True)


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

print()
print("=" * 80)
print("VALIDATION")
print("=" * 80)

print("Master rows:", len(df))

print()
print("Primary conclusion:")
print(
    df["primary_conclusion"]
    .value_counts(dropna=False)
)

print()
print("Runtime status:")
print(
    df["runtime_status"]
    .value_counts(dropna=False)
)

print()
print("Repeatability:")
print(
    df["repeat_status"]
    .value_counts(dropna=False)
)

print()
print("Portability outcome:")
print(
    df["portability_outcome"]
    .value_counts(dropna=False)
)


# ------------------------------------------------------------
# Expected 60 runtime checks
# ------------------------------------------------------------

if len(df) != 60:

    raise SystemExit(
        f"ERROR: Expected 60 runtime checks, "
        f"found {len(df)}"
    )


# ------------------------------------------------------------
# Duplicate check
# ------------------------------------------------------------

duplicate_keys = df.duplicated(
    subset=[
        "repo_full_name",
        "os",
        "requested_php"
    ]
).sum()

print()
print("Duplicate runtime combinations:", duplicate_keys)

if duplicate_keys != 0:

    raise SystemExit(
        "ERROR: Duplicate runtime combinations found."
    )


# ------------------------------------------------------------
# Save
# ------------------------------------------------------------

df.to_csv(
    OUT,
    index=False,
    encoding="utf-8"
)

print()
print("=" * 80)
print("CREATED")
print("=" * 80)

print(OUT)
print("Rows:", len(df))
print("Columns:", len(df.columns))

print()
print("Failure records:")
print(
    df.loc[
        df["primary_conclusion"] == "failure",
        [
            "repo_full_name",
            "os",
            "requested_php",
            "primary_conclusion",
            "failure_stage",
            "failure_category",
            "repeat_status",
            "portability_outcome",
        ]
    ].to_string(index=False)
)

print()
print("Stage 1 master evidence successfully created.")
