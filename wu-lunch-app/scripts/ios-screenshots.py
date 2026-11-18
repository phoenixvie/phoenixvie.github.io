#!/usr/bin/env python3
"""iOS-App im Simulator starten und App-Store-Screenshots aufnehmen (läuft auf dem macOS-Runner).

Nimmt das größte verfügbare iPhone ("Pro Max", 6,9 Zoll, 1320 x 2868 Pixel) und öffnet jede
Ansicht über das Startargument -wuStartScreen (siehe App.tsx), auf Deutsch und auf Englisch.
Ergebnis: ios-screenshots/<sprache>-<nr>-<ansicht>.png
"""
import glob
import json
import subprocess
import sys
import time
from pathlib import Path

BUNDLE = 'at.startit.wufood'
OUT = Path('ios-screenshots'); OUT.mkdir(exist_ok=True)
SCREENS = [('1-liste', None, 14), ('2-menue', 'restaurant:mensa', 12), ('3-info', 'info:mensa', 14), ('4-karte', 'map', 22), ('5-meet', 'meet', 14)]
LANGS = {'de': ('(de)', 'de_AT'), 'en': ('(en)', 'en_GB')}


def run(*args, check=True):
    print('$', ' '.join(args), flush=True)
    return subprocess.run(args, check=check, text=True, capture_output=True).stdout


devices = json.loads(run('xcrun', 'simctl', 'list', 'devices', 'available', '-j'))['devices']
candidates = [(runtime, d) for runtime, items in devices.items() if 'iOS' in runtime for d in items if 'Pro Max' in d['name']]
if not candidates:
    sys.exit('Kein iPhone "Pro Max" im Simulator verfügbar')
runtime, device = sorted(candidates, key=lambda item: (item[0], item[1]['name']))[-1]
udid = device['udid']
print('Simulator:', device['name'], runtime, flush=True)
run('xcrun', 'simctl', 'boot', udid, check=False)
run('xcrun', 'simctl', 'bootstatus', udid, '-b')
run('xcrun', 'simctl', 'status_bar', udid, 'override', '--time', '9:41', '--dataNetwork', 'wifi', '--wifiMode', 'active',
    '--wifiBars', '3', '--cellularMode', 'active', '--cellularBars', '4', '--batteryState', 'charged', '--batteryLevel', '100')
app = glob.glob('build/Build/Products/Release-iphonesimulator/*.app')[0]
run('xcrun', 'simctl', 'install', udid, app)
for lang, (languages, locale) in LANGS.items():
    for name, start, wait in SCREENS:
        run('xcrun', 'simctl', 'terminate', udid, BUNDLE, check=False)
        args = ['xcrun', 'simctl', 'launch', udid, BUNDLE, '-AppleLanguages', languages, '-AppleLocale', locale]
        if start:
            args += ['-wuStartScreen', start]
        run(*args)
        time.sleep(wait)
        target = OUT / f'{lang}-{name}.png'
        run('xcrun', 'simctl', 'io', udid, 'screenshot', '--type=png', str(target))
        size = run('sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(target))
        print(target, ' '.join(size.split()[-4:]), target.stat().st_size // 1024, 'KB', flush=True)
        assert target.stat().st_size > 60_000, f'{target} sieht leer aus'
run('xcrun', 'simctl', 'shutdown', udid, check=False)
