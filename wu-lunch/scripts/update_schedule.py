"""One checked policy for workflow gates and public/Admin timing displays."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

def policy():
    return json.loads((ROOT/'update-policy.json').read_text(encoding='utf-8'))

def allowed(task, now=None, event='schedule'):
    if event != 'schedule':
        return True
    config=policy()
    now=(now or datetime.now(ZoneInfo(config['timezone']))).astimezone(ZoneInfo(config['timezone']))
    rule=config['tasks'][task]
    if rule.get('ends_before') and now.date().isoformat()>=rule['ends_before']:
        return False
    # Match the actual execution window. A green skipped job is never a fetch.
    return now.hour in rule['hours'].get(str(now.isoweekday()%7),[])

def check_workflows():
    for rule in policy()['tasks'].values():
        if not rule.get('workflow'):
            continue
        text=(ROOT.parent/'.github/workflows'/rule['workflow']).read_text(encoding='utf-8')
        actual=re.findall(r"- cron:\s*['\"]([^'\"]+)['\"]",text)
        if actual != rule['cron']:
            raise ValueError('Cron/Anzeige weichen voneinander ab: '+rule['workflow'])
    menus=(ROOT.parent/'.github/workflows/wu-lunch-menus.yml').read_text(encoding='utf-8')
    snapshot=(ROOT.parent/'.github/workflows/wu-lunch-mensa-pdf.yml').read_text(encoding='utf-8')
    if 'update_schedule.py menus' not in menus or 'update_schedule.py topf_browser' not in menus or 'update_schedule.py mensa_snapshot' not in snapshot:
        raise ValueError('Workflow muss die gemeinsame Zeitprüfung verwenden')

if __name__=='__main__':
    if sys.argv[1:] == ['--check']:
        check_workflows()
    else:
        raise SystemExit(0 if allowed(sys.argv[1],event=sys.argv[2] if len(sys.argv)>2 else 'schedule') else 1)
