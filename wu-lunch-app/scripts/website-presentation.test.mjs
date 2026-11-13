import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('Topf shows soup then a single combination then main dishes with separate size prices',async()=>{
  const web=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');
  const c={Intl,dishesForRestaurant:()=>[
    {name:'Curry',category:'Hauptgericht',price:7.5,price_small:7.5,price_large:11.9},
    {name:'Big Lunch',category:'Menükombo',price:13.9},
    {name:'Light Lunch',category:'Menükombo',price:9.5},
    {name:'Karfiolsuppe',category:'Suppe',price:3.9},
  ]};vm.createContext(c);
  vm.runInContext(web.slice(web.indexOf('    function includedDetail('),web.indexOf('    function escapeHtml(')),c);
  const rows=c.visibleDishes({id:'topfdeckel'});
  assert.equal(rows.length,3);assert.equal(rows[0].name,'Karfiolsuppe');
  assert.match(rows[1].name,/Hauptgericht.*kleine Suppe/);assert.equal(rows[2].name,'Curry');
  assert.equal(rows[0].priceDisplay,' ');
  assert.equal(rows[1].priceDisplay,'9,50 € / 13,90 €');
  assert.equal(rows[2].priceDisplay,'7,50 € / 11,90 €');
});

test('website distinguishes included starters, final dessert, optional extras and side dishes',async()=>{
  const web=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');
  const helper=web.slice(web.indexOf('    function renderMenuDishText('),web.indexOf('    function renderRow('));
  const c={escapeHtml:s=>String(s).replaceAll('<','&lt;')};vm.createContext(c);vm.runInContext(helper,c);
  const render=(id,name,detail,detailInline=false)=>c.renderMenuDishText(id,{name,detail,detailInline});
  assert.equal(render('baschly','Curry','Mit Tagessuppe oder kleinem Salat'),'<span class="dish-detail">Tagessuppe oder kleiner Salat</span>Curry');
  assert.equal(render('finn','Pasta','Mit Tagessuppe und grünem Salat'),'<span class="dish-detail">Tagessuppe und grüner Salat</span>Pasta');
  assert.equal(render('campus','Gnocchi','Suppe oder Salat · Dessert'),'<span class="dish-detail">Suppe oder Salat</span>Gnocchi<span class="dish-detail">Dessert</span>');
  assert.equal(render('lia','Pasta',''),'Pasta');
  assert.equal(render('karmafood','Lasagne mit Salat',''),'Lasagne mit Salat');
  assert.equal(render('gruenehuette','Frittatensuppe','Optional zum Tagesteller',true),'Frittatensuppe<span class="dish-detail inline"> Optional zum Tagesteller</span>');
  assert.equal(render('mensa','Ausgabe 1+2','Suppe\nTortillas'),'<span class="mensa-station">Ausgabe 1+2</span><span class="dish-detail">Suppe\nTortillas</span>');
  assert.equal(render('baschly','Kürbisrisotee: A, G',''),'Kürbisrisotee');
  assert.equal(render('baschly','Curry Allergene: Glutenfrei, laktosefrei',''),'Curry');
  assert.equal(render('losteria','Gericht','Mit Suppe'),'Gericht<span class="dish-detail">Mit Suppe</span>');
  assert.ok(render('glashaus','<Gericht>','Mit Suppe oder Salat').includes('&lt;Gericht>'));
  assert.ok(render('baschly','Curry','Mit Reis').startsWith('Curry'));
});
