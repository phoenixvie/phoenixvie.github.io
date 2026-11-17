import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {inflateSync} from 'node:zlib';

const root = new URL('../', import.meta.url);
const json = async name => JSON.parse(await readFile(new URL(name, root), 'utf8'));

// Kleiner PNG-Leser (8 Bit, RGB/RGBA, ohne Interlacing) – genügt für die App-Symbole
// und vermeidet eine zusätzliche Abhängigkeit.
async function png(name) {
  const data = await readFile(new URL(name, root));
  assert.equal(data.subarray(1, 4).toString('latin1'), 'PNG', name + ' ist keine PNG-Datei');
  let offset = 8, width, height, channels; const chunks = [];
  while (offset < data.length) {
    const length = data.readUInt32BE(offset), type = data.subarray(offset + 4, offset + 8).toString('latin1');
    const body = data.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = body.readUInt32BE(0); height = body.readUInt32BE(4);
      assert.equal(body[8], 8, 'nur 8 Bit je Kanal'); assert.equal(body[12], 0, 'kein Interlacing');
      channels = {2: 3, 6: 4}[body[9]]; assert.ok(channels, 'RGB oder RGBA erwartet');
    }
    if (type === 'IDAT') chunks.push(body);
    offset += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(chunks)), stride = width * channels, pixels = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)], line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const left = x >= channels ? pixels[y * stride + x - channels] : 0, up = y ? pixels[(y - 1) * stride + x] : 0;
      const corner = y && x >= channels ? pixels[(y - 1) * stride + x - channels] : 0;
      let predictor = 0;
      if (filter === 1) predictor = left; else if (filter === 2) predictor = up; else if (filter === 3) predictor = (left + up) >> 1;
      else if (filter === 4) { const p = left + up - corner, a = Math.abs(p - left), b = Math.abs(p - up), c = Math.abs(p - corner); predictor = a <= b && a <= c ? left : b <= c ? up : corner; }
      pixels[y * stride + x] = (line[x] + predictor) & 255;
    }
  }
  return {width, height, channels, at: (x, y) => pixels.subarray(y * stride + x * channels, y * stride + x * channels + 3)};
}

test('visible version numbers agree, so two different builds cannot carry the same version by accident', async () => {
  const app = (await json('app.json')).expo, pkg = await json('package.json'), lock = await json('package-lock.json');
  assert.match(app.version, /^\d+\.\d+\.\d+$/);
  assert.equal(pkg.version, app.version, 'package.json und app.json nennen verschiedene Versionen');
  assert.equal(lock.version, app.version); assert.equal(lock.packages[''].version, app.version);
  assert.ok(Number.isInteger(app.android.versionCode) && app.android.versionCode > 0);
});

test('unused Android permissions of the Expo template are blocked (Google Play data safety)', async () => {
  // Die App braucht nur Internet. Überlagerung, Speicherzugriff und Vibration stammen aus der Vorlage und werden
  // ausdrücklich entfernt; verify-apk.py prüft das im fertigen APK.
  const app = (await json('app.json')).expo;
  assert.deepEqual(app.android.permissions, ['INTERNET']);
  for (const name of ['SYSTEM_ALERT_WINDOW', 'READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE', 'VIBRATE'])
    assert.ok(app.android.blockedPermissions.includes('android.permission.' + name), name);
});

test('Android package name is the one registered in the Google Play Console', async () => {
  // Vorgabe des Betreibers (17.11.2026): Paketname at.startit.wufood. Er ist nach dem ersten Upload bei
  // Google Play endgültig und darf nicht mehr geändert werden (bis 0.5.4 hieß das Paket at.startit.wulunch).
  const app = (await json('app.json')).expo;
  assert.equal(app.android.package, 'at.startit.wufood');
  const {readFile} = await import('node:fs/promises');
  for (const script of ['verify-apk.py', 'emulator-smoke.py']) {
    const text = await readFile(new URL('./' + script, import.meta.url), 'utf8');
    assert.ok(text.includes('at.startit.wufood') && !text.includes('at.startit.wulunch'), script);
  }
});

