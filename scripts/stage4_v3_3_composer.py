#!/usr/bin/env python3
"""Isolated exact-SHA Composer diagnostic, independent from DB readiness.

Security posture: do not expose secrets; do not run Composer scripts or plugins;
keep this diagnostic distinct from the full Stage 4 v2 Composer protocol.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PRE = Path('stage4_v3_preflight')
OUT = Path('stage4_v3_3_composer')
LOG_LIMIT = 2 * 1024 * 1024
CMD = ['install', '--no-interaction', '--prefer-dist', '--no-progress', '--no-scripts', '--no-plugins', '--no-ansi']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_stdout(s):
    # No credentials/secrets are passed into this step; additionally redact
    # accidental BasicAuth in URL-form diagnostic messages.
    return re.sub(r'(?i)(https?://)[^/\s@]+@', r'\1[REDACTED]@', s)

def evaluate(project, pre, php_setup_ok=True, composer_bin=None, timeout=720):
    d = {
        'schema_version': 'composer-diagnostic-v3.3',
        'execution_id': os.getenv('STAGE4_EXECUTION_ID',''),
        'os': os.getenv('STAGE4_OS',''),
        'repo_full_name': pre.get('repo_full_name',''),
        'latest_sha': pre.get('latest_sha',''),
        'status': 'NOT_RUN',
        'reason': '',
        'exit_code': None,
        'timeout_seconds': timeout,
        'method': 'COMPOSER_INSTALL_NO_SCRIPTS_NO_PLUGINS',
        'fully_comparable_to_v2': False,
        'lock_sha256_before': None,
        'lock_sha256_after': None,
        'exact_sha_verified': False,
        'php_version_selected': pre.get('php',''),
        'command_flags': CMD,
    }
    if pre.get('resolution_status') != 'RESOLVED':
        d['reason'] = 'PHP_RUNTIME_UNRESOLVED'
        return d, ''
    if not php_setup_ok:
        d['reason'] = 'PHP_SETUP_UNAVAILABLE'
        return d, ''
    if not project.is_dir() or not (project/'composer.json').is_file() or not (project/'composer.lock').is_file():
        d['reason'] = 'EXACT_SHA_PROJECT_OR_COMPOSER_FILES_MISSING'
        return d, ''
    sha = pre.get('latest_sha','')
    if not re.fullmatch(r'[a-f0-9]{40}', str(sha)):
        d['reason'] = 'INVALID_FROZEN_SHA'
        return d, ''
    try:
        got = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=str(project), text=True, timeout=15).strip()
    except (OSError, subprocess.SubprocessError):
        d['reason'] = 'SHA_VERIFICATION_FAILED'
        return d, ''
    if got != sha:
        d['reason'] = 'FROZEN_SHA_MISMATCH'
        return d, ''
    d['exact_sha_verified'] = True
    lock = project/'composer.lock'
    d['lock_sha256_before'] = digest(lock)
    exe = composer_bin or shutil.which('composer')
    if not exe:
        d['reason'] = 'COMPOSER_EXECUTABLE_MISSING'
        return d, ''
    env = dict(os.environ)
    # Never inherit common CI/package registry credentials into untrusted app tooling.
    for key in list(env):
        if (key.upper().startswith(('GH_', 'GITHUB_TOKEN', 'COMPOSER_AUTH', 'STAGE4_MYSQL', 'DB_PASSWORD',
                                   'AWS_', 'AZURE_', 'GCP_', 'GOOGLE_APPLICATION_CREDENTIALS'))):
            env.pop(key, None)
    env['COMPOSER_NO_INTERACTION'] = '1'
    env['COMPOSER_DISABLE_XDEBUG_WARN'] = '1'
    try:
        p = subprocess.run([exe, *CMD], cwd=str(project), env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=False)
        message = p.stdout[:LOG_LIMIT].decode('utf-8', errors='replace')
        if len(p.stdout) > LOG_LIMIT:
            message += '\n[LOG_TRUNCATED_AFTER_2_MiB]\n'
        d['exit_code'] = p.returncode
        d['status'] = 'PASS' if p.returncode == 0 else 'FAIL'
        d['reason'] = 'COMPOSER_RETURNED_ZERO' if p.returncode == 0 else 'COMPOSER_NONZERO_EXIT'
    except subprocess.TimeoutExpired as e:
        message = (e.stdout or b'')[:LOG_LIMIT].decode('utf-8', errors='replace')
        d['status'] = 'TIMEOUT'
        d['reason'] = 'COMPOSER_TIMEOUT'
    except (OSError, subprocess.SubprocessError) as e:
        message = ''  # Exceptions can include local paths or configuration.
        d['status'] = 'ERROR'
        d['reason'] = 'COMPOSER_INVOCATION_' + type(e).__name__
    d['lock_sha256_after'] = digest(lock) if lock.exists() else None
    if d['lock_sha256_before'] != d['lock_sha256_after']:
        d['status'] = 'INVALID'
        d['reason'] = 'FROZEN_COMPOSER_LOCK_CHANGED'
    return d, safe_stdout(message)

def main():
    OUT.mkdir(exist_ok=True)
    prefile = PRE/'preflight.json'
    try:
        pre = json.loads(prefile.read_text(encoding='utf-8')) if prefile.exists() else {}
        diag, log = evaluate(PRE/'repo', pre, os.environ.get('STAGE4_PHP_SETUP_OK','false').lower() == 'true')
    except Exception as e:
        diag = {'schema_version':'composer-diagnostic-v3.3', 'status':'ERROR',
                'reason':'DIAGNOSTIC_EXCEPTION_' + type(e).__name__,
                'method':'COMPOSER_INSTALL_NO_SCRIPTS_NO_PLUGINS', 'fully_comparable_to_v2':False}
        log = ''
    (OUT/'composer_diagnostic.json').write_text(json.dumps(diag, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    (OUT/'composer_install.log').write_text(log, encoding='utf-8')
    print('Composer diagnostic:', diag['status'], 'reason:', diag['reason'])
    # Always return 0 so test DB gating and artifact upload still happen.
    return 0

if __name__ == '__main__':
    sys.exit(main())
