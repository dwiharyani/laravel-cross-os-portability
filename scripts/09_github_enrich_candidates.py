#!/usr/bin/env python3

"""
09_github_enrich_candidates.py

Purpose:
    Re-fetch GitHub repository metadata for the frozen
    Cross-OS candidate set.

Input:
    data/interim/cross_os_candidates.csv

Output:
    data/interim/github_candidates_enriched.csv

This script does NOT perform Laravel screening again.

It only retrieves GitHub metadata needed for the
Cross-OS reproducibility stage, especially:

    - default_branch
    - latest_sha
    - pushed_at
    - updated_at
    - archived
    - fork
    - disabled
    - language
    - license
    - stars
    - forks
    - repository size

The latest SHA is required so that the reproducibility
experiment can test the exact repository state recorded
during screening.
"""

import os
import time
import json
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# PATH CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT /
    "data/interim/cross_os_candidates.csv"
)

OUTPUT_FILE = (
    ROOT /
    "data/interim/github_candidates_enriched.csv"
)


# ============================================================
# GITHUB AUTHENTICATION
# ============================================================

load_dotenv()

TOKEN = os.getenv(
    "GITHUB_TOKEN"
)


HEADERS = {
    "Accept":
        "application/vnd.github+json",

    "X-GitHub-Api-Version":
        "2022-11-28"
}


if TOKEN:

    HEADERS["Authorization"] = (
        f"Bearer {TOKEN}"
    )


# ============================================================
# GITHUB API
# ============================================================

def github_get(url):
    """
    Request one GitHub API endpoint.

    Returns:
        Parsed JSON object on success.
        None on failure.
    """

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code == 200:

            return response.json()

        print(
            "API failed:",
            response.status_code,
            url
        )

        if response.status_code == 403:

            print(
                "Possible GitHub rate limit or "
                "authentication problem."
            )

        return None

    except Exception as exc:

        print(
            "Request error:",
            repr(exc)
        )

        return None


# ============================================================
# REPOSITORY METADATA
# ============================================================

