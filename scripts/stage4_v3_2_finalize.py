#!/usr/bin/env python3
"""Overlay DB audit onto existing v3 result; never invent test evidence."""
import json
import os
from pathlib import Path

ROOT=Path('stage4_execution')
OUT=ROOT/'result.json'
AUDIT=Path('stage4_v3_2_database/database_audit.json')


def finish():
    ROOT.mkdir(exist_ok=True)
    data=json.loads(OUT.read_text(encoding='utf-8')) if OUT.is_file() else {}
    if OUT.is_file():
        (ROOT/'result_before_database_audit.json').write_bytes(OUT.read_bytes())
    db=json.loads(AUDIT.read_text(encoding='utf-8')) if AUDIT.exists() else {
        'status':'DATABASE_INSPECTION_FAILED','reason':'Database audit file missing',
        'run_protocol':'false', 'database_name':''}
    for field,env_key in [('execution_id','STAGE4_EXECUTION_ID'),('repo_full_name','STAGE4_REPO'),
                          ('latest_sha','STAGE4_SHA'),('os','STAGE4_OS'),('project_id','STAGE4_PROJECT_ID')]:
        if not data.get(field):data[field]=os.getenv(env_key,'')
    data['schema_version']='stage4-v3.2-database-aware'
    data['pipeline_revision']='stage4-v3.2'
    data['run_id']=os.getenv('GITHUB_RUN_ID','')
    data['database_audit_status']=db.get('status','DATABASE_INSPECTION_FAILED')
    data['database_expected_engine']=db.get('expected_engine')
    data['database_expected_version']=db.get('expected_version')
    data['database_actual_version']=db.get('server_version_reported')
    data['database_infrastructure_verified']=db.get('infrastructure_verified',False)
    data['database_name_isolated']=db.get('database_name') or None
    data['database_audit_reason']=db.get('reason')
    data['database_audit_comparable']=bool(db.get('infrastructure_verified') or db.get('status')=='DATABASE_NO_EXTERNAL_SERVICE_REQUIRED')
    data['prior_artifacts_preserved']=True
    if db.get('run_protocol')!='true':
        data.update(reproducibility_status='NOT_EVALUATED',
                    execution_validity='DATABASE_INFRASTRUCTURE_NOT_EVALUATED',
                    failure_category=db.get('status','DATABASE_INSPECTION_FAILED'),
                    failure_stage='DATABASE_PREFLIGHT',
                    failure_detail=db.get('reason','Database preflight unavailable'),
                    database_preparation='NOT_AVAILABLE',
                    test_execution='NOT_RUN',test_exit_code=None,
                    tests_total=None,tests_passed=None,tests_failed=None,
                    tests_skipped=None,tests_incomplete=None,
                    test_metrics_status='NOT_AVAILABLE')
        # Never claim that Composer ran when the DB gate skipped entire protocol.
        data['composer_install']='NOT_RUN'
    elif db.get('status')=='DATABASE_READY':
        data['database_preparation']='TLS_VERIFIED_PREEXISTING_SCHEMA'
    elif db.get('status')=='DATABASE_REQUIREMENTS_UNVERIFIED':
        data['database_preparation']='NOT_VERIFIED_NO_EXPLICIT_DB_EVIDENCE'
    elif db.get('status')=='DATABASE_NO_EXTERNAL_SERVICE_REQUIRED':
        data['database_preparation']='IN_PROCESS_SQLITE_DECLARED'
    OUT.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    print('DB-aware finalized:',data.get('execution_id'),data.get('os'),
          data.get('database_audit_status'),data.get('reproducibility_status'))

if __name__=='__main__':finish()
