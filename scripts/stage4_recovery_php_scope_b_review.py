#!/usr/bin/env python3
"""Strict recovery 3x3 validator and baseline comparison. Read-only."""
import argparse
import csv
import json
import re
from pathlib import Path

TARGETS = {
    'A-108': 'tsukumijima/weather-api',
    'A-128': 'systemsdk/docker-nginx-php-laravel',
    'A-129': 'Coyote-OSS/coyote',
}
OSS = ('linux', 'windows', 'macos')
EXPERIMENT = 'stage4-php-hyphen-scope-pilot-a02-b-v1'


def get_baseline(path):
    records = {}
    if not path.is_file():
        raise FileNotFoundError(f'Baseline missing: {path}')
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        wrapper = json.loads(line)
        row = wrapper.get('result', wrapper)
        eid, osname = row.get('execution_id'), row.get('os')
        if eid not in TARGETS:
            continue
        key = (eid, osname)
        if key in records:
            raise ValueError(f'Duplicate baseline key: {key}')
        records[key] = row
    required = {(eid, osname) for eid in TARGETS for osname in OSS}
    if set(records) != required:
        raise ValueError(f'Missing A02 baseline pairs: {required - set(records)}')
    return records


def verified_pass(row):
    def number(key):
        value = row.get(key)
        try:
            return int(value) if value not in (None, '') else None
        except (ValueError, TypeError):
            return None
    total, passed, failed = (number(x) for x in ('tests_total','tests_passed','tests_failed'))
    return bool(row.get('test_execution') == 'PASS' and total is not None and total > 0
                and passed is not None and passed > 0 and failed == 0)


def analyze(folder, baseline_file, output):
    if not folder.is_dir():
        raise FileNotFoundError(f'Recovery folder does not exist: {folder}')
    baselines = get_baseline(baseline_file)
    recovery = {}
    for path in sorted(folder.rglob('result.json')):
        if path.parent.name != 'stage4_execution':
            continue
        row = json.loads(path.read_text(encoding='utf-8'))
        eid, osname = row.get('execution_id'), row.get('os')
        if eid not in TARGETS or osname not in OSS:
            raise ValueError(f'Unexpected recovery result: {path}')
        if row.get('repo_full_name') != TARGETS[eid]:
            raise ValueError(f'Repository mismatch: {path}')
        if not re.fullmatch('[0-9a-fA-F]{40}', row.get('latest_sha', '')):
            raise ValueError(f'Invalid SHA: {path}')
        if row.get('latest_sha') != baselines[(eid, osname)].get('latest_sha'):
            raise ValueError(f'Frozen-SHA mismatch against A02 baseline: {path}')
        meta = row.get('recovery_experiment') or {}
        if meta.get('experiment_id') != EXPERIMENT or meta.get('baseline_preserved') is not True:
            raise ValueError(f'Missing valid recovery provenance: {path}')
        key = (eid, osname)
        if key in recovery:
            raise ValueError(f'Duplicate recovery pair: {key}')
        recovery[key] = row
    expected = {(eid, osname) for eid in TARGETS for osname in OSS}
    if set(recovery) != expected:
        raise ValueError(f'Incomplete recovery: missing={sorted(expected-set(recovery))}, '
                         f'unexpected={sorted(set(recovery)-expected)}')
    rows = []
    print('VALIDATED: 9/9 isolated recovery records; exact frozen SHA matches A02 baseline')
    for eid in TARGETS:
        for osname in OSS:
            old = baselines[(eid, osname)]
            new = recovery[(eid, osname)]
            meta = new['recovery_experiment']
            rows.append({
                'execution_id': eid, 'repository': TARGETS[eid], 'os': osname,
                'frozen_sha': new['latest_sha'],
                'baseline_preflight': old.get('preflight_status', ''),
                'recovery_preflight': meta.get('preflight_resolution_status', ''),
                'selected_php': meta.get('preflight_selected_php', ''),
                'baseline_composer': old.get('composer_install', ''),
                'recovery_composer': new.get('composer_install', ''),
                'recovery_composer_validate': new.get('composer_validate_status', ''),
                'recorder_patch_applied': str(meta.get('v2_failure_recorder_patch_applied', False)),
                'recovery_composer_source': new.get('composer_evidence_source', ''),
                'baseline_test': old.get('test_execution', ''),
                'recovery_test': new.get('test_execution', ''),
                'recovery_test_verified_pass': str(verified_pass(new)),
                'recovery_db': new.get('database_audit_status', ''),
                'recovery_failure_stage': new.get('failure_stage', ''),
                'recovery_failure_detail_excerpt': str(new.get('failure_detail') or '')[:250],
            })
            print(f'{eid} {osname:7} PHP={str(meta.get("preflight_selected_php", "")):3} '
                  f'preflight={str(meta.get("preflight_resolution_status", "?")):11} '
                  f'Composer={str(new.get("composer_install", "?")):8} '
                  f'source={new.get("composer_evidence_source", "?")} '
                  f'validate={str(new.get("composer_validate_status", "?")):6} '
                  f'patch={meta.get("v2_failure_recorder_patch_applied", False)} '
                  f'test={str(new.get("test_execution", "?")):8} '
                  f'verified={verified_pass(new)}')
    output.mkdir(parents=True, exist_ok=True)
    csv_file = output / 'pilot_a02_b_baseline_vs_recovery.csv'
    with csv_file.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = [
        '# Isolated Stage 4 PHP recovery pilot: A02-B (3 repositories)', '',
        '- Baseline: Stage 4 v3.3 (read-only), frozen commits.',
        f'- Recovery: {EXPERIMENT}.',
        '- Collected: 9/9 pairs with exact frozen-SHA match.',
        '- Previously recovered A-340, A-082, A-103 and A-106 are excluded.'
        '- Only failure-recorder corrections are allowed; no automatic SQLite/migrations.',
        '- A recorded `PASS` is parser-verified only when metrics are positive and failures zero.',
        '', '| Execution ID | OS | Old test | New test | Preflight | PHP | Composer source | Validate | Recorder patch | Verified PASS |',
        '|---|---|---|---|---|---|---|---|---|---|',
    ]
    for r in rows:
        summary.append('| ' + ' | '.join(str(r[k]) for k in (
            'execution_id','os','baseline_test','recovery_test','recovery_preflight',
            'selected_php','recovery_composer_source','recovery_composer_validate','recorder_patch_applied','recovery_test_verified_pass')) + ' |')
    summary.extend(['', 'Recovery results are supplemental and must not overwrite A02 baseline.'])
    (output/'pilot_a02_b_recovery_summary.md').write_text('\n'.join(summary)+'\n', encoding='utf-8')
    print('CSV:', csv_file)
    print('REPORT:', output/'pilot_a02_b_recovery_summary.md')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=Path('stage4_v3_3_A02_consolidated.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('stage4_recovery_php_scope_pilot_A02_B_analysis'))
    args = parser.parse_args()
    analyze(args.results, args.baseline, args.output)