def enrich_repository(repo):

    """
    Retrieve repository-level metadata
    from GitHub.
    """

    api_url = (
        "https://api.github.com/repos/"
        f"{repo}"
    )

    data = github_get(
        api_url
    )

    if not data:

        return {
            "repo_full_name": repo,
            "github_api_status": "FAILED",
            "latest_sha": None,
            "pushed_at": None,
            "updated_at": None,
            "default_branch": None,
            "archived": None,
            "fork": None,
            "disabled": None,
            "language": None,
            "license": None,
            "stars_github": None,
            "forks_count": None,
            "open_issues": None,
            "watchers": None,
            "size_kb": None,
        }


    # --------------------------------------------------------
    # Repository metadata
    # --------------------------------------------------------

    default_branch = (
        data.get(
            "default_branch"
        )
    )

    license_data = data.get(
        "license"
    )

    if isinstance(
        license_data,
        dict
    ):

        license_name = (
            license_data.get(
                "spdx_id"
            )
        )

    else:

        license_name = None


    # --------------------------------------------------------
    # Latest commit SHA
    # --------------------------------------------------------

    latest_sha = None

    if default_branch:

        commits_url = (
            "https://api.github.com/repos/"
            f"{repo}/commits/"
            f"{default_branch}"
        )

        commit_data = github_get(
            commits_url
        )

        if commit_data:

            latest_sha = (
                commit_data.get(
                    "sha"
                )
            )


    return {

        "repo_full_name":
            repo,

        "github_api_status":
            "SUCCESS",

        "latest_sha":
            latest_sha,

        "pushed_at":
            data.get(
                "pushed_at"
            ),

        "updated_at":
            data.get(
                "updated_at"
            ),

        "default_branch":
            default_branch,

        "archived":
            data.get(
                "archived"
            ),

        "fork":
            data.get(
                "fork"
            ),

        "disabled":
            data.get(
                "disabled"
            ),

        "language":
            data.get(
                "language"
            ),

        "license":
            license_name,

        "stars_github":
            data.get(
                "stargazers_count"
            ),

        "forks_count":
            data.get(
                "forks_count"
            ),

        "open_issues":
            data.get(
                "open_issues_count"
            ),

        "watchers":
            data.get(
                "watchers_count"
            ),

        "size_kb":
            data.get(
                "size"
            ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "GITHUB ENRICHMENT FOR "
        "CROSS-OS CANDIDATES"
    )

    print("=" * 70)


    # --------------------------------------------------------
    # Check input
    # --------------------------------------------------------

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Input file not found: "
            f"{INPUT_FILE}"
        )


    # --------------------------------------------------------
    # Load candidates
    # --------------------------------------------------------

    candidates = pd.read_csv(
        INPUT_FILE
    )

    candidates = (
        candidates
        .drop_duplicates(
            subset=[
                "repo_full_name"
            ]
        )
        .reset_index(
            drop=True
        )
    )


    print(
        "Input candidates:",
        len(candidates)
    )

    print(
        "Unique repositories:",
        candidates[
            "repo_full_name"
        ].nunique()
    )


    # --------------------------------------------------------
    # Check GitHub token
    # --------------------------------------------------------

    if TOKEN:

        print(
            "GitHub authentication: "
            "TOKEN AVAILABLE"
        )

    else:

        print(
            "GitHub authentication: "
            "NO TOKEN"
        )

        print(
            "Warning: unauthenticated GitHub "
            "API requests have stricter rate limits."
        )


    # --------------------------------------------------------
    # Enrichment
    # --------------------------------------------------------

    records = []


    for index, row in candidates.iterrows():

        repo = str(
            row[
                "repo_full_name"
            ]
        ).strip()


        print(
            f"[{index + 1}/"
            f"{len(candidates)}] "
            f"{repo}"
        )


        metadata = enrich_repository(
            repo
        )


        records.append(
            metadata
        )


        # Small delay to reduce API pressure
        time.sleep(
            0.15
        )


    # --------------------------------------------------------
    # Convert to DataFrame
    # --------------------------------------------------------

    github_df = pd.DataFrame(
        records
    )


    # --------------------------------------------------------
    # Merge with original candidate data
    # --------------------------------------------------------

    enriched = candidates.merge(
        github_df,
        on="repo_full_name",
        how="left",
        validate="one_to_one",
        suffixes=(
            "",
            "_github"
        )
    )


    # --------------------------------------------------------
    # Replace old GitHub fields
    # --------------------------------------------------------

    github_fields = [
        "latest_sha",
        "pushed_at",
        "updated_at",
        "default_branch",
        "archived",
        "fork",
        "disabled",
        "language",
        "license",
        "stars_github",
        "forks_count",
        "open_issues",
        "watchers",
        "size_kb",
    ]


    for field in github_fields:

        github_field = (
            f"{field}_github"
        )

        if github_field in enriched.columns:

            # Use newly retrieved GitHub data.
            enriched[field] = (
                enriched[
                    github_field
                ]
            )

            enriched = (
                enriched.drop(
                    columns=[
                        github_field
                    ]
                )
            )


    # --------------------------------------------------------
    # Save output
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    enriched.to_csv(
        OUTPUT_FILE,
        index=False
    )


    # --------------------------------------------------------
    # Quality checks
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "ENRICHMENT QUALITY CHECK"
    )

    print("=" * 70)


    print(
        "Rows:",
        len(enriched)
    )


    print(
        "Unique repositories:",
        enriched[
            "repo_full_name"
        ].nunique()
    )


    print(
        "Missing latest_sha:",
        enriched[
            "latest_sha"
        ].isna().sum()
    )


    print(
        "Missing pushed_at:",
        enriched[
            "pushed_at"
        ].isna().sum()
    )


    print(
        "GitHub API failures:",
        (
            enriched[
                "github_api_status"
            ]
            != "SUCCESS"
        ).sum()
    )


    print()
    print(
        "First 10 repositories:"
    )


    print(
        enriched[
            [
                "repo_full_name",
                "latest_sha",
                "pushed_at",
                "default_branch",
            ]
        ]
        .head(10)
        .to_string(
            index=False
        )
    )


    print()
    print(
        "OUTPUT:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":

    main()
