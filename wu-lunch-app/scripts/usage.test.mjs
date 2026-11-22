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

test('extended catalogue covers Meet to eat, map, links and sharing with fixed value lists only',()=>{
  const ok=(event,props,expected)=>assert.deepEqual(validateUsage(event,{language:'de',...props}),{event,props:{app_language:'de',...expected}});
  ok('meet_open',{entry:'menu_hint'},{entry:'menu_hint'});
  ok('meet_date_changed',{slot:'following'},{slot:'following'});
  ok('meet_signup_started',{slot:'next'},{slot:'next'});
  ok('meet_input_rejected',{reason:'email_invalid',email:'someone@gmail',name:'Anna'},{reason:'email_invalid'});   // Eingaben selbst werden nie gesendet
  ok('meet_code_requested',{resend:'yes'},{resend:'yes'});
  ok('meet_code_result',{result:'invalid',token:'123456'},{result:'invalid'});
  ok('meet_joined',{slot:'next',weekday:3,first_name:'Anna'},{slot:'next',weekday:3});
  ok('meet_left',{slot:'next'},{slot:'next'});
  ok('meet_maps_opened',{source:'fact',href:'https://maps.example'},{source:'fact'});
  ok('home_view',{view:'map'},{view:'map'});
  ok('map_pin_selected',{restaurant_id:'finn'},{restaurant_id:'finn'});
  ok('restaurant_link',{restaurant_id:'lia',link:'phone',url:'tel:+431'},{restaurant_id:'lia',link:'phone'});
  ok('restaurant_shared',{restaurant_id:'mensa'},{restaurant_id:'mensa'});
  ok('footer_link',{link:'imprint'},{link:'imprint'});
  ok('meet_joined',{slot:'next',weekday:2},{slot:'next',weekday:2});   // Tage sind im Admin einstellbar (Montag bis Freitag)
  ok('update_notice',{action:'later',version:'0.5.6'},{action:'later'});
  ok('menu_day_changed',{restaurant_id:'mensa',weekday:2,method:'swipe'},{restaurant_id:'mensa',weekday:2,method:'swipe'});
  ok('menu_day_changed',{restaurant_id:'mensa',weekday:2},{restaurant_id:'mensa',weekday:2});                          // ältere Aufrufe ohne Methode
  for(const [event,props] of [['meet_joined',{slot:'next',weekday:6}],['meet_open',{entry:'push'}],['meet_input_rejected',{reason:'Anna ist gesperrt'}],
    ['restaurant_link',{restaurant_id:'lia',link:'https://example.org'}],['footer_link',{link:'admin'}],['home_view',{view:'settings'}],['meet_code_result',{result:'123456'}],
    ['menu_day_changed',{restaurant_id:'mensa',weekday:2,method:'shake'}],['constructor',{}],['toString',{}]])
    assert.equal(validateUsage(event,{language:'de',...props}),null,event);
});
