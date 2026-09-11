import json
import subprocess
import shutil
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT = (
    ROOT /
    "data/interim/github_enriched.csv"
)

OUTPUT = (
    ROOT /
    "data/interim/verified_laravel_apps.csv"
)

WORK = (
    ROOT /
    "work/verification"
)


def clone_repo(url, folder):

    if folder.exists():
        shutil.rmtree(folder)

    folder.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result = subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            url,
            str(folder)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return result.returncode == 0



def read_json(path):

    try:
        with open(path) as f:
            return json.load(f)

    except:

        return {}



def verify(row):

    folder = WORK / row.project_id


    result = {

        **row.to_dict(),

        "composer_json": False,

        "laravel_dependency": False,

        "artisan": False,

        "app_dir": False,

        "bootstrap_dir": False,

        "config_dir": False,

        "routes_dir": False,

        "tests_dir": False,

        "classification":
            "Rejected"

    }


    # metadata filter

    if row.archived or row.fork:

        return result



    if not clone_repo(
        row.clone_url,
        folder
    ):

        result["classification"] = (
            "Clone Failed"
        )

        return result



    composer_file = (
        folder /
        "composer.json"
    )


    if composer_file.exists():

        result["composer_json"] = True


    composer = read_json(
        composer_file
    )


    require = composer.get(
        "require",
        {}
    )


    if "laravel/framework" in require:

        result[
            "laravel_dependency"
        ] = True



    for key in [
        "artisan",
        "app",
        "bootstrap",
        "config",
        "routes",
        "tests"
    ]:

        if (
            folder / key
        ).exists():

            result[
                key + "_dir"
                if key != "artisan"
                else "artisan"
            ] = True



    application_score = sum(
        [
            result["composer_json"],
            result["laravel_dependency"],
            result["artisan"],
            result["app_dir"],
            result["bootstrap_dir"],
            result["config_dir"],
            result["routes_dir"],
            result["tests_dir"]
        ]
    )



    if application_score >= 7:

        result[
            "classification"
        ] = "Confirmed Laravel Application"


    elif result["laravel_dependency"]:

        result[
            "classification"
        ] = "Laravel Package/Incomplete"


    return result



df = pd.read_csv(
    INPUT
)


results=[]


for i,row in df.iterrows():

    print(
        f"[{i+1}/{len(df)}]",
        row.repo_full_name
    )


    results.append(
        verify(row)
    )



out = pd.DataFrame(
    results
)


OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True
)


out.to_csv(
    OUTPUT,
    index=False
)


print()
print(
    "Saved:",
    OUTPUT
)


print(
    out.classification.value_counts()
)
