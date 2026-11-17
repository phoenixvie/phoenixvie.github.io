import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('website live refresh re-enables restaurants from fresh data and keeps previous data on API failure',async()=>{
  const html=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');
  let enabled=false,failed=false;
  const c={window:{WULunchI18n:{refresh:async()=>{}}},DATA:{restaurants:[{id:'mensa'}]},Date,console,realMap:null,locationInfo:{},update(){},loadRealMap(){},fetch:async()=>({ok:true,json:async()=>({restaurants:[{id:'mensa'},{id:'finn'}]})}),loadAnnouncement:async()=>{},manualFetchSucceeded:true,profileFetchSucceeded:true,applyManualMenus:async()=>{}};
  // Die Einstellungen werden auf einen eigenen Stand angewendet; DATA darf währenddessen nie die rohen Importdaten zeigen.
  const seenWhileLoading=[];
  c.applyRestaurantOverrides=async target=>{seenWhileLoading.push(c.DATA.restaurants.length);c.profileFetchSucceeded=!failed;if(!enabled)target.restaurants=target.restaurants.filter(r=>r.id!=='finn');};
  vm.createContext(c);vm.runInContext("let liveRefreshing=false,liveSignature='';"+html.slice(html.indexOf('    async function refreshLiveData('),html.indexOf('    window.setInterval(refreshLiveData')),c);
  await c.refreshLiveData();assert.equal(c.DATA.restaurants.length,1);assert.deepEqual(seenWhileLoading,[1]);   // nicht 2: finn ist deaktiviert
  enabled=true;await c.refreshLiveData();assert.equal(c.DATA.restaurants.length,2);
  enabled=false;failed=true;await c.refreshLiveData();assert.equal(c.DATA.restaurants.length,2);
});

test('manual editor preserves source details and saves explicit menu structure',async()=>{
  const html=await readFile(new URL('../../wu-lunch/admin.html',import.meta.url),'utf8');
  const values={'.dish-extra':JSON.stringify({menu_options:[{label:'Kombi',total_price:12}],energy_kcal:500}),'.dish-name':'Curry','.dish-price-input':'10.5','.dish-price-small':'','.dish-price-large':'','.dish-category':'Hauptgericht','.dish-description':'Reis','.dish-soup':'Suppe oder Salat','.dish-dessert':'Dessert','.dish-choices':'','.dish-allergens':'A, G'};
  const c={row:{querySelector:key=>({value:values[key]})}};vm.createContext(c);
  vm.runInContext(html.slice(html.indexOf('    const priceOrNull='),html.indexOf('    async function saveMenu(')),c);
  const dish=c.readDraftDish(c.row);assert.equal(dish.manual_presentation,true);assert.equal(dish.price,10.5);
  assert.equal(dish.included_starter,'Suppe oder Salat');assert.equal(dish.included_dessert,'Dessert');assert.equal(dish.energy_kcal,500);assert.equal(dish.menu_options[0].total_price,12);
});

test('editor fetches current data and offers all five weekdays even if the first restaurant is empty',async()=>{
  const html=await readFile(new URL('../../wu-lunch/admin.html',import.meta.url),'utf8');
  let selected=false,options=[];
  const c={Date,Intl,LOCALE:'en-GB',currentMenu:null,fetch:async()=>({ok:true,json:async()=>({weekStart:'2026-11-09',restaurants:[{days:{}}]})}),api:async()=>({ok:true,json:async()=>[]}),menuDate:{value:'2026-11-12',replaceChildren:(...items)=>{options=items}},document:{createElement:()=>({})},renderSelectedMenu:()=>{selected=true}};vm.createContext(c);
  vm.runInContext(html.slice(html.indexOf('    async function loadMenuEditor('),html.indexOf('    function renderSelectedMenu(')),c);
  await c.loadMenuEditor();assert.equal(options.length,5);assert.equal(options[4].value,'2026-11-13');assert.match(options[4].textContent,/Friday/);assert.equal(c.menuDate.value,'2026-11-12');assert.equal(selected,true);
});

