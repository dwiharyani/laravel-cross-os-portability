
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ============================================================
# PROJECT PATH
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

WORKBOOK = (
    ROOT
    / "data/interim/laravel_eligibility_results.xlsx"
)


# ============================================================
# VALIDATE INPUT
# ============================================================

if not WORKBOOK.exists():
    raise FileNotFoundError(
        f"Workbook not found: {WORKBOOK}"
    )


# ============================================================
# LOAD EXISTING WORKBOOK
# ============================================================

wb = load_workbook(WORKBOOK)


print("=" * 70)
print("UPDATING RESEARCH CONTROL WORKBOOK")
print("=" * 70)

print("Workbook:")
print(WORKBOOK)

print()
print("Existing sheets:")
for sheet in wb.sheetnames:
    print("-", sheet)


# ============================================================
# DOCUMENTATION SHEETS TO CREATE
# ============================================================

DOCUMENTATION_SHEETS = [
    "Measurement Dictionary",
    "Outcome Taxonomy",
    "Experiment Matrix",
    "Reproducibility Protocol",
    "Cross-OS Protocol",
    "Evidence & Artifact Map",
    "Analysis Plan",
    "Stage1_Runtime_Pilot",
    "Stage1_Failure_Evidence",
    "Stage1_Repeatability",
    "Stage1_Summary",
]


# ============================================================
# REMOVE OLD VERSIONS OF THESE SHEETS
# This makes the script safe to run again.
# ============================================================

for sheet_name in DOCUMENTATION_SHEETS:

    if sheet_name in wb.sheetnames:

        del wb[sheet_name]

        print(
            f"Removed previous sheet: {sheet_name}"
        )


# ============================================================
# EXCEL STYLING
# ============================================================

HEADER_FILL = PatternFill(
    "solid",
    fgColor="1F4E78"
)

HEADER_FONT = Font(
    color="FFFFFF",
    bold=True
)

TITLE_FONT = Font(
    bold=True,
    size=14
)

BOLD_FONT = Font(
    bold=True
)

THIN_SIDE = Side(
    style="thin",
    color="D9E1F2"
)

BORDER = Border(
    left=THIN_SIDE,
    right=THIN_SIDE,
    top=THIN_SIDE,
    bottom=THIN_SIDE
)


# ============================================================
# HELPER FUNCTION
# ============================================================

def create_sheet(
    sheet_name,
    title,
    purpose,
    headers,
    rows,
    widths
):

    ws = wb.create_sheet(sheet_name)

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    ws["A1"] = title
    ws["A1"].font = TITLE_FONT

    ws.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=len(headers)
    )

    # --------------------------------------------------------
    # Purpose
    # --------------------------------------------------------

    ws["A2"] = "Purpose"
    ws["A2"].font = BOLD_FONT

    ws["B2"] = purpose

    ws.merge_cells(
        start_row=2,
        start_column=2,
        end_row=2,
        end_column=len(headers)
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    header_row = 4

    for column_index, header in enumerate(
        headers,
        start=1
    ):

        cell = ws.cell(
            row=header_row,
            column=column_index,
            value=header
        )

        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True
        )

        cell.border = BORDER

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    for row_index, row in enumerate(
        rows,
        start=header_row + 1
    ):

        for column_index, value in enumerate(
            row,
            start=1
        ):

            cell = ws.cell(
                row=row_index,
                column=column_index,
                value=value
            )

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True
            )

            cell.border = BORDER

    # --------------------------------------------------------
    # Freeze header
    # --------------------------------------------------------

    ws.freeze_panes = "A5"

    # --------------------------------------------------------
    # Filter
    # --------------------------------------------------------

    last_row = max(
        header_row,
        header_row + len(rows)
    )

    last_column = get_column_letter(
        len(headers)
    )

    ws.auto_filter.ref = (
        f"A{header_row}:"
        f"{last_column}{last_row}"
    )

    # --------------------------------------------------------
    # Column widths
    # --------------------------------------------------------

    for index, width in enumerate(
        widths,
        start=1
    ):

        ws.column_dimensions[
            get_column_letter(index)
        ].width = width

    return ws


