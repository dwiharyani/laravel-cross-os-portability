import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd


def run_cmd(cmd, cwd, timeout=120):
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout[-4000:]
    except subprocess.TimeoutExpired as e:
        return False, f"TIMEOUT\n{e}"
    except Exception as e:
        return False, f"ERROR\n{e}"


def verify_repository(row, work_dir):
    repo = str(row["repo_full_name"])
    clone_url = str(row["clone_url"])

    result = {
        "project_id": row.get("project_id", ""),
        "repo_full_name": repo,
        "stars_github": row.get("stars_github", ""),
        "clone_status": "FAILED",
        "composer_json": False,
        "laravel_framework_require": False,
        "artisan": False,
        "app_dir": False,
        "bootstrap_dir": False,
        "config_dir": False,
        "routes_dir": False,
        "tests_dir": False,
        "composer_lock": False,
        "laravel_classification": "Clone Failed",
    }

    repo_dir = Path(work_dir) / "repo"

    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    ok, output = run_cmd(
        [
            "git",
            "clone",
            "--depth",
            "1",
            clone_url,
            str(repo_dir),
        ],
        cwd=work_dir,
        timeout=180,
    )

    if not ok:
        result["clone_error"] = output
        return result

    result["clone_status"] = "SUCCESS"

    # --------------------------------------------------
    # Structure checks
    # --------------------------------------------------

    result["composer_json"] = (repo_dir / "composer.json").is_file()
    result["artisan"] = (repo_dir / "artisan").is_file()
    result["app_dir"] = (repo_dir / "app").is_dir()
    result["bootstrap_dir"] = (repo_dir / "bootstrap").is_dir()
    result["config_dir"] = (repo_dir / "config").is_dir()
    result["routes_dir"] = (repo_dir / "routes").is_dir()
    result["tests_dir"] = (repo_dir / "tests").is_dir()
    result["composer_lock"] = (repo_dir / "composer.lock").is_file()

    # --------------------------------------------------
    # composer.json Laravel dependency check
    # --------------------------------------------------

    if result["composer_json"]:
        try:
            with open(repo_dir / "composer.json", "r", encoding="utf-8") as f:
                composer = json.load(f)

            require = composer.get("require", {})
            require_dev = composer.get("require-dev", {})

            dependencies = {}
            dependencies.update(require)
            dependencies.update(require_dev)

            result["laravel_framework_require"] = (
                "laravel/framework" in dependencies
            )

        except Exception as e:
            result["composer_error"] = str(e)

    # --------------------------------------------------
    # Classification
    # --------------------------------------------------

    if (
        result["composer_json"]
        and result["laravel_framework_require"]
        and result["artisan"]
        and result["app_dir"]
        and result["bootstrap_dir"]
        and result["config_dir"]
        and result["routes_dir"]
    ):
        result["laravel_classification"] = "Confirmed Laravel Application"

    elif (
        result["composer_json"]
        and result["laravel_framework_require"]
    ):
        result["laravel_classification"] = "Laravel Package/Incomplete"

    else:
        result["laravel_classification"] = "Not Laravel"

    # --------------------------------------------------
    # Cleanup cloned repository
    # --------------------------------------------------

    shutil.rmtree(repo_dir, ignore_errors=True)

    return result


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "input_csv",
        type=Path
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/interim/verified_laravel_apps.csv"
        )
    )

    parser.add_argument(
        "--start",
        type=int,
        default=0
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None
    )

    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)

    start = args.start

    if args.limit is None:
        end = len(df)
    else:
        end = min(
            start + args.limit,
            len(df)
        )

    subset = df.iloc[start:end]

    print(
        f"Processing repositories "
        f"{start + 1}-{end} of {len(df)}"
    )

    work_root = Path(
        tempfile.mkdtemp(
            prefix="laravel_verify_"
        )
    )

    results = []

    try:

        for i, (_, row) in enumerate(
            subset.iterrows(),
            start=start + 1
        ):

            print(
                f"[{i}/{len(df)}] "
                f"{row['repo_full_name']}",
                flush=True
            )

            result = verify_repository(
                row,
                work_root
            )

            results.append(result)

    finally:

        shutil.rmtree(
            work_root,
            ignore_errors=True
        )

    result_df = pd.DataFrame(results)

    # --------------------------------------------------
    # Append / create output
    # --------------------------------------------------

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if (
        start > 0
        and args.output.exists()
    ):
        old = pd.read_csv(args.output)
        result_df = pd.concat(
            [old, result_df],
            ignore_index=True
        )

    result_df.to_csv(
        args.output,
        index=False
    )

    print()
    print("=" * 60)
    print("LARAVEL VERIFICATION SUMMARY")
    print("=" * 60)

    print(
        result_df[
            "laravel_classification"
        ].value_counts()
    )

    print()
    print(
        f"Saved: {args.output}"
    )


if __name__ == "__main__":
    main()
