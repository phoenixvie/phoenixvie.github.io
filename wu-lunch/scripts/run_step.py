"""Record real command attempts, source fetches and semantic menu changes."""
import json
import os
import subprocess
import sys
from pathlib import Path
import source_archive as archive

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data/update-status.json'

def save(data):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def start():
    previous=archive.read_json(PATH,{})
    archive.STAGING.mkdir(parents=True,exist_ok=True)
    (archive.STAGING/'requests.jsonl').write_text('',encoding='utf-8')
    save({'version':1,'previous_completed':previous.get('last_completed'),
          'menus_updated_at':previous.get('menus_updated_at'),
          'menu_sha256':previous.get('menu_sha256') or menu_digest(),
          'run':{'id':os.environ.get('GITHUB_RUN_ID'),'event':os.environ.get('GITHUB_EVENT_NAME'),
                 'started_at':archive.stamp(),'steps':[]}})

def run(name, command):
    record=archive.read_json(PATH,{})
    if not record.get('run'):
        start();record=archive.read_json(PATH,{})
    began=archive.stamp()
    env={**os.environ,'WU_SOURCE_STAGE':name,'WU_SOURCE_CAPTURE':'1'}
    try:
        result=subprocess.run(command,env=env,check=False).returncode
    except OSError:
        result=127
    record['run']['steps'].append({'name':name,'started_at':began,'completed_at':archive.stamp(),'exit_code':result})
    save(record)
    return result

def menu_digest():
    import hashlib
    menu=archive.read_json(ROOT/'data/menus.json',{})
    content=[{'id':r['id'],'menu':archive.semantic_menu(r)} for r in menu.get('restaurants',[])]
    return hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def finish():
    record=archive.read_json(PATH,{})
    menu=archive.read_json(ROOT/'data/menus.json',{})
    digest=menu_digest()
    now=archive.stamp()
    if digest!=record.get('menu_sha256'):
        record['menus_updated_at']=now
    record['menu_sha256']=digest
    logs=archive.requests()
    record['source_checks']={ident:{'last_attempt':max(row['at'] for row in logs if row['restaurant_id']==ident),
        'last_fetched':max((row['at'] for row in logs if row['restaurant_id']==ident and row.get('blob')),default=None),
        'successful_fetches':sum(row['restaurant_id']==ident and bool(row.get('blob')) for row in logs)}
        for ident in sorted({row['restaurant_id'] for row in logs})}
    record['last_source_fetch']=max((row['at'] for row in logs if row.get('blob')),default=None)
    record['last_completed']=now
    record['run']['completed_at']=now
    record['week_start']=menu.get('weekStart')
    record['archive_entries']=len(archive.read_json(ROOT/'source-archive/index.json',{}).get('entries',[]))
    save(record)

if __name__=='__main__':
    if sys.argv[1]=='start': start()
    elif sys.argv[1]=='finish': finish()
    else: raise SystemExit(run(sys.argv[1],sys.argv[2:]))
