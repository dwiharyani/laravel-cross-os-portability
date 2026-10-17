#!/usr/bin/env python3
"""Validate/compare the isolated three-OS A-340 recovery downloads."""
import argparse
import json
from pathlib import Path

SHA = 'a713671b2307fae99847cec2fe78889d4501d0d0'
OS_NAMES = ('linux', 'windows', 'macos')


def review(root):
    evidence = {}
    paths = sorted(root.rglob('result.json'))
    for path in paths:
        if path.parent.name != 'stage4_execution':
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('execution_id') != 'A-340' or data.get('latest_sha') != SHA:
            raise ValueError('Incorrect execution ID or SHA in ' + str(path))
        if data.get('repo_full_name') != 'JieAnthony/apple-mdm-system':
            raise ValueError('Unexpected repository in ' + str(path))
        os_name = data.get('os')
        if os_name not in OS_NAMES or os_name in evidence:
            raise ValueError('Duplicate/unexpected OS ' + str(os_name))
        recovery = data.get('recovery_experiment', {})
        if recovery.get('experiment_id') != 'stage4-recovery-a340-php-hyphen-v1':
            raise ValueError('Missing recovery provenance: ' + str(path))
        evidence[os_name] = data
    if set(evidence) != set(OS_NAMES):
        raise ValueError('Recovery results incomplete: ' + repr(sorted(evidence)))
    print('VALIDATED: 3/3 isolated A-340 recovery OS records, frozen SHA unchanged')
    for os_name in OS_NAMES:
        row = evidence[os_name]
        rec = row['recovery_experiment']
        print(f'{os_name:7} preflight={rec.get("preflight_resolution_status", "?"):12} '
              f'Composer={str(row.get("composer_install", "?")):8} '
              f'source={row.get("composer_evidence_source", "?")} '
              f'test={str(row.get("test_execution", "?")):8} '
              f'DB={row.get("database_audit_status", "?")}')
    print('NOTE: recovery outcomes must not overwrite A05 baseline records.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    if not args.results.is_dir():
        parser.error('Directory not found: ' + str(args.results))
    review(args.results)
