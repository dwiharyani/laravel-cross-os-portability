#!/usr/bin/env python3
"""Read-only project DB evidence, optional TLS-verified research MySQL preflight.
Do not execute checked-out application code, alter repo files, or provision DBs.
Never record credentials or host in artifacts.
"""
import base64
import hashlib
import json
import os
import re
import ssl
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

PRE = Path('stage4_v3_preflight')
OUT = Path('stage4_v3_2_database')
AUDIT = OUT / 'database_audit.json'


def save(audit):
    OUT.mkdir(exist_ok=True)
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            for key in ('status','run_protocol','database_name'):
                f.write(f'{key}={audit.get(key, "")}\n')
    print('DB audit:', audit['status'], 'expected:', audit.get('expected_engine'), audit.get('expected_version'))
    print('DB audit reason:', audit.get('reason', ''))


def envvars(path):
    if not path.is_file():
        return {}
    d = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line or line.lstrip().startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        if key.strip() in ('DB_CONNECTION','DB_HOST','DB_PORT','DB_DATABASE'):
            d[key.strip()] = val.strip().strip('\"\'')
    return d


def phpunit_env(path):
    if not path.is_file():
        return {}
    root = ET.parse(path).getroot()
    return {element.attrib.get('name'):element.attrib.get('value','')
            for element in root.iter() if element.tag in ('env','server') and element.attrib.get('name') in
            ('DB_CONNECTION','DB_HOST','DB_PORT','DB_DATABASE')}


def compose_engines(project):
    evidence = []
    for basename in ('compose.yml','compose.yaml','docker-compose.yml','docker-compose.yaml'):
        p = project / basename
        if not p.is_file():
            continue
        content = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        if not isinstance(content, dict) or not isinstance(content.get('services', {}), dict):
            raise ValueError(f'Invalid Compose services structure: {basename}')
        for service, config in content.get('services',{}).items():
            if not isinstance(config,dict):
                continue
            image = config.get('image','')
            if not isinstance(image,str):
                continue
            m = re.match(r'^(mysql|mariadb|postgres)(?::([^@\s]+))?(?:@.+)?$',image.strip(),re.I)
            if m:
                evidence.append({'file':basename,'service':service,'engine':m.group(1).lower(),
                                 'image_tag':m.group(2) or '', 'image_declared':True})
    return evidence


def driver_of_connection(phpfile, connection):
    """Conservative static inspection: never evaluate PHP; ambiguous => unknown."""
    if not phpfile.exists():
        return None
    s = phpfile.read_text(encoding='utf-8', errors='replace')
    match = re.search(r"['\"]"+re.escape(connection)+r"['\"]\s*=>\s*\[\s*['\"]driver['\"]\s*=>\s*['\"](mysql|pgsql|sqlite|sqlsrv)['\"]",s,re.S)
    return match.group(1) if match else None


def schema_for(execution_id, osname):
    if not re.fullmatch(r'[A-Za-z0-9-]{1,40}', execution_id) or osname not in ('linux','windows','macos'):
        raise ValueError('Unsafe execution_id or OS; cannot construct schema name')
    return 's4_' + execution_id.lower().replace('-','_') + '_' + osname


def detect(project, execution_id, osname):
    env = envvars(project/'.env.example')
    php = phpunit_env(project/'phpunit.xml')
    if not php:
        php = phpunit_env(project/'phpunit.xml.dist')
    conn = php.get('DB_CONNECTION') or env.get('DB_CONNECTION')
    evidence = compose_engines(project)
    driver = driver_of_connection(project/'config/database.php', conn) if conn else None
    if conn == 'sqlite' or driver == 'sqlite':
        return {'classification':'IN_PROCESS_SQLITE','expected_engine':'sqlite',
                'expected_version':None,'connection_name':conn,'testing_driver':driver,
                'compose_evidence':evidence,'db_name_hint':php.get('DB_DATABASE',''),
                'original_env_db_host_declared':bool(env.get('DB_HOST'))}
    # For named custom connections, PHP configuration, not its name, is decisive.
    engine = {'mysql':'mysql','pgsql':'postgres','sqlsrv':'sqlsrv'}.get(driver or conn)
    matching = [e for e in evidence if e['engine']==engine] if engine else []
    if not engine and len(evidence)==1:
        engine = evidence[0]['engine']; matching = evidence
    if not engine:
        return {'classification':'NO_EXPLICIT_EXTERNAL_DATABASE_EVIDENCE',
                'expected_engine':None,'expected_version':None,'connection_name':conn,
                'testing_driver':driver,'compose_evidence':evidence}
    if not matching:
        return {'classification':'EXTERNAL_DATABASE_VERSION_UNKNOWN',
                'expected_engine':engine,'expected_version':None,'connection_name':conn,
                'testing_driver':driver,'compose_evidence':evidence}
    tags = {e['image_tag'] for e in matching}
    if len(tags)!=1 or not next(iter(tags)) or next(iter(tags))=='latest' or '${' in next(iter(tags)):
        return {'classification':'EXTERNAL_DATABASE_VERSION_UNKNOWN',
                'expected_engine':engine,'expected_version':None,'connection_name':conn,
                'testing_driver':driver,'compose_evidence':evidence}
    tag=next(iter(tags))
    minor = re.match(r'^(\d+)\.(\d+)(?:\.\d+)?(?:-.+)?$',tag)
    if not minor:
        return {'classification':'EXTERNAL_DATABASE_VERSION_UNKNOWN',
                'expected_engine':engine,'expected_version':None,'connection_name':conn,
                'testing_driver':driver,'compose_evidence':evidence}
    return {'classification':'PINNED_EXTERNAL_DATABASE','expected_engine':engine,
            'expected_version':minor.group(1)+'.'+minor.group(2),
            'compose_image_tag':tag,'connection_name':conn,'testing_driver':driver,
            'compose_evidence':evidence}


