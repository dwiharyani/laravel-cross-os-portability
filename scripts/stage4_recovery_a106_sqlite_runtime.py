#!/usr/bin/env python3
"""Only A-106: create the frozen project's expected local SQLite file before tests.

Called by a two-line runner-only hook inside the unchanged v2 test protocol.
This module NEVER changes application source/config or runs migrations.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

EXPERIMENT = 'stage4-a106-sqlite-file-provisioning-v1'
REPO = 'aagjalpankaj/larabase'
SHA = '3c3ac5c009f5d87f5e5208be1f213e9aa08e2c2d'
OSS = {'linux', 'windows', 'macos'}
META = Path('stage4_recovery/a106_sqlite_provision.json')


def active_dotenv(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'Expected a non-symlink testing env file: {path}')
    out = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, val = line.split('=', 1)
            key = key.strip()
            if key in ('DB_CONNECTION', 'DB_DATABASE', 'DB_URL'):
                if key in out:
                    raise ValueError('Duplicate database setting in .env.testing: '+key)
                out[key] = val.strip().strip('\'"')
    return out


def xml_db_values(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError('Expected non-symlink phpunit.xml in frozen repository')
    tree = ET.parse(path)
    entries = {}
    for node in tree.iter():
        if node.tag.split('}')[-1] not in ('env', 'server'):
            continue
        name = node.attrib.get('name', '')
        if name in ('DB_CONNECTION', 'DB_DATABASE', 'DB_URL'):
            if name in entries:
                raise ValueError(f'Duplicate phpunit.xml environment definition: {name}')
            entries[name] = node.attrib.get('value', '')
    return entries


def provision(target: Path, env=None, write_metadata=True):
    env = dict(os.environ if env is None else env)
    if not (env.get('GITHUB_ACTIONS') == 'true'
            and env.get('STAGE4_RECOVERY_SQLITE_ONLY') == 'true'
            and env.get('STAGE4_EXECUTION_ID') == 'A-106'
            and env.get('STAGE4_OS') in OSS
            and env.get('STAGE4_REPO') == REPO
            and env.get('STAGE4_SHA') == SHA):
        raise RuntimeError('A-106 SQLite recovery: runner, repository, SHA or OS guard failed')
    target = Path(target)
    if not target.is_dir() or target.is_symlink():
        raise ValueError('Expected a real checked-out target directory')
    actual_sha = subprocess.check_output(
        ['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True
    ).strip()
    if actual_sha != SHA:
        raise RuntimeError(f'Frozen target SHA mismatch: {actual_sha} != {SHA}')
    dot = active_dotenv(target/'.env.testing')
    xml = xml_db_values(target/'phpunit.xml')
    if dot.get('DB_CONNECTION') != 'sqlite':
        raise RuntimeError('Frozen .env.testing does not select SQLite')
    if any(dot.get(k) for k in ('DB_DATABASE','DB_URL')):
        raise RuntimeError('Frozen .env.testing already declares a DB path/URL')
    if any(xml.get(k) for k in ('DB_DATABASE','DB_URL')):
        raise RuntimeError('phpunit.xml overrides SQLite DB path/URL')
    if xml.get('DB_CONNECTION') not in (None, '', 'sqlite'):
        raise RuntimeError('phpunit.xml overrides SQLite connection')
    if env.get('DB_CONNECTION') not in (None, '', 'sqlite') or any(env.get(k) for k in ('DB_DATABASE','DB_URL')):
        raise RuntimeError('Protocol environment overrides frozen SQLite configuration')
    config = target/'config/database.php'
    if not config.is_file() or config.is_symlink():
        raise RuntimeError('config/database.php absent or symlinked')
    config_text = config.read_text(encoding='utf-8')
    # Tight project-specific check of the documented SQLite default.
    if not re.search(r"env\s*\(\s*['\"]DB_DATABASE['\"]\s*,\s*database_path\s*\(\s*['\"]database\.sqlite['\"]\s*\)\s*\)", config_text):
        raise RuntimeError('Project SQLite DB default changed; refusing to provision')
    dbdir = target/'database'
    if dbdir.is_symlink():
        raise RuntimeError('Database directory symlink is not allowed')
    if not dbdir.is_dir():
        # Keep the recovery minimal. Original Laravel repository normally has database/.
        raise RuntimeError('Frozen checkout lacks database directory')
    sqlite_path = dbdir/'database.sqlite'
    if sqlite_path.is_symlink() or (sqlite_path.exists() and not sqlite_path.is_file()):
        raise RuntimeError('Database target is a symlink or is not a regular file')
    existed = sqlite_path.exists()
    if not existed:
        # Exclusive create: never overwrite a preexisting DB file or dataset.
        with sqlite_path.open('xb'):
            pass
    meta = {
        'experiment_id': EXPERIMENT,
        'os': env['STAGE4_OS'],
        'execution_id': 'A-106',
        'repo_full_name': REPO,
        'frozen_sha': SHA,
        'checkout_head_verified': actual_sha,
        'config_path': 'database/database.sqlite',
        'sqlite_file_present_before': existed,
        'sqlite_file_created': not existed,
        'sqlite_file_exists_after': sqlite_path.is_file(),
        'sqlite_file_size_after': sqlite_path.stat().st_size,
        'intervention': 'Exclusive creation of an empty local SQLite file; no migrations, source/config changes or DB overrides',
        'testing_env_sha256': hashlib.sha256((target/'.env.testing').read_bytes()).hexdigest(),
        'config_db_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
    }
    if write_metadata:
        META.parent.mkdir(parents=True, exist_ok=True)
        META.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print('A-106 SQLITE PROVISION:', json.dumps(meta, sort_keys=True))
    return meta
