// Oberfläche nachladen (src/remoteUi.ts): Nur eine vollständige, unveränderte, zur App passende und nicht
// abgeschaltete Fassung wird gezeigt; eine Fassung, die nicht startet, wird nie wieder versucht.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {remoteUi, sha256Hex, versionAtLeast, uiBase} from '../src/remoteUi.ts';

const sha = text => createHash('sha256').update(text).digest('hex');
const design = letter => letter.repeat(64);
const page = hash => `<html><head></head><body><script>window.WU_FOOD_BUILD='${hash}';</script><p>Oberfläche ${hash.slice(0, 4)} – „Menü“ 🍲</p></body></html>`;

function world({enabled, html = page(design('a')), manifest, settingsFail = false} = {}) {
  const store = new Map(), calls = [];
  const state = {enabled, html, manifest: manifest ?? {design: design('a'), sha256: sha(html), min_native: '0.5.9'}, settingsFail};
  const storage = {getItem: async key => store.has(key) ? store.get(key) : null, setItem: async (key, value) => {store.set(key, value);}, removeItem: async key => {store.delete(key);}};
  const fetcher = async url => {
    calls.push(url);
    if (url.includes('supabase.co')) {
      if (state.settingsFail) throw new Error('offline');
      return {ok: true, json: async () => state.enabled === undefined ? [] : [{key: 'remote_ui', value: {enabled: state.enabled}}], text: async () => ''};
    }
    if (url.startsWith(uiBase + 'manifest.json')) return {ok: true, json: async () => state.manifest, text: async () => JSON.stringify(state.manifest)};
    if (url.startsWith(uiBase + 'app.html')) return {ok: true, json: async () => ({}), text: async () => state.html};
    return {ok: false, json: async () => ({}), text: async () => ''};
  };
  return {store, calls, state, ui: (version = '0.5.9', builtin = design('0')) => remoteUi(storage, version, builtin, fetcher)};
}
const minute = 60_000;

test('checksum matches node:crypto for plain, accented, emoji and the real page', async () => {
  for (const text of ['', 'abc', 'Menü – „Tagesteller“ 12,90 €', '🍲'.repeat(100), 'x'.repeat(55), 'x'.repeat(56), 'x'.repeat(64), 'x'.repeat(1000)]) assert.equal(sha256Hex(text), sha(text), JSON.stringify(text.slice(0, 20)));
  const real = await readFile(new URL('../ui/app.html', import.meta.url), 'utf8');
  assert.equal(sha256Hex(real), sha(real));
});

test('version comparison', () => {
  assert.ok(versionAtLeast('0.5.9', '0.5.9')); assert.ok(versionAtLeast('0.6.0', '0.5.9')); assert.ok(versionAtLeast('1.0.0', '0.9.9')); assert.ok(versionAtLeast('0.5.10', '0.5.9'));
  assert.ok(!versionAtLeast('0.5.8', '0.5.9')); assert.ok(!versionAtLeast('0.5', '0.5.9')); assert.ok(!versionAtLeast('0.5.9', 'x'));
});

test('a new page is downloaded, shown on the next start and kept once it reported ready', async () => {
  const w = world(), ui = w.ui();
  assert.equal(await ui.start(), null);                                   // nichts gespeichert: eingebaute Fassung
  assert.equal(await ui.check(1_000_000), 'downloaded');
  assert.deepEqual(await ui.start(), {html: page(design('a')), hash: design('a')});
  await ui.confirm(design('a'));
  assert.equal(await ui.check(1_000_000 + minute), 'skipped');            // höchstens alle fünf Minuten nachsehen
  assert.equal(await ui.check(1_000_000 + 6 * minute), 'unchanged');
  assert.equal((await ui.start()).hash, design('a'));
  // Nächste Fassung: wird bereitgelegt und ersetzt nach der Rückmeldung die alte, deren Kopie gelöscht wird.
  w.state.html = page(design('b')); w.state.manifest = {design: design('b'), sha256: sha(w.state.html), min_native: '0.5.9'};
  assert.equal(await ui.check(1_000_000 + 12 * minute), 'downloaded');
  assert.equal((await ui.start()).hash, design('b'));
  await ui.confirm(design('b'));
  assert.deepEqual([...w.store.keys()].filter(key => key.includes('-html-')), ['wu-remote-ui-html-' + design('b')]);
});

test('a page that did not start is never tried again and the built-in page is used', async () => {
  const w = world(), ui = w.ui();
  await ui.check(1); await ui.reject(design('a'));
  assert.equal(await ui.start(), null);
  assert.equal(await ui.check(1 + 6 * minute), 'unchanged');
  assert.equal(await ui.start(), null);
  assert.equal(w.calls.filter(url => url.includes('app.html')).length, 1);  // kein zweiter Download
  // Eine bewährte Fassung, die später doch nicht mehr startet, fällt ebenfalls weg.
  const v = world(), other = v.ui();
  await other.check(1); await other.confirm(design('a')); await other.reject(design('a'));
  assert.equal(await other.start(), null);
});

