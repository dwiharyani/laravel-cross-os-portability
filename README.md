# Laravel Dataset Discovery Pilot

## Goal
Use SEART/GHS as an existing repository sampling frame, then automatically verify/filter Laravel applications via GitHub API.

## 1. Install

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Export PHP repositories from SEART/GHS
Save the unmodified CSV under `data/source/raw/`, e.g. `seart_php_2026-09-06.csv`.

## 3. Inspect raw file
```bash
python scripts/01_inspect_dataset.py data/source/raw/seart_php_2026-09-06.csv
```

## 4. Create reproducible pilot sample (100 records)
```bash
python scripts/02_prepare_pilot.py data/source/raw/seart_php_2026-09-06.csv --n 100 --seed 2026
```
If URL column is not detected, add `--repo-column COLUMN_NAME`.

## 5. Create GitHub token
Copy `.env.example` to `.env`, paste the token there, and never commit `.env`.

## 6. Verify Laravel automatically
```bash
python scripts/03_verify_laravel.py data/interim/pilot_input.csv
```

## 7. Screen eligibility
```bash
python scripts/04_screen_eligibility.py data/interim/verified_laravel.csv
```

Outputs:
- `data/interim/verified_laravel.csv`
- `data/interim/screened_projects.csv`
- `data/final/eligible_projects.csv`
- audit summaries in `logs/`

Stop after the 100-record pilot and review the funnel before scaling up.
