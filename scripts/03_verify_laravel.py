#!/usr/bin/env python3
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

API = "https://api.github.com"
API_VERSION = "2022-11-28"


def request_with_retry(session, url, params=None, retries=4):
    response = None
    for attempt in range(retries):
        response = session.get(url, params=params, timeout=30)
        if response.status_code not in (403, 429):
            return response

        retry_after = response.headers.get("Retry-After")
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")

        if retry_after:
            wait = int(retry_after)
        elif remaining == "0" and reset:
            wait = max(1, int(reset) - int(time.time()) + 2)
        else:
            wait = min(60, 5 * (2**attempt))

        print(f"Rate limited (HTTP {response.status_code}); sleeping {wait}s")
        time.sleep(wait)

    return response


def get_json(response):
    try:
        return response.json()
    except Exception:
        return None


def get_root_entries(session, full_name, ref):
    response = request_with_retry(
        session,
        f"{API}/repos/{full_name}/contents",
        params={"ref": ref},
    )
    if response is None or response.status_code != 200:
        return None, None if response is None else response.status_code

    data = get_json(response)
    if not isinstance(data, list):
        return None, response.status_code

    return {item.get("name"): item for item in data}, response.status_code


def get_raw_file(session, full_name, path, ref):
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "Authorization": session.headers.get("Authorization", ""),
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "Laravel-Portability-Research-Pilot",
    }
    response = requests.get(
        f"{API}/repos/{full_name}/contents/{path}",
        params={"ref": ref},
        headers=headers,
        timeout=30,
    )
    if response.status_code != 200:
        return None, response.status_code
    return response.text, response.status_code


def get_commit_sha(session, full_name, ref):
    response = request_with_retry(session, f"{API}/repos/{full_name}/commits/{ref}")
    if response is None or response.status_code != 200:
        return None
    data = get_json(response) or {}
    return data.get("sha")


def main() -> None:
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is missing. Copy .env.example to .env and add your token."
        )

    parser = argparse.ArgumentParser(
        description="Verify Laravel evidence for repositories in the pilot sample."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/verified_laravel.csv"),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    if "repo_full_name" not in df.columns:
        raise SystemExit(
            "Input does not contain repo_full_name. Run 02_prepare_pilot.py first."
        )
    if args.limit:
        df = df.head(args.limit).copy()

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "Laravel-Portability-Research-Pilot",
        }
    )

    records = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Verifying repositories"):
        full_name = str(row["repo_full_name"])
        record = {
            "project_id": row.get("project_id", ""),
            "repo_full_name": full_name,
            "repo_url": f"https://github.com/{full_name}",
            "accessible": False,
            "archived": None,
            "fork": None,
            "stars": None,
            "default_branch": None,
            "pushed_at": None,
            "frozen_sha": None,
            "composer_json": False,
            "laravel_framework_require": False,
            "laravel_framework_require_dev": False,
            "artisan": False,
            "app_dir": False,
            "bootstrap_dir": False,
            "config_dir": False,
            "routes_dir": False,
            "tests_dir": False,
            "composer_lock": False,
            "phpunit_config": False,
            "pest_dependency": False,
            "laravel_classification": "Unreachable",
            "verification_note": "",
        }

        meta_response = request_with_retry(session, f"{API}/repos/{full_name}")
        if meta_response is None or meta_response.status_code != 200:
            code = None if meta_response is None else meta_response.status_code
            record["verification_note"] = f"Repository metadata HTTP {code}"
            records.append(record)
            continue

        meta = get_json(meta_response) or {}
        record["accessible"] = True
        record["archived"] = bool(meta.get("archived"))
        record["fork"] = bool(meta.get("fork"))
        record["stars"] = meta.get("stargazers_count")
        record["default_branch"] = meta.get("default_branch")
        record["pushed_at"] = meta.get("pushed_at")

        ref = record["default_branch"]
        if not ref:
            record["verification_note"] = "No default branch"
            records.append(record)
            continue

        root, status = get_root_entries(session, full_name, ref)
        if root is None:
            record["verification_note"] = f"Root contents HTTP {status}"
            records.append(record)
            continue

        names = set(root)
        record["composer_json"] = "composer.json" in names
        record["artisan"] = "artisan" in names
        record["app_dir"] = root.get("app", {}).get("type") == "dir"
        record["bootstrap_dir"] = root.get("bootstrap", {}).get("type") == "dir"
        record["config_dir"] = root.get("config", {}).get("type") == "dir"
        record["routes_dir"] = root.get("routes", {}).get("type") == "dir"
        record["tests_dir"] = root.get("tests", {}).get("type") == "dir"
        record["composer_lock"] = "composer.lock" in names
        record["phpunit_config"] = (
            "phpunit.xml" in names or "phpunit.xml.dist" in names
        )

        composer = {}
        if record["composer_json"]:
            text, _ = get_raw_file(session, full_name, "composer.json", ref)
            if text:
                try:
                    composer = json.loads(text)
                except json.JSONDecodeError:
                    record["verification_note"] = "composer.json is invalid JSON"

        require = composer.get("require", {}) or {}
        require_dev = composer.get("require-dev", {}) or {}
        record["laravel_framework_require"] = "laravel/framework" in require
        record["laravel_framework_require_dev"] = "laravel/framework" in require_dev
        record["pest_dependency"] = any(
            key == "pestphp/pest" or key.startswith("pestphp/pest-plugin")
            for key in require_dev
        )

        conventional_dirs = sum(
            [
                record["app_dir"],
                record["bootstrap_dir"],
                record["config_dir"],
                record["routes_dir"],
            ]
        )

        if (
            record["laravel_framework_require"]
            and record["artisan"]
            and conventional_dirs >= 2
        ):
            record["laravel_classification"] = "Confirmed Laravel"
            record["frozen_sha"] = get_commit_sha(session, full_name, ref)
        elif (
            record["laravel_framework_require"]
            or record["laravel_framework_require_dev"]
        ):
            record["laravel_classification"] = "Needs Review"
        else:
            record["laravel_classification"] = "Not Laravel"

        records.append(record)
        time.sleep(args.delay)

    out = pd.DataFrame(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(args.csv),
        "output_file": str(args.output),
        "repositories_checked": int(len(out)),
        "accessible": int(out["accessible"].fillna(False).sum()),
        "confirmed_laravel": int(
            (out["laravel_classification"] == "Confirmed Laravel").sum()
        ),
        "needs_review": int(
            (out["laravel_classification"] == "Needs Review").sum()
        ),
        "not_laravel": int(
            (out["laravel_classification"] == "Not Laravel").sum()
        ),
        "api_version": API_VERSION,
        "criteria_version": "pilot-v1",
    }

    Path("logs").mkdir(exist_ok=True)
    Path("logs/verification_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
