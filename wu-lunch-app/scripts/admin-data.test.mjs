import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('website live refresh re-enables restaurants from fresh data and keeps previous data on API failure',async()=>{
  const html=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');
  let enabled=false,failed=false;
  const c={window:{WULunchI18n:{refresh:async()=>{}}},DATA:{restaurants:[{id:'mensa'}]},Date,console,realMap:null,locationInfo:{},update(){},loadRealMap(){},fetch:async()=>({ok:true,json:async()=>({restaurants:[{id:'mensa'},{id:'finn'}]})}),loadAnnouncement:async()=>{},manualFetchSucceeded:true,profileFetchSucceeded:true,applyManualMenus:async()=>{}};
  c.applyRestaurantOverrides=async()=>{c.profileFetchSucceeded=!failed;if(!enabled)c.DATA.restaurants=c.DATA.restaurants.filter(r=>r.id!=='finn');};
  vm.createContext(c);vm.runInContext("let liveRefreshing=false,liveSignature='';"+html.slice(html.indexOf('    async function refreshLiveData('),html.indexOf('    window.setInterval(refreshLiveData')),c);
  await c.refreshLiveData();assert.equal(c.DATA.restaurants.length,1);
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
