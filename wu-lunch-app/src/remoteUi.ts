// Oberfläche nachladen: Die App zeigt die aktuelle Oberfläche vom Server, ohne dass ein neuer Build nötig ist.
//
// Die eingebaute Oberfläche (src/previewHtml.ts) bleibt die Reserve. Eine nachgeladene Fassung wird erst gezeigt,
// wenn sie vollständig und unverändert angekommen ist (Prüfsumme), zur App-Version passt und nicht abgeschaltet
// wurde. Startet sie nicht (keine Rückmeldung der Seite), merkt sich die App das und nimmt wieder die eingebaute.
// Abschalten: Admin, „App-Oberfläche nachladen" (Einstellung remote_ui in lunch_settings).

export const uiBase = 'https://phoenixvie.github.io/wu-lunch-app/ui/';
const settingsUrl = 'https://vswnqdqnohbuzbwmsdvv.supabase.co/rest/v1/lunch_settings?select=key,value&key=eq.remote_ui';
// Öffentlicher Schlüssel (derselbe wie in wu-lunch/supabase-config.js); Schreibrechte regelt die Datenbank.
const publishableKey = 'sb_publishable__LAhcQOUGtE-ACAN-RPKkw_UB7Nrub2';
const metaKey = 'wu-remote-ui-v1';
const htmlKey = (hash: string) => 'wu-remote-ui-html-' + hash;

type Storage = {getItem(key: string): Promise<string | null>; setItem(key: string, value: string): Promise<unknown>; removeItem(key: string): Promise<unknown>};
type Fetcher = (url: string, init?: {headers?: Record<string, string>; signal?: unknown}) => Promise<{ok: boolean; json(): Promise<unknown>; text(): Promise<string>}>;
type Entry = {hash: string; sha: string; minNative: string};
type Meta = {current?: Entry; pending?: Entry; failed: string[]; enabled: boolean; checkedAt?: number};
export type RemotePage = {html: string; hash: string};
export type CheckResult = 'skipped' | 'disabled' | 'unchanged' | 'downloaded' | 'error';

const semver = /^\d+\.\d+\.\d+$/;
export function versionAtLeast(version: string, minimum: string): boolean {
  if (!semver.test(version) || !semver.test(minimum)) return false;
  const a = version.split('.').map(Number), b = minimum.split('.').map(Number);
  for (let index = 0; index < 3; index++) if (a[index] !== b[index]) return a[index] > b[index];
  return true;
}

// SHA-256 über den UTF-8-Text (Hermes hat kein crypto.subtle). Geprüft gegen node:crypto in remote-ui.test.mjs.
const K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
function utf8(text: string): number[] {
  const bytes: number[] = [];
  for (let index = 0; index < text.length; index++) {
    let code = text.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff && index + 1 < text.length) {
      const next = text.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {code = 0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00); index++;}
    }
    if (code < 0x80) bytes.push(code);
    else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 63));
    else if (code < 0x10000) bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
    else bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 63), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
  }
  return bytes;
}
export function sha256Hex(text: string): string {
  const bytes = utf8(text), length = bytes.length;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  const high = Math.floor(length / 0x20000000), low = (length << 3) >>> 0;
  for (const part of [high, low]) bytes.push((part >>> 24) & 255, (part >>> 16) & 255, (part >>> 8) & 255, part & 255);
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const w = new Array<number>(64);
  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let index = 0; index < 16; index++) w[index] = ((bytes[offset + index * 4] << 24) | (bytes[offset + index * 4 + 1] << 16) | (bytes[offset + index * 4 + 2] << 8) | bytes[offset + index * 4 + 3]) >>> 0;
    for (let index = 16; index < 64; index++) {
      const x = w[index - 15], y = w[index - 2];
      const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3), s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
      w[index] = (w[index - 16] + s0 + w[index - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, i] = h;
    for (let index = 0; index < 64; index++) {
      const s1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7)), ch = (e & f) ^ (~e & g);
      const t1 = (i + s1 + ch + K[index] + w[index]) >>> 0;
      const s0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10)), maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (s0 + maj) >>> 0;
      i = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    [a, b, c, d, e, f, g, i].forEach((value, index) => {h[index] = (h[index] + value) >>> 0;});
  }
  return h.map(value => ('00000000' + value.toString(16)).slice(-8)).join('');
}

const hex64 = /^[0-9a-f]{64}$/;
const validEntry = (value: unknown): value is Entry => !!value && typeof value === 'object' && hex64.test((value as Entry).hash) && hex64.test((value as Entry).sha) && semver.test((value as Entry).minNative);

/**
 * @param builtinHash designHash der eingebauten Oberfläche: Stimmt der Server damit überein, braucht es kein Nachladen.
 */
