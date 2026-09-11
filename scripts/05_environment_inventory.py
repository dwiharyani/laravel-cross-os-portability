import json
import subprocess
import shutil
from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

WORK = ROOT / "work"
OUTPUT = ROOT / "data/interim/environment_inventory.csv"


def run(cmd, cwd):
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.stdout.strip()
    except:
        return ""


def clone_project(repo, sha, folder):

    if folder.exists():
        shutil.rmtree(folder)

    folder.parent.mkdir(exist_ok=True)

    subprocess.run(
        [
            "git",
            "clone",
            repo,
            str(folder)
        ],
        stdout=subprocess.DEVNULL
    )

    subprocess.run(
        [
            "git",
            "checkout",
            sha
        ],
        cwd=folder,
        stdout=subprocess.DEVNULL
    )


def read_json(path):

    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


def analyze(project):

    folder = WORK / project.project_id

    clone_project(
        project.repo_url,
        project.frozen_sha,
        folder
    )


    composer = read_json(
        folder/"composer.json"
    )


    require = composer.get(
        "require",
        {}
    )

    dev = composer.get(
        "require-dev",
        {}
    )


    scripts = composer.get(
        "scripts",
        {}
    )


    # PHP

    php_version = require.get(
        "php",
        ""
    )


    laravel = require.get(
        "laravel/framework",
        ""
    )


    # Testing detection

    framework=""

    if "pestphp/pest" in dev:
        framework="Pest"

    elif "phpunit/phpunit" in dev:
        framework="PHPUnit"


    if "test" in scripts:
        test_command="composer test"

    elif (folder/"artisan").exists():
        test_command="php artisan test"

    elif framework=="Pest":
        test_command="vendor/bin/pest"

    elif framework=="PHPUnit":
        test_command="vendor/bin/phpunit"

    else:
        test_command=""


    # Frontend

    package = folder/"package.json"

    frontend=False

    manager=""

    lock=""


    if package.exists():

        frontend=True

        if (folder/"package-lock.json").exists():
            manager="npm"
            lock="package-lock"

        elif (folder/"yarn.lock").exists():
            manager="yarn"
            lock="yarn"

        elif (folder/"pnpm-lock.yaml").exists():
            manager="pnpm"
            lock="pnpm"

        else:
            manager="npm"
            lock="none"


    return {

        "project_id":project.project_id,

        "repo":project.repo_full_name,

        "sha":project.frozen_sha,

        "php_requirement":php_version,

        "laravel_version":laravel,

        "test_framework":framework,

        "test_command":test_command,

        "frontend_required":frontend,

        "frontend_manager":manager,

        "frontend_lock":lock

    }



df=pd.read_csv(
    ROOT/"data/final/eligible_projects.csv"
)


results=[]


for _,row in df.iterrows():

    print(
        "Analyzing",
        row.project_id
    )

    results.append(
        analyze(row)
    )


out=pd.DataFrame(results)


OUTPUT.parent.mkdir(
    exist_ok=True
)

out.to_csv(
    OUTPUT,
    index=False
)


print(
    "\nSaved:",
    OUTPUT
)
