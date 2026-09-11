#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def as_bool(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def exclusion_reasons(row) -> list[str]:
    reasons = []
    if row.get("laravel_classification") != "Confirmed Laravel":
        reasons.append("not_confirmed_laravel")
    if as_bool(row.get("archived")):
        reasons.append("archived")
    if as_bool(row.get("fork")):
        reasons.append("fork")
    if not as_bool(row.get("tests_dir")):
        reasons.append("tests_missing")
    if not as_bool(row.get("composer_lock")):
        reasons.append("composer_lock_missing")
    return reasons


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply initial eligibility criteria to verified Laravel repositories."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument(
        "--output-all",
        type=Path,
        default=Path("data/interim/screened_projects.csv"),
    )
    parser.add_argument(
        "--output-eligible",
        type=Path,
        default=Path("data/final/eligible_projects.csv"),
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    reasons = df.apply(exclusion_reasons, axis=1)
    df["exclusion_reason"] = reasons.map(lambda x: ";".join(x))
    df["screening_status"] = reasons.map(
        lambda x: "Eligible" if len(x) == 0 else "Excluded"
    )

    args.output_all.parent.mkdir(parents=True, exist_ok=True)
    args.output_eligible.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_all, index=False)

    eligible = df[df["screening_status"] == "Eligible"].copy()
    eligible.to_csv(args.output_eligible, index=False)

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(args.csv),
        "screened": int(len(df)),
        "eligible": int(len(eligible)),
        "excluded": int((df["screening_status"] == "Excluded").sum()),
        "output_all": str(args.output_all),
        "output_eligible": str(args.output_eligible),
    }

    Path("logs").mkdir(exist_ok=True)
    Path("logs/eligibility_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
