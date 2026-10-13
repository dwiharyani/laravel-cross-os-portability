#!/usr/bin/env python3
import csv
from pathlib import Path

ASSIGNMENT = Path("data/interim/stage4_two_person_execution_assignment_921.csv")
TARGET_REPO = "kbdxbt/kbframe"

with ASSIGNMENT.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

missing = [
    r for r in rows
    if not (r.get("php_version_constraint") or "").strip()
]

print("=" * 70)
print("PHP RUNTIME FREEZE AUDIT")
print("=" * 70)
print("Assignment repositories:", len(rows))
print("Repositories with explicit PHP constraint:", len(rows) - len(missing))
print("Repositories without explicit PHP constraint:", len(missing))

for r in missing:
    print(
        r.get("project_id"),
        r.get("repo_full_name"),
        "reason=missing_reproducible_php_runtime"
    )

assert any(r.get("repo_full_name") == TARGET_REPO for r in missing), \
    f"Expected {TARGET_REPO} to be identified"

expected = len(rows) - len(missing)
print()
print("Expected executable repositories:", expected)
print("Expected OS executions:", expected * 3)
print()
print("STATUS: RUNTIME FREEZE AUDIT COMPLETE")
