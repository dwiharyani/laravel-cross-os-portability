#!/usr/bin/env python3
"""Exact-SHA, fail-closed PHP/version and Composer-test preflight.
This is deliberately strict: unknown Composer PHP syntax is UNRESOLVED, not guessed.
"""
import json, os, re, subprocess, sys
from pathlib import Path

# Shared candidates for all 3 OS. Change only after verifying setup-php availability.
CANDIDATES=['7.4','8.0','8.1','8.2','8.3','8.4','8.5']
PRE=Path('stage4_v3_preflight')

def version(s):
    nums=re.findall(r'^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?',s.strip(),re.I)
    if not nums: raise ValueError('Unknown version token: '+s)
    return tuple(int(x or 0) for x in nums[0])

def cmp_constraint(candidate,expression):
    expr=expression.strip()
    if not expr or expr=='*':return True
    expr=re.sub(r'\s+as\s+[^\s]+','',expr,flags=re.I)
    expr=re.sub(r'@[a-z]+\b','',expr,flags=re.I).strip()
    # Each OR branch is a conjunction of predicates.
    def branch(b):
        b=re.sub(r'(?<!\S)(\d+(?:\.\d+){0,2})\s+-\s+(\d+(?:\.\d+){0,2})(?!\S)',r'>=\1 <=\2',b)
        b=b.replace(',', ' ').replace('&&',' ')
        parts=re.findall(r'(?:\^|~|!=|>=|<=|==|=|>|<)?\s*(?:v?\d+(?:\.(?:\d+|[xX*])){0,3}|\*)',b)
        if not parts or ''.join(parts).replace(' ','')!=re.sub(r'\s+','',b):
            raise ValueError('Unsupported Composer PHP constraint: '+repr(b))
        return all(predicate(candidate,z.strip()) for z in parts)
    return any(branch(b.strip()) for b in re.split(r'\s*\|\|?\s*',expr))

def predicate(candidate, raw):
    m=re.match(r'^(\^|~|!=|>=|<=|==|=|>|<)?\s*(.*)$',raw)
    op,token=m.group(1) or '=',m.group(2)
    if token=='*':return True
    if '*' in token or 'x' in token.lower():
        digits=re.split(r'[.xX*]',token)
        prefix=[int(v) for v in digits if v.isdigit()]
        if not prefix:return True
        lower=tuple((prefix+[0]*(3-len(prefix)))[:3]); pos=len(prefix)-1
        upper=list(lower);upper[pos]+=1
        for j in range(pos+1,3):upper[j]=0
        return lower<=candidate<tuple(upper)
    v=version(token)
    if op in ('^','~'):
        if op=='^':
            idx=next((i for i,a in enumerate(v) if a!=0),2)
        else:
            idx=0 if token.count('.')<=1 else 1
        upper=list(v);upper[idx]+=1
        for j in range(idx+1,3):upper[j]=0
        return v<=candidate<tuple(upper)
    ops={'=':lambda a,b:a==b,'==':lambda a,b:a==b,'!=':lambda a,b:a!=b,
         '>':lambda a,b:a>b,'<':lambda a,b:a<b,'>=':lambda a,b:a>=b,'<=':lambda a,b:a<=b}
    return ops[op](candidate,v)

