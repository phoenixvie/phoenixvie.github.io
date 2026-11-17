import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('preview requires verified email before a registration and supports cancellation', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const handlers={}; let session=null, own=[], otpCalls=0, verifyCalls=0, inserts=0, openedUrl='', redirectTo='';
  const store=new Map();
  const client={auth:{getSession:async()=>({data:{session},error:null}),signInWithOtp:async({options})=>{otpCalls++;redirectTo=options.emailRedirectTo;return {error:null}},verifyOtp:async({token})=>{verifyCalls++;if(token==='000000')return {data:null,error:new Error('expired')};session={user:{id:'test-user'}};return {data:{session},error:null}}},from(table){return {
    select(){return {in:async()=>({data:own,error:null}),gte:async()=>({data:own,error:null})}},
    insert:async row=>{inserts++;own.push(row);return {error:null}},
    delete(){return {eq(){return {eq:async(_key,date)=>{own=own.filter(item=>item.meeting_date!==date);return {error:null}}}}}}
  }}};
  const inputs={'meet-first-name':{value:'Anna'},'meet-email':{value:'anna@example.com'},'meet-code':{value:'123456'}};
  const context={window:{supabase:{createClient:()=>client},open:url=>{openedUrl=url}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:id=>inputs[id]},
    localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
    setInterval(){},console,Intl,Date,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:'mensa',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d};
  vm.createContext(context);vm.runInContext(source,context);
  const click=async (action,slot)=>{handlers.click({target:{closest:()=>({dataset:{action,slot}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  await click('meet-preview');
  assert.equal(context.meetSlot,0);assert.match(context.renderMeet(),/Meet to eat/);assert.doesNotMatch(context.renderMeet(),/Bereits angemeldet|Noch niemand angemeldet/);
  assert.match(context.renderMeet(),/WU-Studenten Gruppe/);assert.doesNotMatch(context.renderMeet(),/Testvorschau|Testteilnehmer|Testtermin/);
  // Vereinfachung vom 17.11.2026: genau ein Termin, keine Terminleiste, keine Wischpunkte, kein Wischen.
  assert.doesNotMatch(context.renderMeet(),/weekday-strip|day-dot|meet-select|data-slot/);
  assert.equal((context.renderMeet().match(/class="meet-fact"/g)||[]).length,5);
  assert.equal(handlers.touchstart,undefined);assert.equal(handlers.touchend,undefined);
  // Vor der Anmeldung gibt es weder Treffpunkt-Bereich noch Karte, auch nicht unscharf.
  assert.doesNotMatch(context.renderMeet(),/meet-reveal|meet-map|meet-locked|Nach Anmeldung sichtbar|meeting-point|maps\/search/);
  assert.match(context.renderMeet(),/Angabe nach Anmeldung/);
  await click('meet-show-form');
  assert.match(context.renderMeet(),/Prüfung der WU-Zugehörigkeit erfolgt derzeit nicht/);
  assert.equal(inserts,0);await click('meet-send-code');assert.equal(otpCalls,1);assert.equal(inserts,0);assert.equal(redirectTo,'https://phoenixvie.github.io/wu-lunch-app/preview/');
  assert.match(context.renderMeet(),/outlook\.cloud\.microsoft/);assert.match(context.renderMeet(),/Bestätigungscode an anna@example\.com gesendet/);
  handlers.click({target:{closest:()=>({dataset:{action:'meet-open-url'},href:'https://outlook.cloud.microsoft'})},preventDefault(){},stopImmediatePropagation(){}});assert.equal(openedUrl,'https://outlook.cloud.microsoft');
  inputs['meet-code'].value='000000';await click('meet-verify');assert.match(context.renderMeet(),/bereits verwendet/);assert.equal(inserts,0);
  await click('meet-resend-code');assert.equal(otpCalls,2);inputs['meet-code'].value='123456';await click('meet-verify');assert.equal(verifyCalls,2);assert.equal(inserts,1);assert.equal(own[0].first_name,'Anna');
  // Nach der Anmeldung erscheinen Treffpunkt, Foto und Karte.
  assert.match(context.renderMeet(),/Bereits angemeldet/);assert.match(context.renderMeet(),/Anna/);assert.match(context.renderMeet(),/48\.21289788048291%2C16\.409449359855884/);assert.match(context.renderMeet(),/Vor dem Baum direkt bei der Mensa/);
  assert.match(context.renderMeet(),/<section class="meet-reveal"><h3>Treffpunkt auf der WU<\/h3>/);assert.match(context.renderMeet(),/id="meet-map"/);assert.match(context.renderMeet(),/meeting-point\.webp/);
  assert.equal(context.meetJoined,true);
  await click('meet-leave');assert.equal(own.length,0);
  assert.doesNotMatch(context.renderMeet(),/Bereits angemeldet|Noch niemand angemeldet|meet-reveal|meet-map/);assert.equal(context.meetJoined,false);
  store.clear();await click('meet-show-form');assert.match(context.renderMeet(),/E-Mail-Adresse ist bestätigt/);await click('meet-confirm-name');assert.equal(inserts,2);await click('meet-leave');
  await click('meet-back');assert.equal(context.meetPreviewOpen,false);assert.equal(context.selectedId,'mensa');
});

test('only one date is shown: the next one open for sign-up, or today while you are signed up', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const viennaClock'),source.indexOf('  // Texte kommen aus dem gemeinsamen Katalog'));
  let current='2026-11-16T09:00:00Z';   // Montag 10:00 Uhr Wien
  class Clock extends Date { constructor(...args){super(...(args.length?args:[current]));} }
  const state={own:[]};
  const context={Intl,Date:Clock,state};vm.createContext(context);vm.runInContext(helper,context);
  const shown=()=>vm.runInContext('date()',context);
  assert.equal(shown(),'2026-11-16');                                    // Anmeldung für heute noch offen
  current='2026-11-16T11:06:00Z';assert.equal(shown(),'2026-11-18');     // 12:06: geschlossen -> nächster Termin
  state.own=[{meeting_date:'2026-11-16'}];assert.equal(shown(),'2026-11-16'); // selbst angemeldet: Treffpunkt bleibt sichtbar
  current='2026-11-16T21:59:00Z';assert.equal(shown(),'2026-11-16');
  current='2026-11-16T22:00:00Z';assert.equal(shown(),'2026-11-18');     // ab 23:00 Uhr: nächster Termin
  state.own=[];current='2026-11-17T08:00:00Z';assert.equal(shown(),'2026-11-18'); // Dienstag
  current='2026-11-19T08:00:00Z';assert.equal(shown(),'2026-11-23');     // Donnerstag -> Montag
});

test('texts fall back to German and use the shared catalogue for English', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const text = (key'),source.indexOf('  const redraw ='));
  const run=localize=>{const context=localize?{localize}:{};vm.createContext(context);vm.runInContext(helper,context);return (key,values,german)=>vm.runInContext('text',context)(key,values,german);};
  const german=run(null);
  assert.equal(german('Jeden {weekday}: Gemeinsam Essen gehen',{weekday:'Mittwoch'}),'Jeden Mittwoch: Gemeinsam Essen gehen');
  assert.equal(german('Meet to eat: Abmelden',{},'Abmelden'),'Abmelden');
  const catalogue=JSON.parse(JSON.stringify((await import('node:module')).createRequire(import.meta.url)('../../wu-lunch/i18n.js')??{}));
  const {ui}=globalThis.WULunchI18n;
  const english=run({label:key=>ui[key]??key});
  assert.equal(english('Jeden {weekday}: Gemeinsam Essen gehen',{weekday:'Wednesday'}),'Every Wednesday: go for lunch together');
  assert.equal(english('Meet to eat: Abmelden',{},'Abmelden'),'Cancel sign-up');
  assert.equal(english('Meet to eat: Anmelden',{},'Anmelden'),'Sign up');
  // Jeder feste Text des Bildschirms hat eine englische Fassung (sonst "English translation pending").
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  for(const key of ['Gemeinsam essen gehen','Datum','Uhrzeit am Treffpunkt','12:00 Uhr','Gemeinsam losgehen','12:05 Uhr','Treffpunkt auf der WU','Angabe nach Anmeldung','Vor dem Baum direkt bei der Mensa','Teilnehmer','WU-Studenten Gruppe','Bereits angemeldet','Verbindlich anmelden','Google Maps öffnen','Vorname','Bestätigungscode senden','Bestätigungscode','Code bestätigen und anmelden','Neuen Code anfordern','WU-Mail öffnen','Die Anmeldung für diesen Termin ist geschlossen.','Das hat nicht funktioniert. Bitte versuche es erneut.','Triff dich am WU Campus mit anderen Studierenden und geht gemeinsam als Gruppe Mittag essen.']){
    assert.ok(source.includes(key)||app.includes(key),'Text wird verwendet: '+key);
    assert.ok(ui[key]&&ui[key]!==key,'englische Fassung fehlt: '+key);
  }
  // "Anmelden" bleibt für den Admin-Login "Sign in"; Meet to eat nutzt eigene Schlüssel.
  assert.equal(ui.Anmelden,'Sign in');assert.notEqual(ui['Meet to eat: Anmelden'],ui.Anmelden);
});

test('Android back button closes Meet to eat instead of leaving the app, and the icon is mirrored', async () => {
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');
  const back=app.slice(app.indexOf('window.wuFoodBack='),app.indexOf('try{const cached='));
  const messages=[];let renders=0;
  const context={sourceViewUrl:null,meetPreviewOpen:true,meetForm:true,meetSlot:0,meetJoined:true,selectedId:null,selectedMapId:null,homeTab:'list',
    render:()=>{renders++},nativePost:type=>messages.push(type),window:{}};
  vm.createContext(context);vm.runInContext(back,context);
  context.window.wuFoodBack();assert.equal(context.meetForm,false);assert.equal(context.meetPreviewOpen,true);   // Formular -> Terminansicht
  context.window.wuFoodBack();assert.equal(context.meetPreviewOpen,false);assert.equal(context.meetJoined,false); // Terminansicht -> Liste
  assert.deepEqual(messages,[]);assert.equal(renders,2);
  context.window.wuFoodBack();assert.deepEqual(messages,['exit']);                                                // erst in der Liste: App verlassen
  assert.match(css,/\.meet-brand-logo \.material-svg\{[^}]*transform:scaleX\(-1\)/);
});

test('restaurant menu offers an internal Meet-to-eat link above the source note', async () => {
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const menu=source.slice(source.indexOf('function renderMenu('),source.indexOf('function renderInfo('));
  assert.match(menu,/data-action="meet-preview"/);
  assert.ok(menu.indexOf('gemeinsam essen</span>') < menu.indexOf('Angaben ohne Gewähr'));
  assert.match(menu,/\[0,2\]\.includes\(dayIndex\)/);
});

test('Vienna dates stay visible until 23:00 and registration closes after 12:05', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const viennaClock'),source.indexOf('  const date ='));
  let current='2026-11-15T23:01:00Z';
  class Clock extends Date { constructor(...args){super(...(args.length?args:[current]));} }
  const context={Intl,Date:Clock};vm.createContext(context);vm.runInContext(helper,context);
  const days=()=>Array.from(vm.runInContext('slotDates()',context));
  const open=(date)=>vm.runInContext(`registrationOpen('${date}')`,context);
  assert.deepEqual(days(),['2026-11-16','2026-11-18','2026-11-23','2026-11-25','2026-11-30']);assert.equal(open('2026-11-16'),true);
  current='2026-11-16T11:05:59Z';assert.equal(open('2026-11-16'),true);assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T11:06:00Z';assert.equal(open('2026-11-16'),false);assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T21:59:00Z';assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T22:00:00Z';assert.deepEqual(days(),['2026-11-18','2026-11-23','2026-11-25','2026-11-30','2026-12-02']);
  current='2026-11-18T22:00:00Z';assert.deepEqual(days(),['2026-11-23','2026-11-25','2026-11-30','2026-12-02','2026-12-07']);
  current='2027-03-29T10:05:59Z';assert.equal(open('2027-03-29'),true);
  current='2027-03-29T10:06:00Z';assert.equal(open('2027-03-29'),false);
});


test('Meet to eat icons are bundled as SVG and inherit their screen colours', async () => {
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');
  const match=app.match(/const meetIcons=(\{.*?\});\nconst icon=/);
  assert.ok(match, 'bundled icon map exists');
  const icons=JSON.parse(match[1]);
  for(const name of ['calendar_today','directions_walk','school','lock','person','person_add']) {
    assert.match(icons[name], /<svg/); assert.match(icons[name], /class="material-svg"/);
  }
  assert.match(css,/\.meet-fact>\.material-svg\{[^}]*color:#6f8192/);
  assert.match(css,/\.meet-person \.material-svg\{[^}]*color:#8a98a5/);
  assert.match(css,/\.meet-brand-logo \.material-svg\{[^}]*width:34px/);
});

test('Meet to eat keeps its scroll position during background redraws', async () => {
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const start=source.indexOf('function render(){');
  const end=source.indexOf('const r=currentRestaurant();',start);
  assert.ok(start>=0 && end>start);
  let screen={scrollTop:540};
  const app={querySelector:()=>screen, set innerHTML(value){screen={scrollTop:0};}};
  const context={data:{},meetPreviewOpen:true,app,map:null,renderMeet:()=>'<div id="meet-screen"></div>',document:{getElementById:()=>null},Number};
  vm.createContext(context);vm.runInContext(source.slice(start,end)+'}',context);
  context.render();assert.equal(screen.scrollTop,540);
  screen.scrollTop=320;context.render();assert.equal(screen.scrollTop,320);
});