# ============================================================
# 1. MEASUREMENT DICTIONARY
# ============================================================

measurement_rows = [

    [
        "repo_full_name",
        "GitHub repository identifier.",
        "Identifier",
        "text",
        "GitHub metadata",
        "Stages 1-7",
        "Multiple scripts/workflows"
    ],

    [
        "url",
        "Repository URL.",
        "Identifier",
        "URL",
        "GitHub metadata",
        "Stages 1-7",
        "Multiple scripts/workflows"
    ],

    [
        "latest_sha",
        "Exact commit used to freeze the repository state.",
        "Experimental control",
        "40-character SHA",
        "GitHub API",
        "Stages 3-7",
        "09_github_enrich_candidates.py"
    ],

    [
        "default_branch",
        "Repository default branch.",
        "Repository metadata",
        "text",
        "GitHub API",
        "Stage 3",
        "09_github_enrich_candidates.py"
    ],

    [
        "php_version_constraint",
        "PHP version requirement declared by the project.",
        "Environment",
        "Composer constraint",
        "composer.json",
        "Stage 2",
        "08_environment_inventory.py"
    ],

    [
        "laravel_version_constraint",
        "Laravel framework requirement declared by the project.",
        "Environment",
        "Composer constraint",
        "composer.json",
        "Stage 2",
        "08_environment_inventory.py"
    ],

    [
        "testing_mechanism",
        "Detected mechanism used to execute project tests.",
        "Environment",
        "categorical",
        "Repository files",
        "Stages 2-7",
        "Inventory / workflow"
    ],

    [
        "os",
        "Operating system used for an execution.",
        "Experimental",
        "categorical",
        "GitHub runner",
        "Stages 5-7",
        "Cross-OS workflow"
    ],

    [
        "os_version",
        "Operating-system version reported by the runner.",
        "Experimental",
        "text",
        "Runner",
        "Stages 5-7",
        "Cross-OS workflow"
    ],

    [
        "php_version_actual",
        "Actual PHP runtime version used.",
        "Experimental",
        "version",
        "Runner",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "composer_version_actual",
        "Actual Composer version used.",
        "Experimental",
        "version",
        "Runner",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "php_extensions",
        "PHP extensions available in the execution environment.",
        "Environment",
        "list",
        "Runner",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "platform_check",
        "Whether Composer platform requirements are satisfied.",
        "Outcome",
        "PASS / FAIL",
        "Composer",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "composer_install",
        "Whether dependencies can be installed from the locked dependency set.",
        "Outcome",
        "PASS / FAIL",
        "Composer",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "runtime_execution",
        "Whether the Laravel application reaches the intended execution stage.",
        "Outcome",
        "PASS / FAIL",
        "Application / Artisan",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "test_execution",
        "Whether the project's test command can be executed.",
        "Outcome",
        "PASS / FAIL",
        "PHPUnit / Pest / etc.",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "test_pass",
        "Whether the executed tests pass.",
        "Outcome",
        "PASS / FAIL",
        "Test runner",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "portability_outcome",
        "Overall reproducibility or portability classification.",
        "Outcome",
        "categorical",
        "Derived from evidence",
        "Stages 4-9",
        "Analysis script"
    ],

    [
        "failure_stage",
        "Stage at which a failure occurs.",
        "Failure characterization",
        "categorical",
        "Execution logs",
        "Stages 4-9",
        "Analysis script"
    ],

    [
        "failure_cause",
        "Technical cause assigned to a failure.",
        "Failure characterization",
        "categorical",
        "Logs + evidence",
        "Stages 4-9",
        "Analysis script"
    ],

    [
        "os_specific",
        "Whether the failure is specifically associated with an OS under controlled comparison.",
        "Cross-OS outcome",
        "YES / NO / UNDETERMINED",
        "Cross-OS comparison",
        "Stages 5-9",
        "Analysis script"
    ],

    [
        "installation_time",
        "Elapsed time for dependency installation.",
        "Performance",
        "seconds",
        "Workflow log",
        "Stages 4-7",
        "Workflow"
    ],

    [
        "test_execution_time",
        "Elapsed time for test execution.",
        "Performance",
        "seconds",
        "Workflow log",
        "Stages 4-7",
        "Workflow"
    ],
]


