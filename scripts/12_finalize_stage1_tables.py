from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"

src = INTERIM / "stage1_runtime_evidence.csv"

df = pd.read_csv(src)

# ============================================================
# 1. FAILURE EVIDENCE
# ============================================================

failure_cols = [
    "primary_run_id",
    "primary_job_id",
    "repo_full_name",
    "os",
    "requested_php",
    "primary_conclusion",
    "runtime_status",
    "failure_stage",
    "failure_category",
    "repeat_status",
    "portability_outcome",
    "primary_job_url",
    "evidence_source",
]

failures = df.loc[
    df["primary_conclusion"] == "failure",
    failure_cols
].copy()

failures.to_csv(
    INTERIM / "stage1_failure_evidence.csv",
    index=False,
    encoding="utf-8"
)


# ============================================================
# 2. REPEATABILITY
# ============================================================

repeat_cols = [
    "repo_full_name",
    "os",
    "requested_php",
    "primary_conclusion",
    "repeat_run_a",
    "repeat_a_conclusion",
    "repeat_run_b",
    "repeat_b_conclusion",
    "repeat_status",
    "portability_outcome",
    "primary_job_url",
    "repeat_a_job_url",
    "repeat_b_job_url",
]

repeatability = df[repeat_cols].copy()

repeatability.to_csv(
    INTERIM / "stage1_repeatability.csv",
    index=False,
    encoding="utf-8"
)


# ============================================================
# 3. SUMMARY
# ============================================================

summary_rows = [
    {
        "metric": "Total runtime combinations",
        "value": len(df),
    },
    {
        "metric": "Primary success",
        "value": int(
            (df["primary_conclusion"] == "success").sum()
        ),
    },
    {
        "metric": "Primary failure",
        "value": int(
            (df["primary_conclusion"] == "failure").sum()
        ),
    },
    {
        "metric": "Stable success",
        "value": int(
            (df["repeat_status"] == "STABLE_SUCCESS").sum()
        ),
    },
    {
        "metric": "Stable failure",
        "value": int(
            (df["repeat_status"] == "STABLE_FAILURE").sum()
        ),
    },
    {
        "metric": "Variable",
        "value": int(
            (df["repeat_status"] == "VARIABLE").sum()
        ),
    },
    {
        "metric": "Reproducible",
        "value": int(
            (df["portability_outcome"] == "REPRODUCIBLE").sum()
        ),
    },
    {
        "metric": "Partially reproducible",
        "value": int(
            (
                df["portability_outcome"]
                == "PARTIALLY_REPRODUCIBLE"
            ).sum()
        ),
    },
    {
        "metric": "Non-reproducible",
        "value": int(
            (
                df["portability_outcome"]
                == "NON_REPRODUCIBLE"
            ).sum()
        ),
    },
]

summary = pd.DataFrame(summary_rows)

summary.to_csv(
    INTERIM / "stage1_summary.csv",
    index=False,
    encoding="utf-8"
)


# ============================================================
# CHECK
# ============================================================

print("=" * 70)
print("STAGE 1 FINAL TABLES")
print("=" * 70)

print("Master evidence      :", len(df))
print("Failure evidence     :", len(failures))
print("Repeatability rows   :", len(repeatability))
print("Summary metrics      :", len(summary))

print("\nFiles created:")

for filename in [
    "stage1_runtime_evidence.csv",
    "stage1_failure_evidence.csv",
    "stage1_repeatability.csv",
    "stage1_summary.csv",
]:
    print(" -", INTERIM / filename)

print("\nStage 1 tables generated successfully.")
