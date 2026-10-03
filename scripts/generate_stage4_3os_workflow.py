import csv
import json
from pathlib import Path

INPUT = Path("data/interim/stage4_cross_os_matrix.csv")
OUTPUT = Path(".github/workflows/reproducibility-cross-os.yml")

rows = list(csv.DictReader(
    INPUT.open(encoding="utf-8", newline="")
))

if len(rows) != 279:
    raise RuntimeError(
        f"Expected 279 rows, found {len(rows)}"
    )

OS_CONFIG = {
    "linux": "ubuntu-22.04",
    "windows": "windows-2022",
    "macos": "macos-15",
}

workflow = """name: Stage 4 Cross-OS Portability

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
"""

for os_name, runner in OS_CONFIG.items():

    os_rows = [
        r for r in rows
        if r["os"] == os_name
    ]

    if len(os_rows) != 93:
        raise RuntimeError(
            f"{os_name}: expected 93 rows, found {len(os_rows)}"
        )

    job_name = f"run-{os_name}"

    workflow += f"""
  {job_name}:

    strategy:
      fail-fast: false
      max-parallel: 12

      matrix:
        include:
"""

    for r in os_rows:

        item = {
            "repo_index": int(r["repo_index"]),
            "repo_full_name": r["repo_full_name"],
            "url": (
                r.get("url")
                or f"https://github.com/{r['repo_full_name']}"
            ),
            "latest_sha": r["latest_sha"],
            "php_runtime": r["php_runtime"],
            "laravel_version_constraint":
                r.get("laravel_version_constraint", ""),
            "test_command":
                r.get("test_command", ""),
            "test_command_source":
                r.get("test_command_source", ""),
            "os": os_name,
            "runner": runner,
        }

        workflow += (
            "          - "
            + json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":")
            )
            + "\n"
        )

    workflow += f"""
    runs-on: ${{{{ matrix.runner }}}}
    continue-on-error: true

    name: "{os_name} / ${{{{ matrix.repo_index }}}} / ${{{{ matrix.repo_full_name }}}}"

    steps:

      - name: Checkout methodology repository
        uses: actions/checkout@v4

      - name: Setup PHP
        uses: shivammathur/setup-php@v2
        continue-on-error: true
        with:
          php-version: ${{{{ matrix.php_runtime }}}}
          tools: composer:v2
          coverage: none

      - name: Verify runtime
        continue-on-error: true
        shell: bash
        run: |
          echo "Repository: ${{{{ matrix.repo_full_name }}}}"
          echo "OS: ${{{{ matrix.os }}}}"
          echo "PHP requested: ${{{{ matrix.php_runtime }}}}"
          php -v || true
          composer --version || true

      - name: Run exact-commit reproducibility protocol
        continue-on-error: true
        shell: bash
        env:
          STAGE4_REPO: ${{{{ matrix.repo_full_name }}}}
          STAGE4_URL: ${{{{ matrix.url }}}}
          STAGE4_SHA: ${{{{ matrix.latest_sha }}}}
          STAGE4_PHP: ${{{{ matrix.php_runtime }}}}
          STAGE4_LARAVEL: ${{{{ matrix.laravel_version_constraint }}}}
          STAGE4_TEST_COMMAND: ${{{{ matrix.test_command }}}}
          STAGE4_OS: ${{{{ matrix.os }}}}
          STAGE4_RUNNER: ${{{{ matrix.runner }}}}
        run: |
          python scripts/14_cross_os_reproducibility.py

      - name: Save result
        if: always()
        shell: bash
        env:
          STAGE4_REPO: ${{{{ matrix.repo_full_name }}}}
          STAGE4_SHA: ${{{{ matrix.latest_sha }}}}
          STAGE4_OS: ${{{{ matrix.os }}}}
          STAGE4_RUNNER: ${{{{ matrix.runner }}}}
          STAGE4_PHP: ${{{{ matrix.php_runtime }}}}
        run: |
          RESULT="stage4_result_${{{{ matrix.repo_index }}}}_${{{{ matrix.os }}}}.json"

          if [ -f stage4_result.json ]; then
            cp stage4_result.json "$RESULT"
          else
            python - <<'PYINNER'
          import json
          import os

          result = {{
              "repo_full_name": os.environ["STAGE4_REPO"],
              "latest_sha": os.environ["STAGE4_SHA"],
              "os": os.environ["STAGE4_OS"],
              "runner": os.environ["STAGE4_RUNNER"],
              "php_runtime_requested":
                  os.environ["STAGE4_PHP"],
              "reproducibility_status": "FAILED",
              "failure_category": "INFRASTRUCTURE",
              "failure_stage": "RUNTIME_SETUP",
              "failure_detail":
                  "Protocol did not produce stage4_result.json."
          }}

          with open(
              "$RESULT",
              "w",
              encoding="utf-8"
          ) as f:
              json.dump(result, f, indent=2)
          PYINNER
          fi

      - name: Upload execution result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: stage4-{os_name}-${{{{ matrix.repo_index }}}}
          path: stage4_result_${{{{ matrix.repo_index }}}}_{os_name}.json
          if-no-files-found: error
          retention-days: 90

"""

