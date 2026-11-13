import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createUsage,validateUsage,isAnalyticsDevice} from '../src/usage.ts';
import {routeAppMessage} from '../src/nativeLinks.ts';

test('app opens count cold start and real foreground return, never inactive overlays or repeated refresh',()=>{
  const calls=[],usage=createUsage((event,props)=>calls.push({event,props}));
  for(const state of ['active','active','inactive','active','background','inactive','active','active'])usage.state(state,'de');
  assert.deepEqual(calls.map(x=>x.props.entry),['cold_start','foreground']);
  assert.ok(calls.every(x=>x.event==='app_open'));
});
test('restaurant analytics contain only bounded usage fields, excluding personal text and arbitrary URLs',()=>{
  const valid=validateUsage('restaurant_open',{language:'en',restaurant_id:'mensa',entry:'list',view:'menu',email:'private@example.test',url:'https://example.test/private',menu:'Secret dish'});
  assert.deepEqual(valid,{event:'restaurant_open',props:{app_language:'en',restaurant_id:'mensa',entry:'list',view:'menu'}});
  for(const props of [{language:'en',restaurant_id:'unknown',entry:'list',view:'menu'},{language:'en',restaurant_id:'mensa',weekday:6},{language:'fr',restaurant_id:'mensa',weekday:2}])assert.equal(validateUsage('menu_day_changed',props),null);
  assert.equal(validateUsage('arbitrary_event',{language:'en'}),null);
});
test('untrusted frames cannot send usage; analytics errors never break app navigation',()=>{
  let sent=0;const usage=createUsage(()=>{sent++;throw Error('offline')});
  const base='https://phoenixvie.github.io/wu-lunch-app/preview/',raw=JSON.stringify({type:'usage',event:'menu_day_changed',props:{language:'de',restaurant_id:'finn',weekday:4}});
  const handlers={openSource(){},openExternal(){},share(){},exit(){},usage:(event,props)=>usage.event(event,props)};
  routeAppMessage('https://restaurant.example',raw,base,handlers);assert.equal(sent,0);
  assert.doesNotThrow(()=>routeAppMessage(base,raw,base,handlers));assert.equal(sent,1);
});

test('German and English usage is measured regardless of automatic or manual selection',()=>{
  const calls=[],usage=createUsage((event,props)=>calls.push({event,props}));
  usage.state('active','de');usage.event('language_changed',{language:'en'});usage.state('background','en');usage.state('active','en');
  assert.deepEqual(calls.map(x=>x.props.app_language),['de','en','en']);
});
test('Android emulator and automated tests never enter production usage statistics',()=>{
  assert.equal(isAnalyticsDevice('android',{Model:'sdk_gphone64_x86_64',Fingerprint:'google/sdk_gphone64_x86_64/emulator'}),false);
  assert.equal(isAnalyticsDevice('android',{isTesting:true,Model:'SM-S918B'}),false);
  assert.equal(isAnalyticsDevice('web',{}),false);
  assert.equal(isAnalyticsDevice('android',{Model:'SM-S918B',Fingerprint:'samsung/dm3qxeea/dm3q'}),true);
});
