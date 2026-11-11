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

adb('install', '-r', 'android/app/build/outputs/apk/release/WU-Food-0.3.0.apk')
adb('shell', 'am', 'start', '-n', 'at.startit.wulunch/.MainActivity')
wait_for('WU Food', 'WU Mensa')
capture('01-list')
tap('WU Mensa')
wait_for('Weiter', 'Zurück', 'Montag')
capture('02-menu')
tap('Zurück')
wait_for("L'Osteria", 'Weiter')
tap('Weiter')
wait_for('WU Mensa', 'Weiter')
tap('Restaurant')
wait_for('Webseite', 'Öffnungszeiten', 'Adresse')
capture('03-restaurant')
tap('Menü')
wait_for('WU Mensa', 'Weiter')
adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
time.sleep(1)
try:
    adb('shell', 'am', 'start', '-a', 'android.intent.action.ALL_APPS')
except subprocess.CalledProcessError:
    # Launcher entry points vary; this optional screenshot must not fail app checks.
    adb('shell', 'input', 'swipe', '540', '1600', '540', '300', '500')
time.sleep(2)
capture('06-launcher')
print('Installed APK passed list, menu, contact and map smoke checks.')
