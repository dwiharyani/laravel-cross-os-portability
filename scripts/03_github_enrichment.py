import os
import time
import json
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# ==========================
# PATH CONFIGURATION
# ==========================

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT /
    "data/interim/pilot_input.csv"
)

OUTPUT_FILE = (
    ROOT /
    "data/interim/github_enriched.csv"
)


# ==========================
# GITHUB AUTH
# ==========================

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



# ==========================
# API FUNCTIONS
# ==========================

def github_get(url):

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

        return None


    except Exception as e:

        print(
            "Request error:",
            e
        )

        return None



def get_latest_sha(
    repo,
    branch
):

    url = (
        "https://api.github.com/repos/"
        f"{repo}/commits/{branch}"
    )


    data = github_get(url)


    if data:

        return data.get(
            "sha"
        )


    return None




def enrich_repository(
    repo
):

    url = (
        "https://api.github.com/repos/"
        f"{repo}"
    )


    data = github_get(url)


    if not data:

        return {

            "api_status":
                "FAILED"

        }


    branch = data.get(
        "default_branch"
    )


    sha = get_latest_sha(
        repo,
        branch
    )


    topics = github_get(
        url + "/topics"
    )


    return {


        "api_status":
            "SUCCESS",


        "github_id":
            data.get("id"),


        "full_name":
            data.get("full_name"),


        "archived":
            data.get("archived"),


        "fork":
            data.get("fork"),


        "disabled":
            data.get("disabled"),


        "default_branch":
            branch,


        "latest_sha":
            sha,


        "language":
            data.get("language"),


        "license":
            (
                data.get("license") or {}
            ).get("spdx_id"),


        "created_at":
            data.get("created_at"),


        "updated_at":
            data.get("updated_at"),


        "pushed_at":
            data.get("pushed_at"),


        "size_kb":
            data.get("size"),


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


        "topics":
            json.dumps(
                (topics or {}).get(
                    "names",
                    []
                )
            ),


        "clone_url":
            data.get(
                "clone_url"
            )

    }



# ==========================
# MAIN PROCESS
# ==========================

print(
    "Loading:",
    INPUT_FILE
)


df = pd.read_csv(
    INPUT_FILE
)


print(
    "Repositories:",
    len(df)
)



results = []


for idx, row in df.iterrows():


    repo = row["repo_full_name"]


    print(
        f"[{idx+1}/{len(df)}]",
        repo
    )


    metadata = enrich_repository(
        repo
    )


    results.append(
        {
            **row.to_dict(),
            **metadata
        }
    )


    # avoid rate-limit pressure

    time.sleep(
        0.5
    )



output = pd.DataFrame(
    results
)


OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


output.to_csv(
    OUTPUT_FILE,
    index=False
)


print("\nFinished")

print(
    "Saved:",
    OUTPUT_FILE
)


print(
    "Rows:",
    len(output)
)