workflow += """
  consolidate:

    needs:
      - run-linux
      - run-windows
      - run-macos

    if: always()

    runs-on: ubuntu-22.04

    steps:

      - name: Checkout methodology repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install consolidation dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pandas openpyxl

      - name: Download all Stage 4 results
        uses: actions/download-artifact@v4
        with:
          pattern: stage4-*
          path: stage4_artifacts
          merge-multiple: true

      - name: Consolidate 279 executions
        shell: bash
        run: |
          python - <<'PY'
          import glob
          import json
          import pandas as pd

          files = sorted(
              glob.glob(
                  "stage4_artifacts/stage4_result_*.json"
              )
          )

          print("Result files:", len(files))

          if len(files) != 279:
              raise RuntimeError(
                  f"Expected 279 result files, found {len(files)}"
              )

          rows = []

          for filename in files:
              with open(filename, encoding="utf-8") as f:
                  rows.append(json.load(f))

          df = pd.DataFrame(rows)

          df.to_csv(
              "stage4_cross_os_results.csv",
              index=False
          )

          pivot = df.pivot_table(
              index=[
                  "repo_full_name",
                  "latest_sha"
              ],
              columns="os",
              values="reproducibility_status",
              aggfunc="first"
          ).reset_index()

          for os_name in ["linux", "windows", "macos"]:
              if os_name not in pivot.columns:
                  pivot[os_name] = "MISSING"

          def classify(row):

              values = [
                  str(row[x]).upper()
                  for x in [
                      "linux",
                      "windows",
                      "macos"
                  ]
              ]

              if all(
                  x == "REPRODUCIBLE"
                  for x in values
              ):
                  return "ALL_OS_REPRODUCIBLE"

              if (
                  values[0] == "REPRODUCIBLE"
                  and values[1] == "FAILED"
                  and values[2] == "REPRODUCIBLE"
              ):
                  return "WINDOWS_FAILURE"

              if (
                  values[0] == "REPRODUCIBLE"
                  and values[1] == "REPRODUCIBLE"
                  and values[2] == "FAILED"
              ):
                  return "MACOS_FAILURE"

              if (
                  values[0] == "FAILED"
                  and values[1] == "REPRODUCIBLE"
                  and values[2] == "REPRODUCIBLE"
              ):
                  return "LINUX_FAILURE"

              if values.count("FAILED") >= 2:
                  return "MULTI_OS_FAILURE"

              return "INCOMPLETE_OR_OTHER"

          pivot["cross_os_status"] = pivot.apply(
              classify,
              axis=1
          )

          pivot.to_csv(
              "stage4_cross_os_portability.csv",
              index=False
          )

          summary = pd.DataFrame(
              [
                  ["Repositories", len(pivot)],
                  ["OS executions", len(df)],
                  [
                      "Linux executions",
                      (df["os"] == "linux").sum()
                  ],
                  [
                      "Windows executions",
                      (df["os"] == "windows").sum()
                  ],
                  [
                      "macOS executions",
                      (df["os"] == "macos").sum()
                  ],
                  [
                      "All three OS reproducible",
                      (
                          pivot["cross_os_status"]
                          == "ALL_OS_REPRODUCIBLE"
                      ).sum()
                  ],
                  [
                      "Windows-specific failure",
                      (
                          pivot["cross_os_status"]
                          == "WINDOWS_FAILURE"
                      ).sum()
                  ],
                  [
                      "macOS-specific failure",
                      (
                          pivot["cross_os_status"]
                          == "MACOS_FAILURE"
                      ).sum()
                  ],
                  [
                      "Linux-specific failure",
                      (
                          pivot["cross_os_status"]
                          == "LINUX_FAILURE"
                      ).sum()
                  ],
                  [
                      "Multi-OS failure",
                      (
                          pivot["cross_os_status"]
                          == "MULTI_OS_FAILURE"
                      ).sum()
                  ],
              ],
              columns=["metric", "count"]
          )

          summary.to_csv(
              "stage4_cross_os_summary.csv",
              index=False
          )

          with pd.ExcelWriter(
              "stage4_cross_os_results.xlsx",
              engine="openpyxl"
          ) as writer:

              df.to_excel(
                  writer,
                  sheet_name="OS_Executions",
                  index=False
              )

              pivot.to_excel(
                  writer,
                  sheet_name="Cross_OS_Portability",
                  index=False
              )

              summary.to_excel(
                  writer,
                  sheet_name="Summary",
                  index=False
              )

          print(summary.to_string(index=False))
          print("Execution rows:", len(df))
          print("Repository rows:", len(pivot))
          PY

      - name: Upload consolidated Stage 4 results
        uses: actions/upload-artifact@v4
        with:
          name: stage4-final-results
          path: |
            stage4_cross_os_results.csv
            stage4_cross_os_portability.csv
            stage4_cross_os_summary.csv
            stage4_cross_os_results.xlsx
          retention-days: 90
"""

OUTPUT.write_text(workflow, encoding="utf-8")

print("Generated:", OUTPUT)
print("Total rows:", len(rows))
print("Linux:", sum(r["os"] == "linux" for r in rows))
print("Windows:", sum(r["os"] == "windows" for r in rows))
print("macOS:", sum(r["os"] == "macos" for r in rows))
