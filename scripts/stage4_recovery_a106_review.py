#!/usr/bin/env python3
"""Strict cross-OS A-106 recovery evidence review; never overwrites baselines."""
import argparse
import csv
import json
from pathlib import Path

TARGET = 'aagjalpankaj/larabase'
EXPERIMENT = 'stage4-a106-v2-set-failure-recovery-v1'
OSS = ('linux', 'windows', 'macos')


def baseline_from(path):
    original = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        wrapper = json.loads(line)
        row = wrapper.get('result', wrapper)
        if row.get('execution_id') != 'A-106':
            continue
        osname = row.get('os')
        if osname in original:
            raise ValueError('Duplicate A-106 baseline OS')
        original[osname] = row
    if set(original) != set(OSS):
        raise ValueError(f'Incomplete original baseline: {sorted(original)}')
    return original


def prior_from(folder):
    if folder is None:
        return {}
    if not folder.is_dir():
        raise FileNotFoundError(folder)
    prior = {}
    for p in folder.rglob('result.json'):
        if p.parent.name != 'stage4_execution':
            continue
        row = json.loads(p.read_text(encoding='utf-8'))
        if row.get('execution_id') == 'A-106':
            if row.get('os') in prior:
                raise ValueError('Duplicate prior A-106 recovery')
            prior[row['os']] = row
    if set(prior) != set(OSS):
        raise ValueError('Prior A-106 3-OS recovery incomplete')
    return prior


def verified_pass(r):
    try:
        total = int(r['tests_total'])
        passed = int(r['tests_passed'])
        failed = int(r['tests_failed'])
    except (TypeError, ValueError, KeyError):
        return False
    return r.get('test_execution') == 'PASS' and total > 0 and passed > 0 and failed == 0


def review(results, baseline_path, previous, output):
    base = baseline_from(baseline_path)
    prior = prior_from(previous)
    newer = {}
    for path in sorted(results.rglob('result.json')):
        if path.parent.name != 'stage4_execution':
            continue
        r = json.loads(path.read_text(encoding='utf-8'))
        osname = r.get('os')
        if (r.get('execution_id'), r.get('repo_full_name')) != ('A-106', TARGET) or osname not in OSS:
            raise ValueError(f'Unexpected result in {path}')
        if osname in newer:
            raise ValueError(f'Duplicate A-106 recovery for {osname}')
        if r.get('latest_sha') != base[osname].get('latest_sha'):
            raise ValueError(f'Frozen SHA mismatch for {osname}')
        if prior and r.get('latest_sha') != prior[osname].get('latest_sha'):
            raise ValueError(f'SHA mismatch against previous PHP recovery for {osname}')
        meta = r.get('recovery_experiment') or {}
        if meta.get('experiment_id') != EXPERIMENT or meta.get('baseline_preserved') is not True:
            raise ValueError(f'Invalid recovery provenance for {osname}')
        if meta.get('protocol_patch_applied') is not True:
            raise ValueError(f'No successful runner-only protocol patch for {osname}')
        newer[osname] = r
    if set(newer) != set(OSS):
        raise ValueError(f'Missing recovery OS: {sorted(set(OSS)-set(newer))}')
    rows = []
    print('VALIDATED: 3/3 isolated A-106 protocol recovery records, exact frozen SHA preserved')
    for osname in OSS:
        old, new = base[osname], newer[osname]
        row = {
            'execution_id': 'A-106', 'os': osname, 'frozen_sha': new['latest_sha'],
            'baseline_test': old.get('test_execution',''),
            'previous_php_recovery_test': prior[osname].get('test_execution','') if prior else '',
            'new_preflight': (new.get('recovery_experiment') or {}).get('preflight_resolution_status',''),
            'new_composer_validate': new.get('composer_validate_status',''),
            'new_composer_install': new.get('composer_install',''),
            'new_composer_source': new.get('composer_evidence_source',''),
            'new_test': new.get('test_execution',''),
            'verified_test_pass': verified_pass(new),
            'failure_category': new.get('failure_category',''),
            'failure_stage': new.get('failure_stage',''),
            'failure_detail_excerpt': str(new.get('failure_detail') or '')[:600],
        }
        rows.append(row)
        print(f"{osname:7} preflight={str(row['new_preflight']):10} "
              f"validate={str(row['new_composer_validate']):6} "
              f"composer={str(row['new_composer_install']):8} "
              f"source={row['new_composer_source']} test={str(row['new_test']):8} "
              f"verified={row['verified_test_pass']} failure={row['failure_stage']}")
        if row['failure_detail_excerpt']:
            print('  failure_detail:', row['failure_detail_excerpt'][:300].replace('\n',' '))
    output.mkdir(parents=True, exist_ok=True)
    csvpath = output/'A106_baseline_vs_recovery.csv'
    with csvpath.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    report = ['# A-106 — isolated v2 set_failure recovery', '',
              'Original A02 baseline and previous PHP-only recovery are not modified.',
              'A recorded PASS is verified only with positive test counts and zero failures.', '',
              '| OS | Baseline test | Previous PHP recovery | New Composer validate | New Composer | New test | Parser verified |',
              '|---|---|---|---|---|---|---|']
    for r in rows:
        report.append('| '+' | '.join(str(r[k]) for k in ('os','baseline_test','previous_php_recovery_test',
            'new_composer_validate','new_composer_install','new_test','verified_test_pass'))+' |')
    report += ['', '## Failure stage and captured evidence', '']
    for r in rows:
        report += [f"### {r['os']}", '',
            f"Category: `{r['failure_category']}`; stage: `{r['failure_stage']}`.", '',
            '```text', r['failure_detail_excerpt'] or '(no recorded error)', '```','']
    mdpath=output/'A106_recovery_summary.md'
    mdpath.write_text('\n'.join(report)+'\n',encoding='utf-8')
    print('CSV:',csvpath)
    print('REPORT:',mdpath)
    return rows

if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--results',type=Path,required=True)
    ap.add_argument('--baseline',type=Path,default=Path('stage4_v3_3_A02_consolidated.jsonl'))
    ap.add_argument('--previous',type=Path,default=Path('stage4_recovery_php_scope_pilot_A02_3_results'))
    ap.add_argument('--output',type=Path,default=Path('stage4_recovery_a106_v2_analysis'))
    args=ap.parse_args()
    review(args.results,args.baseline,args.previous,args.output)
