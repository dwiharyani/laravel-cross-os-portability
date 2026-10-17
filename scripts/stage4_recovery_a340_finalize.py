#!/usr/bin/env python3
"""Annotate isolated A-340 recovery evidence without altering recorded outcome fields."""
import json
import os
from pathlib import Path

ROOT = Path('stage4_execution')
RESULT = ROOT / 'result.json'
PRE = Path('stage4_v3_preflight/preflight.json')
OUT = Path('stage4_recovery/provenance.json')
TARGET_SHA = 'a713671b2307fae99847cec2fe78889d4501d0d0'
TARGET_REPO = 'JieAnthony/apple-mdm-system'


def run():
    eid = os.getenv('STAGE4_EXECUTION_ID')
    os_name = os.getenv('STAGE4_OS')
    sha = os.getenv('STAGE4_SHA')
    repo = os.getenv('STAGE4_REPO')
    if (eid, sha, repo) != ('A-340', TARGET_SHA, TARGET_REPO) or os_name not in ('linux', 'windows', 'macos'):
        raise SystemExit('Recovery target mismatch: will not annotate another repository or SHA')

    pre = json.loads(PRE.read_text(encoding='utf-8')) if PRE.is_file() else {}
    data = json.loads(RESULT.read_text(encoding='utf-8')) if RESULT.is_file() else {}
    if data.get('execution_id') not in (None, '', eid) or data.get('latest_sha') not in (None, '', sha):
        raise SystemExit('Result does not match frozen recovery target')
    if data.get('os') not in (None, '', os_name):
        raise SystemExit('Result OS mismatch')

    metadata = {
        'experiment_id': 'stage4-recovery-a340-php-hyphen-v1',
        'baseline_preserved': True,
        'baseline_batch': 'A05',
        'baseline_pipeline': 'stage4-v3.3',
        'execution_id': eid,
        'repo_full_name': repo,
        'latest_sha': sha,
        'os': os_name,
        'github_run_id': os.getenv('GITHUB_RUN_ID', ''),
        'intervention': 'Replace original PHP hyphen-range parser with fixed recovery copy only',
        'preflight_outcome': os.getenv('STAGE4_RECOVERY_PREFLIGHT_OUTCOME', 'unknown'),
        'preflight_resolution_status': pre.get('resolution_status', 'NO_ARTIFACT'),
        'preflight_selected_php': pre.get('php', ''),
        'preflight_errors': pre.get('errors', []) if isinstance(pre.get('errors', []), list) else [],
        'php_setup_outcome': os.getenv('STAGE4_RECOVERY_PHP_SETUP_OUTCOME', 'unknown'),
        'database_audit_step_outcome': os.getenv('STAGE4_RECOVERY_DB_OUTCOME', 'unknown'),
        'composer_diagnostic_step_outcome': os.getenv('STAGE4_RECOVERY_COMPOSER_OUTCOME', 'unknown'),
        'protocol_step_outcome': os.getenv('STAGE4_RECOVERY_PROTOCOL_OUTCOME', 'unknown'),
        'test_execution': data.get('test_execution', 'NOT_RUN'),
        'composer_install': data.get('composer_install', 'NOT_RUN'),
        'composer_evidence_source': data.get('composer_evidence_source', 'UNKNOWN'),
        'database_audit_status': data.get('database_audit_status', 'UNKNOWN'),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    ROOT.mkdir(exist_ok=True)
    data.setdefault('execution_id', eid)
    data.setdefault('repo_full_name', repo)
    data.setdefault('latest_sha', sha)
    data.setdefault('os', os_name)
    data.setdefault('test_execution', 'NOT_RUN')
    data['recovery_experiment'] = {
        'experiment_id': metadata['experiment_id'],
        'intervention': metadata['intervention'],
        'baseline_preserved': True,
        'preflight_resolution_status': metadata['preflight_resolution_status'],
    }
    RESULT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    print('RECOVERY TAGGED:', eid, os_name,
          'preflight=', metadata['preflight_resolution_status'],
          'php=', metadata['preflight_selected_php'],
          'composer=', metadata['composer_install'],
          'test=', metadata['test_execution'])


if __name__ == '__main__':
    run()
