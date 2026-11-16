"""One checked policy for workflow gates and public/Admin timing displays.

GitHub fires scheduled workflows of this repository only a few times per day
and often hours late. The gates therefore answer "is it useful to work NOW?"
instead of "did GitHub hit the planned minute?":

- menus: every scheduled start during the day counts (a late run is better than
  none); skipped only at night or right after another completed import.
- topf_browser: runs whenever the full weekly menu is not verified yet,
  otherwise only as an occasional refresh.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

def policy():
    return json.loads((ROOT/'update-policy.json').read_text(encoding='utf-8'))

def _json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

def _moment(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def recently_imported(now, minutes, record=None):
    """True if another import finished moments ago (e.g. started by the watch run)."""
    record=_json(ROOT/'data/update-status.json') if record is None else record
    done=_moment(record.get('last_completed'))
    return bool(done and done.tzinfo and timedelta(0) <= now-done < timedelta(minutes=minutes))

def allowed(task, now=None, event='schedule', record=None):
    if event != 'schedule':
        return True
    config=policy()
    now=(now or datetime.now(ZoneInfo(config['timezone']))).astimezone(ZoneInfo(config['timezone']))
    rule=config['tasks'][task]
    if rule.get('ends_before') and now.date().isoformat()>=rule['ends_before']:
        return False
    # Match the actual execution window. A green skipped job is never a fetch.
    if now.hour not in rule['hours'].get(str(now.isoweekday()%7),[]):
        return False
    return not (rule.get('min_gap_minutes') and recently_imported(now,rule['min_gap_minutes'],record))

def topf_browser_due(now=None, event='schedule', data=None, status=None):
    """Decide by need, not by clock: is the full Topf & Deckel week still missing?

    The browser reading is the only way to get all five weekday tabs. Tying it
    to two fixed hours meant a late GitHub start skipped it for the whole day.
    """
    if event == 'push':
        return True  # code change: run once as integration test
    config=policy()
    rule=config['tasks']['topf_browser']
    zone=ZoneInfo(config['timezone'])
    now=(now or datetime.now(zone)).astimezone(zone)
    data=_json(ROOT/'data/menus.json') if data is None else data
    status=_json(ROOT/'status.json') if status is None else status
    attempt=_moment((status.get('topf_browser_attempt') or {}).get('at'))
    if attempt and attempt.tzinfo and timedelta(0) <= now-attempt < timedelta(minutes=rule['retry_minutes']):
        return False  # a failed reading is retried soon, but not every few minutes
    today=now.date()
    monday=today+timedelta(days=7-today.weekday()) if today.weekday()>=5 else today-timedelta(days=today.weekday())
    restaurant=next((r for r in data.get('restaurants',[]) if r.get('id')=='topfdeckel'),{})
    verified=_moment(restaurant.get('browser_verified_at'))
    week_ok=(data.get('weekStart')==monday.isoformat() and restaurant.get('validFrom')==monday.isoformat()
             and verified is not None and verified.date()>=monday
             and all(restaurant.get('days',{}).get((monday+timedelta(days=i)).isoformat()) for i in range(5)))
    if not week_ok:
        return True
    if now.hour not in rule['hours'].get(str(now.isoweekday()%7),[]):
        return False
    return now-verified >= timedelta(hours=rule['refresh_hours'])

def check_workflows():
    config=policy()
    rules=[*config['tasks'].values(),config['watch']]
    for rule in rules:
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
    takt=(ROOT.parent/'.github/workflows'/config['watch']['workflow']).read_text(encoding='utf-8')
    if 'takt.py run' not in takt or 'takt.py ensure' not in menus:
        raise ValueError('Wachlauf ist nicht mit den Workflows verbunden')

if __name__=='__main__':
    if sys.argv[1:] == ['--check']:
        check_workflows()
    else:
        event=sys.argv[2] if len(sys.argv)>2 else 'schedule'
        ok=topf_browser_due(event=event) if sys.argv[1]=='topf_browser' else allowed(sys.argv[1],event=event)
        raise SystemExit(0 if ok else 1)
