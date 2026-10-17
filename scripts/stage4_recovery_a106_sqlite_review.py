#!/usr/bin/env python3
"""Review 3-OS isolated SQLite recovery, compare A02 baseline + previous v2 run."""
import argparse
import csv
import json
from pathlib import Path

from stage4_recovery_a106_sqlite_finalize import EXPERIMENT, SHA, REPO
OSS=('linux','windows','macos')


def load_baseline(path):
    r={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        raw=json.loads(line)
        data=raw.get('result',raw)
        if data.get('execution_id')!='A-106':continue
        osname=data.get('os')
        if osname in r:raise ValueError('Duplicate A02 baseline record')
        r[osname]=data
    if set(r)!=set(OSS):raise ValueError('Incomplete frozen A02 baseline')
    for osname,data in r.items():
        if data.get('latest_sha')!=SHA or data.get('repo_full_name')!=REPO:
            raise ValueError(f'Frozen baseline SHA/repo mismatch: {osname}')
    return r


def load_result_folder(root, required=True):
    if not root.is_dir():
        if required:raise FileNotFoundError(root)
        return {}
    output={}
    for p in sorted(root.rglob('result.json')):
        if p.parent.name != 'stage4_execution':continue
        data=json.loads(p.read_text(encoding='utf-8'))
        if data.get('execution_id')!='A-106':
            raise ValueError('Unexpected repository result in A-106 artifact folder')
        osname=data.get('os')
        if osname not in OSS or osname in output:
            raise ValueError('Invalid/duplicate OS in recovery output')
        if data.get('latest_sha')!=SHA or data.get('repo_full_name')!=REPO:
            raise ValueError(f'Unexpected A-106 SHA/repo at {p}')
        output[osname]=(data,p)
    if required and set(output)!=set(OSS):
        raise ValueError(f'Expected 3/3 recovery records, got {sorted(output)}')
    return output


def pass_verified(r):
    try:
        total=int(r['tests_total']); passed=int(r['tests_passed']); failed=int(r['tests_failed'])
    except (ValueError,KeyError,TypeError):return False
    return r.get('test_execution')=='PASS' and total>0 and passed>0 and failed==0 and passed<=total


def review(results,baseline,previous,output):
    base=load_baseline(baseline)
    old=load_result_folder(previous,required=False) if previous is not None else {}
    if old and set(old)!=set(OSS):raise ValueError('Prior recovery folder incomplete')
    newer=load_result_folder(results)
    rows=[]
    for osname in OSS:
        r, path = newer[osname]
        meta=r.get('recovery_experiment') or {}
        if meta.get('experiment_id')!=EXPERIMENT or meta.get('baseline_preserved') is not True:
            raise ValueError(f'Bad isolated recovery provenance: {osname}')
        patchfile=path.parent.parent/'stage4_recovery/a106_sqlite_hook_patch.json'
        sqlitefile=path.parent.parent/'stage4_recovery/a106_sqlite_provision.json'
        if not patchfile.exists() or not sqlitefile.exists():
            raise ValueError(f'Missing independently recorded SQLite/patch artifacts: {osname}')
        patch=json.loads(patchfile.read_text(encoding='utf-8'))
        sqlite=json.loads(sqlitefile.read_text(encoding='utf-8'))
        if not (meta.get('runner_patch_applied') is True and meta.get('sqlite_file_provisioned') is True
                and patch.get('patch_applied') is True and patch.get('frozen_sha')==SHA
                and patch.get('os')==osname and sqlite.get('sqlite_file_exists_after') is True
                and sqlite.get('checkout_head_verified')==SHA and sqlite.get('frozen_sha')==SHA
                and sqlite.get('os')==osname and sqlite.get('repo_full_name')==REPO):
            raise ValueError(f'Runner patch / SQLite provenance failed validation: {osname}')
        row={
            'execution_id':'A-106', 'os':osname, 'frozen_sha':SHA,
            'baseline_test':base[osname].get('test_execution',''),
            'prior_recovery_test':old[osname][0].get('test_execution','') if old else '',
            'new_preflight':meta.get('preflight_resolution_status'),
            'composer_validate':r.get('composer_validate_status',''),
            'composer_install':r.get('composer_install',''),
            'composer_evidence_source':r.get('composer_evidence_source',''),
            'sqlite_file_created':sqlite.get('sqlite_file_created'),
            'test_execution':r.get('test_execution','NOT_RUN'),
            'verified_test_pass':pass_verified(r),
            'tests_total':r.get('tests_total',''), 'tests_passed':r.get('tests_passed',''),
            'tests_failed':r.get('tests_failed',''),
            'failure_category':r.get('failure_category',''),
            'failure_stage':r.get('failure_stage',''),
            'failure_detail_excerpt':str(r.get('failure_detail') or '')[:1100],
        }
        rows.append(row)
    print('VALIDATED: 3/3 isolated A-106 SQLite recovery records; frozen SHA unchanged')
    for r in rows:
        print(f'{r["os"]:7} PHP={r["new_preflight"]:10} '
              f'SQLite_created={str(r["sqlite_file_created"]):5} composer={r["composer_install"]:8} '
              f'validate={r["composer_validate"]:6} test={r["test_execution"]:8} '
              f'verified={r["verified_test_pass"]} failure={r["failure_stage"]}')
        if r['failure_detail_excerpt']:
            print('  detail:',r['failure_detail_excerpt'][:230].replace('\n',' '))
    output.mkdir(parents=True,exist_ok=True)
    csvfile=output/'A106_sqlite_baseline_vs_recovery.csv'
    with csvfile.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    md=['# A-106 — isolated SQLite file provisioning recovery','','Frozen A02 baseline and all previous recovery outputs remain unchanged.','','| OS | Baseline test | Prior v2 test | SQLite file newly created | New Composer | New test | Verified PASS |','|---|---|---|---|---|---|---|']
    for r in rows:
        md.append('| '+' | '.join(str(r[k]) for k in ('os','baseline_test','prior_recovery_test','sqlite_file_created','composer_install','test_execution','verified_test_pass'))+' |')
    md+=['','## Failures captured after provisioning','']
    for r in rows:
        md += [f'### {r["os"]}',f'Category `{r["failure_category"]}`, stage `{r["failure_stage"]}`.','','```text',r['failure_detail_excerpt'] or '(none)','```','']
    mdfile=output/'A106_sqlite_recovery_summary.md'
    mdfile.write_text('\n'.join(md)+'\n',encoding='utf-8')
    print('CSV:',csvfile);print('REPORT:',mdfile)
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--results',type=Path,required=True)
    ap.add_argument('--baseline',type=Path,default=Path('stage4_v3_3_A02_consolidated.jsonl'))
    ap.add_argument('--previous',type=Path,default=Path('stage4_recovery_A106_v2_setfailure_retry_results'))
    ap.add_argument('--output',type=Path,default=Path('stage4_recovery_a106_sqlite_analysis'))
    a=ap.parse_args();review(a.results,a.baseline,a.previous,a.output)
