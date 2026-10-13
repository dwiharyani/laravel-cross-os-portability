#!/usr/bin/env python3
"""
Consolidate Stage 4 v2 execution artifacts.

This script is intentionally independent of GitHub Actions APIs. It consumes
downloaded execution artifact directories and produces:
- execution-level CSV
- repository-level portability CSV
- failure-level CSV
- LLM comparison bundles
- Excel workbook when pandas/openpyxl are available
"""

import csv, json, sys
from pathlib import Path
from collections import defaultdict

def main(root="stage4_collected", out="stage4_master"):
    root = Path(root)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for p in root.rglob("result.json"):
        try:
            results.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print("SKIP", p, e)

    if not results:
        raise RuntimeError("No result.json files found.")

    # Preserve every field observed across results.
    fields = sorted({k for r in results for k in r})
    with (out / "stage4_execution_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})

    by_repo = defaultdict(dict)
    for r in results:
        by_repo[r["repo_full_name"]][r["os"]] = r

    repo_rows = []
    for repo, osmap in sorted(by_repo.items()):
        statuses = {os: osmap.get(os, {}).get("reproducibility_status") for os in ["linux","windows","macos"]}
        valid = [v for v in statuses.values() if v is not None]
        repo_rows.append({
            "repo_full_name": repo,
            "latest_sha": next(iter(osmap.values())).get("latest_sha", ""),
            "linux_status": statuses["linux"],
            "windows_status": statuses["windows"],
            "macos_status": statuses["macos"],
            "os_executions_present": len(valid),
            "all_three_present": len(valid) == 3,
            "portable_all_os": len(valid) == 3 and all(v == "REPRODUCIBLE" for v in valid),
            "pass_count": sum(v == "REPRODUCIBLE" for v in valid),
            "failure_count": sum(v not in (None, "REPRODUCIBLE") for v in valid),
        })

    with (out / "stage4_repository_portability.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(repo_rows[0]))
        w.writeheader()
        w.writerows(repo_rows)

    failure_fields = [
        "execution_id","project_id","repo_full_name","latest_sha","os","runner",
        "failure_category","failure_stage","failure_detail","test_exit_code",
        "execution_validity","reproducibility_status",
    ]
    with (out / "stage4_failures.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=failure_fields)
        w.writeheader()
        for r in results:
            if r.get("failure_category") != "NONE":
                w.writerow({k: r.get(k, "") for k in failure_fields})

    comparison_dir = out / "llm_repository_comparisons"
    comparison_dir.mkdir(exist_ok=True)
    for repo, osmap in by_repo.items():
        safe = repo.replace("/", "__")
        bundle = {
            "repo_full_name": repo,
            "latest_sha": next(iter(osmap.values())).get("latest_sha", ""),
            "linux": osmap.get("linux"),
            "windows": osmap.get("windows"),
            "macos": osmap.get("macos"),
        }
        (comparison_dir / f"{safe}.json").write_text(
            json.dumps(bundle, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    try:
        import pandas as pd
        xlsx = out / "stage4_cross_os_results.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
            pd.DataFrame(results).to_excel(writer, sheet_name="Execution_Results", index=False)
            pd.DataFrame(repo_rows).to_excel(writer, sheet_name="Repository_Portability", index=False)
            pd.DataFrame(
                [r for r in results if r.get("failure_category") != "NONE"]
            ).to_excel(writer, sheet_name="Failures", index=False)
    except Exception as e:
        print("Excel export skipped:", e)

    print(f"Executions: {len(results)}")
    print(f"Repositories: {len(repo_rows)}")
    print(f"Output: {out}")

if __name__ == "__main__":
    main(*(sys.argv[1:] if len(sys.argv) > 1 else []))