create_sheet(
    "Measurement Dictionary",
    "Measurement Dictionary - Variables, Definitions, Sources and Scripts",
    "Defines every major variable measured during repository screening, reproducibility testing and the cross-OS experiment.",
    [
        "Variable",
        "Definition",
        "Type",
        "Unit / Values",
        "Source",
        "Stage",
        "Code / Workflow"
    ],
    measurement_rows,
    [28, 58, 24, 25, 28, 18, 38]
)


# ============================================================
# 2. OUTCOME TAXONOMY
# ============================================================

taxonomy_rows = [

    [
        "REPRODUCIBLE",
        "Installation, application execution and tests complete successfully under the specified protocol.",
        "Overall outcome",
        "All required checks pass."
    ],

    [
        "PARTIALLY_REPRODUCIBLE",
        "The repository can be reproduced only up to a specified point, or succeeds in one environment/OS but not another.",
        "Overall outcome",
        "At least one required step differs or fails while meaningful execution evidence exists."
    ],

    [
        "NON-REPRODUCIBLE",
        "The repository cannot reach the required reproducibility endpoint under the tested environment.",
        "Overall outcome",
        "Required execution cannot be completed."
    ],

    [
        "NONE",
        "No failure occurred.",
        "Failure stage",
        "Use when execution is successful."
    ],

    [
        "PLATFORM_CHECK",
        "Failure while validating PHP or Composer platform requirements.",
        "Failure stage",
        "Composer platform validation fails."
    ],

    [
        "INSTALLATION",
        "Failure while resolving or installing dependencies.",
        "Failure stage",
        "Composer installation fails."
    ],

    [
        "RUNTIME",
        "Failure after installation when the application is being executed.",
        "Failure stage",
        "Application, bootstrap or runtime error."
    ],

    [
        "TEST",
        "Failure during test execution or test-result evaluation.",
        "Failure stage",
        "Tests cannot execute or tests fail."
    ],

    [
        "PHP_VERSION",
        "Required PHP version is incompatible with the selected runtime.",
        "Failure cause",
        "Version constraint conflict."
    ],

    [
        "PHP_EXTENSION",
        "A required PHP extension is unavailable or disabled.",
        "Failure cause",
        "Required extension is missing."
    ],

    [
        "DEPENDENCY",
        "A dependency cannot be installed or used because of compatibility constraints.",
        "Failure cause",
        "Dependency or lock-file incompatibility."
    ],

    [
        "PRIVATE_DEPENDENCY",
        "A dependency is unavailable because its package source or repository is private or inaccessible.",
        "Failure cause",
        "Package access problem."
    ],

    [
        "FILESYSTEM",
        "Behavior depends on filesystem semantics that differ across environments.",
        "Failure cause",
        "Filesystem-related evidence."
    ],

    [
        "PATH",
        "Failure is related to path handling, separators, case or path assumptions.",
        "Failure cause",
        "Path-related evidence."
    ],

    [
        "PERMISSION",
        "Execution fails because of file or directory permissions.",
        "Failure cause",
        "Permission-related evidence."
    ],

    [
        "CONFIGURATION",
        "Failure is caused by environment or application configuration differences.",
        "Failure cause",
        "Configuration evidence."
    ],

    [
        "NETWORK",
        "Execution fails because required network access is unavailable or different.",
        "Failure cause",
        "Network-related evidence."
    ],

    [
        "OTHER",
        "A documented cause that does not fit the predefined categories.",
        "Failure cause",
        "Supporting evidence must be recorded."
    ],

    [
        "YES",
        "Failure is observed on one OS while controlled comparison environments succeed.",
        "OS-specific",
        "Cross-OS evidence supports OS specificity."
    ],

    [
        "NO",
        "Failure occurs independently of OS or is explained by a common environment constraint.",
        "OS-specific",
        "Evidence does not support OS specificity."
    ],

    [
        "UNDETERMINED",
        "Evidence is insufficient to attribute the failure specifically to OS.",
        "OS-specific",
        "Do not infer OS causality."
    ],
]


