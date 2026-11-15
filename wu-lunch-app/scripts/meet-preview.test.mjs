import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('preview requires verified email before a registration and supports cancellation', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const handlers={}; let session=null, own=[], otpCalls=0, verifyCalls=0, inserts=0;
  const store=new Map();
  const client={auth:{getSession:async()=>({data:{session},error:null}),signInWithOtp:async()=>{otpCalls++;return {error:null}},verifyOtp:async()=>{verifyCalls++;session={user:{id:'test-user'}};return {data:{session},error:null}}},from(table){return {
    select(){return {in:async()=>({data:table==='meet_preview_participants'?own:own,error:null})}},
    insert:async row=>{inserts++;own=[row];return {error:null}},
    delete(){return {eq(){return {eq:async()=>{own=[];return {error:null}}}}}}
  }}};
  const inputs={'meet-first-name':{value:'Anna'},'meet-email':{value:'anna@example.com'},'meet-code':{value:'123456'}};
  const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:id=>inputs[id]},
    localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
    setInterval(){},console,Intl,Date,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d};
  vm.createContext(context);vm.runInContext(source,context);
  const click=async (action,slot)=>{handlers.click({target:{closest:()=>({dataset:{action,slot}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  await click('meet-preview');
  assert.equal(context.meetSlot,0);assert.match(context.renderMeet(),/Gemeinsam essen/);assert.doesNotMatch(context.renderMeet(),/Bereits angemeldet|Noch niemand angemeldet/);
  assert.match(context.renderMeet(),/WU-Studenten Gruppe/);assert.doesNotMatch(context.renderMeet(),/Testvorschau|Testteilnehmer|Testtermin/);
  const touch=(event,x,y)=>handlers[event]({touches:[{}],target:{closest:()=>true},changedTouches:[{screenX:x,screenY:y}],preventDefault(){}});
  touch('touchstart',250,100);touch('touchend',100,105);assert.equal(context.meetSlot,1);
  touch('touchstart',250,100);touch('touchend',245,260);assert.equal(context.meetSlot,1);
  touch('touchstart',100,100);touch('touchend',250,105);assert.equal(context.meetSlot,0);
  await click('meet-select','2');assert.equal(context.meetSlot,2);await click('meet-select','0');
  await click('meet-show-form');
  assert.match(context.renderMeet(),/Prüfung der WU-Zugehörigkeit erfolgt derzeit nicht/);
  assert.equal(inserts,0);await click('meet-send-code');assert.equal(otpCalls,1);assert.equal(inserts,0);
  await click('meet-verify');assert.equal(verifyCalls,1);assert.equal(inserts,1);assert.equal(own[0].first_name,'Anna');
  assert.match(context.renderMeet(),/Bereits angemeldet/);assert.match(context.renderMeet(),/Anna/);await click('meet-leave');assert.equal(own.length,0);
  assert.doesNotMatch(context.renderMeet(),/Bereits angemeldet|Noch niemand angemeldet/);
  await click('meet-back');assert.equal(context.meetPreviewOpen,false);
});

test('Vienna dates stay visible until 23:00 and registration closes after 12:05', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const viennaClock'),source.indexOf('  const date ='));
  let current='2026-11-15T23:01:00Z';
  class Clock extends Date { constructor(...args){super(...(args.length?args:[current]));} }
  const context={Intl,Date:Clock};vm.createContext(context);vm.runInContext(helper,context);
  const days=()=>Array.from(vm.runInContext('slotDates()',context));
  const open=(date)=>vm.runInContext(`registrationOpen('${date}')`,context);
  assert.deepEqual(days(),['2026-11-16','2026-11-18','2026-11-23']);assert.equal(open('2026-11-16'),true);
  current='2026-11-16T11:05:59Z';assert.equal(open('2026-11-16'),true);assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T11:06:00Z';assert.equal(open('2026-11-16'),false);assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T21:59:00Z';assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T22:00:00Z';assert.deepEqual(days(),['2026-11-18','2026-11-23','2026-11-25']);
  current='2026-11-18T22:00:00Z';assert.deepEqual(days(),['2026-11-23','2026-11-25','2026-11-30']);
  current='2027-03-29T10:05:59Z';assert.equal(open('2027-03-29'),true);
  current='2027-03-29T10:06:00Z';assert.equal(open('2027-03-29'),false);
});

