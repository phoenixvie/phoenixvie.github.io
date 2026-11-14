"""Exact public source bytes, staged per run; immutable snapshots on menu changes.

No cookies, request headers or credentials are stored. Capturing is opt-in in
the production job; tests and ad-hoc parser imports have no filesystem effects.
"""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
STAGING=ROOT/'.source-capture'
ARCHIVE=ROOT/'source-archive'
HOSTS={'wumensa.at':'mensa','dascampus.at':'campus','dasglashaus.at':'glashaus',
       'shop.baschly.com':'baschly','baschly.com':'baschly','finn.wien':'finn',
       'lia.coffee':'lia','karmafood.at':'karmafood','topfdeckel.at':'topfdeckel',
       'zurgruenenhuette.com':'gruenehuette','xn--omakche-q2a.at':'omakueche','losteria.net':'losteria'}

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def owner(url):
    value=urlparse(url)
    if value.scheme!='https' or value.username or value.password:
        return None
    host=(value.hostname or '').removeprefix('www.')
    if host=='cdn.shopify.com':
        name=value.path.casefold().replace('-','').replace('_','')
        return 'finn' if 'finnkw' in name else 'karmafood' if 'karmafood' in name else None
    return HOSTS.get(host)

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return default

def record(row):
    STAGING.mkdir(parents=True,exist_ok=True)
    with (STAGING/'requests.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(row,ensure_ascii=False)+'\n')

def capture(url, raw, restaurant=None, *, kind=None, context=None):
    if os.environ.get('WU_SOURCE_CAPTURE')!='1':
        return
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password:
        return
    ident=restaurant or owner(url)
    if ident not in set(HOSTS.values()) or not raw or len(raw)>12_000_000:
        return
    if kind is None:
        kind='pdf' if raw.startswith(b'%PDF-') else 'jpg' if raw.startswith(b'\xff\xd8\xff') else 'png' if raw.startswith(b'\x89PNG') else 'webp' if raw[8:12]==b'WEBP' else 'html'
    if kind not in ('html','pdf','jpg','png','webp'):
        raise ValueError('Unsupported source format')
    digest=hashlib.sha256(raw).hexdigest()
    path=STAGING/'blobs'/(digest+'.'+kind)
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    record({'restaurant_id':ident,'url':url,'at':stamp(),'sha256':digest,'bytes':len(raw),
            'format':kind,'blob':path.name,'stage':os.environ.get('WU_SOURCE_STAGE','source'),
            'context':context})

def failure(url, error):
    if os.environ.get('WU_SOURCE_CAPTURE')=='1' and owner(url):
        record({'restaurant_id':owner(url),'url':url,'at':stamp(),
                'error':str(error)[:180],'stage':os.environ.get('WU_SOURCE_STAGE','source')})

def requests():
    path=STAGING/'requests.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

def semantic_menu(restaurant):
    # Acquisition times, browser hashes and provenance do not change a dish.
    transient={'source_sha256','source_url','source_day','ai_confidence','price_source','manual_presentation'}
    def clean(value):
        if isinstance(value,dict):
            return {key:clean(item) for key,item in value.items() if key not in transient}
        if isinstance(value,list):
            return [clean(item) for item in value]
        return value
    return clean({'days':restaurant.get('days',{}),'seasonal':restaurant.get('seasonal',[]),
                  'validFrom':restaurant.get('validFrom'),'validUntil':restaurant.get('validUntil')})

def supplemental_images(ident,evidence):
    """Copy linked menu images for curation; never call them model input."""
    if ident!='baschly' or os.environ.get('WU_SOURCE_CAPTURE')!='1':
        return []
    import requests as http
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    urls=set()
    for row in evidence:
        if row['format']!='html':continue
        raw=(STAGING/'blobs'/row['blob']).read_bytes()
        soup=BeautifulSoup(raw,'html.parser')
        for image in (soup.select('main img') or soup.select('img')):
            url=urljoin(row['url'],image.get('src') or image.get('data-src') or '')
            if urlparse(url).scheme=='https' and urlparse(url).hostname=='cdn.shopify.com' and any(word in (url+' '+image.get('alt','')).casefold() for word in ('lunch','mittag','menu','menü','woche')):
                urls.add(url)
    before=len(requests())
    for url in sorted(urls)[:4]:
        try:
            with http.get(url,timeout=(6,20),stream=True,allow_redirects=False) as response:
                response.raise_for_status()
                raw=bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw)>8_000_000:raise ValueError('Supplement too large')
                if not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG') or raw[8:12]==b'WEBP'):
                    raise ValueError('Supplement is not an image')
                capture(url,bytes(raw),ident,context='supplemental_image_not_model_input')
        except Exception as error:
            record({'restaurant_id':ident,'url':url,'at':stamp(),'error':str(error)[:180],
                    'stage':'source_archive','context':'supplemental_image_not_model_input'})
    return requests()[before:]

def finalize(data=None,status=None):
    data=data or read_json(ROOT/'data/menus.json',{})
    status=status or read_json(ROOT/'status.json',{})
    logs=requests()
    index=read_json(ARCHIVE/'index.json',{'version':1,'entries':[]})
    existing={(row['restaurant_id'],row['week_start'],row['menu_sha256']) for row in index['entries']}
    added=[]
    for restaurant in data.get('restaurants',[]):
        ident=restaurant['id']
        if ident not in set(HOSTS.values()):
            continue
        menu=semantic_menu(restaurant)
        if not any(menu['days'].values()) and not menu['seasonal']:
            continue
        digest=hashlib.sha256(json.dumps(menu,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        week=data['weekStart']
        datetime.strptime(week,'%Y-%m-%d')
        if (ident,week,digest) in existing:
            continue
        evidence=[row for row in logs if row['restaurant_id']==ident and row.get('blob') and (row['stage']!='observe' or restaurant.get('status')=='recurring')]
        if not evidence:
            continue # Never attach a later observation to an older cached menu.
        evidence.extend(row for row in supplemental_images(ident,evidence) if row.get('blob'))
        for row in evidence:
            source=STAGING/'blobs'/row['blob']
            raw=source.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']:
                raise ValueError('Archive source hash mismatch')
            target=ARCHIVE/'blobs'/row['blob']
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():
                shutil.copyfile(source,target)
        folder=ARCHIVE/week/ident/digest
        folder.mkdir(parents=True,exist_ok=True)
        audit=(status.get('mensa_luna_audit') if ident=='mensa' else status.get('topf_luna_audit') if ident=='topfdeckel' else status.get('ai_repair',{}).get(ident))
        manifest={'version':1,'restaurant_id':ident,'week_start':week,'menu_sha256':digest,
                  'captured_at':stamp(),'run_id':os.environ.get('GITHUB_RUN_ID'),
                  'code_commit':os.environ.get('GITHUB_SHA'),'menu_status':restaurant.get('status'),
                  'publication_time_confirmed':False,'training_review_required':True,
                  'source_state':status.get('sources',{}).get(ident),'ai_audit':audit,
                  'sources':[{**row,'used_for_extraction':row['stage']!='observe' and row.get('context')!='supplemental_image_not_model_input'} for row in evidence],'menu':menu}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        entry={key:manifest[key] for key in ('restaurant_id','week_start','menu_sha256','captured_at','menu_status')}
        entry['manifest']=str((folder/'manifest.json').relative_to(ARCHIVE)).replace('\\','/')
        entry['source_count']=len(evidence)
        index['entries'].append(entry)
        added.append(entry)
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    (ARCHIVE/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return added

if __name__=='__main__':
    print(json.dumps({'archived':finalize()},ensure_ascii=False))