create_sheet(
    "Outcome Taxonomy",
    "Outcome Taxonomy - Outcome, Failure Stage, Failure Cause and OS Specificity",
    "Defines how execution outcomes and technical failures will be classified consistently.",
    [
        "Code",
        "Definition",
        "Dimension",
        "Decision rule / evidence"
    ],
    taxonomy_rows,
    [25, 65, 25, 60]
)


# ============================================================
# 3. EXPERIMENT MATRIX
# ============================================================

experiment_rows = [

    [
        "R01",
        "Reproducibility Pilot",
        20,
        "Representative pilot repositories",
        "Linux",
        "Same repository SHA; PHP selected from declared compatibility",
        "Pilot reproducibility results",
        "DONE"
    ],

    [
        "R02",
        "Cross-OS Pilot",
        20,
        "Same 20 pilot repositories",
        "Ubuntu + Windows + macOS",
        "Same SHA and controlled PHP / Composer where feasible",
        "60 executions",
        "NEXT"
    ],

    [
        "R03",
        "Full Cross-OS Experiment",
        555,
        "All eligible repositories",
        "Ubuntu + Windows + macOS",
        "Controlled execution protocol",
        "1,665 executions",
        "NOT STARTED"
    ],

    [
        "R04",
        "Failure Analysis",
        "All executions",
        "Experiment outputs",
        "All tested OS",
        "Apply final taxonomy consistently",
        "Coded failure dataset",
        "NOT STARTED"
    ],
]


create_sheet(
    "Experiment Matrix",
    "Experiment Matrix - Experimental Units and OS Coverage",
    "Defines the experimental units, OS configurations and planned execution counts.",
    [
        "Experiment ID",
        "Experiment",
        "Repositories",
        "Repository Selection",
        "OS",
        "Control Conditions",
        "Expected Output",
        "Status"
    ],
    experiment_rows,
    [16, 28, 18, 35, 30, 58, 32, 18]
)


# ============================================================
# 4. REPRODUCIBILITY PROTOCOL
# ============================================================

reproducibility_rows = [

    [
        "R1",
        "Freeze repository",
        "Record repository name and exact SHA before execution.",
        "Repository + SHA",
        "09_github_enrich_candidates.py",
        "DONE"
    ],

    [
        "R2",
        "Validate project metadata",
        "Read Composer and Laravel constraints and testing infrastructure.",
        "Environment metadata",
        "08_environment_inventory.py",
        "DONE"
    ],

    [
        "R3",
        "Prepare pilot",
        "Select representative repositories across major environment groups.",
        "20 pilot repositories",
        "09_reproducibility_check.py",
        "DONE"
    ],

    [
        "R4",
        "Provision runtime",
        "Run the project in a controlled execution environment.",
        "PHP + Composer runtime",
        "GitHub Actions workflow",
        "DONE / PILOT"
    ],

    [
        "R5",
        "Check platform",
        "Run Composer platform checks before installation where applicable.",
        "Platform result",
        "Workflow",
        "DONE / PILOT"
    ],

    [
        "R6",
        "Install dependencies",
        "Attempt dependency installation using the locked dependency set.",
        "Installation result + logs",
        "Workflow",
        "DONE / PILOT"
    ],

    [
        "R7",
        "Execute application",
        "Attempt application or bootstrap execution where required.",
        "Runtime result",
        "Workflow",
        "PILOT PROTOCOL"
    ],

    [
        "R8",
        "Execute tests",
        "Run the detected or declared test command.",
        "Test result",
        "Workflow",
        "PILOT PROTOCOL"
    ],

    [
        "R9",
        "Classify outcome",
        "Assign portability outcome, failure stage and failure cause from evidence.",
        "Coded outcome",
        "Analysis script",
        "NEXT"
    ],

    [
        "R10",
        "Preserve evidence",
        "Store logs, metadata and artifacts so results can be audited.",
        "Execution artifacts",
        "GitHub Actions",
        "NEXT"
    ],
]


