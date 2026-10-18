#!/usr/bin/env python3
"""Strict 30/30 provenance + immutable baseline comparison, read-only."""
import argparse
import csv
import json
from pathlib import Path
from stage4_recovery_bulk10_prepare import TARGET_IDS, OS_LIST, EXPERIMENT, published_targets


def verified_pass(row):
    if row.get('test_execution') != 'PASS':return False
    def n(key):
        v=row.get(key)
        if isinstance(v,bool) or v is None or str(v).strip()=='':return None
        try:return int(v)
        except (TypeError,ValueError):return None
    total,passed,failed=(n(k) for k in ('tests_total','tests_passed','tests_failed'))
    return total is not None and total>0 and passed is not None and passed>0 and failed==0 and passed<=total


def check_baseline(expected,base_dir):
    batches=sorted({r['execution_batch'] for r in expected.values()})
    out={}
    for batch in batches:
        p=base_dir/f'stage4_v3_3_{batch}_consolidated.jsonl'
        if not p.is_file():raise FileNotFoundError(f'Read-only baseline missing: {p}')
        for line in p.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            d=json.loads(line);r=d.get('result',d)
            key=(r.get('execution_id'),r.get('os'))
            if key not in expected:continue
            ident=expected[key]
            for f in ('execution_id','repo_full_name','latest_sha','os'):
                if r.get(f)!=ident[f]:raise ValueError(f'Baseline frozen identity mismatch {key}: {f}')
            if r.get('execution_batch') not in (None,'',ident['execution_batch']):
                raise ValueError(f'Baseline batch mismatch {key}')
            if key in out:raise ValueError(f'Duplicate baseline record {key}')
            out[key]=r
    if set(out)!=set(expected):
        raise ValueError(f'Baseline incomplete: missing={sorted(set(expected)-set(out))}')
    return out


def analyze(folder,base_dir,output, matrix=None):
    if not folder.is_dir():raise FileNotFoundError(f'Recovery directory missing: {folder}')
    matrix=published_targets() if matrix is None else matrix
    expected={(r['execution_id'],r['os']):r for r in matrix['include']}
    if len(expected)!=30 or set(expected)!={(e,s) for e in TARGET_IDS for s in OS_LIST}:
        raise ValueError('Expected exactly ten frozen repos x three OS')
    baseline=check_baseline(expected,base_dir)
    recovered={}
    for path in sorted(folder.rglob('result.json')):
        if path.parent.name!='stage4_execution':continue
        row=json.loads(path.read_text(encoding='utf-8'))
        key=(row.get('execution_id'),row.get('os'))
        if key not in expected:raise ValueError(f'Unexpected recovery record: {path}')
        original=expected[key]
        for field in ('execution_id','repo_full_name','latest_sha','os','execution_batch'):
            if row.get(field)!=original[field]:raise ValueError(f'Recovery frozen mismatch {key} field {field}')
        meta=row.get('recovery_experiment') or {}
        if (meta.get('experiment_id')!=EXPERIMENT or meta.get('baseline_preserved') is not True or
            meta.get('batch')!=original['execution_batch']):
            raise ValueError(f'Invalid recovery provenance: {path}')
        if key in recovered:raise ValueError(f'Duplicate recovery record: {key}')
        recovered[key]=row
    if set(recovered)!=set(expected):
        raise ValueError(f'Incomplete recovery: missing={sorted(set(expected)-set(recovered))}')
    report=[]
    for eid in TARGET_IDS:
        for system in OS_LIST:
            key=eid,system
            old,new=baseline[key],recovered[key]
            meta=new['recovery_experiment']
            row={
                'execution_id':eid,'repository':expected[key]['repo_full_name'],
                'batch':expected[key]['execution_batch'],'project_id':expected[key]['project_id'],
                'os':system,'frozen_sha':expected[key]['latest_sha'],
                'baseline_preflight':old.get('preflight_status',''),
                'baseline_composer':old.get('composer_install',''),
                'baseline_test':old.get('test_execution',''),
                'recovery_preflight':meta.get('preflight_resolution_status',''),
                'php':meta.get('preflight_selected_php',''),
                'composer_status':new.get('composer_install','NOT_RUN'),
                'composer_evidence_source':new.get('composer_evidence_source','UNKNOWN'),
                'composer_validate':new.get('composer_validate_status','UNKNOWN'),
                'database_status':new.get('database_audit_status','UNKNOWN'),
                'test_status':new.get('test_execution','NOT_RUN'),
                'test_pass_verified':verified_pass(new),
                'tests_total':new.get('tests_total'), 'tests_passed':new.get('tests_passed'),
                'tests_failed':new.get('tests_failed'),
                'runner_patch_applied':meta.get('v2_failure_recorder_patch_applied',False),
                'failure_stage':new.get('failure_stage',''),
                'failure_category':new.get('failure_category',''),
                'failure_detail':str(new.get('failure_detail') or '')[:250],
            }
            report.append(row)
            print(f'{eid} {system:7} PHP={str(row["php"]):3} '
                  f'preflight={str(row["recovery_preflight"]):10} Composer={str(row["composer_status"]):8} '
                  f'source={row["composer_evidence_source"]} '
                  f'validate={str(row["composer_validate"]):6} test={str(row["test_status"]):8} '
                  f'verified={row["test_pass_verified"]}')
    output.mkdir(parents=True,exist_ok=True)
    csv_file=output/'bulk10_baseline_vs_recovery.csv'
    with csv_file.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(report[0]));w.writeheader();w.writerows(report)
    summary=['# Stage 4: 10-repository cross-batch PHP recovery (30 OS records)','',
        f'- Experiment: `{EXPERIMENT}`','- Frozen SHA and baseline identities checked against 921 master,',
        '  all published batch manifests and per-batch consolidated baselines.',
        '- No baseline modifications. No application database provisioning or Composer update.',
        '- Protocol success, no-script Composer diagnostic, Composer validate, and verified test PASS remain distinct.',
        '- A recorded test PASS counts as verified only with positive test counts and zero failures.','',
        '| ID | OS | Original batch | PHP | Preflight | Composer | Evidence source | Test | Verified PASS |',
        '|---|---|---|---|---|---|---|---|---|']
    for r in report:
        summary.append('| '+' | '.join(str(r[x]) for x in (
            'execution_id','os','batch','php','recovery_preflight','composer_status',
            'composer_evidence_source','test_status','test_pass_verified'))+' |')
    summary.extend(['',f'- Verified test PASS: **{sum(r["test_pass_verified"] for r in report)}/30 OS**',
        f'- Test NOT_RUN: **{sum(r["test_status"]=="NOT_RUN" for r in report)}/30 OS**',
        '- Reminder: `VALIDATED 30/30` means evidence completeness, not 30 passing tests.'])
    md=output/'bulk10_recovery_summary.md'
    md.write_text('\n'.join(summary)+'\n',encoding='utf-8')
    print(f'VALIDATED: 30/30 frozen 10-repo recovery records, strict baseline identity preserved')
    print('CSV:',csv_file)
    print('REPORT:',md)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True)
    p.add_argument('--baseline-dir',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,default=Path('stage4_recovery_bulk10_analysis'))
    a=p.parse_args();analyze(a.results,a.baseline_dir,a.output)
