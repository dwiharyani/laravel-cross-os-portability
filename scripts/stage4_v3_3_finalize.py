#!/usr/bin/env python3
"""Attach independently measured Composer evidence without manufacturing test PASS.

Run this AFTER the original v3 and v3.2 finalizers. Original full-protocol
Composer outcome takes precedence, with provenance field explicitly recorded.
"""
import json
import os
from pathlib import Path

ROOT = Path('stage4_execution')
RESULT = ROOT/'result.json'
DIAG = Path('stage4_v3_3_composer/composer_diagnostic.json')
AUDIT = Path('stage4_v3_2_database/database_audit.json')

def overlay(data, d, db, protocol_outcome):
    data = dict(data)
    data['schema_version'] = 'stage4-v3.3-composer-first'
    data['pipeline_revision'] = 'stage4-v3.3'
    data['composer_diagnostic'] = d.get('status', 'NOT_RUN')
    data['composer_diagnostic_method'] = d.get('method', 'COMPOSER_INSTALL_NO_SCRIPTS_NO_PLUGINS')
    data['composer_diagnostic_exit_code'] = d.get('exit_code')
    data['composer_diagnostic_reason'] = d.get('reason','')
    data['composer_diagnostic_lock_sha256'] = d.get('lock_sha256_before')
    data['composer_diagnostic_fully_comparable_to_v2'] = False
    data['composer_diagnostic_exact_sha_verified'] = d.get('exact_sha_verified', False)
    data['full_protocol_step_outcome'] = protocol_outcome
    data['database_audit_status'] = db.get('status', data.get('database_audit_status'))
    actual_composer = str(data.get('composer_install') or '').upper()
    if protocol_outcome in ('success','failure') and actual_composer in ('PASS','FAIL'):
        data['composer_evidence_source'] = 'V2_FULL_PROTOCOL'
        data['composer_diagnostic_vs_v2'] = ('SAME' if actual_composer == d.get('status')
                                              else 'DIFFERENT')
    elif d.get('status') in ('PASS','FAIL') and d.get('exact_sha_verified'):
        data['composer_install'] = d['status']
        data['composer_evidence_source'] = 'V3_3_DIAGNOSTIC_NO_SCRIPTS_NO_PLUGINS'
        data['composer_diagnostic_vs_v2'] = 'NO_V2_COMPOSER_RESULT'
    else:
        if actual_composer not in ('PASS', 'FAIL'):
            data['composer_install'] = 'NOT_RUN'
        data['composer_evidence_source'] = ('V2_FULL_PROTOCOL' if actual_composer in ('PASS','FAIL')
                                           else 'NO_VALID_COMPOSER_EVIDENCE')
        data['composer_diagnostic_vs_v2'] = 'NOT_COMPARABLE'
    # Once external DB is unavailable or unresolved, test must remain NOT_RUN,
    # even if isolated Composer install succeeded; never override the DB cause.
    if db.get('run_protocol') != 'true':
        data['test_execution'] = 'NOT_RUN'
        data['reproducibility_status'] = 'NOT_EVALUATED'
        data['tests_total'] = data['tests_passed'] = data['tests_failed'] = None
        data['tests_skipped'] = data['tests_incomplete'] = None
        data['test_metrics_status'] = 'NOT_AVAILABLE'
        data['composer_diagnostic_only_due_to_db_gate'] = d.get('status') in ('PASS','FAIL')
    else:
        data['composer_diagnostic_only_due_to_db_gate'] = False
    # A workflow can finish green after a caught protocol failure. Preserve
    # protocol interruption as NOT_EVALUATED, not application test FAIL.
    if protocol_outcome in ('failure','cancelled','skipped') and data.get('test_execution') not in ('PASS','FAIL'):
        data['test_execution'] = 'NOT_RUN'
        data['reproducibility_status'] = 'NOT_EVALUATED'
        data['tests_total'] = data['tests_passed'] = data['tests_failed'] = None
    return data

def main():
    ROOT.mkdir(exist_ok=True)
    data = json.loads(RESULT.read_text(encoding='utf-8')) if RESULT.exists() else {}
    if RESULT.exists():
        (ROOT/'result_before_v3_3_overlay.json').write_bytes(RESULT.read_bytes())
    d = json.loads(DIAG.read_text(encoding='utf-8')) if DIAG.exists() else {'status':'NOT_RUN', 'reason':'MISSING_DIAGNOSTIC'}
    db = json.loads(AUDIT.read_text(encoding='utf-8')) if AUDIT.exists() else {'run_protocol':'false', 'status':'DATABASE_AUDIT_UNAVAILABLE'}
    data = overlay(data, d, db, os.getenv('STAGE4_PROTOCOL_OUTCOME','skipped'))
    RESULT.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('v3.3 finalized:', data.get('execution_id'), data.get('os'),
          'Composer=', data.get('composer_install'), 'source=', data.get('composer_evidence_source'),
          'test=', data.get('test_execution'), 'db=', data.get('database_audit_status'))

if __name__ == '__main__':
    main()
