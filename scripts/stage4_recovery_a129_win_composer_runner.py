#!/usr/bin/env python3
"""Isolated, Windows-only Composer executable recovery for A-129 native tests."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXPECTED_ID = 'A-129'
EXPECTED_REPO = 'Coyote-OSS/coyote'
EXPECTED_SHA = '0ead8b60f68f3acac974000357b73b4a89049d76'
EXPECTED_OS = {'windows'}
PROTOCOL_ID = 'A129_UPSTREAM_CI_NATIVE_UNIT_INMEMORY_WIN_COMPOSER_V2'
COMMANDS = (
    ('module_unit', ['php', './vendor/bin/phpunit', './modules/'], None, 'phpunit'),
    ('acceptance_unit', ['php', './vendor/bin/phpunit', './features/'], None, 'phpunit'),
    ('behat_in_memory', ['php', './vendor/bin/behat'], {'TEST_CHANNEL': 'in-memory'}, 'behat'),
)


def positive_counts(output, kind):
    if kind == 'phpunit':
        patterns = (r'(?im)\bTests:\s*(\d+)\b', r'(?im)\bOK\s*\(\s*(\d+)\s+tests?\b')
    elif kind == 'behat':
        patterns = (r'(?im)\b(\d+)\s+scenarios?\b',)
    else:
        return None
    for pat in patterns:
        matches = re.findall(pat, output)
        if matches:
            return int(matches[-1])
    return None


def status_for(returncode, output, kind):
    if returncode != 0:
        return 'FAIL', False, positive_counts(output, kind)
    count = positive_counts(output, kind)
    return ('PASS_VERIFIED' if count is not None and count > 0 else 'PASS_UNVERIFIED',
            count is not None and count > 0, count)



def composer_candidates(platform_name=None, which=None):
    """Return explicit Windows invocations, with no arbitrary shell interpolation.

    Running a bare `composer` through Python CreateProcess on Windows is not
    equivalent to invoking `composer` from GitHub Actions' Git Bash step.
    Candidate list is local-runner discovery, not a change to frozen source.
    """
    platform_name = sys.platform if platform_name is None else platform_name
    which = shutil.which if which is None else which
    if platform_name == 'win32':
        out = []
        seen = set()
        for ext in ('composer.bat', 'composer.cmd', 'composer.exe'):
            path = which(ext)
            if path and os.path.normcase(path) not in seen:
                out.append((f'EXPLICIT_{ext.upper()}', [path]))
                seen.add(os.path.normcase(path))
        bash = which('bash.exe') or which('bash')
        if bash:
            # $@ supplies fixed arguments to bash without injecting user text
            # into shell syntax. Replicates GitHub Actions' `shell: bash` lookup.
            out.append(('GIT_BASH_PATH', [bash, '-c', 'composer "$@"', 'stage4-composer']))
        return out
    path = which('composer')
    return [('NATIVE_PATH', [path])] if path else []


def run_step(name, args, cwd, logs_dir, timeout, extra_env=None):
    start = time.monotonic()
    environ = os.environ.copy()
    if extra_env:
        environ.update(extra_env)
    try:
        completed = subprocess.run(args, cwd=str(cwd), env=environ, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors='replace',
                                   timeout=timeout, check=False)
        rc, out, timed_out = completed.returncode, completed.stdout, False
    except subprocess.TimeoutExpired as e:
        raw = e.stdout or b''
        out = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else str(raw)
        out += '\nTIMEOUT'
        rc, timed_out = 124, True
    except OSError as e:
        rc, out, timed_out = 127, f'{type(e).__name__}: {e}', False
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / f'{name}.log').write_text(out[-250000:], encoding='utf-8', errors='replace')
    return {'return_code': rc, 'timeout': timed_out,
            'duration_seconds': round(time.monotonic()-start, 3),
            'log_file': f'logs/{name}.log', 'log_tail': out[-2000:]}


def validate_inputs(env):
    eid, repo, sha, osname = (env.get(v, '') for v in
                             ('STAGE4_EXECUTION_ID','STAGE4_REPO','STAGE4_SHA','STAGE4_OS'))
    if (eid,repo,sha) != (EXPECTED_ID,EXPECTED_REPO,EXPECTED_SHA):
        raise ValueError('Unexpected recovery target; no third-party checkout will run')
    if osname not in EXPECTED_OS:
        raise ValueError(f'Unexpected OS: {osname}')
    return eid, repo, sha, osname


def execute(output_dir):
    eid, repo, sha, osname = validate_inputs(os.environ)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs = output_dir / 'logs'
    record = {'execution_id':eid, 'repo_full_name':repo, 'frozen_sha':sha,
              'os':osname, 'runner':os.environ.get('STAGE4_RUNNER',''),
              'protocol_id':PROTOCOL_ID, 'scope':'TARGETED_NATIVE_UNIT_IN_MEMORY_ONLY',
              'baseline_overwritten':False, 'full_protocol_equivalent':False,
              'php_setup_ok':os.environ.get('STAGE4_PHP_SETUP_OK') == 'true',
              'checkout':'NOT_RUN', 'actual_sha':None,
              'composer_install':'NOT_RUN','composer_install_source':'UPSTREAM_CI_NO_SCRIPTS',
              'composer_validate':'NOT_RUN', 'steps':{},'test_execution':'NOT_RUN'}
    def save():
        (output_dir / 'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    try:
        target = output_dir / 'frozen_checkout'
        target.mkdir(exist_ok=True)
        step = run_step('git_init',['git','init',str(target.resolve())],Path.cwd(),logs,60)
        if step['return_code'] != 0: raise RuntimeError('git init failed: '+step['log_tail'])
        step = run_step('git_remote',['git','-C',str(target.resolve()),'remote','add','origin',
                                    'https://github.com/'+repo+'.git'],Path.cwd(),logs,60)
        if step['return_code'] != 0: raise RuntimeError('git remote failed: '+step['log_tail'])
        step = run_step('git_fetch',['git','-C',str(target.resolve()),'fetch','--depth=1','origin',sha],Path.cwd(),logs,240)
        if step['return_code'] != 0: raise RuntimeError('git fetch failed: '+step['log_tail'])
        step = run_step('git_checkout',['git','-C',str(target.resolve()),'checkout','--detach','FETCH_HEAD'],Path.cwd(),logs,60)
        if step['return_code'] != 0: raise RuntimeError('git checkout failed: '+step['log_tail'])
        got = subprocess.check_output(['git','-C',str(target.resolve()),'rev-parse','HEAD'],text=True).strip()
        record['actual_sha'] = got
        if got != sha: raise RuntimeError(f'Frozen SHA mismatch: {got}')
        record['checkout'] = 'PASS'
        if not record['php_setup_ok']:
            record['blocked_reason'] = 'PHP setup step did not succeed; refusing to use another PHP runtime'
            return record
        record['steps']['php_version'] = run_step('php_version',['php','--version'],target,logs,40)
        if record['steps']['php_version']['return_code'] != 0:
            record['blocked_reason'] = 'PHP executable unavailable'
            return record
        runtime_text=(logs/'php_version.log').read_text(encoding='utf-8',errors='replace')
        runtime_match=re.search(r'PHP\s+(\d+)\.(\d+)\.(\d+)',runtime_text)
        record['php_runtime_version'] = runtime_match.group(0) if runtime_match else None
        if runtime_match is None or (runtime_match.group(1),runtime_match.group(2)) != ('8','5'):
            record['blocked_reason'] = 'Actual PHP runtime is not the requested PHP 8.5'
            return record
        # Windows CreateProcess may not resolve the extensionless 'composer' command
        # that the Git Bash workflow shell resolves. Try explicit Windows shims,
        # then Git Bash with fixed shell source and safely positional arguments.
        record['composer_resolution_attempts'] = []
        selected = None
        for idx, (strategy, prefix) in enumerate(composer_candidates(platform_name='win32')):
            probe = run_step(f'composer_probe_{idx}', prefix + ['--version'], target, logs, 45)
            record['composer_resolution_attempts'].append({
                'strategy': strategy, 'return_code': probe['return_code'],
                'log_file': probe['log_file'], 'log_tail': probe['log_tail']})
            if probe['return_code'] == 0:
                selected = prefix
                record['composer_invocation_strategy'] = strategy
                record['steps']['composer_version'] = probe
                break
        if selected is None:
            record['blocked_reason'] = 'Composer command unresolved after Windows shim and Bash probes'
            return record
        record['steps']['composer_validate'] = run_step('composer_validate',
                    selected + ['validate','--no-check-publish'],target,logs,180)
        record['composer_validate'] = ('PASS' if record['steps']['composer_validate']['return_code'] == 0 else 'FAIL')
        # Matches original tests.yml command; NOT equivalent to full protocol Composer install.
        install = run_step('composer_install',
                    selected + ['install','--no-interaction','--no-scripts','--prefer-dist'],
                    target,logs,1200)
        record['steps']['composer_install'] = install
        record['composer_install'] = 'PASS' if install['return_code'] == 0 else 'FAIL'
        if record['composer_install'] != 'PASS':
            record['blocked_reason'] = 'Composer install failed; tests correctly NOT_RUN'
            return record
        outcomes = []
        for name,args,env_override,kind in COMMANDS:
            binary = target/'vendor'/'bin'/('behat' if kind=='behat' else 'phpunit')
            if not binary.is_file():
                record['steps'][name] = {'status':'NOT_RUN','verified':False,'reason':f'No {binary.name} binary'}
                outcomes.append('NOT_RUN')
                continue
            step = run_step(name,args,target,logs,600,env_override)
            full_log=(logs/f'{name}.log').read_text(encoding='utf-8',errors='replace')
            status, verified, count = status_for(step['return_code'], full_log, kind)
            step.update(status=status, verified=verified, detected_test_count=count,
                        invoked_as=' '.join(args), ci_source_command= ('TEST_CHANNEL=in-memory ./vendor/bin/behat' if name=='behat_in_memory' else
                        './vendor/bin/phpunit ./modules/' if name=='module_unit' else './vendor/bin/phpunit ./features/'))
            record['steps'][name] = step
            outcomes.append(status)
        if any(s=='FAIL' for s in outcomes): record['test_execution']='FAIL'
        elif any(s=='NOT_RUN' for s in outcomes): record['test_execution']='PARTIAL_NOT_RUN'
        elif all(s=='PASS_VERIFIED' for s in outcomes): record['test_execution']='PASS_VERIFIED_ALL_THREE_TARGETS'
        else: record['test_execution']='PASS_UNVERIFIED_OR_MIXED'
        return record
    except Exception as e:
        record['exception'] = f'{type(e).__name__}: {e}'
        return record
    finally:
        save()
        # Source checkout never uploaded: workflow artifact explicitly excludes frozen_checkout.


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', default='stage4_recovery_a129_windows_composer')
    args=parser.parse_args()
    try:
        row=execute(Path(args.output))
        print(json.dumps({k:row.get(k) for k in ('execution_id','os','frozen_sha','actual_sha','checkout',
                  'composer_install','composer_validate','test_execution','blocked_reason','exception')},indent=2))
        for name in ('module_unit','acceptance_unit','behat_in_memory'):
            print(name, row['steps'].get(name,{}).get('status','NOT_RUN'))
    except Exception as e:
        print(f'RECOVERY INPUT GUARD FAILURE: {type(e).__name__}: {e}',file=sys.stderr)
        return 2
    return 0

if __name__=='__main__': sys.exit(main())
