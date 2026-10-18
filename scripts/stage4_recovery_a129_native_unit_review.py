#!/usr/bin/env python3
"""Review exactly 3 separate A-129 native unit/in-memory OS records."""
import argparse
import csv
import json
from pathlib import Path

SHA = '0ead8b60f68f3acac974000357b73b4a89049d76'
OS_SET = {'linux','windows','macos'}
TARGETS = ('module_unit','acceptance_unit','behat_in_memory')
PROTOCOL_ID = 'A129_UPSTREAM_CI_NATIVE_UNIT_INMEMORY_V1'


def analyze(root, baseline, output):
    if not root.is_dir(): raise FileNotFoundError(f'Downloaded artifacts folder missing: {root}')
    if not baseline.is_file(): raise FileNotFoundError(f'A02 baseline evidence missing: {baseline}')
    rows_base=[]
    with baseline.open(encoding='utf-8') as fh:
        for line in fh:
            obj=json.loads(line)
            row=obj.get('result',obj)
            if row.get('execution_id')=='A-129': rows_base.append(row)
    if not rows_base:
        raise ValueError('A-129 not found in immutable A02 baseline')
    for row in rows_base:
        if row.get('latest_sha') != SHA or row.get('repo_full_name')!='Coyote-OSS/coyote':
            raise ValueError('A02 baseline repo or SHA mismatch')
    found={}
    for p in root.rglob('result.json'):
        obj=json.loads(p.read_text(encoding='utf-8'))
        row=obj.get('result',obj)
        if row.get('protocol_id')!=PROTOCOL_ID: continue
        osname=row.get('os')
        if osname not in OS_SET or osname in found:
            raise ValueError('Unknown/duplicated OS: '+str(osname))
        if row.get('execution_id')!='A-129' or row.get('repo_full_name')!='Coyote-OSS/coyote':
            raise ValueError('Unexpected recovery ID/repo')
        if row.get('frozen_sha')!=SHA or row.get('actual_sha')!=SHA:
            raise ValueError('Frozen SHA mismatch for '+osname)
        if row.get('checkout')!='PASS':
            raise ValueError('Checkout did not pass for '+osname)
        if row.get('scope')!='TARGETED_NATIVE_UNIT_IN_MEMORY_ONLY' or row.get('full_protocol_equivalent') is not False:
            raise ValueError('Recovery provenance mislabeled')
        if row.get('composer_install_source')!='UPSTREAM_CI_NO_SCRIPTS':
            raise ValueError('Composer installation provenance mislabeled')
        for t in TARGETS:
            step=row.get('steps',{}).get(t,{})
            status=step.get('status','NOT_RUN')
            if status=='PASS_VERIFIED' and not (step.get('verified') is True and
                        isinstance(step.get('detected_test_count'),int) and step['detected_test_count']>0 and
                        step.get('return_code')==0):
                raise ValueError('Unsupported verified PASS for '+osname+'/'+t)
        if row.get('test_execution')=='PASS_VERIFIED_ALL_THREE_TARGETS' and not all(
                row.get('steps',{}).get(t,{}).get('status')=='PASS_VERIFIED' for t in TARGETS):
            raise ValueError('Overall test PASS claimed without all three verified command outcomes')
        found[osname]=row
    if set(found)!=OS_SET:
        raise ValueError(f'Expected 3 A-129 OS rows, found {sorted(found)}')
    output.mkdir(parents=True,exist_ok=True)
    csv_path=output/'A129_native_unit_recovery_records.csv'
    headers=['execution_id','os','frozen_sha','scope','composer_install_source','composer_install','composer_validate','module_unit','module_unit_verified','acceptance_unit','acceptance_unit_verified','behat_in_memory','behat_in_memory_verified','test_execution','blocked_reason','exception']
    results=[]
    for osname in ('linux','windows','macos'):
        r=found[osname]
        item={k:r.get(k,'') for k in headers}
        for target in TARGETS:
            step=r.get('steps',{}).get(target,{})
            item[target]=step.get('status','NOT_RUN')
            item[target+'_verified']=step.get('verified') is True
        results.append(item)
        print(f"{osname:7} Composer={r['composer_install']:8} validate={r['composer_validate']:8} " +
              ' '.join(f'{t}={item[t]}' for t in TARGETS))
        if r.get('blocked_reason'): print('  BLOCKED:',r['blocked_reason'])
        if r.get('exception'):print('  EXCEPTION:',r['exception'])
        for t in TARGETS:
            st=r.get('steps',{}).get(t,{})
            if st.get('status')=='FAIL': print('  '+t+' failure log tail:',str(st.get('log_tail',''))[-550:])
    with csv_path.open('w',encoding='utf-8',newline='') as fp:
        w=csv.DictWriter(fp,fieldnames=headers)
        w.writeheader();w.writerows(results)
    md=['# A-129 — isolated native unit/in-memory recovery','',
        '- Original A02 Stage 4 baseline remains unchanged.',
        '- Frozen SHA: `'+SHA+'` (verified for all three OS).',
        '- This is a **targeted upstream-CI unit/in-memory** experiment, **not** the v2 full Stage 4 protocol.',
        '- Composer provenance: `UPSTREAM_CI_NO_SCRIPTS` (not full-protocol Composer).',
        '- A PHPUnit or Behat PASS is parser-verified only with return code zero and positive detected test/scenario counts.',
        '', '| OS | Composer (CI no-scripts) | Validate | Module unit | Acceptance unit | Behat in-memory |',
        '|---|---|---|---|---|---|']
    for item in results:
        md.append('| '+' | '.join(str(item[col]) for col in ('os','composer_install','composer_validate','module_unit','acceptance_unit','behat_in_memory'))+' |')
    md+=['','## Boundaries','',
         'This recovery does not establish PostgreSQL, Elasticsearch, Redis, Selenium, or Docker integration-test reproducibility.',
         'The unchanged baseline remains database-gated NOT_RUN.','','See CSV and per-OS logs for details.']
    report=output/'A129_native_unit_recovery_summary.md'
    report.write_text('\n'.join(md)+'\n',encoding='utf-8')
    print('VALIDATED: 3/3 A-129 native unit/in-memory recovery records; immutable SHA preserved')
    print('CSV:',csv_path);print('REPORT:',report)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',required=True,type=Path)
    parser.add_argument('--baseline',type=Path,default=Path('stage4_v3_3_A02_consolidated.jsonl'))
    parser.add_argument('--output',type=Path,default=Path('stage4_recovery_a129_native_unit_analysis'))
    a=parser.parse_args()
    analyze(a.results,a.baseline,a.output)
