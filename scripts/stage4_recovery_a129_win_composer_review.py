#!/usr/bin/env python3
"""Merge immutable A-129 V1 Linux/macOS evidence with isolated Windows V2.

Existing baseline and original recovery results are READ-ONLY. No claims of full
protocol equivalence, nor PASS with missing/zero parsed tests.
"""
import argparse
import csv
import json
from pathlib import Path

SHA='0ead8b60f68f3acac974000357b73b4a89049d76'
REPO='Coyote-OSS/coyote'
OLD='A129_UPSTREAM_CI_NATIVE_UNIT_INMEMORY_V1'
NEW='A129_UPSTREAM_CI_NATIVE_UNIT_INMEMORY_WIN_COMPOSER_V2'
TARGETS=('module_unit','acceptance_unit','behat_in_memory')


def collect(root, protocol):
    if not root.is_dir(): raise FileNotFoundError(f'Artifact folder does not exist: {root}')
    found={}
    for p in root.rglob('result.json'):
        r=json.loads(p.read_text(encoding='utf-8'))
        r=r.get('result',r)
        if r.get('protocol_id')!=protocol: continue
        osname=r.get('os')
        if osname not in {'linux','windows','macos'} or osname in found:
            raise ValueError('Unexpected/duplicated OS record '+str(osname)+' in '+str(root))
        if r.get('execution_id')!='A-129' or r.get('repo_full_name')!=REPO:
            raise ValueError('Recovery identity mismatch: '+str(p))
        if r.get('frozen_sha')!=SHA or r.get('actual_sha')!=SHA or r.get('checkout')!='PASS':
            raise ValueError('Frozen SHA / checkout mismatch: '+str(p))
        if r.get('scope')!='TARGETED_NATIVE_UNIT_IN_MEMORY_ONLY':
            raise ValueError('Scope mismatch: '+str(p))
        if r.get('full_protocol_equivalent') is not False or r.get('baseline_overwritten') is not False:
            raise ValueError('Provenance guard mismatch: '+str(p))
        if r.get('composer_install_source')!='UPSTREAM_CI_NO_SCRIPTS':
            raise ValueError('Composer protocol incorrectly labeled: '+str(p))
        for target in TARGETS:
            st=r.get('steps',{}).get(target,{})
            status=st.get('status','NOT_RUN')
            if status not in ('PASS_VERIFIED','PASS_UNVERIFIED','FAIL','NOT_RUN'):
                raise ValueError('Unknown test status: '+str(status))
            if status=='PASS_VERIFIED' and not (st.get('verified') is True and
                    isinstance(st.get('detected_test_count'),int) and
                    not isinstance(st.get('detected_test_count'),bool) and
                    st['detected_test_count']>0 and st.get('return_code')==0):
                raise ValueError('Unsupported verified PASS: '+osname+'/'+target)
        if r.get('test_execution')=='PASS_VERIFIED_ALL_THREE_TARGETS' and not all(
                r.get('steps',{}).get(t,{}).get('status')=='PASS_VERIFIED' for t in TARGETS):
            raise ValueError('Overall PASS not supported: '+osname)
        found[osname]=r
    return found


