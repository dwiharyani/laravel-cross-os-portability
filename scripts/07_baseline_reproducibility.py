import os
import time
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT / "data/interim/eligible_laravel_apps_pilot20.csv"
)

OUTPUT_FILE = (
    ROOT / "data/interim/baseline_reproducibility.csv"
)

CHECKPOINT_FILE = (
    ROOT / "data/interim/baseline_checkpoint.csv"
)

LOG_DIR = (
    ROOT / "logs/baseline"
)

WORK_DIR = (
    ROOT / "work/baseline"
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)

WORK_DIR.mkdir(
    parents=True,
    exist_ok=True
)

load_dotenv(
    ROOT / ".env"
)

TOKEN = os.getenv(
    "GITHUB_TOKEN"
)

if not TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN is not configured."
    )


HEADERS = {
    "Accept":
        "application/vnd.github+json",

    "X-GitHub-Api-Version":
        "2022-11-28",

    "Authorization":
        f"Bearer {TOKEN}",
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# SETTINGS
# ============================================================

COMPOSER_TIMEOUT = 600
PHPUNIT_TIMEOUT = 600

MAX_SOURCE_SIZE_MB = 500


# ============================================================
# GITHUB API
# ============================================================

def github_get(
    url,
    retries=3
):

    for attempt in range(
        1,
        retries + 1
    ):

        try:

            response = session.get(
                url,
                timeout=60
            )

            if response.status_code == 200:
                return response.json()

            if response.status_code == 404:
                return None

            if response.status_code in (
                403,
                429
            ):

                reset = (
                    response.headers.get(
                        "X-RateLimit-Reset"
                    )
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
                    f"Rate limit. "
                    f"Waiting {wait}s..."
                )

                time.sleep(
                    wait
                )

                continue

            print(
                "GitHub API error:",
                response.status_code,
                url
            )

        except requests.RequestException as e:

            print(
                f"GitHub request error "
                f"{attempt}/{retries}:",
                repr(e)
            )

            time.sleep(
                5 * attempt
            )

    return None


# ============================================================
# DOWNLOAD SOURCE ARCHIVE
# ============================================================

def download_repository(
    repo,
    sha,
    destination
):

    url = (
        f"https://api.github.com/repos/"
        f"{repo}/tarball/{sha}"
    )

    archive = destination / "repo.tar.gz"

    try:

        with session.get(
            url,
            stream=True,
            timeout=120
        ) as response:

            if response.status_code != 200:

                return False, (
                    f"GitHub archive HTTP "
                    f"{response.status_code}"
                )

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length:

                size_mb = (
                    int(content_length)
                    / 1024
                    / 1024
                )

                if size_mb > MAX_SOURCE_SIZE_MB:

                    return False, (
                        f"Repository archive "
                        f"too large: "
                        f"{size_mb:.1f} MB"
                    )

            with open(
                archive,
                "wb"
            ) as f:

                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):

                    if chunk:
                        f.write(chunk)

        # ----------------------------------------------------
        # Extract
        # ----------------------------------------------------

        extract_dir = destination / "source"

        extract_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        result = subprocess.run(
            [
                "tar",
                "-xzf",
                str(archive),
                "-C",
                str(extract_dir),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:

            return False, (
                "Archive extraction failed: "
                + result.stderr[-1000:]
            )

        # GitHub tarballs normally contain
        # one top-level directory.
        directories = [
            p
            for p in extract_dir.iterdir()
            if p.is_dir()
        ]

        if len(directories) != 1:

            return False, (
                "Unexpected archive structure"
            )

        source_dir = directories[0]

        return True, source_dir

    except Exception as e:

        return False, repr(e)


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(
    command,
    cwd,
    timeout
):

    start = time.time()

    try:

        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        duration = (
            time.time()
            - start
        )

        return {
            "returncode":
                result.returncode,

            "stdout":
                result.stdout,

            "stderr":
                result.stderr,

            "duration":
                duration,

            "timeout":
                False,
        }

    except subprocess.TimeoutExpired as e:

        duration = (
            time.time()
            - start
        )

        return {
            "returncode":
                None,

            "stdout":
                e.stdout or "",

            "stderr":
                e.stderr or "",

            "duration":
                duration,

            "timeout":
                True,
        }

    except Exception as e:

        return {
            "returncode":
                None,

            "stdout":
                "",

            "stderr":
                repr(e),

            "duration":
                time.time()
                - start,

            "timeout":
                False,
        }


# ============================================================
# FIND PHPUNIT
# ============================================================

def find_phpunit(
    source_dir
):

    candidates = [
        source_dir / "vendor/bin/phpunit",
        source_dir / "vendor/bin/phpunit.bat",
    ]

    for path in candidates:

        if path.exists():

            return path

    return None


# ============================================================
# BASELINE TEST
# ============================================================

def run_baseline(
    row
):

    repo = row[
        "repo_full_name"
    ]

    sha = row[
        "latest_sha"
    ]

    result = {
        "repo_full_name":
            repo,

        "latest_sha":
            sha,

        "source_download":
            "FAILED",

        "composer_install":
            "NOT_RUN",

        "phpunit_execution":
            "NOT_RUN",

        "tests_discovered":
            None,

        "tests_executed":
            None,

        "baseline_status":
            "FAILED",

        "failure_category":
            "",

        "composer_duration_sec":
            None,

        "phpunit_duration_sec":
            None,

        "log_file":
            "",
    }

    # --------------------------------------------------------
    # Working directory
    # --------------------------------------------------------

    safe_name = (
        repo.replace(
            "/",
            "__"
        )
        .replace(
            "\\",
            "__"
        )
    )

    project_dir = (
        WORK_DIR / safe_name
    )

    if project_dir.exists():

        shutil.rmtree(
            project_dir
        )

    project_dir.mkdir(
        parents=True
    )

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    print(
        "  Downloading source..."
    )

    ok, source_or_error = (
        download_repository(
            repo,
            sha,
            project_dir
        )
    )

    if not ok:

        result[
            "failure_category"
        ] = "Source Download Failure"

        result[
            "log_file"
        ] = ""

        return result

    source_dir = source_or_error

    result[
        "source_download"
    ] = "SUCCESS"

    # --------------------------------------------------------
    # Composer
    # --------------------------------------------------------

    composer_json = (
        source_dir
        / "composer.json"
    )

    if not composer_json.exists():

        result[
            "failure_category"
        ] = "Missing composer.json"

        return result

    print(
        "  Running composer install..."
    )

    composer_result = run_command(
        [
            "composer",
            "install",
            "--no-interaction",
            "--prefer-dist",
            "--no-progress",
        ],
        source_dir,
        COMPOSER_TIMEOUT
    )

    result[
        "composer_duration_sec"
    ] = round(
        composer_result[
            "duration"
        ],
        2
    )

    # --------------------------------------------------------
    # Composer failure
    # --------------------------------------------------------

    if (
        composer_result["timeout"]
    ):

        result[
            "composer_install"
        ] = "TIMEOUT"

        result[
            "failure_category"
        ] = "Composer Timeout"

    elif (
        composer_result["returncode"]
        != 0
    ):

        result[
            "composer_install"
        ] = "FAILED"

        result[
            "failure_category"
        ] = "Dependency Failure"

    else:

        result[
            "composer_install"
        ] = "SUCCESS"

    # --------------------------------------------------------
    # Save composer log
    # --------------------------------------------------------

    log_file = (
        LOG_DIR
        / f"{safe_name}.log"
    )

    with open(
        log_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "=== COMPOSER STDOUT ===\n"
        )

        f.write(
            composer_result[
                "stdout"
            ]
            or ""
        )

        f.write(
            "\n\n=== COMPOSER STDERR ===\n"
        )

        f.write(
            composer_result[
                "stderr"
            ]
            or ""
        )

    result[
        "log_file"
    ] = str(
        log_file
    )

    # --------------------------------------------------------
    # Stop if Composer failed
    # --------------------------------------------------------

    if (
        result[
            "composer_install"
        ] != "SUCCESS"
    ):

        return result

    # --------------------------------------------------------
    # PHPUnit
    # --------------------------------------------------------

    phpunit = find_phpunit(
        source_dir
    )

    if phpunit is None:

        result[
            "failure_category"
        ] = (
            "PHPUnit Not Available"
        )

        return result

    print(
        "  Running PHPUnit..."
    )

    phpunit_result = run_command(
        [
            str(phpunit),
            "--testdox",
        ],
        source_dir,
        PHPUNIT_TIMEOUT
    )

    result[
        "phpunit_duration_sec"
    ] = round(
        phpunit_result[
            "duration"
        ],
        2
    )

    # --------------------------------------------------------
    # Save PHPUnit output
    # --------------------------------------------------------

    with open(
        log_file,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n\n=== PHPUNIT STDOUT ===\n"
        )

        f.write(
            phpunit_result[
                "stdout"
            ]
            or ""
        )

        f.write(
            "\n\n=== PHPUNIT STDERR ===\n"
        )

        f.write(
            phpunit_result[
                "stderr"
            ]
            or ""
        )

    # --------------------------------------------------------
    # PHPUnit classification
    # --------------------------------------------------------

    if phpunit_result[
        "timeout"
    ]:

        result[
            "phpunit_execution"
        ] = "TIMEOUT"

        result[
            "failure_category"
        ] = "PHPUnit Timeout"

        return result

    if phpunit_result[
        "returncode"
    ] == 0:

        result[
            "phpunit_execution"
        ] = "SUCCESS"

        result[
            "baseline_status"
        ] = "BASELINE PASS"

        result[
            "failure_category"
        ] = ""

    else:

        result[
            "phpunit_execution"
        ] = "FAILED"

        result[
            "failure_category"
        ] = (
            "Test Execution Failure"
        )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "BASELINE REPRODUCIBILITY"
    )
    print("=" * 60)

    df = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Projects:",
        len(df)
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
            "Checkpoint:",
            len(processed)
        )

    else:

        processed = set()

        results = []

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    for i, (_, row) in enumerate(
        df.iterrows(),
        start=1
    ):

        repo = row[
            "repo_full_name"
        ]

        if repo in processed:
            continue

        print()
        print(
            f"[{i}/{len(df)}] {repo}"
        )

        result = run_baseline(
            row
        )

        results.append(
            result
        )

        processed.add(
            repo
        )

        # ----------------------------------------------------
        # Checkpoint every 5
        # ----------------------------------------------------

        if len(results) % 5 == 0:

            pd.DataFrame(
                results
            ).to_csv(
                CHECKPOINT_FILE,
                index=False
            )

            print(
                "Checkpoint saved:",
                len(results)
            )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    result_df = pd.DataFrame(
        results
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    result_df.to_csv(
        CHECKPOINT_FILE,
        index=False
    )

    print()
    print("=" * 60)
    print(
        "BASELINE SUMMARY"
    )
    print("=" * 60)

    print(
        result_df[
            "baseline_status"
        ].value_counts()
    )

    print()
    print(
        "Failure categories:"
    )

    print(
        result_df[
            "failure_category"
        ]
        .replace(
            "",
            "None"
        )
        .value_counts()
    )

    print()
    print(
        "Saved:",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
