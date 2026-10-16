#!/usr/bin/env python3
"""Run unchanged v2 Stage 4 protocol; apply ephemeral DB env only for a verified DB."""
import json
import os
import subprocess
import sys
from pathlib import Path

DB=Path('stage4_v3_2_database/database_audit.json')


def build_env(audit, original):
    env=original.copy()
    # Remove database connection secrets intended only for preflight.
    for name in ('STAGE4_MYSQL57_HOST','STAGE4_MYSQL57_USER','STAGE4_MYSQL57_PASSWORD',
                 'STAGE4_MYSQL57_TLS_CA_B64','STAGE4_MYSQL57_PORT'):
        env.pop(name,None)
    if audit.get('status')=='DATABASE_READY':
        if original.get('STAGE4_DB_MODE')!='remote_tls':
            raise RuntimeError('DB preflight mode mismatch')
        name=audit.get('database_name','')
        if not name.startswith('s4_'):
            raise RuntimeError('Invalid isolated schema name')
        # The test application receives *only* a restricted disposable DB account.
        for target,source in [('DB_HOST','STAGE4_MYSQL57_HOST'),
                             ('DB_USERNAME','STAGE4_MYSQL57_USER'),
                             ('DB_PASSWORD','STAGE4_MYSQL57_PASSWORD'),
                             ('DB_PORT','STAGE4_MYSQL57_PORT')]:
            value=original.get(source,'')
            if source=='STAGE4_MYSQL57_PORT' and not value:value='3306'
            if not value: raise RuntimeError('Missing DB environment field')
            env[target]=value
        env['DB_DATABASE']=name
        # Preserve project's DB_CONNECTION alias (A-012 uses 'testing').
    return env


def main():
    audit=json.loads(DB.read_text(encoding='utf-8'))
    if audit.get('run_protocol')!='true':
        print('Protocol blocked by DB audit:',audit.get('status'))
        return 2
    env=build_env(audit,dict(os.environ))
    result=subprocess.run([sys.executable,'scripts/14_cross_os_reproducibility_v2.py'],env=env)
    return result.returncode

if __name__=='__main__':sys.exit(main())
