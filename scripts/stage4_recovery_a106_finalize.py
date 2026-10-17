#!/usr/bin/env python3
"""Label A-106 isolated full-protocol recovery without fabricating outcomes."""
import json
import os
from pathlib import Path

EXPERIMENT = 'stage4-a106-v2-set-failure-recovery-v1'
REPO = 'aagjalpankaj/larabase'


def finalize(root=Path('.'), env=None):
    env = os.environ if env is None else env
    eid, repo, sha, osname, batch = (env.get(k, '') for k in
        ('STAGE4_EXECUTION_ID', 'STAGE4_REPO', 'STAGE4_SHA', 'STAGE4_OS', 'STAGE4_RECOVERY_BATCH'))
    if (eid, repo, batch) != ('A-106', REPO, 'A02') or osname not in {'linux','windows','macos'}:
        raise ValueError('Not an authorized A-106 recovery target')
    if len(sha) != 40 or any(c not in '0123456789abcdefABCDEF' for c in sha):
        raise ValueError('Bad SHA')
    outfile = root / 'stage4_execution/result.json'
    patchfile = root / 'stage4_recovery/a106_v2_patch_provenance.json'
    metafile = root / 'stage4_recovery/a106_recovery_provenance.json'
    prefile = root / 'stage4_v3_preflight/preflight.json'
    data = json.loads(outfile.read_text(encoding='utf-8')) if outfile.exists() else {}
    pre = json.loads(prefile.read_text(encoding='utf-8')) if prefile.exists() else {}
    patch = json.loads(patchfile.read_text(encoding='utf-8')) if patchfile.exists() else None
    for key, expected in [('execution_id',eid),('repo_full_name',repo),('latest_sha',sha),('os',osname)]:
        if data.get(key) not in (None, '', expected):
            raise ValueError(f'Recovery {key} mismatch')
        data[key] = expected
    provenance = {
        'experiment_id': EXPERIMENT,
        'baseline_preserved': True,
        'baseline_batch': 'A02',
        'execution_id': eid, 'repo_full_name': repo, 'latest_sha': sha, 'os': osname,
        'github_run_id': env.get('GITHUB_RUN_ID',''),
        'interventions': [
            'Previously verified PHP hyphen-range resolver recovery',
            'Runner-only v2 set_failure detail/command/exit-code patch',
        ],
        'preflight_resolution_status': pre.get('resolution_status', 'NO_ARTIFACT'),
        'preflight_selected_php': pre.get('php',''),
        'patch_applied': bool(patch and patch.get('applied_in_ephemeral_runner')),
        'patch': patch,
        'protocol_step_outcome': env.get('STAGE4_RECOVERY_PROTOCOL_OUTCOME','unknown'),
        'composer_validate_status': data.get('composer_validate_status'),
        'composer_install_status': data.get('composer_install','NOT_RUN'),
        'composer_evidence_source': data.get('composer_evidence_source',''),
        'test_execution': data.get('test_execution','NOT_RUN'),
        'failure_category': data.get('failure_category'),
        'failure_stage': data.get('failure_stage'),
    }
    data.setdefault('test_execution', 'NOT_RUN')
    data['recovery_experiment'] = {
        'experiment_id': EXPERIMENT,
        'baseline_preserved': True,
        'preflight_resolution_status': provenance['preflight_resolution_status'],
        'preflight_selected_php': provenance['preflight_selected_php'],
        'protocol_patch_applied': provenance['patch_applied'],
    }
    metafile.parent.mkdir(parents=True, exist_ok=True)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    metafile.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding='utf-8')
    print('ISOLATED A-106:', osname, 'patch=', provenance['patch_applied'],
          'composer_validate=', provenance['composer_validate_status'],
          'composer=', provenance['composer_install_status'],
          'test=', provenance['test_execution'],
          'failure_stage=', provenance['failure_stage'])
    return data

if __name__ == '__main__':
    finalize()
