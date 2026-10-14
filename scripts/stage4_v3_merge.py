#!/usr/bin/env python3
"""Read v3 artifacts after gh run download; preserve v2 baseline separately."""
import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path

FIELDS=['execution_id','project_id','repo_full_name','latest_sha','os','runner',
'php_runtime_requested','php_runtime_resolved','php_version_actual',
'composer_lock_hash','composer_install','test_command','test_execution',
'tests_total','tests_passed','tests_failed','tests_skipped','tests_incomplete',
'test_metrics_status','reproducibility_status','execution_validity',
'failure_category','failure_stage','failure_detail','extension_support_status',
'php_extensions_missing','php_extensions_unavailable_on_os','source_file']

def save_csv(path,rows,fields):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def clean(r):
    for k,v in list(r.items()):
        if isinstance(v,(dict,list)):r[k]=json.dumps(v,ensure_ascii=False,sort_keys=True)
    return r

def confirmed(row):
    try:
        n=int(row.get('tests_total') or 0)
        return n>0 and row.get('test_execution')=='PASS' and row.get('test_metrics_status','').startswith('PARSED_') and int(row.get('tests_passed') or 0)>0 and int(row.get('tests_failed') or 0)==0
    except (ValueError,TypeError):return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dir',default='stage4_v3_downloads')
    ap.add_argument('--out',default='stage4_v3_reports')
    args=ap.parse_args()
    root=Path(args.dir);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    found=[]
    for p in root.rglob('result.json'):
        try:r=json.loads(p.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError):continue
        if r.get('schema_version')!='stage4-v3-corrective':continue
        r['source_file']=str(p);found.append(r)
    latest={}
    for r in found:
        key=(r.get('execution_id'),r.get('repo_full_name'),r.get('latest_sha'),r.get('os'))
        if not all(key):continue
        if key not in latest or (r.get('finished_at') or '')>(latest[key].get('finished_at') or ''):
            latest[key]=r
    rows=list(latest.values())
    save_csv(out/'stage4_v3_results.csv',[clean(r.copy()) for r in rows],FIELDS)
    groups=defaultdict(list)
    for r in rows: groups[(r['execution_id'],r['repo_full_name'],r['latest_sha'])].append(r)
    comparison=[]
    for (eid,repo,sha),g in sorted(groups.items()):
        statuses={x['os']:x.get('test_execution','NOT_RUN') for x in g}
        osset=set(statuses)
        php={x.get('php_runtime_resolved','') for x in g if x.get('php_runtime_resolved')}
        locks={x.get('composer_lock_hash','') for x in g if x.get('composer_lock_hash')}
        totals={str(x.get('tests_total','')) for x in g}
        common=osset=={'linux','windows','macos'} and len(php)==1 and len(locks)==1 and len(totals)==1
        if osset!={'linux','windows','macos'}:label='INCOMPLETE_3OS'
        elif len(php)!=1:label='PHP_NOT_IDENTICAL'
        elif len(locks)!=1:label='COMPOSER_LOCK_NOT_IDENTICAL'
        elif all(confirmed(x) for x in g) and len(totals)==1:label='VERIFIED_3OS_PASS'
        elif len(set(statuses.values()))>1:label='REVIEW_DIFFERENTIAL_OUTCOME'
        else:label='NOT_YET_VERIFIED'
        comparison.append({'execution_id':eid,'repo_full_name':repo,'latest_sha':sha,
            'linux':statuses.get('linux','MISSING'),'windows':statuses.get('windows','MISSING'),
            'macos':statuses.get('macos','MISSING'),'same_php_and_lock_and_counts':common,
            'analysis_status':label})
    save_csv(out/'stage4_v3_cross_os_comparison.csv',comparison,
        ['execution_id','repo_full_name','latest_sha','linux','windows','macos','same_php_and_lock_and_counts','analysis_status'])
    summary=[]
    for os_name in ['linux','windows','macos']:
        g=[r for r in rows if r.get('os')==os_name]
        summary.append({'os':os_name,'records':len(g),'composer_pass':sum(r.get('composer_install')=='PASS' for r in g),
            'test_pass':sum(r.get('test_execution')=='PASS' for r in g),
            'test_fail':sum(r.get('test_execution')=='FAIL' for r in g),
            'verified_test_pass':sum(confirmed(r) for r in g)})
    save_csv(out/'stage4_v3_summary_by_os.csv',summary,summary[0].keys())
    print('v3 files:',len(found),'unique executions:',len(rows),'projects:',len(groups))
    print('analysis statuses:',dict(Counter(r['analysis_status'] for r in comparison)))
    print('Output folder:',out)
if __name__=='__main__':main()