create_sheet(
    "Reproducibility Protocol",
    "Reproducibility Protocol - Controlled Execution Procedure",
    "Documents exactly how a repository moves from a frozen commit to dependency installation, application execution and testing.",
    [
        "Step",
        "Activity",
        "Procedure",
        "Measured Output",
        "Code / Tool",
        "Status"
    ],
    reproducibility_rows,
    [14, 28, 60, 34, 38, 22]
)


# ============================================================
# 5. CROSS-OS PROTOCOL
# ============================================================

cross_os_rows = [

    [
        "C1",
        "Same repository",
        "Use the same repository for every OS comparison.",
        "Repository ID",
        "Required"
    ],

    [
        "C2",
        "Same commit",
        "Use the same exact SHA across OS runs.",
        "latest_sha",
        "Required"
    ],

    [
        "C3",
        "PHP control",
        "Use the same compatible PHP version across OS where technically feasible and record the actual version.",
        "php_version_actual",
        "Required"
    ],

    [
        "C4",
        "Composer control",
        "Use the same Composer version policy and record the actual version.",
        "composer_version_actual",
        "Required"
    ],

    [
        "C5",
        "Dependency control",
        "Use the repository lock file where available and do not silently update dependencies.",
        "composer.lock / install result",
        "Required"
    ],

    [
        "C6",
        "Test control",
        "Use the same test command and test selection across OS.",
        "test command / result",
        "Required"
    ],

    [
        "C7",
        "OS comparison",
        "Compare Ubuntu, Windows and macOS outcomes for the same repository.",
        "OS-specific outcome",
        "Required"
    ],

    [
        "C8",
        "Failure attribution",
        "Do not label PHP or dependency failures as OS-specific unless controlled comparison supports that interpretation.",
        "os_specific",
        "Required"
    ],

    [
        "C9",
        "Evidence capture",
        "Store OS version, PHP, Composer, extensions, logs and test results.",
        "Execution metadata",
        "Required"
    ],

    [
        "C10",
        "Pilot before scale",
        "Validate the protocol on 20 repositories before the 555-repository experiment.",
        "60 pilot executions",
        "Required"
    ],
]


create_sheet(
    "Cross-OS Protocol",
    "Cross-OS Protocol - Rules for Isolating Operating-System Effects",
    "Defines the controls needed to distinguish OS-specific portability issues from PHP, dependency and other environment constraints.",
    [
        "Rule",
        "Control",
        "Procedure",
        "Measurement",
        "Requirement"
    ],
    cross_os_rows,
    [14, 28, 68, 35, 20]
)


# ============================================================
# 6. EVIDENCE & ARTIFACT MAP
# ============================================================

artifact_rows = [

    [
        "Candidate dataset",
        "data/interim/cross_os_candidates.csv",
        "Repository eligibility and environment metadata.",
        "Stages 1-2",
        "Dataset"
    ],

    [
        "Candidate manifest",
        "data/interim/cross_os_candidates.manifest.json",
        "Provenance and metadata for candidate dataset.",
        "Stages 1-2",
        "Manifest"
    ],

    [
        "Environment inventory",
        "data/interim/cross_os_environment_inventory.csv",
        "Environment characterization.",
        "Stage 2",
        "Dataset"
    ],

    [
        "Environment inventory workbook",
        "data/interim/cross_os_environment_inventory.xlsx",
        "Human-readable environment inventory.",
        "Stage 2",
        "Workbook"
    ],

    [
        "GitHub enriched candidates",
        "data/interim/github_candidates_enriched.csv",
        "Verified GitHub metadata and exact SHA.",
        "Stage 3",
        "Dataset"
    ],

    [
        "Pilot dataset",
        "data/interim/reproducibility_pilot20.csv",
        "20 repositories selected for the reproducibility pilot.",
        "Stage 4",
        "Dataset"
    ],

    [
        "Reproducibility results",
        "data/interim/reproducibility_results.csv",
        "Pilot execution results.",
        "Stage 4",
        "Dataset"
    ],

    [
        "Reproducibility results workbook",
        "data/interim/reproducibility_results.xlsx",
        "Human-readable pilot results.",
        "Stage 4",
        "Workbook"
    ],

    [
        "Reproducibility manifest",
        "data/interim/reproducibility_results.manifest.json",
        "Provenance for pilot results.",
        "Stage 4",
        "Manifest"
    ],

    [
        "Pilot workflow",
        ".github/workflows/reproducibility-pilot20.yml",
        "Automated GitHub Actions execution.",
        "Stage 4",
        "Workflow"
    ],

    [
        "GitHub enrichment script",
        "scripts/09_github_enrich_candidates.py",
        "Fetch current repository SHA and GitHub metadata.",
        "Stage 3",
        "Python script"
    ],

    [
        "Reproducibility script",
        "scripts/09_reproducibility_check.py",
        "Validate and select the reproducibility pilot.",
        "Stage 4",
        "Python script"
    ],

    [
        "Environment inventory script",
        "scripts/08_environment_inventory.py",
        "Build environment inventory.",
        "Stage 2",
        "Python script"
    ],

    [
        "SLURM pilot job",
        "jobs/09_reproducibility_pilot20.slurm",
        "HPC execution route for reproducibility checks.",
        "Stage 4",
        "SLURM script"
    ],

    [
        "Future cross-OS pilot results",
        "data/results/cross_os_pilot20.csv",
        "Planned 20 repository × 3 OS results.",
        "Stage 5",
        "Planned output"
    ],

    [
        "Future full results",
        "data/results/cross_os_results.csv",
        "Planned 555 repository × 3 OS results.",
        "Stage 7",
        "Planned output"
    ],
]


