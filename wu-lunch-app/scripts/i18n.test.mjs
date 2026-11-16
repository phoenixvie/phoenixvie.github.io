import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {validateTranslations,translateBatch,translateResilient,fetchWithRetry} from '../../wu-lunch/scripts/translate_menus.mjs';

const script=await readFile(new URL('../../wu-lunch/i18n.js',import.meta.url),'utf8');
test('translation review feedback is repaired and rechecked; persistent rejection never publishes',async()=>{
  let calls=0;
  const items=await translateBatch(['Überbackener Käse'],async(instructions,input)=>{
    calls++;
    if(calls===1)return {items:[{id:0,english:'Cheese'}]};
    if(calls===2)return {faithful:false,problems:['Missing gratinated preparation']};
    if(calls===3){assert.deepEqual(input.reviewNotes,['Missing gratinated preparation']);return {items:[{id:0,english:'Gratinated cheese'}]};}
    return {faithful:true,problems:[]};
  });assert.equal(calls,4);assert.equal(items[0].english,'Gratinated cheese');
  let requests=0;
  await assert.rejects(()=>translateBatch(['Käse'],async()=>++requests%2?{items:[{id:0,english:'Cheese'}]}:{faithful:false,problems:['Rejected']}),/after 3 attempts/);
  assert.equal(requests,6);
});
function context(language,cache=[],systemLanguage){const c={WU_SYSTEM_LANGUAGE:systemLanguage,navigator:{language},console,localStorage:{getItem:()=>JSON.stringify(cache),setItem(){}},fetch:async()=>({ok:true,json:async()=>[]})};c.window=c;vm.createContext(c);vm.runInContext(script,c);return c;}
test('German primary locales use German; every other primary locale uses English',()=>{
  for(const language of ['de','de-AT','de-DE','de-CH']){const c=context(language);assert.equal(c.WULunchI18n.language,'de');assert.equal(c.WULunchI18n.text('Zurück'),'Zurück');}
  for(const language of ['en-GB','en-US','fr-FR','es','it','nl-NL']){const c=context(language);assert.equal(c.WULunchI18n.language,'en');assert.equal(c.WULunchI18n.text('Zurück'),'Back');}
});
test('native system locale takes priority over WebView language',()=>{assert.equal(context('en-US',[],'de-AT').WULunchI18n.language,'de');assert.equal(context('de-DE',[],'en-US').WULunchI18n.language,'en');});

test('admin UI texts update German and English without changing source keys or menu translations',async()=>{
  const c=context('de-AT');c.Event=Event;c.dispatchEvent=()=>{};
  const node={textContent:'Menü',parentElement:{closest:()=>null}},body={querySelectorAll:()=>[]};
  c.document={body,documentElement:{setAttribute(){}},createTreeWalker:()=>{let seen=false;return {nextNode:()=>seen?null:(seen=true,node)}}};
  c.fetch=async()=>({ok:true,json:async()=>[{text_key:'Menü',de_text:'Speisen',en_text:'Dishes',updated_at:'2026-11-13T18:00:00Z'}]});
  await c.WULunchI18n.refreshUi();assert.equal(node.textContent,'Speisen');assert.equal(c.WULunchI18n.catalog().find(row=>row.text_key==='Menü').default_de,'Menü');
  c.WULunchI18n.setLanguage('en');assert.equal(node.textContent,'Dishes');assert.equal(c.WULunchI18n.english('Unbekanntes Hauptgericht'),null);
  c.WULunchI18n.setLanguage('de');assert.equal(node.textContent,'Speisen');
});

test('explicit manual menu/profile translations retain priority over shared default labels',async()=>{
  const c=context('en',[['International','Global cuisine','manual']]);
  c.fetch=async()=>({ok:true,json:async()=>[{text_key:'International',de_text:'International',en_text:'International',updated_at:'2026-11-13T18:00:00Z'}]});
  await c.WULunchI18n.refreshUi();assert.equal(c.WULunchI18n.english('International'),'Global cuisine');
});

