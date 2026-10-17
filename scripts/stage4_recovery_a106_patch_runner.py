#!/usr/bin/env python3
"""Fail-closed, AST-checked repair for a missing failure-detail argument.

Only --apply changes the *ephemeral* GitHub Actions checkout. The user's
committed v2 protocol and all baseline artifacts are never modified.
"""
import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

SOURCE = Path('scripts/14_cross_os_reproducibility_v2.py')
META = Path('stage4_recovery/a106_v2_patch_provenance.json')
EXPECTED = Counter({'CLONE': 1, 'CHECKOUT': 2, 'COMPOSER_VALIDATE': 1})


def at(data, line, col):
    lines = data.splitlines(keepends=True)
    return sum(len(s) for s in lines[:line-1]) + col


def recover_source(original):
    """Return (patched source bytes, stage counters); fail on any source drift."""
    source = original.decode('utf-8')
    tree = ast.parse(source)
    signatures = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'set_failure']
    if len(signatures) != 1 or [arg.arg for arg in signatures[0].args.args[:3]] != ['category', 'stage', 'detail']:
        raise ValueError('Unexpected set_failure signature; source changed')
    definitions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'classify_failure']
    if len(definitions) != 1:
        raise ValueError('Missing/ambiguous classify_failure')
    edits = []
    stages = Counter()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != 'set_failure':
            continue
        if not call.args or not isinstance(call.args[0], ast.Starred):
            continue
        inner = call.args[0].value
        if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                and inner.func.id == 'classify_failure' and len(inner.args) == 2
                and isinstance(inner.args[0], ast.Name) and inner.args[0].id == 'out'
                and isinstance(inner.args[1], ast.Constant) and isinstance(inner.args[1].value, str)):
            raise ValueError('Unexpected starred set_failure call; refusal to patch')
        stage = inner.args[1].value
        if stage not in EXPECTED:
            raise ValueError(f'Unexpected classify_failure stage: {stage}')
        stages[stage] += 1
        if len(call.args) != 1:
            raise ValueError('Unexpected other positional arguments')
        insert = ', out'
        if stage == 'COMPOSER_VALIDATE':
            if call.keywords:
                raise ValueError('Unexpected COMPOSER_VALIDATE keyword arguments')
            insert += ', command="composer validate --no-check-publish", exit_code=rc'
        insertion_position = at(original, call.args[0].end_lineno, call.args[0].end_col_offset)
        edits.append((insertion_position, insert.encode('utf-8')))
    if stages != EXPECTED:
        raise ValueError(f'Expected {dict(EXPECTED)} call sites, got {dict(stages)}')
    patched = original
    for offset, insertion in sorted(edits, reverse=True):
        patched = patched[:offset] + insertion + patched[offset:]
    compile(patched, str(SOURCE), 'exec')
    # Ensure no risky semantic changes: all edits are insertions at audited call sites.
    return patched, dict(stages)


def run(mode):
    if not SOURCE.is_file():
        raise FileNotFoundError(f'Source not found: {SOURCE}')
    original = SOURCE.read_bytes()
    patched, stages = recover_source(original)
    before = sha256(original).hexdigest()
    after = sha256(patched).hexdigest()
    if mode == 'check':
        print(f'PATCH CHECK OK: {sum(stages.values())} call sites; source_sha256={before} patched_sha256={after}')
        return {'original_sha256': before, 'patched_sha256': after, 'repaired_call_sites': stages}
    if (os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('STAGE4_RECOVERY_PATCH_RUNNER_ONLY') != 'true'
            or os.getenv('STAGE4_EXECUTION_ID') != 'A-106'
            or os.getenv('STAGE4_OS') not in ('linux', 'windows', 'macos')):
        raise RuntimeError('Runner-only patch guard failed; no Mac/local in-place changes permitted')
    # Refuse any source modified relative to the checked-out commit.
    git_source = subprocess.check_output(['git', 'show', 'HEAD:scripts/14_cross_os_reproducibility_v2.py'])
    if original != git_source:
        raise RuntimeError('Checked-out source differs from HEAD; refusing patch')
    metadata = {
        'experiment_id': 'stage4-a106-v2-set-failure-recovery-v1',
        'applied_in_ephemeral_runner': True,
        'original_sha256': before,
        'patched_sha256': after,
        'repaired_call_sites': stages,
        'intervention': 'Supply original captured command output to set_failure; retain composer validate exit code',
        'execution_id': 'A-106',
        'os': os.environ['STAGE4_OS'],
        'source_path': str(SOURCE),
    }
    META.parent.mkdir(parents=True, exist_ok=True)
    SOURCE.write_bytes(patched)
    META.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('RUNNER-ONLY PATCH APPLIED:', json.dumps(metadata, sort_keys=True))
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply-runner-only', action='store_true')
    args = parser.parse_args()
    run('apply' if args.apply_runner_only else 'check')