test('switching it off in the admin wins over everything stored, switching it on again brings the page back', async () => {
  const w = world(), ui = w.ui();
  await ui.check(1); await ui.confirm(design('a'));
  w.state.enabled = false;
  assert.equal(await ui.check(1 + 6 * minute), 'disabled');
  assert.equal(await ui.start(), null);
  w.state.settingsFail = true;                                             // Einstellung nicht erreichbar: letzter Stand gilt
  assert.equal(await ui.check(1 + 12 * minute), 'disabled');
  w.state.settingsFail = false; w.state.enabled = true;
  assert.equal(await ui.check(1 + 18 * minute), 'unchanged');
  assert.equal((await ui.start()).hash, design('a'));
});

test('damaged, mislabeled or too new pages are not taken over', async () => {
  const tampered = world(); tampered.state.html = page(design('a')) + '<script>alert(1)</script>';
  assert.equal(await tampered.ui().check(1), 'error');
  assert.equal(await tampered.ui().start(), null);
  const mislabeled = world({html: page(design('b')), manifest: {design: design('a'), sha256: sha(page(design('b'))), min_native: '0.5.9'}});
  assert.equal(await mislabeled.ui().check(1), 'error');
  const broken = world({manifest: {design: 'kaputt', sha256: 'x', min_native: '0.5.9'}});
  assert.equal(await broken.ui().check(1), 'error');
  const newer = world({manifest: {design: design('a'), sha256: sha(page(design('a'))), min_native: '0.6.0'}});
  assert.equal(await newer.ui('0.5.9').check(1), 'unchanged');             // braucht eine neuere App
  assert.equal(newer.calls.filter(url => url.includes('app.html')).length, 0);
  assert.equal(await newer.ui('0.6.0').check(1 + 6 * minute), 'downloaded');
});

test('when the server shows the same page as the built-in one nothing is loaded and stored copies are dropped', async () => {
  const w = world();
  await w.ui().check(1); await w.ui().confirm(design('a'));
  assert.equal(await w.ui('0.5.9', design('a')).check(1 + 6 * minute), 'unchanged');   // neuer Build enthält dieselbe Fassung
  assert.equal(await w.ui('0.5.9', design('a')).start(), null);
  assert.deepEqual([...w.store.keys()].filter(key => key.includes('-html-')), []);
});

test('published page, checksum list and built-in page are the same thing', async () => {
  const manifest = JSON.parse(await readFile(new URL('../ui/manifest.json', import.meta.url), 'utf8'));
  const published = await readFile(new URL('../ui/app.html', import.meta.url), 'utf8');
  const {designHash, previewHtml} = await import('../src/previewHtml.ts');
  assert.equal(published, previewHtml, 'ui/app.html weicht von der eingebauten Oberfläche ab – npm run bundle:preview ausführen');
  assert.deepEqual([manifest.design, manifest.sha256, manifest.bytes], [designHash, sha(published), Buffer.byteLength(published)]);
  assert.match(manifest.min_native, /^\d+\.\d+\.\d+$/);
  assert.ok(published.includes(`window.WU_FOOD_BUILD='${designHash}'`));
  assert.match(published, /nativePost\('ui-ready',\{build:String\(window\.WU_FOOD_BUILD\|\|''\)\}\)/);
});

test('the app shows a downloaded page only with a ready signal and falls back otherwise', async () => {
  const app = await readFile(new URL('../App.tsx', import.meta.url), 'utf8');
  assert.match(app, /const remote = remoteUi\(AsyncStorage, appVersion, designHash\);/);
  assert.match(app, /Promise\.all\(\[preferences\.load\(\),remote\.start\(\)\]\)/);
  assert.match(app, /if\(next\)readyTimer\.current=setTimeout\(\(\)=>failRemote\(next\.hash\),READY_TIMEOUT\);/);
  assert.match(app, /const failRemote=\(hash: string\)=>\{if\(awaiting\.current!==hash\)return;awaiting\.current=null;void remote\.reject\(hash\);showPage\(null\);\};/);
  assert.match(app, /onError=\{\(\)=>\{if\(awaiting\.current\)failRemote\(awaiting\.current\);\}\}/);
  assert.match(app, /setHtmlSource\(pageSource\(next\?next\.html:previewHtml,savedLanguage\.current\)\);/);   // eingebaute Fassung bleibt die Reserve
});