test('language toggle restores German text and accessibility labels and remembers the explicit choice',()=>{
  const saved=new Map(),events=[],messages=[];
  const node={textContent:'Zurück',parentElement:{closest:()=>null}};
  const child={label:'Zurück',getAttribute(name){return name==='aria-label'?this.label:null},setAttribute(name,value){this.label=value}};
  const body={querySelectorAll:()=>[child]};
  const c={Event,navigator:{language:'de-AT'},localStorage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)},console,fetch:async()=>({ok:true,json:async()=>[]}),dispatchEvent:event=>events.push(event.type),ReactNativeWebView:{postMessage:value=>messages.push(JSON.parse(value))},document:{title:'WU Food',documentElement:{setAttribute(){}},body,addEventListener(){},createTreeWalker:()=>{let seen=false;return {nextNode:()=>seen?null:(seen=true,node)}}}};
  c.window=c;vm.createContext(c);vm.runInContext(script,c);
  c.WULunchI18n.toggleLanguage();assert.equal(c.WULunchI18n.language,'en');assert.equal(c.WULunchI18n.locale,'en-GB');assert.equal(node.textContent,'Back');assert.equal(child.label,'Back');assert.equal(saved.get('wu-lunch-language'),'en');assert.equal(messages.at(-1).language,'en');
  const reboot={navigator:{language:'de-DE'},localStorage:c.localStorage,console};reboot.window=reboot;vm.runInNewContext(script,reboot);assert.equal(reboot.WULunchI18n.language,'en');
  c.WULunchI18n.toggleLanguage();assert.equal(node.textContent,'Zurück');assert.equal(child.label,'Zurück');assert.equal(saved.get('wu-lunch-language'),'de');assert.deepEqual(events,['wu-language-change','wu-language-change']);
});

test('empty announcements stay hidden in English; actual untranslated announcements remain explicit',async()=>{
  const html=await readFile(new URL('../../wu-lunch/index.html',import.meta.url),'utf8');
  const announcementElement={style:{},innerHTML:''},announcement={desktop_message:'',mobile_message:''};
  const c={LANG:'en',announcementElement,announcement,announcementHtml:s=>s,window:{matchMedia:()=>({matches:false}),WULunchI18n:{text:()=>null}}};
  vm.createContext(c);vm.runInContext(html.slice(html.indexOf('    function renderAnnouncement(){'),html.indexOf('    async function loadAnnouncement(){')),c);
  c.renderAnnouncement();assert.equal(announcementElement.style.display,'none');assert.equal(announcementElement.innerHTML,'');
  announcement.desktop_message='Neue Nachricht';c.renderAnnouncement();assert.equal(announcementElement.style.display,'block');assert.equal(announcementElement.innerHTML,'Announcement translation pending');
});
test('exact German source binding prevents stale menus and manual component translations compose correctly',()=>{
  const c=context('en',[['Suppe','Soup'],['Curry mit Reis','Curry with rice'],['Dessert','Dessert']]);
  assert.equal(c.WULunchI18n.english('Curry mit Reis'),'Curry with rice');
  assert.equal(c.WULunchI18n.english('Curry mit Reis und Huhn'),null);
  assert.equal(c.WULunchI18n.english('Suppe\nCurry mit Reis\nDessert'),'Soup\nCurry with rice\nDessert');
});
test('translation validation rejects missing dishes, duplicate identities and changed numbers/links',()=>{
  assert.deepEqual(validateTranslations(['Menü 2'],[{id:0,english:'Menu 2'}]),[{id:0,english:'Menu 2'}]);
  assert.throws(()=>validateTranslations(['Menü 2'],[{id:0,english:'Menu 3'}]));
  assert.throws(()=>validateTranslations(['Menü 2'],[]));
  assert.throws(()=>validateTranslations(['A','B'],[{id:0,english:'A'},{id:0,english:'B'}]));
  assert.throws(()=>validateTranslations(['[Menü](https://example.test/menu)'],[{id:0,english:'[Menu](https://evil.test/menu)'}]));
});
test('missing English text shows a pending message and becomes English after database refresh',async()=>{
  const c=context('en');const parent={closest:s=>s.includes('.dish-text')?{}:null};const node={textContent:'Neues Gericht',parentElement:parent};
  const body={querySelectorAll:()=>[]};c.document={body,createTreeWalker:()=>{let done=false;return {nextNode:()=>done?null:(done=true,node)}}};
  c.WULunchI18n.apply(body);assert.equal(node.textContent,'English translation pending');
  c.fetch=async()=>({ok:true,json:async()=>[{source_text:'Neues Gericht',english_text:'New dish',updated_at:'2026-11-13T15:00:00Z'}]});
  await c.WULunchI18n.refresh();assert.equal(node.textContent,'New dish');
});

