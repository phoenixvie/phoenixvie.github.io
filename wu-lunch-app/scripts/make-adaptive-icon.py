#!/usr/bin/env python3
"""Adaptives Android-Icon aus dem quadratischen Logo erzeugen.

Android schneidet App-Symbole je nach Gerät rund, als abgerundetes Quadrat oder
als "Squircle" zu und zeigt dabei nur die Mitte der Vorlage. Liegt das
quadratische Logo unverändert darunter, werden Gabel und Löffel angeschnitten;
verkleinert man es einfach, bleibt ein einfarbiger Rand um ein kleines Quadrat.

Dieses Skript baut deshalb eine eigene Vorlage (assets/adaptive-icon.png):
- Gabel, Messer und Löffel liegen vollständig in der garantiert sichtbaren Mitte
  ("safe zone": Kreis mit 66 von 108 Einheiten Durchmesser).
- Die drei blauen Streifen samt Verlauf werden bis an den Rand der Vorlage
  fortgesetzt, sodass bei keiner Maskenform ein Rand oder eine Kante sichtbar ist.

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
SAFE_RADIUS = 33 / 108   # Radius der sicheren Zone, relativ zur Vorlage
MARGIN = 0.985           # etwas Luft zur Grenze der sicheren Zone


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
    centre_x, centre_y = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    reach = np.sqrt((xs - centre_x) ** 2 + (ys - centre_y) ** 2).max()   # in Quellpixeln
    scale = SAFE_RADIUS * MARGIN * canvas / reach                        # Quellpixel -> Zielpixel
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
