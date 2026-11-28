# Software Metrics & Measurement Framework

This website presents the metrics actually reported in Haryani & Mehdawi, *Cross-OS Portability of Laravel Applications* (JSS manuscript), rather than a generic set of software quality metrics.

## Execution and evidence metrics (manuscript Table 4)

- **TRR (Test-Result Reachability Rate):** recorded verdicts / 921 attempts on each OS.
- **PER (Parser Evidence Rate):** parser-backed verdicts / recorded verdicts on that OS.
- **PGP (Parser-Backed Pass Rate):** parser-verified PASS / parser-backed verdicts on that OS.
- **VSD (Verified Success Detection Rate):** parser-verified PASS / 921 = TRR × PER × PGP.
- **3VSC:** number of repositories with parser-verified PASS on all three OS / 921.
- **CES:** Composer success conditional on PASS or FAIL within one channel; full installation and diagnostic are separate protocols.

## Comparisons and evidence reliability

- **VA / Cohen's and Fleiss' kappa:** agreement among harmonized fully observed test triplets; shared FAIL counts as agreement.
- **Paired risk difference (Δ):** `(A_only - B_only) / matched_n × 100` percentage points.
- **Directional dominance (D):** `A_only / (A_only + B_only)` within discordant paired repositories.
- **OS-invariance index (ι):** fraction of NOT_RUN records in a category whose repository had that same category on all three OS.
- **Tiered prevalence (T1–T4):** nested evidence claims; T4 is a worst-case upper bound.
- **Adjusted odds ratio (OR):** logistic regression association, not causation.

## Repository properties

Sampled per-project properties include GitHub stars/forks, age, size in MB, open issues, Docker/Compose presence, PHP/Laravel requirements and versions, locked package count and extension requirements, test file count, PHPUnit and Composer test script availability, and SQLite test configuration. Most are explanatory variables, *not* traditional source code complexity metrics.

The paper **does not report measurements** of source lines of code, cyclomatic complexity, maintainability index, coupling, cohesion, or CK metrics. These cannot be honestly described as calculated.

## Source & reporting limits

- Study source: uploaded JSS manuscript, §§4.1–4.5, 5.1–5.5, 6.1–6.5; especially Tables 3–5, 7, 8, 13, 15, 18–21 and Figure 8.
- Primary evidence: final frozen 921 repositories / 2763 OS run records.
- Logistic models: NR-all-three n=861, all-FAIL n=365; adjusted OR point estimates only shown on the website.
- The website is an explanatory companion. It does **not** recalculate every regression from raw per-repo metadata because not all source metadata columns are shipped within the public `repositories.js` payload.