export function remoteUi(storage: Storage, appVersion: string, builtinHash: string, fetcher: Fetcher = fetch as unknown as Fetcher) {
  const read = async (): Promise<Meta> => {
    try {
      const value = JSON.parse((await storage.getItem(metaKey)) || '{}');
      return {current: validEntry(value.current) ? value.current : undefined, pending: validEntry(value.pending) ? value.pending : undefined,
        failed: Array.isArray(value.failed) ? value.failed.filter((item: unknown) => typeof item === 'string' && hex64.test(item)).slice(-10) : [],
        enabled: value.enabled !== false, checkedAt: typeof value.checkedAt === 'number' ? value.checkedAt : undefined};
    } catch {return {failed: [], enabled: true};}
  };
  const write = (meta: Meta) => storage.setItem(metaKey, JSON.stringify(meta));
  const usable = (meta: Meta, entry?: Entry) => !!entry && !meta.failed.includes(entry.hash) && versionAtLeast(appVersion, entry.minNative);
  return {
    /** Welche nachgeladene Fassung jetzt zu zeigen ist: zuerst eine neu heruntergeladene, sonst die zuletzt bewährte. null = eingebaute. */
    async start(): Promise<RemotePage | null> {
      try {
        const meta = await read();
        if (!meta.enabled) return null;
        for (const entry of [meta.pending, meta.current]) {
          if (!usable(meta, entry)) continue;
          const html = await storage.getItem(htmlKey(entry!.hash));
          if (html && html.includes('<head>')) return {html, hash: entry!.hash};
        }
      } catch {}
      return null;
    },
    /** Die Seite hat sich gemeldet: Fassung gilt als bewährt. */
    async confirm(hash: string): Promise<void> {
      try {
        const meta = await read();
        if (meta.pending?.hash !== hash) return;
        const old = meta.current?.hash;
        meta.current = meta.pending; meta.pending = undefined;
        await write(meta);
        if (old && old !== hash) await storage.removeItem(htmlKey(old));
      } catch {}
    },
    /** Die Seite ist nicht gestartet: nie wieder versuchen, eingebaute Fassung nehmen. */
    async reject(hash: string): Promise<void> {
      try {
        const meta = await read();
        if (!meta.failed.includes(hash)) meta.failed = [...meta.failed, hash].slice(-10);
        if (meta.pending?.hash === hash) meta.pending = undefined;
        if (meta.current?.hash === hash) meta.current = undefined;
        await write(meta);
        await storage.removeItem(htmlKey(hash));
      } catch {}
    },
    /** Im Hintergrund nachsehen, ob es eine neue Fassung gibt, und sie für den nächsten Start bereitlegen. */
    async check(now = Date.now()): Promise<CheckResult> {
      try {
        const meta = await read();
        if (meta.checkedAt && now - meta.checkedAt < 5 * 60_000 && now >= meta.checkedAt) return 'skipped';
        meta.checkedAt = now;
        try {
          const response = await fetcher(settingsUrl, {headers: {apikey: publishableKey}});
          if (response.ok) {
            const rows = await response.json();
            const value = Array.isArray(rows) && rows[0] && typeof rows[0] === 'object' ? (rows[0] as {value?: {enabled?: unknown}}).value : undefined;
            meta.enabled = !(value && value.enabled === false);
          }
        } catch {}  // Einstellung nicht erreichbar: letzter bekannter Stand gilt
        if (!meta.enabled) {await write(meta); return 'disabled';}
        const manifestResponse = await fetcher(uiBase + 'manifest.json?t=' + now);
        if (!manifestResponse.ok) {await write(meta); return 'error';}
        const manifest = await manifestResponse.json() as {design?: unknown; sha256?: unknown; min_native?: unknown};
        const entry = {hash: manifest.design, sha: manifest.sha256, minNative: manifest.min_native};
        if (!validEntry(entry)) {await write(meta); return 'error';}
        if (entry.hash === builtinHash) {
          // Der Server zeigt dasselbe wie die eingebaute Fassung: nichts nachladen, Gespeichertes verwerfen.
          const stale = [meta.current?.hash, meta.pending?.hash].filter((hash): hash is string => !!hash);
          meta.current = undefined; meta.pending = undefined;
          await write(meta);
          for (const hash of stale) await storage.removeItem(htmlKey(hash));
          return 'unchanged';
        }
        if (entry.hash === meta.current?.hash || entry.hash === meta.pending?.hash || !usable(meta, entry)) {await write(meta); return 'unchanged';}
        const pageResponse = await fetcher(uiBase + 'app.html?v=' + entry.hash);
        if (!pageResponse.ok) {await write(meta); return 'error';}
        const html = await pageResponse.text();
        // Vollständig und unverändert? Sonst nichts übernehmen.
        if (html.length > 3_000_000 || !html.includes('<head>') || !html.includes("window.WU_FOOD_BUILD='" + entry.hash + "'") || sha256Hex(html) !== entry.sha) {await write(meta); return 'error';}
        await storage.setItem(htmlKey(entry.hash), html);
        const replaced = meta.pending?.hash;
        meta.pending = entry;
        await write(meta);
        if (replaced && replaced !== entry.hash && replaced !== meta.current?.hash) await storage.removeItem(htmlKey(replaced));
        return 'downloaded';
      } catch {return 'error';}
    },
  };
}
