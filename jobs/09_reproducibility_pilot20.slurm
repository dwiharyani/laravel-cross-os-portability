#!/bin/bash
#SBATCH --job-name=laravel-repro20
#SBATCH --partition=cpu_x440
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/repro20_%j.out
#SBATCH --error=logs/repro20_%j.err

set -euo pipefail

cd /home/g202527350/laravel-cross-os-portability

source .venv/bin/activate

mkdir -p logs
mkdir -p data/work/reproducibility

echo "=========================================="
echo "Laravel Reproducibility Pilot"
echo "=========================================="

echo "Host:"
hostname

echo
echo "Python:"
python --version

echo
echo "Git:"
git --version

echo
echo "PHP:"
if command -v php >/dev/null 2>&1; then
    php --version
else
    echo "PHP NOT AVAILABLE"
fi

echo
echo "Composer:"
if command -v composer >/dev/null 2>&1; then
    composer --version
else
    echo "Composer NOT AVAILABLE"
fi

echo
echo "=========================================="
echo "Running reproducibility check"
echo "=========================================="

python scripts/09_reproducibility_check.py \
    --input data/interim/cross_os_candidates.csv \
    --pilot data/interim/reproducibility_pilot20.csv \
    --limit 20 \
    --workspace data/work/reproducibility

echo
echo "=========================================="
echo "JOB FINISHED"
echo "=========================================="
