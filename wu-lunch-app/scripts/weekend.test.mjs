import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
const calendar=source.slice(source.indexOf('function displayWeekStart('),source.indexOf('const currentRestaurant='));

test('Vienna weekend switches at Saturday midnight to the coming Monday, independent of source data',()=>{
  const c={Intl,Date,data:{weekStart:'2026-11-09'}};vm.createContext(c);vm.runInContext(calendar,c);
  for(const [at,monday] of [['2026-11-13T22:59:00Z','2026-11-09'],['2026-11-13T23:00:00Z','2026-11-16'],['2026-11-15T12:00:00Z','2026-11-16'],['2026-11-16T12:00:00Z','2026-11-16'],['2027-01-02T12:00:00Z','2027-01-04']])assert.equal(c.displayWeekStart(new Date(at)),monday);
});
test('unpublished next week never reuses old dishes; explicit future manual entries remain visible',()=>{
  class Saturday extends Date {constructor(...args){super(...(args.length?args:['2026-11-14T10:00:00Z']));}}
  const c={Intl,Date:Saturday,data:{weekStart:'2026-11-09'},restaurantDisplayRules:(_id,rows)=>rows,dishRank:()=>0};vm.createContext(c);vm.runInContext(calendar,c);vm.runInContext(source.slice(source.indexOf('function dishes('),source.indexOf('function contactEmail(')),c);
  const r={id:'campus',days:{'2026-11-09':[{name:'Altes Gericht',price:10}]}};
  assert.equal(c.dishes(r,'2026-11-16').length,0);
  r.days['2026-11-16']=[{name:'Manuell freigegeben',price:12,manual_presentation:true}];r.manualDays={'2026-11-16':true};assert.equal(c.dishes(r,'2026-11-16')[0].name,'Manuell freigegeben');
  assert.equal(c.dishes({id:'omakueche',days:{}},'2026-11-16')[0].price,10.9);
});
test('app text categories cover interface labels and exclude dishes, cuisine types and Admin tools',async()=>{
  const code=await readFile(new URL('../../wu-lunch/i18n.js',import.meta.url),'utf8'),c={console};c.window=c;vm.runInNewContext(code,c);const rows=c.WULunchI18n.appCatalog();
  assert.equal(rows.find(row=>row.text_key==='Weiter').category,'navigation');assert.equal(rows.find(row=>row.text_key==='X €').category,'status');
  for(const key of ['Tagessuppe','Suppe oder Salat','International','Menüs manuell bearbeiten'])assert.ok(!rows.some(row=>row.text_key===key));
  const web=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8'),css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');assert.equal(web.match(/\.map-letter-pin\{[^}]+\}/)[0],css.match(/\.map-letter-pin\{[^}]+\}/)[0]);
});