test('admin lists Meet-to-eat sign-ups, deletes single names and notices a missing database permission',async()=>{
  const html=await readFile(new URL('../../wu-lunch/admin.html',import.meta.url),'utf8');
  const sql=await readFile(new URL('../../wu-lunch/supabase/20261117_meet_admin.sql',import.meta.url),'utf8');
  // Nur der Admin bekommt Lese- und Löschrecht; für alle anderen bleibt es bei der eigenen Zeile.
  assert.match(sql,/for select to authenticated using \(\(select private\.is_lunch_admin\(\)\)\)/);
  assert.match(sql,/for delete to authenticated using \(\(select private\.is_lunch_admin\(\)\)\)/);
  assert.doesNotMatch(sql,/\bto anon\b|for (insert|update)/);
  const rows=[{user_id:'u-1',meeting_date:'2026-11-18',first_name:'Lena',created_at:'x'},{user_id:'u-2',meeting_date:'2026-11-18',first_name:'Jonas',created_at:'y'}];
  const start=({visible=2,deleted=1,ok=true}={})=>{
    const requests=[];let rendered=0;
    const c={Intl,Date,meetRows:[],renderMeetRegistrations:()=>{rendered++},api:async(path,options={})=>{requests.push({path,options});
      if(options.method==='DELETE')return {ok,json:async()=>rows.slice(0,deleted)};
      return {ok,json:async()=>path.includes('meet_preview_participants')?Array.from({length:visible},()=>({meeting_date:'2026-11-18'})):rows.slice()};}};
    vm.createContext(c);vm.runInContext(html.slice(html.indexOf('    let meetRows=[];'),html.indexOf('    function renderMeetRegistrations(')),c);
    return {c,requests,get rendered(){return rendered}};
  };
  const fine=start();
  assert.equal(await fine.c.loadMeetRegistrations(),2);assert.equal(fine.rendered,1);
  assert.match(fine.requests[0].path,/^\/rest\/v1\/meet_preview_registrations\?select=user_id,meeting_date,first_name,created_at&meeting_date=gte\.\d{4}-\d\d-\d\d&order=meeting_date\.asc,created_at\.asc$/);
  // Löschen trifft genau eine Zeile (Person + Termin) und zählt nach, ob wirklich gelöscht wurde.
  const listed=vm.runInContext('meetRows',fine.c);
  await fine.c.deleteMeetRegistration(listed[0]);
  const call=fine.requests.at(-1);assert.equal(call.options.method,'DELETE');assert.equal(call.path,'/rest/v1/meet_preview_registrations?user_id=eq.u-1&meeting_date=eq.2026-11-18');assert.equal(call.options.headers.Prefer,'return=representation');
  assert.deepEqual(vm.runInContext('meetRows.map(row=>row.first_name)',fine.c),['Jonas']);
  // Ohne Freigabe löscht die Datenbank still nichts: das muss als Fehler erscheinen, die Liste bleibt.
  const blocked=start({deleted:0});await blocked.c.loadMeetRegistrations();
  await assert.rejects(()=>blocked.c.deleteMeetRegistration(vm.runInContext('meetRows',blocked.c)[0]),/nicht gelöscht/);
  assert.equal(vm.runInContext('meetRows.length',blocked.c),2);
  // Öffentlich mehr Namen sichtbar als im Admin: die Freigabe fehlt – klarer Hinweis statt scheinbar leerer Liste.
  await assert.rejects(()=>start({visible:5}).c.loadMeetRegistrations(),/20261117_meet_admin\.sql/);
  await assert.rejects(()=>start({ok:false}).c.loadMeetRegistrations(),/nicht geladen/);
  // Der neue Bereich darf den übrigen Admin beim Anmelden nicht blockieren.
  assert.match(html,/void refreshMeetRegistrations\(\);/);assert.match(html,/<h2>Meet to eat: Anmeldungen<\/h2>/);
});