def analyze(original,windows,baseline,output):
    if not baseline.is_file():raise FileNotFoundError('A02 immutable baseline missing: '+str(baseline))
    base=[]
    for line in baseline.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        row=json.loads(line)
        row=row.get('result',row)
        if row.get('execution_id')=='A-129':base.append(row)
    if len(base)!=3 or {r.get('os') for r in base}!={'linux','windows','macos'}:
        raise ValueError('A02 frozen baseline must contain A-129 three-OS records')
    if any(r.get('latest_sha')!=SHA or r.get('repo_full_name')!=REPO for r in base):
        raise ValueError('Baseline A-129 SHA/repo mismatch')
    old=collect(original,OLD)
    new=collect(windows,NEW)
    if set(old)!={'linux','windows','macos'}:
        raise ValueError('Original recovery missing OS record(s): '+str(sorted(old)))
    if set(new)!={'windows'}:
        raise ValueError('New experiment must contain Windows record ONLY: '+str(sorted(new)))
    if any(old[o].get('test_execution')!='PASS_VERIFIED_ALL_THREE_TARGETS' for o in ('linux','macos')):
        raise ValueError('Original Linux/macOS not fully verified; refuse to merge')
    if old['windows'].get('test_execution')!='NOT_RUN':
        raise ValueError('Original Windows already contains executed tests; investigate before merge')
    merged={'linux':old['linux'],'windows':new['windows'],'macos':old['macos']}
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for osname in ('linux','windows','macos'):
        r=merged[osname]
        source='ORIGINAL_V1' if osname!='windows' else 'WIN_COMPOSER_V2'
        item={'os':osname,'record_source':source,'protocol_id':r['protocol_id'],
              'frozen_sha':r['frozen_sha'], 'composer_install':r['composer_install'],
              'composer_validate':r['composer_validate'],
              'composer_invocation_strategy':r.get('composer_invocation_strategy',''),
              'test_execution':r.get('test_execution','NOT_RUN'),
              'blocked_reason':r.get('blocked_reason',''), 'exception':r.get('exception','')}
        for t in TARGETS:
            st=r.get('steps',{}).get(t,{})
            item[t]=st.get('status','NOT_RUN')
            item[t+'_verified']=st.get('verified') is True
            item[t+'_count']=st.get('detected_test_count',None)
        rows.append(item)
        print(f"{osname:7} source={source:16} Composer={item['composer_install']:7} "+
              ' '.join(f'{t}={item[t]}' for t in TARGETS))
        if item['blocked_reason']:print('  BLOCKED:',item['blocked_reason'])
        if item['exception']:print('  EXCEPTION:',item['exception'])
    csv_path=output/'A129_native_unit_windows_recovery_merged.csv'
    with csv_path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        writer.writeheader();writer.writerows(rows)
    md=['# A-129 targeted unit/in-memory recovery: Windows composer fix','',
        '- Baseline: **unchanged**, exact frozen SHA `'+SHA+'`.','- Source of Linux/macOS evidence: original V1 experiment.',
        '- Source of Windows evidence: separate V2 Windows-only experiment.','- Targeted native unit/in-memory scope only. **NOT** equivalent to full Stage 4 integration protocol.',
        '- Composer: `UPSTREAM_CI_NO_SCRIPTS`, not full-protocol install.','',
        '| OS | Source | Composer | Validate | Module unit | Acceptance unit | Behat in-memory |',
        '|---|---|---|---|---|---|---|']
    for item in rows:
        md.append('| '+' | '.join(str(item[k]) for k in
          ('os','record_source','composer_install','composer_validate','module_unit','acceptance_unit','behat_in_memory'))+' |')
    md+=['','## Interpretation','',
        'Green workflow completion or artifact collection is **not** an application test PASS.',
        'Only `PASS_VERIFIED` accompanied by positive parsed test/scenario counts and return code zero qualifies as a verified group result.',
        'PostgreSQL, Redis, Elasticsearch, Selenium and Docker integration are outside this experiment.',
        'Windows invocation strategy (if successful): `'+str(rows[1]['composer_invocation_strategy'])+'`.',
        '']
    md_path=output/'A129_native_unit_windows_recovery_merged.md'
    md_path.write_text('\n'.join(md),encoding='utf-8')
    print('VALIDATED: 3 merged OS records (V1 linux/macos + V2 windows), exact SHA unchanged')
    print('CSV:',csv_path)
    print('REPORT:',md_path)
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--original',type=Path,default=Path('stage4_recovery_A129_native_unit_results'))
    p.add_argument('--windows',type=Path,default=Path('stage4_recovery_A129_windows_composer_results'))
    p.add_argument('--baseline',type=Path,default=Path('stage4_v3_3_A02_consolidated.jsonl'))
    p.add_argument('--output',type=Path,default=Path('stage4_recovery_A129_windows_composer_analysis'))
    a=p.parse_args()
    analyze(a.original,a.windows,a.baseline,a.output)
