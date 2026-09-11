#!/usr/bin/env python3
import argparse
import hashlib
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a raw repository CSV without modifying it."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--rows", type=int, default=5)
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"File not found: {args.csv}")

    df = pd.read_csv(args.csv)

    print(f"File   : {args.csv}")
    print(f"Rows   : {len(df):,}")
    print(f"Columns: {len(df.columns)}")
    for column in df.columns:
        print(f"  - {column}")

    print(f"SHA256 : {sha256(args.csv)}")
    print("\nFirst rows:")
    print(df.head(args.rows).to_string(index=False))


if __name__ == "__main__":
    main()
