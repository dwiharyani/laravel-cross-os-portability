#!/usr/bin/env python3
"""Write isolated recovery provenance; never rewrite Stage 4 baseline artifacts."""
import json
import os
from pathlib import Path
from stage4_recovery_bulk10_prepare import published_targets, EXPERIMENT, TARGET_IDS


def finalize(root=Path('.'), env=None, matrix=None):
    env = os.environ if env is None else env
    eid, repo, sha, system, batch = (env.get(k,'') for k in
        ('STAGE4_EXECUTION_ID','STAGE4_REPO','STAGE4_SHA','STAGE4_OS','STAGE4_RECOVERY_BATCH'))
    if eid not in TARGET_IDS:raise ValueError('Not one of ten frozen recovery candidates')
    rows = matrix['include'] if matrix is not None else published_targets()['include']
    allowed = [r for r in rows if r['execution_id'] == eid and r['os'] == system]
    if len(allowed) != 1:raise ValueError('Invalid/missing OS in immutable manifest')
    allowed=allowed[0]
    for key,value in [('repo_full_name',repo),('latest_sha',sha),('execution_batch',batch)]:
        if allowed[key] != value:raise ValueError(f'Frozen {key} mismatch')
    result_path = root/'stage4_execution/result.json'
    preflight_path = root/'stage4_v3_preflight/preflight.json'
    patch_path = root/'stage4_recovery/bulk10_protocol_patch.json'
    provenance_path = root/'stage4_recovery/bulk10_provenance.json'
    result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {}
    preflight = json.loads(preflight_path.read_text(encoding='utf-8')) if preflight_path.exists() else {}
    patch = json.loads(patch_path.read_text(encoding='utf-8')) if patch_path.exists() else None
    patch_ok = bool(patch and patch.get('experiment_id')==EXPERIMENT and
                    patch.get('applied_in_ephemeral_runner') is True and
                    patch.get('execution_id')==eid and patch.get('frozen_sha')==sha and
                    patch.get('os')==system and patch.get('repository')==repo)
    for key,expected in [('execution_id',eid),('repo_full_name',repo),('latest_sha',sha),
                         ('os',system),('execution_batch',batch)]:
        if result.get(key) not in (None,'',expected):
            raise ValueError(f'Result identity mismatch: {key}')
        result[key]=expected
    result['test_execution']=result.get('test_execution') or 'NOT_RUN'
    provenance = {
        'experiment_id':EXPERIMENT,'baseline_preserved':True,'full_protocol_equivalent':False,
        'intervention':'PHP hyphen resolver + optional ephemeral v2 failure recorder fix; no automatic DB provisioning',
        'execution_id':eid,'repo_full_name':repo,'latest_sha':sha,'os':system,
        'batch':batch,'project_id':allowed['project_id'],
        'github_run_id':env.get('GITHUB_RUN_ID',''),
        'preflight_resolution_status':preflight.get('resolution_status','NO_ARTIFACT'),
        'preflight_selected_php':preflight.get('php',''),
        'preflight_errors':preflight.get('errors',[]),
        'v2_failure_recorder_patch_applied':patch_ok,
        'v2_failure_recorder_patch':patch,
        'preflight_step':env.get('STAGE4_RECOVERY_PREFLIGHT_OUTCOME','unknown'),
        'php_setup_step':env.get('STAGE4_RECOVERY_PHP_SETUP_OUTCOME','unknown'),
        'db_audit_step':env.get('STAGE4_RECOVERY_DB_OUTCOME','unknown'),
        'composer_diagnostic_step':env.get('STAGE4_RECOVERY_COMPOSER_OUTCOME','unknown'),
        'full_protocol_step':env.get('STAGE4_RECOVERY_PROTOCOL_OUTCOME','unknown'),
        'recorder_patch_step':env.get('STAGE4_RECOVERY_PATCH_OUTCOME','unknown'),
        'composer_install':result.get('composer_install','NOT_RUN'),
        'composer_evidence_source':result.get('composer_evidence_source','UNKNOWN'),
        'composer_validate':result.get('composer_validate_status','UNKNOWN'),
        'test_execution':result['test_execution'],
        'database_audit_status':result.get('database_audit_status','UNKNOWN'),
    }
    result['recovery_experiment'] = {
        'experiment_id':EXPERIMENT,'baseline_preserved':True,
        'full_protocol_equivalent':False,
        'batch':batch,'project_id':allowed['project_id'],
        'preflight_resolution_status':provenance['preflight_resolution_status'],
        'preflight_selected_php':provenance['preflight_selected_php'],
        'v2_failure_recorder_patch_applied':patch_ok,
        'intervention':provenance['intervention'],
    }
    result_path.parent.mkdir(parents=True,exist_ok=True)
    provenance_path.parent.mkdir(parents=True,exist_ok=True)
    result_path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    provenance_path.write_text(json.dumps(provenance,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'ISOLATED RECOVERY {eid}/{system}: PHP={provenance["preflight_selected_php"]} '
          f'Composer={provenance["composer_install"]} '
          f'source={provenance["composer_evidence_source"]} test={result["test_execution"]}')
    return result

if __name__=='__main__':finalize()
