#!/usr/bin/env python3
"""Create B02 exclusively from the original immutable 921-row A/B assignment.

Preserves every original execution_id, owner, batch, repository, SHA and original
B02 ordering; never performs resampling or renumbers selected entries.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

OUTPUT_COLUMNS = [
    'execution_id','execution_owner','execution_batch','project_id','repo_full_name',
    'url','latest_sha','laravel_version_constraint','php_runtime_constraint',
    'php_runtime_requested','php_runtime_source','stars_github','forks_count',
    'popularity_quartile','docker_status','source_master_row',
    'source_execution_id','master_file_sha256'
]
EXPECTED_BATCH_SIZES = {
    **{f'A{i:02d}': 75 for i in range(1,7)}, 'A07':10,
    **{f'B{i:02d}': 75 for i in range(1,7)}, 'B07':11,
}

def get(row, *names):
    canon={str(k).strip().lower():str(v or '').strip() for k,v in row.items() if k is not None}
    for n in names:
        x=canon.get(n.lower(),'')
        if x:return x
    return ''

def repo_name(row):
    s=get(row,'repo_full_name','full_name','repository_full_name','github_full_name','repository','repo','name_with_owner')
    if not s:s=get(row,'url','html_url','repository_url','github_url')
    s=re.sub(r'^https?://github\.com/','',s,flags=re.I).strip().rstrip('/')
    s=re.sub(r'\.git$','',s,flags=re.I).split('?')[0].split('#')[0]
    return s

def prepare(master:Path, baseline:Path, out:Path):
    if not master.is_file():raise ValueError(f'Frozen assignment not found: {master}')
    if not baseline.is_file():raise ValueError(f'A01 baseline not found: {baseline}')
    with master.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    with baseline.open(encoding='utf-8-sig',newline='') as f:old=list(csv.DictReader(f))
    if len(rows)!=921:raise ValueError(f'Original assignment must be 921 rows; found {len(rows)}')
    old_names={repo_name(r).lower() for r in old}
    old_ids={get(r,'execution_id') for r in old}
    if len(old_names)!=70 or len(old_ids)!=70 or '' in old_names:
        raise ValueError(f'A01 baseline must contain 70 unique repositories and 70 execution IDs (got {len(old_names)}/{len(old_ids)})')

    unique_names=set();unique_ids=set();counts={};b02=[];all_a01_names=set()
    for lineno,r in enumerate(rows,2):
        batch=get(r,'execution_batch')
        owner=get(r,'execution_owner')
        eid=get(r,'execution_id')
        name=repo_name(r)
        sha=get(r,'latest_sha','sha','commit_sha','frozen_sha','head_sha')
        if batch not in EXPECTED_BATCH_SIZES:
            raise ValueError(f'Master row {lineno}: missing/invalid batch: {batch!r}')
        if owner!=batch[0]:raise ValueError(f'Master row {lineno}: owner {owner!r} conflicts with batch {batch!r}')
        if not re.fullmatch(r'[AB]-\d{3}',eid):raise ValueError(f'Master row {lineno}: invalid execution ID {eid!r}')
        if not eid.startswith(owner+'-'):raise ValueError(f'Master row {lineno}: ID {eid!r} conflicts with owner {owner!r}')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',name):
            raise ValueError(f'Master row {lineno}: invalid repository {name!r}')
        if not re.fullmatch(r'[a-fA-F0-9]{40}',sha):
            raise ValueError(f'Master row {lineno}: missing invalid pinned 40-hex SHA for {name!r}')
        key=name.lower()
        if key in unique_names:raise ValueError(f'Master row {lineno}: duplicate repository {name}')
        if eid in unique_ids:raise ValueError(f'Master row {lineno}: duplicate execution ID {eid}')
        unique_names.add(key);unique_ids.add(eid)
        counts[batch]=counts.get(batch,0)+1
        if batch=='A01':all_a01_names.add(key)
        if batch=='B02':b02.append((lineno,r,name,sha.lower()))
    if counts!=EXPECTED_BATCH_SIZES:
        diff={k:(counts.get(k,0),v) for k,v in EXPECTED_BATCH_SIZES.items() if counts.get(k,0)!=v}
        raise ValueError(f'Unexpected original assignment batch counts: {diff}')
    if not old_names.issubset(all_a01_names):
        raise ValueError('The 70 analyzed A01 identities are not a subset of the original frozen A01 assignment; stop to resolve identity mismatches')
    collision=[name for _,_,name,_ in b02 if name.lower() in old_names]
    if collision:raise ValueError(f'B02 overlaps executed A01 repositories: {collision}')
    sha256=hashlib.sha256(master.read_bytes()).hexdigest()
    selected=[]
    for lineno,r,name,sha in b02:
        rec={x:'' for x in OUTPUT_COLUMNS}
        rec.update({
            'execution_id':get(r,'execution_id'),
            'execution_owner':'B','execution_batch':'B02',
            'project_id':get(r,'project_id','projectid','repo_id'),
            'repo_full_name':name,
            'url':get(r,'url','html_url','repository_url','repo_url','github_url') or f'https://github.com/{name}',
            'latest_sha':sha,
            'laravel_version_constraint':get(r,'laravel_version_constraint','laravel_constraint','laravel_version'),
            'php_runtime_constraint':get(r,'php_runtime_constraint','php_constraint','php_version_constraint'),
            'php_runtime_requested':get(r,'php_runtime_requested','php_version_requested'),
            'php_runtime_source':get(r,'php_runtime_source'),
            'stars_github':get(r,'stars_github','stars','stargazers_count'),
            'forks_count':get(r,'forks_count','forks'),
            'popularity_quartile':get(r,'popularity_quartile','quartile'),
            'docker_status':get(r,'docker_status','docker'),
            'source_master_row':lineno,
            'source_execution_id':get(r,'execution_id'),
            'master_file_sha256':sha256,
        })
        selected.append(rec)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=OUTPUT_COLUMNS);w.writeheader();w.writerows(selected)
    audit={
        'source':'ORIGINAL_TWO_PERSON_ASSIGNMENT',
        'master':str(master),'master_sha256':sha256,'master_rows':len(rows),
        'owner_A_total':sum(counts[k] for k in counts if k.startswith('A')),
        'owner_B_total':sum(counts[k] for k in counts if k.startswith('B')),
        'batch':'B02','selected_repositories':len(selected),'planned_os_jobs':3*len(selected),
        'original_execution_ids_preserved':True,'selection_order':'ORIGINAL_B02_ASSIGNMENT_ORDER',
        'A01_baseline_repositories':len(old_names),'A01_overlap':0,
        'first_3_ids':[r['execution_id'] for r in selected[:3]],
        'first_3_repositories':[r['repo_full_name'] for r in selected[:3]],
        'warning':'B02 is the ORIGINAL owner-B second batch, NOT simply the next repositories after A01. B01 is a different batch.'
    }
    audit_path=out.with_name('stage4_B02_selection_audit.json')
    audit_path.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('MASTER:',master,'(921 original repository assignments)')
    print('B02:',len(selected),'repositories x 3 OS =',3*len(selected),'execution jobs')
    print('A01 overlap:',0)
    print('Original B02 IDs:',', '.join(r['execution_id'] for r in selected[:3]),'...')
    print('Manifest:',out)
    print('Audit:',audit_path)
    return selected

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--master',type=Path,default=Path('data/interim/stage4_two_person_execution_assignment_921.csv'))
    p.add_argument('--baseline',type=Path,default=Path('stage4_A01_70_analysis/A01_210_execution_results.csv'))
    p.add_argument('--out',type=Path,default=Path('data/interim/stage4_B02_manifest.csv'))
    a=p.parse_args();prepare(a.master,a.baseline,a.out)

if __name__=='__main__':main()