def check_mysql_tls(audit):
    host=os.getenv('STAGE4_MYSQL57_HOST','').strip()
    user=os.getenv('STAGE4_MYSQL57_USER','').strip()
    password=os.getenv('STAGE4_MYSQL57_PASSWORD','')
    ca_b64=os.getenv('STAGE4_MYSQL57_TLS_CA_B64','')
    # Explicit repository/SHA allowlist: no accidental secret exposure to 57 unknown repositories.
    approved=os.getenv('STAGE4_APPROVED_DB_SHA','').strip()
    if not approved or approved != os.getenv('STAGE4_SHA','').strip():
        return 'DATABASE_ACCESS_NOT_APPROVED','Repository commit has not been explicitly reviewed/approved for DB credentials'
    if not all((host,user,password,ca_b64)):
        return 'DATABASE_ENVIRONMENT_UNAVAILABLE','MySQL 5.7 research-only endpoint/TLS credentials not configured'
    import pymysql
    ca_pem=base64.b64decode(ca_b64,validate=True).decode('utf-8')
    ctx=ssl.create_default_context(cadata=ca_pem)
    ctx.check_hostname=True
    ctx.verify_mode=ssl.CERT_REQUIRED
    database_name=audit['database_name']
    port=int(os.getenv('STAGE4_MYSQL57_PORT','3306'))
    if port<1 or port>65535:raise ValueError('Invalid MySQL port')
    audit['endpoint_fingerprint']=hashlib.sha256((host+':'+str(port)).encode()).hexdigest()[:12]
    audit['schema_reset_verified']=False  # Preprovisioned schema must be cleaned between reruns.
    with pymysql.connect(host=host,port=port,user=user,password=password,
                         database=database_name,ssl=ctx,connect_timeout=8,read_timeout=8,
                         write_timeout=8,autocommit=True) as con:
        with con.cursor() as c:
            c.execute('SELECT VERSION(), DATABASE(), 1')
            ver, db, flag=c.fetchone()
            audit['server_version_reported']=str(ver)
            if 'mariadb' in str(ver).lower() or not re.match(r'^5\.7\.',str(ver)):
                return 'DATABASE_VERSION_MISMATCH','Remote database does not run genuine MySQL 5.7'
            if db!=database_name or flag!=1:
                return 'DATABASE_PREPARATION_FAILURE','Database connectivity/schema verification failed'
            # This does not certify migrations, fixtures, or test PHP TLS settings.
            audit['connection_probe']='TLS_VERIFIED_SELECT_1'
    return 'DATABASE_READY','MySQL 5.7 TLS connectivity confirmed for isolated preprovisioned schema'


def audit_repository(project, execution_id, osname, mode):
    details=detect(project,execution_id,osname)
    audit={'execution_id':execution_id,'os':osname,'database_mode':mode,
           'database_name':'','status':'','run_protocol':'false',
           'reason':'','infrastructure_verified':False,
           'source_files_checked':['.env.example','phpunit.xml','phpunit.xml.dist','config/database.php',
                                   'compose.yml','compose.yaml','docker-compose.yml','docker-compose.yaml'],
           **details}
    classification=details['classification']
    if classification in ('IN_PROCESS_SQLITE','NO_EXPLICIT_EXTERNAL_DATABASE_EVIDENCE'):
        audit.update(status='DATABASE_NO_EXTERNAL_SERVICE_REQUIRED' if classification=='IN_PROCESS_SQLITE' else 'DATABASE_REQUIREMENTS_UNVERIFIED',
                     run_protocol='true',reason='SQLite in-process' if classification=='IN_PROCESS_SQLITE' else 'No explicit external DB; run with limitation flag')
    elif classification != 'PINNED_EXTERNAL_DATABASE':
        audit.update(status='DATABASE_REQUIREMENTS_UNRESOLVED', reason='DB type/version cannot be established from checked-in metadata')
    elif audit['expected_engine']!='mysql' or audit['expected_version']!='5.7':
        audit.update(status='DATABASE_INFRASTRUCTURE_UNSUPPORTED',reason='This version currently provisions only audited external MySQL 5.7; no silent engine/version replacement')
    elif mode=='audit_only':
        audit.update(status='DATABASE_ENVIRONMENT_UNAVAILABLE',reason='MySQL 5.7 detected but no external DB provisioned in audit_only mode')
    elif mode!='remote_tls':
        audit.update(status='DATABASE_INVALID_MODE',reason='Only audit_only or remote_tls allowed')
    else:
        audit['database_name']=schema_for(execution_id,osname)
        try:
            status,reason=check_mysql_tls(audit)
            audit.update(status=status,reason=reason,run_protocol='true' if status=='DATABASE_READY' else 'false',
                         infrastructure_verified=(status=='DATABASE_READY'))
        except Exception as e:
            # Never print or serialize raw exception strings: PyMySQL errors can contain host/user.
            audit.update(status='DATABASE_ENVIRONMENT_UNAVAILABLE',reason='TLS probe failed: '+type(e).__name__)
    return audit


def main():
    try:
        audit=audit_repository(PRE/'repo',os.environ['STAGE4_EXECUTION_ID'],os.environ['STAGE4_OS'],
                               os.getenv('STAGE4_DB_MODE','audit_only'))
    except Exception as e:
        audit={'status':'DATABASE_INSPECTION_FAILED','run_protocol':'false','database_name':'',
               'reason':'Inspection failed: '+type(e).__name__,
               'execution_id':os.getenv('STAGE4_EXECUTION_ID',''),'os':os.getenv('STAGE4_OS','')}
    save(audit)
    return 0

if __name__ == '__main__':
    sys.exit(main())
