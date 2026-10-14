#!/usr/bin/env python3
"""Build a conservative per-PROJECT selective rerun manifest from immutable v2 results.
Run in methodology repo root; input is consolidated stage4_latest_per_execution_os.csv.
One selected repository is rerun on ALL three OS, never just failed OS.
"""
import argparse, csv
from collections import defaultdict
from pathlib import Path

POTENTIALLY_PIPELINE = {'PHP_VERSION_DEPENDENCY_MISMATCH', 'COMPOSER_FAILURE',
    'EXTENSION_MISSING', 'TEST_COMMAND_UNAVAILABLE'}
OUT_FIELDS = ['execution_id','execution_owner','execution_batch','project_id',
 'repo_full_name','url','latest_sha','laravel_version_constraint','php_runtime_constraint',
 'php_runtime_requested','php_runtime_source','stars_github','forks_count',
 'popularity_quartile','docker_status','rerun_reasons']

def identify(g):
    why=[]
    if {x.get('os','').lower() for x in g} != {'linux','windows','macos'}:
        why.append('INCOMPLETE_OS_TRIPLET')
    if any(x.get('failure_category','') in POTENTIALLY_PIPELINE for x in g):
        why.append('PRETEST_PIPELINE_FAILURE')
    if any(x.get('test_command','').strip().startswith('test:') for x in g):
        why.append('MALFORMED_TEST_COMMAND')
    if any(x.get('test_execution') == 'PASS' and not x.get('tests_total','').strip() for x in g):
        why.append('PASS_WITHOUT_TEST_COUNTS')
    return why

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input', default='stage4_reports/stage4_latest_per_execution_os.csv')
    p.add_argument('--output', default='data/interim/stage4_v3_rerun_manifest.csv')
    p.add_argument('--policy',choices=['pipeline','all'],default='pipeline')
    args=p.parse_args()
    with open(args.input,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    groups=defaultdict(list)
    for r in rows:
        key=r['execution_id'],r['repo_full_name'],r['latest_sha']
        groups[key].append(r)
    selected=[]
    for key, group in sorted(groups.items()):
        reasons=identify(group)
        if args.policy=='pipeline' and not reasons: continue
        if not reasons: reasons=['FULL_REAUDIT_REQUESTED']
        record=dict(next((r for r in group if r['os']=='linux'),group[0]))
        record['rerun_reasons']=';'.join(reasons)
        selected.append({f:record.get(f,'') for f in OUT_FIELDS})
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=OUT_FIELDS);w.writeheader();w.writerows(selected)
    print('Baseline rows:',len(rows),'repositories:',len(groups))
    print('Selected repository triplets:',len(selected),'expected OS executions:',len(selected)*3)
    print('Manifest:',out)
if __name__=='__main__':main()
