import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

# PILOT INPUT
# Change this to verified_laravel_apps.csv for full run.
INPUT_FILE = (
    ROOT / "data/interim/verified_laravel_apps.csv"
)

ENRICHED_FILE = (
    ROOT / "data/interim/github_enriched.csv"
)

OUTPUT_CSV = (
    ROOT / "data/interim/eligible_laravel_apps.csv"
)

OUTPUT_EXCEL = (
    ROOT / "data/interim/laravel_eligibility_results.xlsx"
)

CHECKPOINT_FILE = (
    ROOT / "data/interim/eligibility_checkpoint.csv"
)

load_dotenv(ROOT / ".env")

TOKEN = os.getenv("GITHUB_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN is not configured."
    )


HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Authorization": f"Bearer {TOKEN}",
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# GITHUB API
# ============================================================

def github_get(url, retries=3):

    for attempt in range(1, retries + 1):

        try:

            response = session.get(
                url,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()

            if response.status_code == 404:
                return None

            if response.status_code in (403, 429):

                print(
                    f"Rate limit / forbidden "
                    f"(attempt {attempt}/{retries})"
                )

                reset = response.headers.get(
                    "X-RateLimit-Reset"
                )

                if reset:

                    try:
                        wait = max(
                            5,
                            int(reset)
                            - int(time.time())
                            + 2
                        )
                    except Exception:
                        wait = 30

                else:
                    wait = 30

                print(
                    f"Waiting {wait} seconds..."
                )

                time.sleep(wait)
                continue

            print(
                "API error:",
                response.status_code,
                url
            )

        except requests.RequestException as e:

            print(
                f"Request error "
                f"(attempt {attempt}/{retries}):",
                repr(e)
            )

            time.sleep(
                min(10 * attempt, 30)
            )

    return None


# ============================================================
# REPOSITORY TREE
# ============================================================

def get_tree(repo, sha):

    url = (
        f"https://api.github.com/repos/"
        f"{repo}/git/trees/{sha}"
        f"?recursive=1"
    )

    return github_get(url)


# ============================================================
# PATH NORMALIZATION
# ============================================================

def normalize_paths(tree_data):

    if not tree_data:
        return set()

    return {
        item.get("path", "").lower()
        for item in tree_data.get(
            "tree",
            []
        )
        if item.get("path")
    }


# ============================================================
# TEST CHECK
# ============================================================

def check_tests(paths):

    test_directory = any(
        p == "tests"
        or p.startswith("tests/")
        for p in paths
    )

    phpunit_config = any(
        p in {
            "phpunit.xml",
            "phpunit.xml.dist",
        }
        for p in paths
    )

    return (
        test_directory,
        phpunit_config
    )


# ============================================================
# DOCKERFILE CHECK
# ============================================================

def check_dockerfile(paths):

    return any(
        Path(p).name.lower()
        == "dockerfile"
        for p in paths
    )


# ============================================================
# REPOSITORY EVALUATION
# ============================================================

def evaluate_repository(row):

    repo = row["repo_full_name"]

    pushed_at = row.get(
        "pushed_at",
        None
    )

    latest_sha = row.get(
        "latest_sha",
        None
    )

    result = {
        "repo_full_name": repo,

        "url": row.get(
            "url",
            ""
        ),

        "stars_github": row.get(
            "stars_github",
            None
        ),

        "pushed_at": pushed_at,

        "latest_sha": latest_sha,

        # ---------------------------------------------
        # Individual checks
        # ---------------------------------------------

        "recent_activity": False,

        "composer_json": False,

        "composer_lock": False,

        "test_directory": False,

        "phpunit_config": False,

        "dockerfile": False,

        # ---------------------------------------------
        # Final decision
        # ---------------------------------------------

        "eligibility_status":
            "Not Eligible",

        "exclusion_reason":
            "",
    }

    # ========================================================
    # RECENT ACTIVITY
    # ========================================================

    if pd.notna(pushed_at):

        pushed_date = pd.to_datetime(
            pushed_at,
            utc=True,
            errors="coerce"
        )

        cutoff = (
            pd.Timestamp.now(
                tz="UTC"
            )
            - pd.Timedelta(
                days=365
            )
        )

        if (
            pd.notna(pushed_date)
            and pushed_date >= cutoff
        ):

            result[
                "recent_activity"
            ] = True

    # ========================================================
    # GITHUB TREE
    # ========================================================

    tree_data = get_tree(
        repo,
        latest_sha
    )

    if not tree_data:

        result[
            "exclusion_reason"
        ] = "GitHub tree unavailable"

        return result

    paths = normalize_paths(
        tree_data
    )

    # ========================================================
    # COMPOSER
    # ========================================================

    result[
        "composer_json"
    ] = (
        "composer.json"
        in paths
    )

    result[
        "composer_lock"
    ] = (
        "composer.lock"
        in paths
    )

    # ========================================================
    # TESTS
    # ========================================================

    (
        result["test_directory"],
        result["phpunit_config"]
    ) = check_tests(
        paths
    )

    # ========================================================
    # DOCKER
    # ========================================================

    result[
        "dockerfile"
    ] = check_dockerfile(
        paths
    )

    # ========================================================
    # EXCLUSION REASONS
    # ========================================================

    reasons = []

    if not result["recent_activity"]:

        reasons.append(
            "Not recently active"
        )

    if not result["test_directory"]:

        reasons.append(
            "No tests directory"
        )

    if not result["phpunit_config"]:

        reasons.append(
            "No PHPUnit configuration"
        )

    if result["dockerfile"]:

        reasons.append(
            "Dockerfile present"
        )

    if not result["composer_json"]:

        reasons.append(
            "composer.json missing"
        )

    # ========================================================
    # FINAL ELIGIBILITY
    # ========================================================

    if not reasons:

        result[
            "eligibility_status"
        ] = "Eligible"

        result[
            "exclusion_reason"
        ] = ""

    else:

        result[
            "eligibility_status"
        ] = "Not Eligible"

        result[
            "exclusion_reason"
        ] = "; ".join(
            reasons
        )

    return result


# ============================================================
# EXCEL GENERATION
# ============================================================

def save_excel(result_df):

    summary = (
        result_df[
            "eligibility_status"
        ]
        .value_counts()
        .rename_axis(
            "eligibility_status"
        )
        .reset_index(
            name="count"
        )
    )

    summary["percentage"] = (
        summary["count"]
        / len(result_df)
    )

    # --------------------------------------------------------
    # Individual filter summary
    # --------------------------------------------------------

    filter_rows = []

    filter_columns = [
        "recent_activity",
        "composer_json",
        "composer_lock",
        "test_directory",
        "phpunit_config",
        "dockerfile",
    ]

    for column in filter_columns:

        counts = (
            result_df[column]
            .value_counts()
        )

        for value, count in counts.items():

            filter_rows.append({
                "filter": column,
                "value": value,
                "count": count,
                "percentage":
                    count / len(result_df)
            })

    filter_summary = pd.DataFrame(
        filter_rows
    )

    # --------------------------------------------------------
    # Exclusion reason summary
    # --------------------------------------------------------

    exclusion_summary = (
        result_df[
            "exclusion_reason"
        ]
        .replace(
            "",
            "Eligible"
        )
        .value_counts()
        .rename_axis(
            "exclusion_reason"
        )
        .reset_index(
            name="count"
        )
    )

    exclusion_summary["percentage"] = (
        exclusion_summary["count"]
        / len(result_df)
    )

    # --------------------------------------------------------
    # Eligible only
    # --------------------------------------------------------

    eligible = result_df[
        result_df[
            "eligibility_status"
        ] == "Eligible"
    ].copy()

    # --------------------------------------------------------
    # Excluded only
    # --------------------------------------------------------

    excluded = result_df[
        result_df[
            "eligibility_status"
        ] == "Not Eligible"
    ].copy()

    # --------------------------------------------------------
    # Save Excel
    # --------------------------------------------------------

    with pd.ExcelWriter(
        OUTPUT_EXCEL,
        engine="openpyxl"
    ) as writer:

        result_df.to_excel(
            writer,
            sheet_name="Eligibility Results",
            index=False
        )

        summary.to_excel(
            writer,
            sheet_name="Summary",
            index=False
        )

        filter_summary.to_excel(
            writer,
            sheet_name="Filter Summary",
            index=False
        )

        exclusion_summary.to_excel(
            writer,
            sheet_name="Exclusion Reasons",
            index=False
        )

        eligible.to_excel(
            writer,
            sheet_name="Eligible Projects",
            index=False
        )

        excluded.to_excel(
            writer,
            sheet_name="Excluded Projects",
            index=False
        )

    print(
        "Excel saved:",
        OUTPUT_EXCEL
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "LARAVEL ELIGIBILITY SCREENING"
    )
    print("=" * 60)

    df = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Input rows:",
        len(df)
    )

    # --------------------------------------------------------
    # Only confirmed Laravel applications
    # --------------------------------------------------------

    if "laravel_classification" in df.columns:

        df = df[
            df[
                "laravel_classification"
            ]
            == "Confirmed Laravel Application"
        ].copy()

    print(
        "Confirmed Laravel applications:",
        len(df)
    )

    # --------------------------------------------------------
    # Load GitHub metadata
    # --------------------------------------------------------

    enriched = pd.read_csv(
        ENRICHED_FILE
    )

    metadata_columns = [
        "repo_full_name",
        "pushed_at",
        "stars_github",
        "latest_sha",
        "url",
    ]

    metadata_columns = [
        c
        for c in metadata_columns
        if c in enriched.columns
    ]

    enriched = enriched[
        metadata_columns
    ].drop_duplicates(
        subset=[
            "repo_full_name"
        ]
    )

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    df = df.merge(
        enriched,
        on="repo_full_name",
        how="left",
        suffixes=(
            "",
            "_enriched"
        )
    )

    # --------------------------------------------------------
    # Checkpoint
    # --------------------------------------------------------

    if CHECKPOINT_FILE.exists():

        checkpoint = pd.read_csv(
            CHECKPOINT_FILE
        )

        processed = set(
            checkpoint[
                "repo_full_name"
            ]
        )

        results = checkpoint.to_dict(
            orient="records"
        )

        print(
            "Checkpoint found:",
            len(processed)
        )

    else:

        processed = set()

        results = []

        print(
            "No checkpoint found."
        )

    # --------------------------------------------------------
    # Processing
    # --------------------------------------------------------

    total = len(df)

    for i, (_, row) in enumerate(
        df.iterrows(),
        start=1
    ):

        repo = row[
            "repo_full_name"
        ]

        if repo in processed:

            continue

        print(
            f"[{i}/{total}] {repo}",
            flush=True
        )

        result = evaluate_repository(
            row
        )

        results.append(
            result
        )

        processed.add(
            repo
        )

        # ----------------------------------------------------
        # Checkpoint every 25
        # ----------------------------------------------------

        if len(results) % 25 == 0:

            checkpoint_df = (
                pd.DataFrame(
                    results
                )
            )

            checkpoint_df.to_csv(
                CHECKPOINT_FILE,
                index=False
            )

            print(
                f"Checkpoint saved: "
                f"{len(results)}"
            )

        time.sleep(
            0.2
        )

    # --------------------------------------------------------
    # Final dataframe
    # --------------------------------------------------------

    result_df = pd.DataFrame(
        results
    )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    result_df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    # Final checkpoint
    result_df.to_csv(
        CHECKPOINT_FILE,
        index=False
    )

    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    save_excel(
        result_df
    )

    # --------------------------------------------------------
    # Terminal summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "ELIGIBILITY SCREENING SUMMARY"
    )
    print("=" * 60)

    print(
        result_df[
            "eligibility_status"
        ].value_counts()
    )

    print()
    print(
        "=" * 60
    )

    print(
        "EXCLUSION REASONS"
    )

    print(
        "=" * 60
    )

    print(
        result_df[
            "exclusion_reason"
        ]
        .replace(
            "",
            "Eligible"
        )
        .value_counts()
    )

    print()
    print(
        "Eligible projects:",
        (
            result_df[
                "eligibility_status"
            ] == "Eligible"
        ).sum()
    )

    print(
        "CSV:",
        OUTPUT_CSV
    )

    print(
        "Excel:",
        OUTPUT_EXCEL
    )


if __name__ == "__main__":
    main()
