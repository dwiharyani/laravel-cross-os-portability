#!/bin/bash
#SBATCH --job-name=laravel_verify
#SBATCH --partition=cpu_x440
#SBATCH --array=0-51%4
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --output=logs/verification/verify_%A_%a.out
#SBATCH --error=logs/verification/verify_%A_%a.err

set -euo pipefail

PROJECT="/scratch/g202527350/laravel-cross-os-portability"

cd "$PROJECT"
module load git/2.46.1
module load python/3.10.18
source .venv/bin/activate

INPUT="data/interim/laravel_candidates.csv"
OUTPUT="data/interim/verification_parts/verified_${SLURM_ARRAY_TASK_ID}.csv"

mkdir -p data/interim/verification_parts
mkdir -p logs/verification

# 100 repositories per array task
START=$((SLURM_ARRAY_TASK_ID * 100))
LIMIT=100

echo "=========================================="
echo "Laravel Verification"
echo "Job ID:       $SLURM_JOB_ID"
echo "Array ID:     $SLURM_ARRAY_TASK_ID"
echo "Node:         $SLURMD_NODENAME"
echo "Start index:  $START"
echo "Limit:        $LIMIT"
echo "=========================================="

python scripts/05_verify_laravel_full.py \
    "$INPUT" \
    --start "$START" \
    --limit "$LIMIT" \
    --output "$OUTPUT"

echo "Finished."