def dump(d):
    PRE.mkdir(exist_ok=True)
    (PRE/'preflight.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
            for k in ['php','command','resolution_status']:
                f.write(k+'='+str(d.get(k,''))+'\n')
    print(json.dumps(d,indent=2))

def main():
    repo=os.environ['STAGE4_REPO'];sha=os.environ['STAGE4_SHA']
    dst=PRE/'repo'
    detail={'repo_full_name':repo,'latest_sha':sha,'php':'','command':'',
        'resolution_status':'UNRESOLVED','php_candidate_evidence':{},'test_selection_reason':'',
        'php_constraint_sources':[],'errors':[], 'candidate_patch_model':'MINOR_LATEST_PATCH_APPROXIMATION'}
    try:
        PRE.mkdir(exist_ok=True)
        subprocess.run(['git','init',str(dst)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['git','-C',str(dst),'remote','add','origin','https://github.com/'+repo+'.git'],check=True)
        subprocess.run(['git','-C',str(dst),'fetch','--depth','1','origin',sha],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
        subprocess.run(['git','-C',str(dst),'checkout','--detach','FETCH_HEAD'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        got=subprocess.check_output(['git','-C',str(dst),'rev-parse','HEAD'],text=True).strip()
        if got!=sha:raise ValueError('Commit mismatch '+got+' vs '+sha)
        data=json.loads((dst/'composer.json').read_text(encoding='utf-8'))
        lockfile=dst/'composer.lock'
        if not lockfile.exists():raise ValueError('NO_COMPOSER_LOCK; strict reproduction requires composer.lock')
        lock=json.loads(lockfile.read_text(encoding='utf-8'))
        rules=[]
        def capture(source,expr,conflict=False):
            if expr and isinstance(expr,str) and expr!='*':rules.append((source,expr,conflict))
        capture('composer.json:require.php',data.get('require',{}).get('php'))
        capture('composer.json:require-dev.php',data.get('require-dev',{}).get('php'))
        for pkg in lock.get('packages',[])+lock.get('packages-dev',[]):
            name=pkg.get('name','?')
            capture(name+':require.php',pkg.get('require',{}).get('php'))
            capture(name+':conflict.php',pkg.get('conflict',{}).get('php'),True)
        for part in ['platform','platform-dev']:
            capture('composer.lock:'+part+'.php',lock.get(part,{}).get('php'))
        override=data.get('config',{}).get('platform',{}).get('php')
        if override:detail['platform_php_override']=override
        detail['php_constraint_sources']=[{'source':s,'constraint':expr,'negated':neg} for s,expr,neg in rules]
        for c in CANDIDATES:
            # Minor-version matrix selects the latest patch at setup time. A high
            # sentinel admits lower-bound patch constraints; actual Composer
            # validation remains authoritative after setup.
            v=version(c)[:2]+(9999,)
            reasons=[]
            for src,expr,negative in rules:
                ok=cmp_constraint(v,expr)
                if (ok and negative) or (not ok and not negative):reasons.append(src+' '+expr)
            detail['php_candidate_evidence'][c]=reasons
        compatible=[c for c,why in detail['php_candidate_evidence'].items() if not why]
        if not compatible:raise ValueError('NO_COMPATIBLE_PHP among shared candidates')
        detail['php']=compatible[0]
        # Never execute assignment's human-readable "test: [...]" representation as shell.
        if 'test' in data.get('scripts',{}):
            detail['command']='composer run-script test'
            detail['test_selection_reason']='COMPOSER_SCRIPT_TEST'
        elif (dst/'artisan').exists() and ((dst/'tests').is_dir() or (dst/'phpunit.xml').exists() or (dst/'phpunit.xml.dist').exists()):
            detail['command']='php artisan test'
            detail['test_selection_reason']='ARTISAN_TEST_FALLBACK'
        elif ((dst/'phpunit.xml').exists() or (dst/'phpunit.xml.dist').exists()) and (dst/'tests').is_dir():
            detail['command']='vendor/bin/phpunit'
            detail['test_selection_reason']='PHPUNIT_FALLBACK'
        else:
            detail['test_selection_reason']='NO_TEST_DISCOVERED'
        detail['required_extensions']=sorted({k[4:].lower() for obj in ([data.get('require',{}),data.get('require-dev',{})]+[p.get('require',{}) for p in lock.get('packages',[])+lock.get('packages-dev',[])]) for k in obj if k.startswith('ext-')})
        detail['resolution_status']='RESOLVED'
    except Exception as e:
        detail['errors']=[repr(e)]
    dump(detail)
    return 0 if detail['resolution_status']=='RESOLVED' else 2

if __name__=='__main__':sys.exit(main())
