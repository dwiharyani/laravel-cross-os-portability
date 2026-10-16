#!/usr/bin/env python3
"""Combine v3.2 result.json files; never overwrite earlier experiment outputs."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

FIELDS=['execution_id','project_id','repo_full_name','latest_sha','os','runner','run_id',
        'schema_version','php_version_actual','composer_install','test_execution',
        'tests_total','tests_passed','tests_failed','tests_skipped','reproducibility_status',
        'execution_validity','failure_category','failure_stage',
        'database_expected_engine','database_expected_version','database_actual_version',
        'database_audit_status','database_infrastructure_verified',
        'database_audit_comparable','database_preparation',
        'database_name_isolated','database_audit_reason','source_file']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dir',required=True)
    p.add_argument('--out',default='stage4_v3_2_reports')
    args=p.parse_args()
    resultdir=Path(args.dir); out=Path(args.out);out.mkdir(exist_ok=True)
    records=[]
    for f in resultdir.rglob('result.json'):
        try:
            r=json.loads(f.read_text(encoding='utf-8'))
            if r.get('schema_version')!='stage4-v3.2-database-aware':continue
            r['source_file']=str(f);records.append(r)
        except Exception as exc:
            print('Unreadable JSON:',f,type(exc).__name__)
    if not records:
        raise SystemExit('No v3.2 result.json found; check directory or workflow artifact')
    with (out/'stage4_v3_2_all_results.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore')
        writer.writeheader();writer.writerows(records)
    groups=defaultdict(dict)
    for r in records:
        groups[(r['run_id'],r['execution_id'],r['repo_full_name'],r['latest_sha'])][r['os']]=r
    comp=[]
    for key,oss in sorted(groups.items()):
        row={'run_id':key[0],'execution_id':key[1],'repo_full_name':key[2],'latest_sha':key[3]}
        for osname in ['linux','windows','macos']:
            r=oss.get(osname,{})
            row[osname+'_db']=r.get('database_audit_status','MISSING')
            row[osname+'_test']=r.get('test_execution','MISSING')
        row['comparable_db']=len(oss)==3 and all(r.get('database_audit_comparable') for r in oss.values()) and len({(r.get('database_expected_engine'),r.get('database_actual_version')) for r in oss.values()})==1
        comp.append(row)
    fields=['run_id','execution_id','repo_full_name','latest_sha','linux_db','windows_db','macos_db','linux_test','windows_test','macos_test','comparable_db']
    with (out/'stage4_v3_2_cross_os.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(comp)
    print('Records:',len(records),'groups:',len(groups))
    print('DB statuses:',dict(Counter(r.get('database_audit_status') for r in records)))
    print('Outputs:',out)

if __name__=='__main__':main()
