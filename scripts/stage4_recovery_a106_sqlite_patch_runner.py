#!/usr/bin/env python3
"""Runner-only patch: reuse the proven set_failure fix and insert SQLite hook before tests.

Checks Git HEAD equivalence (except harmless CRLF conversion). A baseline runner
source and local v2 file are never altered. The hook does not change the repo.
"""
import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from stage4_recovery_a106_patch_runner import recover_source, verify_checkout_source

SOURCE = Path('scripts/14_cross_os_reproducibility_v2.py')
META = Path('stage4_recovery/a106_sqlite_hook_patch.json')
SHA = '3c3ac5c009f5d87f5e5208be1f213e9aa08e2c2d'
HOOK = '''    from stage4_recovery_a106_sqlite_runtime import provision as _stage4_sqlite_provision
    _stage4_sqlite_provision(TARGET)

'''


def patch_source(original: bytes):
    fixed, stages = recover_source(original)
    # Restrict injection to ONE AST-validated subprocess test execution in main().
    tree = ast.parse(fixed.decode('utf-8'))
    calls = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'run' and len(node.args) == 1
                and isinstance(node.args[0], ast.Name) and node.args[0].id == 'command'
                and any(kw.arg == 'step' and isinstance(kw.value, ast.Constant)
                        and kw.value.value == 'test_execution' for kw in node.keywords)):
            calls.append(node)
    if len(calls) != 1:
        raise ValueError(f'Expected exactly 1 test_execution run(command), found {len(calls)}')
    call = calls[0]
    containing = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and n.value is call]
    if len(containing) != 1 or not isinstance(containing[0].targets[0], ast.Tuple):
        raise ValueError('Unexpected shape of test result assignment')
    fields = containing[0].targets[0].elts
    if [getattr(f, 'id', None) for f in fields] != ['rc','out','dur']:
        raise ValueError('Unexpected test command output assignment')
    lines = fixed.decode('utf-8').splitlines(keepends=True)
    line_index = containing[0].lineno - 1
    if not lines[line_index].startswith('    rc, out, dur = run('):
        raise ValueError('Unexpected test command indentation')
    if lines[line_index-1].strip():
        raise ValueError('Expected a blank line before the test invocation')
    # Strong guard: command has already been selected and recorded.
    preceding = ''.join(lines[max(0,line_index-8):line_index])
    if 'result["test_command"] = command' not in preceding:
        raise ValueError('Test command assignment no longer precedes invocation')
    newline = '\r\n' if b'\r\n' in fixed else '\n'
    insertion = HOOK.replace('\n', newline)
    lines.insert(line_index, insertion)
    patched = ''.join(lines).encode('utf-8')
    compile(patched, str(SOURCE), 'exec')
    if patched.count(b'from stage4_recovery_a106_sqlite_runtime import provision') != 1:
        raise ValueError('Unexpected SQLite hook count')
    return patched, stages


def run(apply: bool):
    original = SOURCE.read_bytes()
    patched, stages = patch_source(original)
    if not apply:
        print('A106 SQLITE PATCH CHECK OK: four set_failure calls + one SQLite hook')
        return
    env = os.environ
    if (env.get('GITHUB_ACTIONS') != 'true' or env.get('STAGE4_RECOVERY_SQLITE_RUNNER_ONLY') != 'true'
            or env.get('STAGE4_EXECUTION_ID') != 'A-106'
            or env.get('STAGE4_REPO') != 'aagjalpankaj/larabase'
            or env.get('STAGE4_SHA') != SHA
            or env.get('STAGE4_OS') not in {'linux','windows','macos'}):
        raise RuntimeError('Runner-only SQLite patch guard refused execution')
    commit_bytes = subprocess.check_output(['git','show','HEAD:scripts/14_cross_os_reproducibility_v2.py'])
    comparison = verify_checkout_source(original, commit_bytes)
    # Refuse to edit the user's working directory outside the ephemeral Action.
    provenance = {
        'experiment_id': 'stage4-a106-sqlite-file-provisioning-v1',
        'patch_applied': True,
        'runner_only': True,
        'execution_id': 'A-106',
        'os': env['STAGE4_OS'],
        'repo_full_name': env['STAGE4_REPO'],
        'frozen_sha': SHA,
        'checkout_verified': comparison,
        'original_v2_sha256': sha256(original).hexdigest(),
        'patched_v2_sha256': sha256(patched).hexdigest(),
        'previous_recorder_repair_calls': stages,
        'sqlite_hook_count': 1,
        'intervention': 'Ephemeral error recorder fix plus SQLite creation hook before test invocation',
    }
    META.parent.mkdir(parents=True, exist_ok=True)
    SOURCE.write_bytes(patched)
    META.write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print('A106 SQLITE RUNNER PATCH APPLIED', json.dumps(provenance, sort_keys=True))

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply-runner-only', action='store_true')
    args = ap.parse_args()
    run(apply=args.apply_runner_only)