create_sheet(
    "Evidence & Artifact Map",
    "Evidence & Artifact Map - Where Each Research Output Lives",
    "Maps every major research artifact to its location, purpose and research stage.",
    [
        "Artifact",
        "Path",
        "Purpose",
        "Stage",
        "Type"
    ],
    artifact_rows,
    [34, 68, 58, 18, 25]
)

# ============================================================
# 7. STAGE 1 — RUNTIME AVAILABILITY PILOT
# ============================================================

stage1_runtime = pd.read_csv(
    ROOT / "data/interim/stage1_runtime_evidence.csv"
)

stage1_failure = pd.read_csv(
    ROOT / "data/interim/stage1_failure_evidence.csv"
)

stage1_repeatability = pd.read_csv(
    ROOT / "data/interim/stage1_repeatability.csv"
)

stage1_summary = pd.read_csv(
    ROOT / "data/interim/stage1_summary.csv"
)


# ------------------------------------------------------------
# Stage 1 Runtime Pilot
# ------------------------------------------------------------

create_sheet(
    "Stage1_Runtime_Pilot",
    "Stage 1 Runtime Availability Pilot",
    "Master evidence for the 20-repository x 3-OS runtime availability pilot.",
    list(stage1_runtime.columns),
    stage1_runtime.fillna("").values.tolist(),
    [20] * len(stage1_runtime.columns)
)


# ------------------------------------------------------------
# Stage 1 Failure Evidence
# ------------------------------------------------------------

create_sheet(
    "Stage1_Failure_Evidence",
    "Stage 1 Failure Evidence",
    "Primary runtime failures identified during the Stage 1 pilot.",
    list(stage1_failure.columns),
    stage1_failure.fillna("").values.tolist(),
    [22] * len(stage1_failure.columns)
)


# ------------------------------------------------------------
# Stage 1 Repeatability
# ------------------------------------------------------------

create_sheet(
    "Stage1_Repeatability",
    "Stage 1 Repeatability",
    "Repeat-run comparison for the Stage 1 runtime pilot.",
    list(stage1_repeatability.columns),
    stage1_repeatability.fillna("").values.tolist(),
    [22] * len(stage1_repeatability.columns)
)


# ------------------------------------------------------------
# Stage 1 Summary
# ------------------------------------------------------------

create_sheet(
    "Stage1_Summary",
    "Stage 1 Summary",
    "Summary of runtime availability, repeatability and portability outcomes.",
    list(stage1_summary.columns),
    stage1_summary.fillna("").values.tolist(),
    [45, 20]
)
# ============================================================
# 7. ANALYSIS PLAN
# ============================================================

