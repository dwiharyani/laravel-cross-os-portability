#!/usr/bin/env python3
"""Audit postprocessing. Never rewrite the raw v2 protocol result without backing it up."""
import json, os, re
from pathlib import Path
ROOT=Path('stage4_execution');ROOT.mkdir(exist_ok=True)
PREF=Path('stage4_v3_preflight/preflight.json')
RESULT=ROOT/'result.json'
ANSI=re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

def extract_counts(s):
    s=ANSI.sub('',s)
    # PHPUnit summary: OK (42 tests, 101 assertions), PHPUnit failure summary
    matches=list(re.finditer(r'\b(?:OK\s*\(|Tests:\s*)(\d+)\s+tests?\b',s,re.I))
    full=list(re.finditer(r'\bTests:\s*(\d+)(?:\s*,|\s*$)',s,re.I|re.M))
    pest=list(re.finditer(r'\bTests:\s*((?:\d+\s+(?:passed|failed|skipped|incomplete|pending|risky|warnings?|errors?)\b[\s,]*)+)',s,re.I))
    if pest:
        target=pest[-1].group(1)
        pairs=re.findall(r'(\d+)\s+(passed|failed|skipped|incomplete|pending|risky|warnings?|errors?)\b',target,re.I)
        counts={k:0 for k in ['passed','failed','skipped','incomplete','pending','risky','warnings','errors']}
        for n,k in pairs:
            k=k.lower(); k='warnings' if k=='warning' else ('errors' if k=='error' else k)
            counts[k]+=int(n)
        return {'tests_total':sum(counts.values()),'tests_passed':counts['passed'],
                'tests_failed':counts['failed']+counts['errors'],
                'tests_skipped':counts['skipped']+counts['pending'],
                'tests_incomplete':counts['incomplete']+counts['risky']+counts['warnings'],
                'test_metrics_status':'PARSED_PEST_SUMMARY'}
    if full or matches:
        total=int((full or matches)[-1].group(1))
        def get(name):
            ms=list(re.finditer(r'\b'+name+r':\s*(\d+)',s,re.I))
            return int(ms[-1].group(1)) if ms else 0
        failed=get('Failures')+get('Errors');skipped=get('Skipped');incomplete=get('Incomplete')
        return {'tests_total':total,'tests_failed':failed,'tests_skipped':skipped,
                'tests_incomplete':incomplete,'tests_passed':max(0,total-failed-skipped-incomplete),
                'test_metrics_status':'PARSED_PHPUNIT_SUMMARY'}
    return {'test_metrics_status':'NOT_AVAILABLE'}

