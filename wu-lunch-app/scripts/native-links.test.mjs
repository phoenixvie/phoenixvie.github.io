import {test} from 'node:test';
import assert from 'node:assert/strict';
import {isTrustedAppMessageSource, routeAppMessage} from '../src/nativeLinks.ts';

const base = 'https://phoenixvie.github.io/wu-lunch-app/preview/';
const origin = 'https://phoenixvie.github.io';
const fixture = () => {
  const calls = [];
  return {calls, handlers: Object.fromEntries(['openSource','openExternal','share','exit'].map(name => [name, (...args) => calls.push([name, ...args])]))};
};

test('Android origin-only events and legacy full-page events both open web, PDF, telephone and mail links', () => {
  for (const source of [origin, origin+'/', base, base+'index.html?v=1', 'about:blank']) {
    const {calls, handlers} = fixture();
    for (const url of ['https://www.wumensa.at/', 'https://www.wumensa.at/menu.pdf', 'tel:+4367688488254', 'mailto:office@wumensa.at']) {
      routeAppMessage(source, JSON.stringify({type: url.startsWith('https:') ? 'open-source' : 'open-external', url, title:'WU Mensa'}), base, handlers);
    }
    assert.deepEqual(calls, [
      ['openSource','https://www.wumensa.at/','WU Mensa'],
      ['openSource','https://www.wumensa.at/menu.pdf','WU Mensa'],
      ['openExternal','tel:+4367688488254'],
      ['openExternal','mailto:office@wumensa.at'],
    ], source);
  }
});

test('foreign origins, other repository paths and malformed events cannot invoke native actions', () => {
  const {calls, handlers} = fixture();
  for (const source of [undefined, '', 'null', 'https://www.wumensa.at', 'http://phoenixvie.github.io', 'https://phoenixvie.github.io.evil.test', 'https://phoenixvie.github.io@evil.test/', origin+'/other-project/']) {
    assert.equal(isTrustedAppMessageSource(source, base), false);
    routeAppMessage(source, JSON.stringify({type:'exit'}), base, handlers);
  }
  for (const raw of ['bad json', 'null', '[]', '{}', JSON.stringify({type:'open-source',url:'javascript:alert(1)'}), JSON.stringify({type:'open-external',url:'intent://app'}), JSON.stringify({type:'share',text:42})]) routeAppMessage(origin, raw, base, handlers);
  assert.deepEqual(calls, []);
});
