#!/usr/bin/env python3
"""Adaptives Android-Icon aus dem quadratischen Logo erzeugen.

Android schneidet App-Symbole je nach Gerät rund, als abgerundetes Quadrat oder
als "Squircle" zu und zeigt dabei nur die Mitte der Vorlage. Liegt das
quadratische Logo unverändert darunter, werden Gabel und Löffel angeschnitten;
verkleinert man es einfach, bleibt ein einfarbiger Rand um ein kleines Quadrat.

Dieses Skript baut deshalb eine eigene Vorlage (assets/adaptive-icon.png):
- Vorgabe des Betreibers (17.11.2026): näher heran – das Besteck ist groß, und sein
  unteres Ende wird vom unteren Rand des Symbols knapp abgeschnitten (es "wächst"
  aus dem Rand). Oben bleibt es vollständig sichtbar, auch bei runden Symbolen.
- Die drei blauen Streifen samt Verlauf werden bis an den Rand der Vorlage
  fortgesetzt, sodass bei keiner Maskenform ein Rand oder eine Kante sichtbar ist.

Maße: Sichtbar ist höchstens das mittlere Quadrat mit 72 von 108 Einheiten; sein
unterer Rand liegt bei 5/6 der Vorlagenhöhe. Runde Masken schneiden die äußeren
Griffe (Gabel, Löffel) unten etwas stärker an als das Messer in der Mitte.

Aufruf (nur nötig, wenn sich assets/icon.png ändert):
    python3 scripts/make-adaptive-icon.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/icon.png"
TARGET = ROOT / "assets/adaptive-icon.png"
CANVAS = 1024            # Expo erwartet 1024 x 1024 für die adaptive Vorlage
VISIBLE_BOTTOM = 0.5 + 36 / 108   # unterer Rand des sichtbaren Bereichs (relativ zur Vorlagenhöhe)
CUT = 0.022                       # so weit ragt das Besteck unten über den sichtbaren Rand hinaus
TOP = 0.5 - 0.288                 # Oberkante des Bestecks (Messerspitze), sicher innerhalb jeder Maske


def motif(pixels):
    """Maske des weißen Bestecks ohne die dünnen weißen Streifenlinien."""
    height, width, _ = pixels.shape
    white = pixels.min(axis=2) > 225
    lines = [x for x in range(width) if white[:, x].sum() > 0.9 * height]
    for x in lines:
        white[:, max(0, x - 3):x + 4] = False
    return white


def build(source=SOURCE, canvas=CANVAS):
    art = Image.open(source).convert("RGB")
    pixels = np.asarray(art).astype(int)
    height, width, _ = pixels.shape
    ys, xs = np.nonzero(motif(pixels))
    centre_x = (xs.min() + xs.max()) / 2
    scale = (VISIBLE_BOTTOM + CUT - TOP) * canvas / (ys.max() - ys.min())   # Quellpixel -> Zielpixel
    # Quellzeile, die in der Mitte der Vorlage landet: Besteck-Oberkante liegt bei TOP.
    centre_y = ys.min() + (0.5 - TOP) * canvas / scale
    # Jedes Zielpixel auf die Quelle abbilden; außerhalb wird die Randzeile bzw.
    # -spalte fortgesetzt (Streifen und Verlauf laufen bis zum Rand weiter).
    target = np.arange(canvas) + 0.5
    source_x = np.clip((target - canvas / 2) / scale + centre_x, 0, width - 1)
    source_y = np.clip((target - canvas / 2) / scale + centre_y, 0, height - 1)
    enlarged = art.resize((round(width * scale), round(height * scale)), Image.LANCZOS)
    small = np.asarray(enlarged)
    sx = np.clip(np.round(source_x * scale - 0.5).astype(int), 0, small.shape[1] - 1)
    sy = np.clip(np.round(source_y * scale - 0.5).astype(int), 0, small.shape[0] - 1)
    result = small[np.ix_(sy, sx)]
    return Image.fromarray(result.astype("uint8"), "RGB"), scale * width / canvas


if __name__ == "__main__":
    image, share = build()
    image.save(TARGET, optimize=True)
    print(f"{TARGET.relative_to(ROOT)}: {image.size[0]} x {image.size[1]}, Logo nimmt {share:.0%} der Vorlagenbreite ein")