def main():
    r=json.loads(RESULT.read_text(encoding='utf-8')) if RESULT.exists() else {}
    if RESULT.exists():
        (ROOT/'result_original_v2.json').write_bytes(RESULT.read_bytes())
    pre=json.loads(PREF.read_text()) if PREF.exists() else {'resolution_status':'MISSING_PREFLIGHT','errors':['preflight file absent']}
    r.update({'schema_version':'stage4-v3-corrective','baseline_preserved':True,
             'pipeline_revision':'stage4-v3-corrective','preflight_status':pre.get('resolution_status'),
             'php_runtime_resolved':pre.get('php',''),'php_runtime_resolution':'COMPOSER_JSON_AND_LOCK_CONSTRAINTS',
             'php_runtime_candidate_evidence':pre.get('php_candidate_evidence',{}),
             'test_command_selection_reason':pre.get('test_selection_reason',''),
             'php_extensions_required':pre.get('required_extensions',[]),
             'test_metrics_status':'NOT_AVAILABLE'})
    for k in ['execution_id','repo_full_name','latest_sha','os','project_id','execution_batch','execution_owner']:
        if not r.get(k):r[k]=os.getenv('STAGE4_'+{'execution_id':'EXECUTION_ID','repo_full_name':'REPO','latest_sha':'SHA','os':'OS','project_id':'PROJECT_ID','execution_batch':'BATCH','execution_owner':'OWNER'}[k],'')
    if pre.get('resolution_status')!='RESOLVED':
        r.update({'reproducibility_status':'NOT_EVALUATED','execution_validity':'INVALID_PREFLIGHT',
          'failure_stage':'PHP_RUNTIME_RESOLUTION','failure_category':'PHP_RUNTIME_UNRESOLVED',
          'failure_detail':'; '.join(pre.get('errors',[])),'test_execution':'NOT_RUN'})
    elif os.getenv('STAGE4_V3_SETUP_OUTCOME') not in ('success',''):
        r.update({'reproducibility_status':'NOT_EVALUATED','execution_validity':'INVALID_INFRASTRUCTURE',
          'failure_stage':'PHP_SETUP','failure_category':'PHP_SETUP_FAILURE',
          'failure_detail':'setup-php step failed','test_execution':'NOT_RUN'})
    elif pre.get('resolution_status')=='RESOLVED' and not pre.get('command'):
        r.update({'reproducibility_status':'NOT_EVALUATED', 'execution_validity':'NO_TEST_COMMAND',
                  'failure_stage':'TEST_DISCOVERY', 'failure_category':'TEST_COMMAND_UNAVAILABLE',
                  'failure_detail':'No Composer test script or eligible PHPUnit/Pest test runner found',
                  'test_execution':'NOT_RUN'})
    elif os.getenv('STAGE4_V3_PROTOCOL_OUTCOME') not in ('success','') and not RESULT.exists():
        r.update({'reproducibility_status':'NOT_EVALUATED','execution_validity':'INVALID_INFRASTRUCTURE',
          'failure_stage':'PROTOCOL','failure_category':'PROTOCOL_FAILURE',
          'failure_detail':'Protocol step failed without a result.json','test_execution':'NOT_RUN'})
    # Compare exact PHP extensions with declared platform requirements.
    modules_file=Path('stage4_v3_preflight/php_modules.txt')
    if modules_file.exists():
        installed={z.strip().lower() for z in modules_file.read_text(errors='replace').splitlines() if z.strip() and not z.startswith('[')}
        required={z.lower() for z in pre.get('required_extensions',[])}
        missing=sorted(required-installed)
        windows_only={'pcntl','posix','sysvmsg','sysvsem','sysvshm','shmop'}
        r['php_extensions_installed']=sorted(installed)
        r['php_extensions_missing']=missing
        r['php_extensions_unavailable_on_os']=sorted(set(missing)&windows_only) if r.get('os')=='windows' else []
        r['php_extensions_missing_configurable']=sorted(set(missing)-set(r['php_extensions_unavailable_on_os']))
        r['extension_support_status']='UNAVAILABLE_ON_WINDOWS' if r['php_extensions_unavailable_on_os'] else ('MISSING_CONFIGURABLE' if missing else 'AVAILABLE')
    else:
        r['extension_support_status']='NOT_CHECKED'
    # Composer install fatal exceptions can be secondary PHP version mismatch or extension failures.
    if r.get('composer_install')=='FAIL':
        detail=r.get('failure_detail','') or ''
        low=detail.lower()
        if any(k in low for k in ['require a php version', 'requires php ', 'php version (', 'your php version', 'php ^', 'php >=']):
            r['failure_category']='PHP_VERSION_DEPENDENCY_MISMATCH'
        elif 'requires ext-' in low or 'missing from your system' in low or 'extension' in low and 'missing' in low:
            r['failure_category']='EXTENSION_MISSING'
        if r.get('failure_category')=='EXTENSION_MISSING' and r.get('os')=='windows':
            detail_low=detail.lower()
            unsupported={'pcntl','posix','sysvmsg','sysvsem','sysvshm','shmop'}
            if any(('ext-'+x) in detail_low for x in unsupported):
                r['failure_category']='PLATFORM_EXTENSION_UNAVAILABLE'
        r['failure_stage']='COMPOSER_INSTALL'
    logs=ROOT/'logs'; pieces=[]
    if logs.exists():
        for f in sorted(logs.glob('*test*.log')):
            try:pieces.append(f.read_text(encoding='utf-8',errors='replace'))
            except:pass
    if r.get('test_execution') in ('PASS','FAIL'):
        metrics=extract_counts('\n'.join(pieces))
        if metrics['test_metrics_status']=='NOT_AVAILABLE':
            # v2 may have captured output in a differently named log; do not invent counts.
            r['tests_total']=r['tests_passed']=r['tests_failed']=r['tests_skipped']=r['tests_incomplete']=None
            if r.get('test_execution')=='PASS':
                r['reproducibility_status']='UNVERIFIED_TEST_COUNTS'
                r['execution_validity']='INCOMPLETE_TEST_EVIDENCE'
        else:
            for k,v in metrics.items():r[k]=v
            if r.get('test_execution')=='PASS' and metrics['tests_total']<=0:
                r['reproducibility_status']='UNVERIFIED_TEST_COUNTS'
                r['execution_validity']='INCOMPLETE_TEST_EVIDENCE'
        r['test_metrics_status']=metrics['test_metrics_status']
    RESULT.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Finalized',r.get('execution_id'),r.get('os'),r.get('failure_category'),r.get('reproducibility_status'))
if __name__=='__main__':main()