analysis_rows = [

    [
        "A1",
        "Descriptive environment analysis",
        "PHP/Laravel constraints, testing mechanisms and environment groups.",
        "555 eligible repositories",
        "Counts and distributions",
        "Stage 8"
    ],

    [
        "A2",
        "Reproducibility outcome",
        "Reproducible / partially reproducible / non-reproducible.",
        "Pilot and full experiment",
        "Counts and proportions",
        "Stages 4, 7-8"
    ],

    [
        "A3",
        "Failure stage analysis",
        "Platform check / installation / runtime / test.",
        "Failed executions",
        "Frequency and proportion",
        "Stages 6-8"
    ],

    [
        "A4",
        "Failure cause analysis",
        "PHP version / extension / dependency / private dependency / filesystem / path / permission / configuration / network / other.",
        "Failed executions",
        "Frequency and proportion",
        "Stages 6-8"
    ],

    [
        "A5",
        "Cross-OS comparison",
        "Compare the same repository across Ubuntu, Windows and macOS.",
        "20 pilot then 555 full",
        "Paired outcome comparison",
        "Stages 5-8"
    ],

    [
        "A6",
        "OS-specific failure analysis",
        "Identify failures supported by controlled OS comparison.",
        "Cross-OS executions",
        "OS-specific rates and categories",
        "Stages 5-8"
    ],

    [
        "A7",
        "Environment association analysis",
        "Assess associations between repository/environment characteristics and portability outcomes.",
        "Full experiment",
        "Effect estimates / association measures",
        "Stage 9"
    ],

    [
        "A8",
        "Evidence traceability",
        "Trace reported results back to execution logs, SHA and workflow artifacts.",
        "All experiments",
        "Audit trail",
        "Stages 4-10"
    ],
]


create_sheet(
    "Analysis Plan",
    "Analysis Plan - What Will Be Measured and How It Will Be Used",
    "Defines the analyses that will be performed after the reproducibility and cross-OS experiments.",
    [
        "ID",
        "Analysis",
        "Variables / Evidence",
        "Population",
        "Planned Summary",
        "Stage"
    ],
    analysis_rows,
    [12, 32, 70, 35, 40, 18]
)


# ============================================================
# ADD DOCUMENTATION CHECKPOINT TO EXISTING SHEET
# ============================================================

if "Project Checkpoint" in wb.sheetnames:

    ws = wb["Project Checkpoint"]

    start_row = ws.max_row + 3

    ws.cell(
        start_row,
        1,
        "RESEARCH CONTROL DOCUMENTATION"
    )

    ws.cell(
        start_row,
        1
    ).font = Font(
        bold=True,
        size=12
    )

    ws.cell(
        start_row + 1,
        1,
        "The following documentation sheets were added:"
    )

    for offset, sheet_name in enumerate(
        DOCUMENTATION_SHEETS,
        start=2
    ):

        ws.cell(
            start_row + offset,
            1,
            sheet_name
        )


# ============================================================
# SAVE WORKBOOK
# ============================================================

wb.save(WORKBOOK)


# ============================================================
# FINAL VERIFICATION
# ============================================================

print()
print("=" * 70)
print("RESEARCH CONTROL WORKBOOK UPDATED SUCCESSFULLY")
print("=" * 70)

print()
print("Workbook:")
print(WORKBOOK)

print()
print("New documentation sheets:")

for sheet_name in DOCUMENTATION_SHEETS:
    print("-", sheet_name)

print()
print("Total sheets:", len(wb.sheetnames))

print()
print("All sheets:")

for sheet_name in wb.sheetnames:
    print("-", sheet_name)

print()
print("=" * 70)
print("NEXT RESEARCH STAGE")
print("=" * 70)

print(
    "Cross-OS Pilot 20:"
)

print(
    "20 repositories x 3 operating systems = 60 executions"
)

print()
print(
    "The workbook now documents:"
)

print(
    "1. What is measured"
)

print(
    "2. How outcomes are classified"
)

print(
    "3. How the experiment is controlled"
)

print(
    "4. Where the code and artifacts are stored"
)

print(
    "5. What analysis will be performed"
)

print("=" * 70)