test('adaptive Android icon shows the cutlery large, cut slightly by the lower edge, and fills the whole shape', async () => {
  const app = (await json('app.json')).expo;
  assert.equal(app.icon, './assets/icon.png');
  assert.equal(app.android.adaptiveIcon.foregroundImage, './assets/adaptive-icon.png');
  // Kein nachträglicher Innenabstand mehr: Er erzeugte einen sichtbaren Rand um ein verkleinertes Quadrat.
  assert.ok(!JSON.stringify(app.plugins || []).includes('Inset'));
  const image = await png('assets/adaptive-icon.png');
  assert.equal(image.width, 1024); assert.equal(image.height, 1024);
  assert.equal(image.channels, 3, 'Vorlage muss deckend sein (kein Alphakanal)');
  const size = image.width, white = (x, y) => Math.min(...image.at(x, y)) > 225;
  // Dünne weiße Streifenlinien laufen über die volle Höhe und zählen nicht zum Besteck.
  const lines = new Set();
  for (let x = 0; x < size; x++) { let count = 0; for (let y = 0; y < size; y += 4) if (white(x, y)) count++; if (count > 0.9 * size / 4) for (let d = -3; d <= 3; d++) lines.add(x + d); }
  assert.ok(lines.size >= 2, 'Streifenlinien reichen von oben bis unten');
  let cutlery = 0, top = size, bottom = 0, upperReach = 0, left = size, right = 0;
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) if (!lines.has(x) && white(x, y)) {
    cutlery++; top = Math.min(top, y); bottom = Math.max(bottom, y); left = Math.min(left, x); right = Math.max(right, x);
    if (y < size / 2) upperReach = Math.max(upperReach, Math.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2));
  }
  assert.ok(cutlery > 0.06 * size * size, 'Besteck ist groß und deutlich sichtbar');
  // Vorgabe des Betreibers (17.11.2026): herangezoomt; das untere Ende des Bestecks wird knapp abgeschnitten.
  // Sichtbar ist höchstens das mittlere Quadrat mit 72/108 der Vorlage, sein unterer Rand liegt bei 5/6.
  const visibleBottom = size * 5 / 6, over = (bottom - visibleBottom) / size;
  assert.ok(over >= 0.01 && over <= 0.04, `Besteck ragt unten ${(over * 100).toFixed(1)} % über den sichtbaren Rand (knapp abgeschnitten: 1–4 %)`);
  // Oben und seitlich bleibt es vollständig sichtbar, auch bei runden Symbolen (Kreis mit 72/108 Durchmesser).
  assert.ok(upperReach / size <= 36 / 108, `Besteck reicht oben bis ${(upperReach / size).toFixed(4)} (Kreisradius ${(36 / 108).toFixed(4)})`);
  assert.ok(left / size > 1 / 6 + 0.02 && right / size < 5 / 6 - 0.02, 'Gabel und Löffel bleiben seitlich im sichtbaren Bereich');
  // Der Hintergrund füllt die Vorlage: Ecken sind blau wie im Logo, nicht die einfarbige Ersatzfarbe.
  const blue = ([r, g, b]) => b > 90 && b > r + 40 && b > g;
  for (const [x, y] of [[2, 2], [size - 3, 2], [2, size - 3], [size - 3, size - 3], [size / 2, 2], [size / 2, size - 3]]) assert.ok(blue(image.at(x, y)), `Rand bei ${x},${y} ist nicht blau`);
  const upper = image.at(size / 2, 2), lower = image.at(size / 2, size - 3);
  assert.ok(lower[0] + lower[1] > upper[0] + upper[1], 'Verlauf (oben dunkler, unten heller) bleibt erhalten');
});
