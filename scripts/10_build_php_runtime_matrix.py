from pathlib import Path
import pandas as pd
import re


ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT / "data/interim/reproducibility_pilot20.csv"
)

OUTPUT_FILE = (
    ROOT / "data/interim/php_runtime_matrix.csv"
)


def select_php_runtime(constraint: str):
    """
    Select a representative PHP runtime from the declared
    Composer PHP constraint.

    The selected version is a test runtime, not a claim that
    every PHP version satisfying the constraint has been tested.
    """

    c = str(constraint).strip()

    # Exact legacy Laravel constraints
    if re.search(r"5\.4", c):
        return "5.4", "Legacy PHP 5.4 constraint"

    if re.search(r"5\.6", c):
        return "5.6", "PHP 5.6 constraint"

    # PHP 7.x
    if re.search(r"7\.0", c):
        return "7.0", "PHP 7.0 constraint"

    if re.search(r"7\.1", c):
        return "7.4", (
            "Representative PHP 7.x runtime "
            "within the declared major-version range"
        )

    if re.search(r"7\.2", c):
        return "7.4", (
            "Representative PHP 7.x runtime "
            "within the declared major-version range"
        )

    if re.search(r"7\.3", c):
        return "7.4", (
            "Representative PHP 7.x runtime "
            "within the declared major-version range"
        )

    # PHP 8.x
    if re.search(r"8\.0", c):
        return "8.0", "PHP 8.0 representative runtime"

    if re.search(r"8\.1", c):
        return "8.1", "PHP 8.1 representative runtime"

    if re.search(r"8\.2", c):
        return "8.2", "PHP 8.2 representative runtime"

    if re.search(r"8\.3", c):
        return "8.3", "PHP 8.3 representative runtime"

    if re.search(r"8\.4", c):
        return "8.4", "PHP 8.4 representative runtime"

    if re.search(r"8\.5", c):
        return "8.5", "PHP 8.5 representative runtime"

    # Broad lower-bound constraint
    if re.search(r">=\s*5\.6", c):
        return "5.6", (
            "Lowest practical representative "
            "for declared PHP >=5.6 constraint"
        )

    return None, "NO_RUNTIME_MAPPING"


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required = [
        "repo_full_name",
        "latest_sha",
        "php_version_constraint",
        "laravel_version_constraint",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    records = []

    for _, row in df.iterrows():

        constraint = row[
            "php_version_constraint"
        ]

        runtime, rationale = select_php_runtime(
            constraint
        )

        records.append({
            "repo_full_name":
                row["repo_full_name"],

            "latest_sha":
                row["latest_sha"],

            "php_version_constraint":
                constraint,

            "laravel_version_constraint":
                row["laravel_version_constraint"],

            "selected_php_runtime":
                runtime,

            "runtime_selection_rationale":
                rationale,

            "runtime_selection_status":
                (
                    "MAPPED"
                    if runtime
                    else "UNMAPPED"
                ),
        })

    result = pd.DataFrame(records)

    # Integrity checks
    if len(result) != len(df):
        raise RuntimeError(
            "Output row count differs from pilot dataset."
        )

    if result["repo_full_name"].nunique() != len(result):
        raise RuntimeError(
            "Duplicate repositories detected."
        )

    if result["latest_sha"].isna().any():
        raise RuntimeError(
            "Missing SHA detected."
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("=" * 70)
    print("PHP RUNTIME MATRIX")
    print("=" * 70)

    print("Input:", INPUT_FILE)
    print("Output:", OUTPUT_FILE)
    print("Repositories:", len(result))

    print("\nRuntime distribution:")
    print(
        result[
            "selected_php_runtime"
        ].value_counts(
            dropna=False
        ).sort_index()
    )

    print("\nMapping status:")
    print(
        result[
            "runtime_selection_status"
        ].value_counts()
    )

    print("\nRepositories:")
    print(
        result[
            [
                "repo_full_name",
                "php_version_constraint",
                "selected_php_runtime",
                "laravel_version_constraint",
            ]
        ].to_string(index=False)
    )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
