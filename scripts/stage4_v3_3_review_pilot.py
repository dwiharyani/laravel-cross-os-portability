#!/usr/bin/env python3
"""Read-only validation of curated stage4-v3.3 pilot artifacts on the user's Mac."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

OS={'linux','windows','macos'}

def review(root:Path,manifest:Path):
    with manifest.open(encoding='utf-8-sig',newline='') as f:
        originals={r['execution_id']:(r['repo_full_name'],r['latest_sha']) for r in csv.DictReader(f)}
    paths=sorted(root.rglob('result.json'))
    rows={}
    for p in paths:
        r=json.loads(p.read_text(encoding='utf-8'))
        key=(str(r.get('execution_id','')),str(r.get('os','')).lower())
        if key in rows:raise ValueError(f'Duplicate result {key}: {p}')
        if key[0] not in originals or key[1] not in OS:raise ValueError(f'Unexpected execution/os: {key}')
        expected_name,expected_sha=originals[key[0]]
        if str(r.get('latest_sha','')).lower()!=expected_sha.lower() or str(r.get('repo_full_name','')).lower()!=expected_name.lower():
            raise ValueError(f'Repository or frozen SHA mismatch: {key}')
        if r.get('pipeline_revision')!='stage4-v3.3':raise ValueError(f'Wrong pipeline revision {key}')
        rows[key]=r
    triples={eid for eid,os in rows if {name for id2,name in rows if id2==eid}==OS}
    print('Artifacts:',len(paths),'| Repositories:',len({k[0] for k in rows}), '| Complete triples:',len(triples))
    print('Composer diagnostic / test / DB audit:')
    for (eid,os_name),r in sorted(rows.items()):
        print(f'  {eid:7} {os_name:7} Composer={str(r.get("composer_install","?")):9} '
              f'({r.get("composer_evidence_source","unknown")}) '
              f'Diagnostic={str(r.get("composer_diagnostic","?")):8} '
              f'Test={str(r.get("test_execution","?")):8} '
              f'DB={r.get("database_audit_status","?")}')
    print('Test outcomes:',dict(Counter(r.get('test_execution','?') for r in rows.values())))
    print('Composer evidence sources:',dict(Counter(r.get('composer_evidence_source','?') for r in rows.values())))
    return len(paths),len(triples)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=Path('data/interim/stage4_v3_3_A02_manifest.csv'))
    a=p.parse_args()
    review(a.results,a.manifest)
