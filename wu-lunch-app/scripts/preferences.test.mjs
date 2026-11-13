import {test} from 'node:test';
import assert from 'node:assert/strict';
import {languagePreferences} from '../src/preferences.ts';

test('manual language survives a cold app restart and rapid changes persist in order',async()=>{
  const values=new Map(),storage={getItem:async key=>values.get(key)||null,setItem:async(key,value)=>{await new Promise(resolve=>setTimeout(resolve,value==='en'?10:0));values.set(key,value);}};
  const firstApp=languagePreferences(storage);assert.equal(await firstApp.load(),null);
  await firstApp.save('en');assert.equal(await languagePreferences(storage).load(),'en');
  await Promise.all([firstApp.save('en'),firstApp.save('de')]);assert.equal(await languagePreferences(storage).load(),'de');
});
test('invalid or unavailable language storage safely falls back to device language',async()=>{
  assert.equal(await languagePreferences({getItem:async()=> 'fr',setItem:async()=>{}}).load(),null);
  assert.equal(await languagePreferences({getItem:async()=>{throw Error('unavailable')},setItem:async()=>{}}).load(),null);
});
