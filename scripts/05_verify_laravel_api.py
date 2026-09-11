import os
import time
import json
import base64
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = ROOT / "data/interim/laravel_candidates.csv"

CHECKPOINT_FILE = (
    ROOT / "data/interim/verification_api_checkpoint.csv"
)

OUTPUT_FILE = (
    ROOT / "data/interim/verified_laravel_apps.csv"
)

load_dotenv(ROOT / ".env")

TOKEN = os.getenv("GITHUB_TOKEN")

if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN is not configured.")


HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Authorization": f"Bearer {TOKEN}",
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# API REQUEST
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
                            int(reset) - int(time.time()) + 2
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
# TREE
# ============================================================

def get_tree(repo, sha):

    url = (
        f"https://api.github.com/repos/"
        f"{repo}/git/trees/{sha}"
        f"?recursive=1"
    )

    return github_get(url)


# ============================================================
# FILE
# ============================================================

def get_file(repo, sha, path):

    url = (
        f"https://api.github.com/repos/"
        f"{repo}/contents/{path}"
        f"?ref={sha}"
    )

    return github_get(url)


def decode_content(data):

    if not data:
        return None

    content = data.get("content")

    if not content:
        return None

    try:

        return base64.b64decode(
            content
        ).decode(
            "utf-8",
            errors="replace"
        )

    except Exception:

        return None


# ============================================================
# VERIFY REPOSITORY
# ============================================================

def verify_repository(row):

    repo = row["repo_full_name"]
    sha = row["latest_sha"]

    result = {
        "project_id": row.get("project_id", ""),
        "name": row.get("name", ""),
        "repo_full_name": repo,
        "url": row.get("url", ""),
        "stars_github": row.get("stars_github", ""),
        "latest_sha": sha,

        "api_verification": "FAILED",

        "composer_json": False,
        "laravel_framework_require": False,

        "artisan": False,
        "app_dir": False,
        "bootstrap_dir": False,
        "config_dir": False,
        "routes_dir": False,
        "tests_dir": False,

        "laravel_classification":
            "API Verification Failed",
    }

    # --------------------------------------------------------
    # TREE
    # --------------------------------------------------------

    tree_data = get_tree(
        repo,
        sha
    )

    if not tree_data:

        return result

    result["api_verification"] = "SUCCESS"

    tree = tree_data.get(
        "tree",
        []
    )

    paths = {
        item.get("path", "")
        for item in tree
        if item.get("path")
    }

    # --------------------------------------------------------
    # STRUCTURE
    # --------------------------------------------------------

    result["composer_json"] = (
        "composer.json" in paths
    )

    result["artisan"] = (
        "artisan" in paths
    )

    result["app_dir"] = any(
        p == "app"
        or p.startswith("app/")
        for p in paths
    )

    result["bootstrap_dir"] = any(
        p == "bootstrap"
        or p.startswith("bootstrap/")
        for p in paths
    )

    result["config_dir"] = any(
        p == "config"
        or p.startswith("config/")
        for p in paths
    )

    result["routes_dir"] = any(
        p == "routes"
        or p.startswith("routes/")
        for p in paths
    )

    result["tests_dir"] = any(
        p == "tests"
        or p.startswith("tests/")
        for p in paths
    )

    # --------------------------------------------------------
    # COMPOSER
    # --------------------------------------------------------

    if result["composer_json"]:

        composer_data = get_file(
            repo,
            sha,
            "composer.json"
        )

        composer_text = decode_content(
            composer_data
        )

        if composer_text:

            try:

                composer = json.loads(
                    composer_text
                )

                require = composer.get(
                    "require",
                    {}
                )

                require_dev = composer.get(
                    "require-dev",
                    {}
                )

                dependencies = {}

                dependencies.update(
                    require
                )

                dependencies.update(
                    require_dev
                )

                result[
                    "laravel_framework_require"
                ] = (
                    "laravel/framework"
                    in dependencies
                )

            except json.JSONDecodeError:

                pass

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    if (
        result["composer_json"]
        and
        result["laravel_framework_require"]
        and
        result["artisan"]
        and
        result["app_dir"]
        and
        result["bootstrap_dir"]
        and
        result["config_dir"]
        and
        result["routes_dir"]
    ):

        result[
            "laravel_classification"
        ] = (
            "Confirmed Laravel Application"
        )

    elif (
        result["composer_json"]
        and
        result["laravel_framework_require"]
    ):

        result[
            "laravel_classification"
        ] = (
            "Laravel Package/Incomplete"
        )

    else:

        result[
            "laravel_classification"
        ] = "Not Laravel"

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("LARAVEL API VERIFICATION")
    print("=" * 60)

    df = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Input repositories:",
        len(df)
    )

    # --------------------------------------------------------
    # Load checkpoint
    # --------------------------------------------------------

    if CHECKPOINT_FILE.exists():

        checkpoint = pd.read_csv(
            CHECKPOINT_FILE
        )

        processed = set(
            checkpoint["repo_full_name"]
        )

        results = checkpoint.to_dict(
            orient="records"
        )

        print(
            "Checkpoint found:",
            len(processed),
            "repositories already processed"
        )

    else:

        checkpoint = pd.DataFrame()

        processed = set()

        results = []

        print(
            "No checkpoint found."
        )

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    total = len(df)

    for i, (_, row) in enumerate(
        df.iterrows(),
        start=1
    ):

        repo = row["repo_full_name"]

        if repo in processed:

            continue

        print(
            f"[{i}/{total}] {repo}",
            flush=True
        )

        result = verify_repository(
            row
        )

        results.append(
            result
        )

        processed.add(repo)

        # ----------------------------------------------------
        # Save checkpoint every 25 repositories
        # ----------------------------------------------------

        if len(results) % 25 == 0:

            checkpoint_df = pd.DataFrame(
                results
            )

            checkpoint_df.to_csv(
                CHECKPOINT_FILE,
                index=False
            )

            print(
                f"Checkpoint saved: "
                f"{len(results)} repositories"
            )

        # Small delay
        time.sleep(0.2)

    # --------------------------------------------------------
    # Final save
    # --------------------------------------------------------

    result_df = pd.DataFrame(
        results
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    # Save final checkpoint too
    result_df.to_csv(
        CHECKPOINT_FILE,
        index=False
    )

    print()
    print("=" * 60)
    print("LARAVEL API VERIFICATION SUMMARY")
    print("=" * 60)

    print(
        result_df[
            "laravel_classification"
        ].value_counts()
    )

    print()
    print("API status:")

    print(
        result_df[
            "api_verification"
        ].value_counts()
    )

    print()
    print(
        "Total processed:",
        len(result_df)
    )

    print(
        "Saved:",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
