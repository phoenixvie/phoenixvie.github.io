#!/usr/bin/env python3
"""iOS-App-Symbol und Store-Symbol im selben Ausschnitt wie das Android-Symbol erzeugen.

Vorgabe des Betreibers (17./18.11.2026): Das Besteck ist herangezoomt und unten knapp
abgeschnitten – so wie Android es auf dem Startbildschirm zeigt. Android zeigt vom
adaptiven Symbol nur das mittlere Quadrat (72 von 108 Einheiten); genau dieses Quadrat
wird hier in voller Schärfe erzeugt:
- assets/icon-ios.png   1024 x 1024, ohne Transparenz (Apple-Vorgabe; iOS rundet die Ecken selbst)
- store-listing/app-icon-512.png  512 x 512 für Google Play

Aufruf (nur nötig, wenn sich assets/icon.png ändert):
    python3 scripts/make-ios-icon.py
"""
import importlib.util
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adaptive", ROOT / "scripts/make-adaptive-icon.py")
adaptive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adaptive)


def visible_square(size=1024):
    canvas = round(size * 108 / 72)          # Vorlage so groß, dass ihr sichtbares Quadrat genau `size` misst
    image, _ = adaptive.build(canvas=canvas)
    offset = (canvas - size) // 2
    return image.crop((offset, offset, offset + size, offset + size))


if __name__ == "__main__":
    icon = visible_square(1024).convert("RGB")
    icon.save(ROOT / "assets/icon-ios.png", optimize=True)
    icon.resize((512, 512), Image.LANCZOS).save(ROOT / "store-listing/app-icon-512.png", optimize=True)
    print("assets/icon-ios.png: 1024 x 1024 · store-listing/app-icon-512.png: 512 x 512")
