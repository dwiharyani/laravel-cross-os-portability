#!/usr/bin/env python3
"""Curated, separate A-106 SQLite recovery outcomes; NEVER modifies A02 baseline."""
import json
import os
from pathlib import Path

EXPERIMENT = 'stage4-a106-sqlite-file-provisioning-v1'
SHA = '3c3ac5c009f5d87f5e5208be1f213e9aa08e2c2d'
REPO = 'aagjalpankaj/larabase'


def read_optional(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def finalize(root=Path('.'), env=None):
    env = dict(os.environ if env is None else env)
    expected = {'STAGE4_EXECUTION_ID':'A-106','STAGE4_REPO':REPO,'STAGE4_SHA':SHA,'STAGE4_RECOVERY_BATCH':'A02'}
    if any(env.get(k) != v for k, v in expected.items()) or env.get('STAGE4_OS') not in ('linux','windows','macos'):
        raise ValueError('Not the exact frozen A-106 recovery assignment')
    osname = env['STAGE4_OS']
    outfile = root/'stage4_execution/result.json'
    pre = read_optional(root/'stage4_v3_preflight/preflight.json') or {}
    patch = read_optional(root/'stage4_recovery/a106_sqlite_hook_patch.json')
    sqlite = read_optional(root/'stage4_recovery/a106_sqlite_provision.json')
    data = read_optional(outfile) or {}
    for key, value in [('execution_id','A-106'),('repo_full_name',REPO),('latest_sha',SHA),('os',osname)]:
        if data.get(key) not in (None, '', value):
            raise ValueError(f'Unexpected A-106 result identity: {key}')
        data[key] = value
    patch_ok = bool(patch and patch.get('patch_applied') is True and patch.get('os') == osname and patch.get('frozen_sha') == SHA)
    sqlite_ok = bool(sqlite and sqlite.get('sqlite_file_exists_after') is True and sqlite.get('os') == osname
                     and sqlite.get('frozen_sha') == SHA and sqlite.get('checkout_head_verified') == SHA)
    provenance = {
        'experiment_id': EXPERIMENT,
        'baseline_preserved': True,
        'baseline_batch': 'A02',
        'execution_id': 'A-106', 'repo_full_name': REPO, 'latest_sha': SHA, 'os': osname,
        'github_run_id': env.get('GITHUB_RUN_ID',''),
        'interventions': ['Previously validated PHP hyphen resolver fix',
                          'Ephemeral Python set_failure recorder fix',
                          'Create frozen-project default SQLite file before running tests'],
        'preflight_status': pre.get('resolution_status','NO_ARTIFACT'),
        'selected_php': pre.get('php',''),
        'patch_applied': patch_ok,
        'sqlite_provisioned': sqlite_ok,
        'patch': patch, 'sqlite': sqlite,
        'protocol_step_outcome': env.get('STAGE4_RECOVERY_PROTOCOL_OUTCOME','unknown'),
        'composer_validate_status': data.get('composer_validate_status','UNKNOWN'),
        'composer_install_status': data.get('composer_install','NOT_RUN'),
        'composer_evidence_source': data.get('composer_evidence_source',''),
        'test_execution': data.get('test_execution','NOT_RUN'),
        'failure_category': data.get('failure_category'),
        'failure_stage': data.get('failure_stage'),
    }
    data.setdefault('test_execution','NOT_RUN')
    data['recovery_experiment'] = {
        'experiment_id': EXPERIMENT,
        'baseline_preserved': True,
        'runner_patch_applied': patch_ok,
        'sqlite_file_provisioned': sqlite_ok,
        'preflight_resolution_status': provenance['preflight_status'],
        'preflight_selected_php': provenance['selected_php'],
    }
    outfile.parent.mkdir(parents=True, exist_ok=True)
    metafile = root/'stage4_recovery/a106_sqlite_recovery_provenance.json'
    metafile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    metafile.write_text(json.dumps(provenance,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'SQLITE A-106 {osname}: preflight={provenance["preflight_status"]}, '
          f'patch={patch_ok}, sqlite={sqlite_ok}, composer={provenance["composer_install_status"]}, '
          f'test={provenance["test_execution"]}')
    return data

if __name__ == '__main__':
    finalize()
