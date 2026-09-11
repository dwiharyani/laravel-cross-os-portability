# Reproducibility Pilot

## Input

Source:
data/final/eligible_projects.csv

Number of initially eligible projects:
7

## Purpose

This stage evaluates whether initially eligible Laravel applications can
actually be installed and tested in a clean baseline environment.

Initial eligibility does not imply executable reproducibility.

## Baseline Environment

Operating system:
Ubuntu Linux

Execution environment:
GitHub Actions

## Repository Version

Every repository must be checked out at the frozen commit SHA recorded during
dataset screening.

## Possible Outcomes

- Reproducible
- Install Failure
- Environment Setup Required
- External Service Required
- Test Command Not Found
- Baseline Test Failure
- Infrastructure Failure
- Needs Manual Review

## Rule

Only projects successfully installed and tested in the baseline environment
will proceed to the cross-OS experiment.
