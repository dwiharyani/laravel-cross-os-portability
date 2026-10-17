#!/usr/bin/env python3
"""Immutable 921-row two-owner assignment -> batch manifest, or CI matrix validation.

Does not re-sample, fetch HEAD, or silently change project/commit identities.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path

MASTER_DEFAULT = Path('data/interim/stage4_two_person_execution_assignment_921.csv')
SIZES = {**{f'A{i:02d}':75 for i in range(1,7)},'A07':10,
         **{f'B{i:02d}':75 for i in range(1,7)},'B07':11}
COLS = ['execution_id','execution_owner','execution_batch','project_id','repo_full_name',
        'url','latest_sha','laravel_version_constraint','php_runtime_constraint',
        'php_runtime_requested','php_runtime_source','stars_github','forks_count',
        'popularity_quartile','docker_status','source_master_row','source_execution_id',
        'master_file_sha256']

def get(row,*keys):
    lower = {str(k).strip().lower():str(v or '').strip() for k,v in row.items() if k is not None}
    return next((lower[k.lower()] for k in keys if lower.get(k.lower())), '')

def name_of(row):
    name = get(row,'repo_full_name','full_name','repository_full_name','github_full_name','repository','repo','name_with_owner')
    if not name:
        name = get(row,'url','html_url','repository_url','github_url')
    name = re.sub(r'^https?://github\.com/','',name,flags=re.I).rstrip('/').strip()
    return re.sub(r'\.git$','',name,flags=re.I).split('?')[0].split('#')[0]

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def master_rows(path):
    if not path.is_file():
        raise ValueError(f'Missing frozen master: {path}')
    rows = read_csv(path)
    if len(rows)!=921:
        raise ValueError(f'Frozen master must have 921 rows, found {len(rows)}')
    counts={}; seen_names=set(); seen_ids=set()
    for i,r in enumerate(rows,2):
        batch=get(r,'execution_batch'); owner=get(r,'execution_owner')
        eid=get(r,'execution_id'); name=name_of(r)
        sha=get(r,'latest_sha','sha','commit_sha','frozen_sha','head_sha').lower()
        if batch not in SIZES or owner!=batch[0]:raise ValueError(f'Row {i}: invalid batch/owner')
        if not re.fullmatch(r'[AB]-\d{3}',eid) or not eid.startswith(owner+'-'):
            raise ValueError(f'Row {i}: invalid execution ID')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',name):
            raise ValueError(f'Row {i}: invalid GitHub repository name')
        if not re.fullmatch(r'[a-f0-9]{40}',sha):raise ValueError(f'Row {i}: invalid pinned SHA')
        if name.lower() in seen_names or eid in seen_ids:raise ValueError(f'Row {i}: duplicate repo or ID')
        seen_names.add(name.lower());seen_ids.add(eid)
        counts[batch]=counts.get(batch,0)+1
    if counts!=SIZES:
        raise ValueError('Original frozen A01-A07/B01-B07 counts differ from 921 assignment')
    return rows

def make_row(i, r, masterhash):
    name=name_of(r)
    return {
        'execution_id':get(r,'execution_id'),
        'execution_owner':get(r,'execution_owner'),
        'execution_batch':get(r,'execution_batch'),
        'project_id':get(r,'project_id','projectid','repo_id'),
        'repo_full_name':name,
        'url':get(r,'url','html_url','repository_url','repo_url','github_url') or f'https://github.com/{name}',
        'latest_sha':get(r,'latest_sha','sha','commit_sha','frozen_sha','head_sha').lower(),
        'laravel_version_constraint':get(r,'laravel_version_constraint','laravel_constraint','laravel_version'),
        'php_runtime_constraint':get(r,'php_runtime_constraint','php_constraint','php_version_constraint'),
        'php_runtime_requested':get(r,'php_runtime_requested','php_version_requested'),
        'php_runtime_source':get(r,'php_runtime_source'),
        'stars_github':get(r,'stars_github','stars','stargazers_count'),
        'forks_count':get(r,'forks_count','forks'),
        'popularity_quartile':get(r,'popularity_quartile','quartile'),
        'docker_status':get(r,'docker_status','docker'),
        'source_master_row':str(i),
        'source_execution_id':get(r,'execution_id'),
        'master_file_sha256':masterhash,
    }

def paths_for(batch):
    if batch not in SIZES:raise ValueError(f'Invalid batch ID: {batch!r}')
    base=Path('data/interim')
    return base/f'stage4_v3_3_{batch}_manifest.csv', base/f'stage4_v3_3_{batch}_selection_audit.json'

def generate(batch, master=MASTER_DEFAULT, exclude_csv=None):
    path,audit_path=paths_for(batch)
    rows=master_rows(master)
    mhash=hashlib.sha256(master.read_bytes()).hexdigest()
    excluded=set()
    if exclude_csv is not None:
        if not exclude_csv.is_file():raise ValueError(f'Exclusion baseline missing: {exclude_csv}')
        old=read_csv(exclude_csv)
        excluded={name_of(r).lower() for r in old}
        if '' in excluded:raise ValueError('Exclusion CSV lacks repository identities')
    original=[make_row(i,r,mhash) for i,r in enumerate(rows,2) if get(r,'execution_batch')==batch]
    selected=[r for r in original if r['repo_full_name'].lower() not in excluded]
    if not selected:raise ValueError('No new repository remains in this batch')
    if len(selected)*3>256:raise ValueError('Exceeds 256 matrix jobs; use partition selection')
    matched=[r['repo_full_name'].lower() for r in original if r['repo_full_name'].lower() in excluded]
    # Prevent silently applying a wrong A01 baseline.
    if batch=='A01' and exclude_csv and len(matched)!=70:
        raise ValueError(f'A01 exclusion must match 70 previously analyzed repos; matched {len(matched)}')
    audit={'batch':batch,'master':str(master),'master_sha256':mhash,'source_rows':921,
           'original_batch_count':len(original),'selected_repositories':len(selected),
           'excluded_in_batch_count':len(matched), 'excluded_repo_full_names':matched,
           'selection_order':'ORIGINAL_FROZEN_ASSIGNMENT_ORDER',
           'original_ids_and_shas_preserved':True,
           'manifest_path':str(path),
           'warning':'A01 comprises 75 frozen assignments, but only 70 analyzed in the previous A01 baseline; use exclude CSV to select the remaining five.'}
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        current=read_csv(path)
        if current!=selected:raise ValueError(f'Refusing to overwrite a different existing manifest: {path}')
    else:
        with path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=COLS); writer.writeheader();writer.writerows(selected)
    if audit_path.exists() and json.loads(audit_path.read_text(encoding='utf-8'))!=audit:
        raise ValueError(f'Refusing to overwrite changed audit file: {audit_path}')
    audit_path.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'FROZEN BATCH {batch}: original={len(original)}, excluded={len(matched)}, selected={len(selected)}; OS jobs={3*len(selected)}')
    print('Manifest:',path)
    print('Audit:',audit_path)
    return selected

def validate(batch, master=MASTER_DEFAULT, max_repositories=3, execution_ids=''):
    path,audit_path=paths_for(batch)
    rows=master_rows(master)
    if not path.is_file() or not audit_path.is_file():
        raise ValueError(f'Missing {batch} manifest/audit in GitHub main; generate and commit first')
    audit=json.loads(audit_path.read_text(encoding='utf-8'))
    digest=hashlib.sha256(master.read_bytes()).hexdigest()
    if audit.get('batch')!=batch or audit.get('master_sha256')!=digest:
        raise ValueError('Master has changed or manifest audit mismatches')
    source=[make_row(i,r,digest) for i,r in enumerate(rows,2) if get(r,'execution_batch')==batch]
    excluded=set(audit.get('excluded_repo_full_names',[]))
    if not excluded.issubset({r['repo_full_name'].lower() for r in source}):
        raise ValueError('Exclusions not in original assigned batch')
    expected=[r for r in source if r['repo_full_name'].lower() not in excluded]
    actual=read_csv(path)
    if not expected or expected!=actual:
        raise ValueError('Published manifest differs from original frozen assignment')
    ids={r['execution_id'] for r in actual}
    request={s.strip() for s in execution_ids.split(',') if s.strip()}
    if max_repositories<0:raise ValueError('Invalid max_repositories')
    if request:
        if max_repositories>0:raise ValueError('When execution_ids is set, use max_repositories=0')
        if request-ids:raise ValueError('Unknown selection IDs: '+str(sorted(request-ids)))
        chosen=[r for r in actual if r['execution_id'] in request]
    else:
        chosen=actual[:max_repositories] if max_repositories else actual
    if not chosen or len(chosen)*3>256:
        raise ValueError('Matrix must contain 1-256 OS jobs; partition the batch')
    matrix=[{**r,'os':system,'runner':runner} for r in chosen for system,runner in
            [('linux','ubuntu-22.04'),('windows','windows-2022'),('macos','macos-15')]]
    return {'include':matrix}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',default='A02',choices=sorted(SIZES))
    p.add_argument('--master',type=Path,default=MASTER_DEFAULT)
    p.add_argument('--exclude-results-csv',type=Path)
    p.add_argument('--validate-only',action='store_true')
    p.add_argument('--max-repositories',type=int,default=3)
    p.add_argument('--execution-ids',default='')
    a=p.parse_args()
    if a.validate_only:
        matrix=validate(a.batch,a.master,a.max_repositories,a.execution_ids)
        s=json.dumps(matrix,separators=(',',':'))
        path=os.environ.get('GITHUB_OUTPUT')
        if path:
            with open(path,'a',encoding='utf-8') as f:
                f.write('matrix<<MATRIX\n'+s+'\nMATRIX\n')
        else:
            print(s)
        print('Validated matrix jobs:',len(matrix['include']))
    else:
        generate(a.batch,a.master,a.exclude_results_csv)

if __name__=='__main__': main()
