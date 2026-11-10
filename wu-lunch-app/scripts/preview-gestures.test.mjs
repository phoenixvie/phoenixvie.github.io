import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('Mensa retains only stations 1+2, 3+4 and 8 with separate soup lines',async()=>{
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('function mensaStations('),source.indexOf('function dishes('));
  const context={Intl};vm.createContext(context);vm.runInContext(helper,context);
  const rows=['Global & Grill','Bowls & Co','Pasta & Co','Meaty','Powered by plants / Veggie','Pizza & Co','Weekly Special'].map((category,i)=>({category,name:'Originalgericht '+i,price:i+5,description:'Quellenbeilage'}));
  rows.push({category:'Tagessuppe',name:'Gemüsesuppe',price:null});
  const result=context.mensaStations(rows);
  assert.equal(result.map(i=>i.category).join('|'),'Ausgabe 1+2|Ausgabe 3+4|Ausgabe 8');
  assert.ok(!result.some(item=>item.category==='Tagessuppe'));
  assert.match(result[0].name,/Gemüsesuppe/);assert.match(result[1].name,/Gemüsesuppe/);
  assert.match(result[0].name,/Gemüsesuppe\nOriginalgericht/);
  assert.match(result[0].name,/Originalgericht 4/);assert.match(result[0].name,/Quellenbeilage/);
  assert.equal(context.mensaStations([]).length,0);
  const web=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');
  assert.ok(web.includes(helper.trim()));
});

test('restaurant rules retain verified totals, remove commentary and merge Topf combos',async()=>{
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('function restaurantDisplayRules('),source.indexOf('function mensaStations('));
  const c={};vm.createContext(c);vm.runInContext(helper,c);
  const main={name:'Pasta mit grünem Salat',category:'Hauptgericht',price:10,description:'Preis bestätigt',menu_options:[{label:'Hauptgericht mit Suppe',total_price:11}]};
  const finn=c.restaurantDisplayRules('finn',[main,{name:'Tagessuppe oder Salat',category:'Suppe/Salat',price:3.5}]);
  assert.equal(finn.length,1);assert.equal(finn[0].price,11);assert.equal(finn[0].description,'Mit Tagessuppe und grünem Salat');assert.equal(finn[0].menu_options.length,0);
  assert.equal(main.price,10); // presentation never rewrites source data
  assert.equal(c.restaurantDisplayRules('lia',[main])[0].description,'');
  assert.equal(finn[0].name,'Pasta');
  assert.equal(c.restaurantDisplayRules('lia',[main])[0].price,10);
  assert.deepEqual(Array.from(c.restaurantDisplayRules('lia',[main])[0].included_choices),[]);
  assert.equal(c.restaurantDisplayRules('finn',[{...main,name:'Curry mit Reis'}])[0].description,'Mit Tagessuppe');
  assert.equal(c.restaurantDisplayRules('karmafood',[main])[0].description,'');
  assert.equal(c.restaurantDisplayRules('baschly',[main])[0].description,main.description);
  const topf=c.restaurantDisplayRules('topfdeckel',[
    {name:'Paprika Suppe',category:'Suppe',price:3.9},
    {name:'Light Lunch Kombi: klein',category:'Menükombo',price:9.5},
    {name:'Big Lunch Kombi: groß',category:'Menükombo',price:13.9},
    {name:'Haussalat',category:'Salat',price:3.9},{name:'Dessert des Tages',category:'Dessert',price:2.9},main]);
  assert.equal(topf.length,3);assert.equal(topf[0].priceLabel,' ');
  assert.equal(topf[1].price_small,9.5);assert.equal(topf[1].price_large,13.9);
  assert.equal(topf[2].description,'(klein / groß)');
  assert.equal(c.restaurantDisplayRules('omakueche',[{name:'All-you-can-eat-Buffet (Erwachsene)',description:'to go'}])[0].name,'All-you-can-eat-Buffet');
  assert.equal(c.restaurantDisplayRules('gruenehuette',[{name:'Suppen zur Auswahl: Frittatensuppe',category:'Suppe',price:2}])[0].description,'Optional zum Tagesteller');
  assert.equal(c.restaurantDisplayRules('gruenehuette',[{name:'Frittatensuppe',category:'Suppe'}])[0].detailInline,true);
  const web=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');assert.ok(web.includes(helper.trim()));
  assert.match(web,/dish-detail\{white-space:pre-line\}/);
});

test('Mensa removes repeated identical burger rows and never displays allergen codes',async()=>{
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('function mensaStations('),source.indexOf('function dishes('));
  const c={Intl};vm.createContext(c);vm.runInContext(helper,c);
  const burger={name:"Mensa Burger mit Pommes – Planted 'Crispy Chicken style'",category:'Global & Grill',price:9.8,allergens:['A']};
  const rows=c.mensaStations([burger,{...burger}, {...burger,name:'Mensa Burger mit Pommes – Beef',allergens:['A','C','G']}]);
  assert.equal(rows.length,1);
  assert.equal(rows[0].name.match(/Planted/g).length,1);assert.match(rows[0].name,/Beef/);
  assert.equal(rows[0].name.match(/Mensa Burger/g).length,1);
  assert.ok(!source.includes('Allergene:'));
});

test('white menu pane accepts horizontal swipes and ignores vertical or cancelled gestures', async()=>{
  const actions=new Map(), events=new Map();
  const app={innerHTML:'',addEventListener:(name,fn)=>actions.set(name,fn)};
  const context={URL,URLSearchParams,Intl,Date,console,navigator:{},location:{hostname:'localhost',search:''},
    document:{getElementById:()=>app,addEventListener:(name,fn)=>events.set(name,fn)},setInterval:()=>0,setTimeout:()=>0,
    fetch:async url=>({ok:true,json:async()=>url.includes('rest/v1')?[]:url.includes('restaurant-contact')?{restaurants:{}}:{weekStart:'2026-11-09',restaurants:[{id:'lia',name:'Lia',url:'https://lia.coffee/',days:{}}]}})};
  context.window=context;
  vm.runInNewContext(await readFile(new URL('../preview/app.js',import.meta.url),'utf8'),context);
  events.get('DOMContentLoaded')?.();
  for(let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve));
  const click=dataset=>actions.get('click')({target:{closest:selector=>selector==='a[href]'?null:{dataset}}});
  await click({restaurant:'lia'}); await click({day:'0'});
  const whitePane={closest:selector=>selector==='#menu-screen'?{}:null};
  const start=()=>actions.get('touchstart')({target:whitePane,touches:[{}],changedTouches:[{screenX:300,screenY:400}]});
  const end=(x,y)=>actions.get('touchend')({target:whitePane,changedTouches:[{screenX:x,screenY:y}],preventDefault:()=>{}});
  start();end(100,405);
  assert.match(app.innerHTML,/weekday active" data-day="1"/);
  start();end(100,700);
  assert.match(app.innerHTML,/weekday active" data-day="1"/);
  start();actions.get('touchcancel')();end(100,400);
  assert.match(app.innerHTML,/weekday active" data-day="1"/);
  start();end(400,400);
  assert.match(app.innerHTML,/weekday active" data-day="0"/);
});
