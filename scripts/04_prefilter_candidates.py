import argparse
from pathlib import Path
import pandas as pd


def normalize_bool(series):
    return (
        series
        .fillna(False)
        .astype(str)
        .str.strip()
        .str.lower()
        .map({
            "true": True,
            "false": False,
            "1": True,
            "0": False,
        })
        .fillna(False)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Pre-filter GitHub repositories before Laravel verification."
    )

    parser.add_argument(
        "input_csv",
        type=Path,
        help="GitHub enrichment CSV"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/laravel_candidates.csv"),
        help="Output candidate CSV"
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # Load data
    # ---------------------------------------------------------

    print(f"Loading: {args.input_csv}")

    df = pd.read_csv(args.input_csv)

    print(f"Original repositories: {len(df)}")

    # ---------------------------------------------------------
    # Normalize fields
    # ---------------------------------------------------------

    if "fork" in df.columns:
        df["fork"] = normalize_bool(df["fork"])

    if "archived" in df.columns:
        df["archived"] = normalize_bool(df["archived"])

    if "disabled" in df.columns:
        df["disabled"] = normalize_bool(df["disabled"])

    # ---------------------------------------------------------
    # 1. GitHub API success
    # ---------------------------------------------------------

    if "api_status" in df.columns:

        df_api = df[
            df["api_status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("SUCCESS")
        ].copy()

    else:

        print("WARNING: api_status column not found.")
        df_api = df.copy()

    print(f"After API accessibility filter: {len(df_api)}")

    # ---------------------------------------------------------
    # 2. Remove forks
    # ---------------------------------------------------------

    if "fork" in df_api.columns:

        df_no_fork = df_api[
            df_api["fork"] == False
        ].copy()

    else:

        df_no_fork = df_api.copy()

    print(f"After removing forks: {len(df_no_fork)}")

    # ---------------------------------------------------------
    # 3. Remove archived repositories
    # ---------------------------------------------------------

    if "archived" in df_no_fork.columns:

        df_active = df_no_fork[
            df_no_fork["archived"] == False
        ].copy()

    else:

        df_active = df_no_fork.copy()

    print(f"After removing archived repositories: {len(df_active)}")

    # ---------------------------------------------------------
    # 4. Remove disabled repositories
    # ---------------------------------------------------------

    if "disabled" in df_active.columns:

        df_enabled = df_active[
            df_active["disabled"] == False
        ].copy()

    else:

        df_enabled = df_active.copy()

    print(f"After removing disabled repositories: {len(df_enabled)}")

    # ---------------------------------------------------------
    # 5. Keep primarily PHP repositories
    # ---------------------------------------------------------

    if "language" in df_enabled.columns:

        df_php = df_enabled[
            df_enabled["language"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("php")
        ].copy()

    else:

        print("WARNING: language column not found.")
        df_php = df_enabled.copy()

    print(f"After PHP language filter: {len(df_php)}")

    # ---------------------------------------------------------
    # Keep metadata needed for later analysis
    # ---------------------------------------------------------

    keep_columns = [
        "project_id",
        "name",
        "url",
        "repo_full_name",
        "clone_url",
        "api_status",

        # Repository characteristics
        "stars",
        "stars_github",
        "forks_count",
        "open_issues",
        "watchers",
        "size_kb",

        # Repository metadata
        "description",
        "language",
        "license",
        "created_at",
        "updated_at",
        "pushed_at",
        "default_branch",
        "latest_sha",
        "github_id",
        "topics",

        # Screening information
        "fork",
        "archived",
        "disabled",
    ]

    keep_columns = [
        column
        for column in keep_columns
        if column in df_php.columns
    ]

    result = df_php[keep_columns].copy()

    # ---------------------------------------------------------
    # Save output
    # ---------------------------------------------------------

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result.to_csv(
        args.output,
        index=False
    )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("PRE-FILTER SUMMARY")
    print("=" * 60)

    print(f"Original repositories:       {len(df)}")
    print(f"API accessible:              {len(df_api)}")
    print(f"Non-fork:                    {len(df_no_fork)}")
    print(f"Non-archived:                {len(df_active)}")
    print(f"Enabled:                     {len(df_enabled)}")
    print(f"PHP repositories:            {len(result)}")

    print("=" * 60)

    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