test('English admin save routes text pairs to translations instead of overwriting the German menu',async()=>{
  const html=await readFile(new URL('../../wu-lunch/admin.html',import.meta.url),'utf8');
  const pairs=[],fields=[{dataset:{german:'Suppe'},value:'Soup'},{dataset:{german:'Gemüsecurry'},value:'Vegetable curry'}];
  const button={disabled:false},notice={};let writes=0;
  const c={editLanguage:'en',document:{getElementById:id=>id==='saveMenuButton'?button:notice},menuEditor:{querySelectorAll:()=>fields,dataset:{dirty:'true'}},saveEnglishPairs:async rows=>pairs.push(...rows),text(){},api:()=>{writes++;throw new Error('German data must not change');}};
  vm.createContext(c);vm.runInContext(html.slice(html.indexOf('    async function saveMenu('),html.indexOf('    async function resetMenu(')),c);await c.saveMenu();
  assert.equal(writes,0);assert.equal(pairs[0][0],'Suppe');assert.equal(pairs[0][1],'Soup');assert.equal(c.menuEditor.dataset.dirty,'false');assert.equal(button.disabled,false);
});

test('admin app-text save updates only the chosen language and validates contact addresses and placeholders',async()=>{
  const html=await readFile(new URL('../../wu-lunch/admin.html',import.meta.url),'utf8'),requests=[];
  const c={editLanguage:'en',uiTextRows:new Map([['Menü',{text_key:'Menü',de_text:'Menü',en_text:'Menu'}]]),window:{WULunchI18n:{catalog:()=>[{text_key:'Menü',default_de:'Menü',default_en:'Menu'}],refreshUi(){}}},api:async(path,options)=>{requests.push({path,options});return {ok:true,json:async()=>[{text_key:'Menü',de_text:'Menü',en_text:'Meals'}]}}};
  vm.createContext(c);vm.runInContext(html.slice(html.indexOf('    async function saveUiText('),html.indexOf('    function renderUiTexts(')),c);
  await c.saveUiText('Menü','Meals');assert.equal(requests[0].options.method,'PATCH');assert.deepEqual(JSON.parse(requests[0].options.body),{en_text:'Meals'});
  await assert.rejects(()=>c.saveUiText('Webseite von {restaurant}','Website'),/Platzhalter/);
  await assert.rejects(()=>c.saveUiText('Kontakt-E-Mail','bad address'),/E-Mail/);assert.equal(requests.length,1);
});
test('one unreviewable source text no longer blocks every other English translation',async()=>{
  // Regression 16.11.2026: "Kirche Erbsen" (Tippfehler in der Originalkarte) ließ den ganzen Stapel scheitern.
  const batch=['Tagessuppe','Kirche Erbsen Curry','Apfelstrudel','Gemischter Salat','Reis'];
  const sizes=[];
  const translate=async part=>{
    sizes.push(part.length);
    if(part.includes('Kirche Erbsen Curry'))throw new Error('Translation batch failed review after 3 attempts: misspelling');
    return part.map((german,id)=>({id,english:'EN '+german}));
  };
  const result=await translateResilient(batch,translate);
  assert.deepEqual(result.done.map(x=>x.german).sort(),['Apfelstrudel','Gemischter Salat','Reis','Tagessuppe']);
  assert.ok(result.done.every(x=>x.english==='EN '+x.german));
  assert.deepEqual(result.failed.map(x=>x.german),['Kirche Erbsen Curry']);
  assert.match(result.failed[0].reason,/misspelling/);
  assert.equal(sizes[0],5);
  // Ein fehlerfreier Stapel kostet weiterhin genau einen Durchgang.
  sizes.length=0;
  assert.equal((await translateResilient(['A','B'],translate)).failed.length,0);
  assert.deepEqual(sizes,[2]);
  // Technische Fehler werden nicht durch Teilen vervielfacht, sondern beim nächsten Lauf wiederholt.
  await assert.rejects(()=>translateResilient(batch,async()=>{throw new Error('Translation model HTTP 401');}),/HTTP 401/);
});
test('translation model calls survive a short outage',async()=>{
  const replies=[{status:503,ok:false},{status:200,ok:true}],waits=[];
  const response=await fetchWithRetry('https://example.test',{},{send:async()=>replies.shift(),sleep:async ms=>waits.push(ms)});
  assert.equal(response.status,200);assert.deepEqual(waits,[4000]);
  const denied=await fetchWithRetry('https://example.test',{},{send:async()=>({status:401,ok:false}),sleep:async ms=>waits.push(ms)});
  assert.equal(denied.status,401);assert.equal(waits.length,1);
  let sent=0;
  const down=await fetchWithRetry('https://example.test',{},{send:async()=>{sent++;return {status:529,ok:false};},sleep:async()=>{}});
  assert.equal(down.status,529);assert.equal(sent,3);
});
