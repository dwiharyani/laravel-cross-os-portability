#!/usr/bin/env python3
"""Resume-safe dispatcher for previously unexecuted Stage 4 v3.3 BASELINE batches.

It uses (and never replaces) stage4_v3_3_prepare_batch.py, and preserves the
921-row immutable master, assignment, frozen commits, and historical results.
Artifact collection is NOT an assertion that Composer/tests passed.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BATCHES = ('A06', 'A07', 'B01', 'B03', 'B04', 'B05', 'B06', 'B07')
COUNTS = {'A06':75, 'A07':10, 'B01':75, 'B03':75, 'B04':75,
          'B05':75, 'B06':75, 'B07':11}
TOTAL = sum(COUNTS.values())
OS_NAMES = ('linux', 'windows', 'macos')
WORKFLOW = 'stage4_v3_3_composer_first.yml'
EXPECTED_REPO = 'dwiharyani/laravel-cross-os-portability'
DEFAULT_STATE = 'stage4_baseline_bulk_471_tracking'


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(message):
    raise RuntimeError(message)


def call(args, *, capture=False, allow_fail=False):
    print('$', ' '.join(str(a) for a in args), flush=True)
    p = subprocess.run([str(a) for a in args], text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    if p.returncode and not allow_fail:
        if capture and p.stderr:
            print(p.stderr[-3000:], file=sys.stderr)
        fail(f'Exit {p.returncode}: {args[0]} {args[1] if len(args)>1 else ""}')
    return p


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def module():
    path = Path('scripts/stage4_v3_3_prepare_batch.py')
    if not path.exists():
        fail(f'Cannot find original frozen assignment validator: {path}')
    spec = importlib.util.spec_from_file_location('stage4_existing_prepare', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def expected_plan(chunksize=25, generate=False):
    if not 1 <= chunksize <= 75:
        fail('chunk-size must be in 1..75, to stay below the 256-job GitHub matrix limit')
    prep = module()
    master = prep.MASTER_DEFAULT
    frozen = prep.master_rows(master)  # checks EXACT 921 assignments, owner, and SHA
    digest = hashlib.sha256(master.read_bytes()).hexdigest()
    master_map = {r['execution_id']:r for r in frozen}
    if len(master_map) != 921:
        fail('Duplicate execution IDs in master')
    plans = []
    selected_all = []
    for batch in BATCHES:
        path, auditpath = prep.paths_for(batch)
        if generate:
            prep.generate(batch, master, None)  # original fail-closed generator
        else:
            if not (path.is_file() and auditpath.is_file()):
                fail(f'Batch {batch} missing generated manifest/audit: run prepare first')
        actual = read_csv(path)
        if len(actual) != COUNTS[batch]:
            fail(f'{batch}: expected {COUNTS[batch]} rows, got {len(actual)}')
        if len({r['execution_id'] for r in actual}) != len(actual):
            fail(f'{batch}: duplicate execution IDs')
        for r in actual:
            m = master_map.get(r['execution_id'])
            if not m or m['execution_batch'] != batch or m['execution_owner'] != batch[0]:
                fail(f'{batch}: assignment mismatch for {r["execution_id"]}')
            if r['latest_sha'].lower() != m['latest_sha'].lower():
                fail(f'{batch}: SHA mismatch for {r["execution_id"]}')
        for offset in range(0, len(actual), chunksize):
            segment = actual[offset:offset+chunksize]
            ids = [r['execution_id'] for r in segment]
            matrix = prep.validate(batch, master, 0, ','.join(ids))
            got = matrix['include']
            wanted = {(r['execution_id'], osname, r['latest_sha'])
                      for r in segment for osname in OS_NAMES}
            produced = {(r['execution_id'], r['os'], r['latest_sha']) for r in got}
            if produced != wanted or len(got) != len(wanted):
                fail(f'{batch} chunk {1 + offset//chunksize}: matrix does not match frozen assignment')
            selected_all.extend(ids)
            plans.append({'key': f'{batch}-{1+offset//chunksize:02d}',
                          'batch': batch, 'chunk': 1+offset//chunksize,
                          'ids': ids, 'expected_artifacts': len(ids)*3,
                          'run_id': None, 'run_status': 'NOT_DISPATCHED',
                          'conclusion': None, 'artifact_count': 0,
                          'missing_artifacts': [], 'collected_at': None})
    if len(selected_all) != TOTAL or len(set(selected_all)) != TOTAL:
        fail(f'Expected {TOTAL} unique repositories, got {len(set(selected_all))}')
    return digest, plans


def statepath(args):
    return Path(args.state_dir) / 'progress.json'


def prepare(args):
    digest, plans = expected_plan(args.chunk_size, generate=True)
    path = statepath(args)
    if path.exists():
        old = json.loads(path.read_text(encoding='utf-8'))
        if old.get('master_sha256') != digest or old.get('chunk_size') != args.chunk_size:
            fail('Existing progress file uses a DIFFERENT master or chunk size. Refusing overwrite.')
        if [(p['key'],p['ids']) for p in old['plans']] != [(p['key'],p['ids']) for p in plans]:
            fail('Existing run plan differs; refusing to overwrite previously dispatched run IDs')
        print(f'Existing state preserved: {path}')
    else:
        state = {'protocol': 'STAGE4_V3_3_ORIGINAL_BASELINE',
                 'scope': '471_NOT_YET_EXECUTED_ASSIGNED_REPOSITORIES',
                 'master_sha256': digest, 'chunk_size':args.chunk_size,
                 'created_utc':now(), 'baseline_overwritten':False,
                 'warning':'Artifacts collected != tests passed; this does not modify previous consolidated results',
                 'plans':plans}
        atomic_json(path, state)
        print('NEW STATE:',path)
    print('FROZEN MASTER:',digest)
    print(f'VALIDATED: {TOTAL} repositories, {TOTAL*3} OS jobs, {len(plans)} workflow runs')
    print('BATCHES:', ', '.join(f'{b}={COUNTS[b]}' for b in BATCHES))
    print('A01 EXCLUDED: reconcile prior 57 vs 70 repository evidence before dispatch')
    print('NEXT: install/commit/push manifests before running execution.')


def check_remote_files():
    if not shutil.which('gh'):
        fail('GitHub CLI gh missing')
    call(['gh','auth','status'])
    p = call(['gh','repo','view','--json','nameWithOwner','--jq','.nameWithOwner'],capture=True)
    if p.stdout.strip().lower() != EXPECTED_REPO.lower():
        fail(f'Unexpected GitHub repo: {p.stdout.strip()} (wanted {EXPECTED_REPO})')
    b = call(['git','branch','--show-current'],capture=True).stdout.strip()
    if b != 'main':
        fail(f'Expected local main branch, found {b}')
    needed = [f'data/interim/stage4_v3_3_{batch}_{kind}' for batch in BATCHES
              for kind in ('manifest.csv','selection_audit.json')]
    needed += ['scripts/stage4_bulk_baseline_471.py',
               '.github/workflows/'+WORKFLOW,
               'scripts/stage4_v3_3_prepare_batch.py',
               'data/interim/stage4_two_person_execution_assignment_921.csv']
    for p in needed:
        q = call(['git','ls-files','--error-unmatch',p],capture=True,allow_fail=True)
        if q.returncode:
            fail(f'File not committed/tracked; push first: {p}')
    # Staged files can appear in git ls-files but are not yet in remote main.
    dirty = call(['git','status','--porcelain','--'] + needed,capture=True).stdout.strip()
    if dirty:
        fail('Required workflow, script, or manifests have uncommitted changes: '+dirty[:1200])
    current = call(['git','rev-parse','HEAD'],capture=True).stdout.strip()
    remote = call(['git','ls-remote','origin','refs/heads/main'],capture=True).stdout.split()[0]
    if current != remote:
        fail('Local HEAD differs from remote main. Push/resolve before dispatch to prevent stale manifests.')


def get_state(args):
    p = statepath(args)
    if not p.exists():
        fail(f'No tracking file: {p}. Run prepare first.')
    obj = json.loads(p.read_text(encoding='utf-8'))
    digest, expected = expected_plan(obj['chunk_size'], generate=False)
    if digest != obj['master_sha256']:
        fail('Frozen master SHA differs from saved state; refusing dispatch')
    if [(p['key'],p['ids']) for p in obj['plans']] != [(p['key'],p['ids']) for p in expected]:
        fail('Saved manifest differs from existing frozen plan; refusing dispatch')
    if obj.get('protocol') != 'STAGE4_V3_3_ORIGINAL_BASELINE':
        fail('Unrecognized provenance protocol')
    return obj


def find_artifacts(run_id):
    url = f'repos/{EXPECTED_REPO}/actions/runs/{run_id}/artifacts?per_page=100'
    p = call(['gh','api','-X','GET',url],capture=True)
    items = json.loads(p.stdout)['artifacts']
    return [item['name'] for item in items if not item.get('expired')]


def process_run(args, state, item):
    key = item['key']
    if item.get('collected_at'):
        print('ALREADY COLLECTED:',key, 'run=',item['run_id'])
        return
    batch = item['batch']
    ids = item['ids']
    if not item.get('run_id') and state.get('needs_manual_reconciliation') == key:
        fail(f'{key}: ambiguous dispatch. Find run ID and use attach-run BEFORE resuming; DO NOT redispatch.')
    if not item.get('run_id'):
        print(f'\nDISPATCHING {key}: {len(ids)} repos x 3 OS')
        command = ['gh','workflow','run',WORKFLOW,'--ref','main',
                   '-f',f'batch_id={batch}', '-f','max_repositories=0',
                   '-f','execution_ids='+','.join(ids)]
        p = call(command,capture=True)
        output = (p.stdout or '')+'\n'+(p.stderr or '')
        print(output)
        found = re.findall(r'/actions/runs/(\d+)',output)
        if not found:
            item['run_status'] = 'DISPATCHED_RUN_ID_UNRESOLVED'
            state['needs_manual_reconciliation'] = key
            atomic_json(statepath(args),state)
            fail(f'Workflow {key} may have been dispatched but GitHub returned no run ID. '
                 'DO NOT RERUN. Find numeric run ID using gh run list, then use attach-run.')
        item['run_id'] = found[-1]
        item['run_status'] = 'DISPATCHED'
        atomic_json(statepath(args),state)
    run_id = item['run_id']
    print(f'WAITING: {key} run={run_id}')
    call(['gh','run','watch',str(run_id),'--interval','30'],allow_fail=True)
    view = call(['gh','run','view',str(run_id),'--json','status,conclusion,jobs'],capture=True)
    data = json.loads(view.stdout)
    item['run_status'] = data['status']
    item['conclusion'] = data['conclusion']
    item['job_outcomes'] = [{'name':j['name'],'conclusion':j.get('conclusion')}
                            for j in data.get('jobs',[])]
    atomic_json(statepath(args),state)
    if data['status'] != 'completed':
        fail(f'{key}: workflow not completed; rerun controller to continue watching')
    listed = find_artifacts(run_id)
    expected = {f'stage4-v3-3-{eid}-{osname}' for eid in ids for osname in OS_NAMES}
    received = set(listed)
    missing = sorted(expected - received)
    unexpected = sorted(received - expected)
    item['artifact_count'] = len(received & expected)
    item['missing_artifacts'] = missing
    item['unexpected_artifacts'] = unexpected
    atomic_json(statepath(args),state)
    if missing or unexpected:
        print(f'{key}: INCOMPLETE or UNEXPECTED artifacts. Missing {len(missing)}, unexpected {len(unexpected)}')
        print('First missing:', missing[:8])
        fail(f'Halting before next batch: {key} missing/unexpected artifacts. Inspect run {run_id}.')
    dest = Path(args.state_dir)/'artifacts'/f'{key}_run{run_id}'
    marker = Path(args.state_dir)/'receipts'/f'{key}_run{run_id}.json'
    if marker.exists():
        receipt = json.loads(marker.read_text(encoding='utf-8'))
        if receipt.get('run_id') != str(run_id) or receipt.get('artifacts') != sorted(expected):
            fail(f'Mismatched receipt for {key}')
        if not dest.is_dir():
            fail(f'Receipt exists but artifact folder missing: {dest}')
    else:
        if dest.exists():
            fail(f'Partial destination exists without receipt: {dest}. Inspect manually before resume.')
        print(f'DOWNLOADING: {run_id} -> {dest}')
        call(['gh','run','download',str(run_id),'--dir',str(dest)])
        if not dest.is_dir() or not all((dest/n).is_dir() for n in expected):
            fail(f'{key}: missing extracted artifact folders; inspect {dest}')
        atomic_json(marker, {'run_id':str(run_id), 'key':key, 'artifacts':sorted(expected),
                             'warning':'Artifact collection is NOT test verification'})
    item['collected_at'] = now()
    item['run_status'] = 'ARTIFACTS_COLLECTED'
    atomic_json(statepath(args),state)
    print(f'COLLECTED {key}: {len(expected)}/{len(expected)} OS artifacts; workflow={item["conclusion"]}')
    if item['conclusion'] != 'success':
        print('WARNING: GitHub workflow not successful. Evidence collected but investigate jobs before test conclusions.')


def execute(args):
    state = get_state(args)
    check_remote_files()
    for i, item in enumerate(state['plans'], 1):
        print(f'\n=== BASELINE BULK {i}/{len(state["plans"])} | {item["key"]} ===',flush=True)
        process_run(args,state,item)
    print('\nALL BATCH ARTIFACTS COLLECTED. Still validate result records and tests separately.')
    report(args)


def attach(args):
    obj = get_state(args)
    item = next((p for p in obj['plans'] if p['key']==args.key),None)
    if item is None:
        fail(f'Invalid chunk key: {args.key}')
    if item.get('run_id') and str(item['run_id']) != args.run_id:
        fail('Refusing to change already assigned run ID')
    if not re.fullmatch(r'\d+',args.run_id):
        fail('Run ID must be numeric')
    data=json.loads(call(['gh','run','view',args.run_id,'--json','databaseId,workflowName'],capture=True).stdout)
    if data.get('workflowName') != 'Stage 4 v3.3 - Composer-First Cross-OS':
        fail(f'Unexpected workflow for run ID: {data.get("workflowName")}')
    item['run_id']=args.run_id
    item['run_status']='DISPATCHED'
    obj.pop('needs_manual_reconciliation',None)
    atomic_json(statepath(args),obj)
    print('RUN ATTACHED:',args.key,args.run_id)


def report(args):
    obj = get_state(args)
    collected = sum(1 for p in obj['plans'] if p.get('collected_at'))
    artifacts = sum(p.get('artifact_count',0) for p in obj['plans'])
    summary = {'protocol':obj['protocol'], 'master_sha256':obj['master_sha256'],
               'sample_master':921, 'assigned_in_this_plan':TOTAL,
               'planned_workflows':len(obj['plans']), 'collected_workflows':collected,
               'expected_os_artifacts':TOTAL*3, 'observed_expected_artifacts':artifacts,
               'not_included_A01_or_prior_baselines':True,
               'not_a_verified_test_pass_count':True,
               'runs':[{'key':p['key'],'repos':len(p['ids']),'run_id':p['run_id'],
                        'conclusion':p.get('conclusion'), 'collected':bool(p.get('collected_at')),
                        'expected_os':p['expected_artifacts'],
                        'found_os':p.get('artifact_count',0),
                        'missing':p.get('missing_artifacts',[])} for p in obj['plans']]}
    out=Path(args.state_dir)/'baseline_bulk_471_artifact_summary.json'
    atomic_json(out,summary)
    print(f'ARTIFACT COVERAGE: {artifacts}/{TOTAL*3} expected OS artifacts')
    print(f'WORKFLOWS COLLECTED: {collected}/{len(obj["plans"])}')
    print('NOT equivalent to validated baseline result records or TEST PASS')
    print('Summary:',out)
    for p in summary['runs']:
        print(f"{p['key']:8} run={str(p['run_id']):12} workflow={str(p['conclusion']):9} "
              f"artifacts={p['found_os']:3}/{p['expected_os']:3}")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['prepare','run','report','attach-run'])
    ap.add_argument('--state-dir',default=DEFAULT_STATE)
    ap.add_argument('--chunk-size',type=int,default=25)
    ap.add_argument('--key',default='')
    ap.add_argument('--run-id',default='')
    args=ap.parse_args()
    if args.action=='prepare':prepare(args)
    elif args.action=='run':execute(args)
    elif args.action=='report':report(args)
    elif args.action=='attach-run':attach(args)


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,KeyError,subprocess.SubprocessError, OSError) as e:
        print('\nSTOPPED SAFELY:',str(e),file=sys.stderr)
        sys.exit(2)
