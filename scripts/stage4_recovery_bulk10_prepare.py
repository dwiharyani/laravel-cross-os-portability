#!/usr/bin/env python3
"""Select ten frozen PHP recovery candidates in ONE cross-batch matrix.

Reuse the published v3.3 per-batch immutable manifest/audit validator. Never
regenerate a manifest or use HEAD. The ten targets were NOT previously given a
completed PHP recovery experiment (six other scanned IDs are excluded).
"""
import hashlib
import json
import os
from pathlib import Path
from collections import Counter
import stage4_v3_3_prepare_batch as base

EXPERIMENT = 'stage4-php-hyphen-bulk10-v1'
TARGET_IDS = ('A-128','A-133','A-138','A-156','A-207','A-213','A-218','A-250','A-287','A-399')
PREVIOUS_IDS = ('A-082','A-103','A-106','A-108','A-129','A-340')
OS_LIST = ('linux','windows','macos')


def published_targets():
    """Validate immutable 921 master + ALL corresponding published manifests."""
    rows = base.master_rows(base.MASTER_DEFAULT)
    digest = hashlib.sha256(base.MASTER_DEFAULT.read_bytes()).hexdigest()
    master = {base.get(r,'execution_id'): base.make_row(i,r,digest)
              for i,r in enumerate(rows,2)}
    absent = set(TARGET_IDS) - master.keys()
    if absent: raise ValueError(f'Target IDs absent from frozen master: {sorted(absent)}')
    if set(TARGET_IDS) & set(PREVIOUS_IDS):
        raise ValueError('Already-recovered IDs must not be repeated in bulk10')
    if len(set(TARGET_IDS)) != len(TARGET_IDS):raise ValueError('Duplicate IDs in allowlist')
    groups = {}
    for eid in TARGET_IDS:
        row = master[eid]
        if row['execution_owner'] != 'A':raise ValueError(f'Unexpected owner: {eid}')
        groups.setdefault(row['execution_batch'],[]).append(eid)
    items = {}
    for batch,ids in sorted(groups.items()):
        # This is v3.3's original fully audited manifest selection; 3OS each.
        m = base.validate(batch, base.MASTER_DEFAULT, 0, ','.join(ids))
        for r in m['include']:
            eid,system = r['execution_id'],r['os']
            if eid not in ids or system not in OS_LIST:
                raise ValueError(f'Unexpected manifest matrix row: {eid}/{system}')
            key = (eid,system)
            if key in items:raise ValueError(f'Duplicate pair: {key}')
            original = master[eid]
            for field in ('latest_sha','project_id','repo_full_name','execution_batch','execution_owner'):
                if r.get(field) != original.get(field):
                    raise ValueError(f'Frozen assignment mismatch {key} {field}')
            items[key] = r
    expected = {(eid,system) for eid in TARGET_IDS for system in OS_LIST}
    if set(items) != expected:
        raise ValueError(f'Matrix incomplete: missing={sorted(expected-set(items))}')
    ordered = [items[(eid,system)] for eid in TARGET_IDS for system in OS_LIST]
    if len(ordered) != 30:raise ValueError('Must have exactly 30 OS records')
    return {'include':ordered}


def main():
    matrix = published_targets()
    data = json.dumps(matrix,separators=(',',':'))
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output,'a',encoding='utf-8') as f:
            f.write('matrix<<BULK10_MATRIX\n'+data+'\nBULK10_MATRIX\n')
    else:
        print(data)
    print('BULK PHP RECOVERY MATRIX VERIFIED:',len(matrix['include']), 'OS jobs;',len(TARGET_IDS),'repositories')
    print('BATCHES:',dict(Counter(x['execution_batch'] for x in matrix['include'])))

if __name__ == '__main__':main()
