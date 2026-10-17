#!/usr/bin/env python3
"""Tag A02-B isolated PHP resolver + v2 recorder recovery; preserve outcomes.

Run after v3.3 finalization; never touch baseline files.
"""
import json
import os
import re
from pathlib import Path

TARGETS = {
    'A-108': 'tsukumijima/weather-api',
    'A-128': 'systemsdk/docker-nginx-php-laravel',
    'A-129': 'Coyote-OSS/coyote',
}
EXPERIMENT = 'stage4-php-hyphen-scope-pilot-a02-b-v1'
OSS = {'linux', 'windows', 'macos'}


def finalize(root=Path('.'), environ=None):
    env = os.environ if environ is None else environ
    eid, repo, sha, osname = (env.get(x, '') for x in
        ('STAGE4_EXECUTION_ID', 'STAGE4_REPO', 'STAGE4_SHA', 'STAGE4_OS'))
    if TARGETS.get(eid) != repo or env.get('STAGE4_RECOVERY_BATCH') != 'A02':
        raise ValueError('Not a permitted frozen A02 recovery repository')
    if osname not in OSS or not re.fullmatch('[0-9a-fA-F]{40}', sha):
        raise ValueError('Invalid OS/SHA for recovery')
    result_path = root / 'stage4_execution/result.json'
    preflight_path = root / 'stage4_v3_preflight/preflight.json'
    provenance_path = root / 'stage4_recovery/provenance_b.json'
    result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {}
    patch_path = root / 'stage4_recovery/pilot_b_protocol_patch.json'
    patch = json.loads(patch_path.read_text(encoding='utf-8')) if patch_path.exists() else None
    patch_ok = bool(patch and patch.get('experiment_id') == EXPERIMENT and
                    patch.get('applied_in_ephemeral_runner') is True and
                    patch.get('execution_id') == eid and patch.get('os') == osname and
                    patch.get('frozen_sha') == sha)
    preflight = json.loads(preflight_path.read_text(encoding='utf-8')) if preflight_path.exists() else {}
    for key, expected in (('execution_id', eid), ('repo_full_name', repo),
                          ('latest_sha', sha), ('os', osname)):
        if result.get(key) not in (None, '', expected):
            raise ValueError(f'Recovery result {key} mismatch')
        result.setdefault(key, expected)
    provenance = {
        'experiment_id': EXPERIMENT,
        'intervention': 'Fixed PHP hyphen range parser + fail-closed ephemeral v2 failure recorder correction (no app DB changes)',
        'v2_failure_recorder_patch_applied': patch_ok,
        'v2_failure_recorder_patch': patch,
        'baseline_preserved': True,
        'baseline_batch': 'A02',
        'original_pipeline': 'stage4-v3.3',
        'execution_id': eid, 'repo_full_name': repo,
        'latest_sha': sha, 'os': osname,
        'github_run_id': env.get('GITHUB_RUN_ID', ''),
        'preflight_resolution_status': preflight.get('resolution_status', 'NO_ARTIFACT'),
        'preflight_selected_php': preflight.get('php', ''),
        'preflight_errors': preflight.get('errors', []),
        'preflight_step': env.get('STAGE4_RECOVERY_PREFLIGHT_OUTCOME', 'unknown'),
        'php_setup_step': env.get('STAGE4_RECOVERY_PHP_SETUP_OUTCOME', 'unknown'),
        'db_audit_step': env.get('STAGE4_RECOVERY_DB_OUTCOME', 'unknown'),
        'composer_diagnostic_step': env.get('STAGE4_RECOVERY_COMPOSER_OUTCOME', 'unknown'),
        'full_protocol_step': env.get('STAGE4_RECOVERY_PROTOCOL_OUTCOME', 'unknown'),
        'recorder_patch_step': env.get('STAGE4_RECOVERY_PATCH_OUTCOME', 'unknown'),
        'composer_validate': result.get('composer_validate_status', 'UNKNOWN'),
        'composer_install': result.get('composer_install', 'NOT_RUN'),
        'composer_evidence_source': result.get('composer_evidence_source', 'UNKNOWN'),
        'test_execution': result.get('test_execution', 'NOT_RUN'),
        'database_audit_status': result.get('database_audit_status', 'UNKNOWN'),
    }
    result.setdefault('test_execution', 'NOT_RUN')
    result['recovery_experiment'] = {
        'experiment_id': EXPERIMENT,
        'baseline_preserved': True,
        'intervention': provenance['intervention'],
        'v2_failure_recorder_patch_applied': patch_ok,
        'preflight_resolution_status': provenance['preflight_resolution_status'],
        'preflight_selected_php': provenance['preflight_selected_php'],
        'recorder_patch_step': provenance['recorder_patch_step'],
    }
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'RECOVERY TAGGED {eid}/{osname} PHP={provenance["preflight_selected_php"]} '
          f'preflight={provenance["preflight_resolution_status"]} '
          f'Composer={provenance["composer_install"]} test={provenance["test_execution"]}')
    return result


if __name__ == '__main__':
    finalize()
