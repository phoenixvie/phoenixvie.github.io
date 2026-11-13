import json
import re
import subprocess
import sys
import time
from pathlib import Path
import xml.etree.ElementTree as ET

proof = Path('android-proof')
proof.mkdir(exist_ok=True)
def adb(*args):
    return subprocess.check_output(['adb', *args], text=True)
def snapshot():
    adb('shell', 'uiautomator', 'dump', '/sdcard/window.xml')
    return adb('shell', 'cat', '/sdcard/window.xml')
def wait_for(*labels):
    last = ''
    for _ in range(35):
        last = snapshot()
        if all(label in last for label in labels):
            return last
        time.sleep(2)
    (proof / 'failure.xml').write_text(last)
    raise AssertionError('Missing screen labels: ' + str(labels))
def tap(label):
    for _ in range(6):
        xml = ET.fromstring(snapshot())
        nodes = [n for n in xml.iter('node') if n.get('clickable') == 'true' and (n.get('text') == label or n.get('content-desc') == label or n.get('text', '').startswith(label + ' '))]
        nodes.sort(key=lambda n: 0 if n.get('text') == label or n.get('content-desc') == label else 1)
        for node in nodes:
            x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
            if x2 > x1 and y2 > y1:
                adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
                return
        adb('shell', 'input', 'swipe', '540', '1450', '540', '500', '250')
    raise AssertionError('No visible button for ' + label)
def capture(name):
    (proof / (name+'.xml')).write_text(snapshot())
    with (proof / (name+'.png')).open('wb') as out:
        subprocess.run(['adb', 'exec-out', 'screencap', '-p'], stdout=out, check=True)
def failure(kind, value, traceback):
    try:
        capture('failure')
        (proof / 'logcat.txt').write_text(adb('logcat', '-d', '-t', '500'))
    finally:
        sys.__excepthook__(kind, value, traceback)
sys.excepthook = failure

version=json.loads(Path('app.json').read_text())['expo']['version']
adb('install', '-r', f'android/app/build/outputs/apk/release/WU-Food-{version}.apk')
adb('shell', 'am', 'start', '-n', 'at.startit.wulunch/.MainActivity')
wait_for('WU Food', 'WU Mensa')
capture('01-list')
tap('WU Mensa')
wait_for('WU Mensa')
english='Next' in snapshot()
words={'Weiter':'Next','Zur\u00fcck':'Back','Montag':'Monday','Zur\u00fcck zur Liste':'Back to list','Webseite':'Website','\u00d6ffnungszeiten':'Opening hours','Adresse':'Address','Men\u00fc':'Menu','Zur\u00fcck zum Men\u00fc':'Back to menu'}
label=lambda value:words.get(value,value) if english else value
wait_for(label('Weiter'),label('Zur\u00fcck'),label('Montag'))
capture('02-menu')
tap(label('Zur\u00fcck'))
wait_for(label('Weiter'))
tap(label('Weiter'))
wait_for('WU Mensa',label('Weiter'))
tap('Restaurant')
wait_for(label('Webseite'),label('\u00d6ffnungszeiten'),label('Adresse'))
capture('03-restaurant')
tap('www.wumensa.at')
wait_for(label('Zur\u00fcck zum Men\u00fc'))
capture('04-in-app-website')
tap(label('Zur\u00fcck zum Men\u00fc'))
wait_for(label('Webseite'),label('\u00d6ffnungszeiten'),label('Adresse'))
tap(label('Men\u00fc'))
wait_for('WU Mensa',label('Weiter'))
tap(label('Zur\u00fcck zur Liste'))
wait_for('WU Food')
tap('Change Language')
english=not english
list_label='List' if english else 'Liste'
wait_for(list_label)
adb('shell','am','force-stop','at.startit.wulunch')
adb('shell','am','start','-n','at.startit.wulunch/.MainActivity')
wait_for('WU Food',list_label)
capture('05-language-after-restart')
adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
time.sleep(1)
try:
    adb('shell', 'am', 'start', '-a', 'android.intent.action.ALL_APPS')
except subprocess.CalledProcessError:
    adb('shell', 'input', 'swipe', '540', '1600', '540', '300', '500')
time.sleep(2)
capture('06-launcher')
print('Installed APK passed list, menu, restaurant navigation and in-app website checks.')
