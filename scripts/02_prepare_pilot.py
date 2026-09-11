import argparse
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


def sha256(path):

    h = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):
            h.update(chunk)

    return h.hexdigest()



def normalize_github_url(url):

    """
    Convert:

    https://github.com/owner/repo

    into:

    owner/repo
    """

    if pd.isna(url):
        return None


    url = str(url).strip()


    parsed = urlparse(url)


    if parsed.hostname != "github.com":
        return None


    parts = parsed.path.strip("/").split("/")


    if len(parts) < 2:
        return None


    owner = parts[0]
    repo = parts[1]


    if repo.endswith(".git"):
        repo = repo[:-4]


    return f"{owner}/{repo}"



parser = argparse.ArgumentParser()


parser.add_argument(
    "csv",
    type=Path
)


parser.add_argument(
    "--repo-column",
    default="url"
)


parser.add_argument(
    "--n",
    type=int,
    default=100
)


parser.add_argument(
    "--seed",
    type=int,
    default=2026
)


args = parser.parse_args()



df = pd.read_csv(args.csv)


print("Original rows:", len(df))


if args.repo_column not in df.columns:

    raise ValueError(
        f"Column {args.repo_column} not found.\n"
        f"Available columns:\n{list(df.columns)}"
    )



# Create normalized repository name

df["repo_full_name"] = (
    df[args.repo_column]
    .apply(normalize_github_url)
)



# Remove invalid URLs

df = df[
    df["repo_full_name"].notna()
]


# Remove duplicate repositories

df = df.drop_duplicates(
    subset=["repo_full_name"]
)


print(
    "Valid repositories:",
    len(df)
)



# Random sampling

pilot = df.sample(
    n=min(args.n, len(df)),
    random_state=args.seed
)



# Create project ID

pilot = pilot.reset_index(drop=True)


pilot.insert(
    0,
    "project_id",
    [
        f"P{i+1:03d}"
        for i in range(len(pilot))
    ]
)



# Add clone URL

pilot["clone_url"] = (
    "https://github.com/"
    + pilot["repo_full_name"]
    + ".git"
)



output = Path(
    "data/interim/pilot_input.csv"
)


output.parent.mkdir(
    exist_ok=True
)



pilot.to_csv(
    output,
    index=False
)



manifest = {

    "source_file":
        str(args.csv),

    "source_sha256":
        sha256(args.csv),

    "source_rows":
        len(pd.read_csv(args.csv)),

    "valid_unique_repositories":
        len(df),

    "pilot_n":
        len(pilot),

    "random_seed":
        args.seed,

    "repository_column":
        args.repo_column,

    "output_file":
        str(output)

}



print("\n")
for k,v in manifest.items():
    print(
        f"{k}: {v}"
    )


print(
    "\nCreated:",
    output
)
