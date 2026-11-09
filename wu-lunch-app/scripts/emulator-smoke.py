import re
import subprocess
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
    xml = ET.fromstring(snapshot())
    node = next(n for n in xml.iter('node') if n.get('text') == label or n.get('content-desc') == label)
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
    adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
def capture(name):
    (proof / (name+'.xml')).write_text(snapshot())
    with (proof / (name+'.png')).open('wb') as out:
        subprocess.run(['adb', 'exec-out', 'screencap', '-p'], stdout=out, check=True)

adb('install', '-r', 'android/app/build/outputs/apk/release/WU-Food-0.2.0.apk')
adb('shell', 'am', 'start', '-n', 'at.startit.wulunch/.MainActivity')
wait_for('WU Food', 'WU Mensa')
capture('01-list')
tap('WU Mensa')
wait_for('Weiter', 'Zurück', 'Montag')
capture('02-menu')
tap('Kontakt')
wait_for('ANRUFEN', 'MAIL', 'WEBSEITE', 'Öffnungszeiten')
capture('03-contact')
tap('Karte')
wait_for('In Google Maps öffnen')
capture('04-map')
print('Installed APK passed list, menu, contact and map smoke checks.')
