import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('preview requires verified email before a registration and supports cancellation', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  let handler, session=null, own=[], otpCalls=0, verifyCalls=0, inserts=0;
  const store=new Map();
  const client={auth:{getSession:async()=>({data:{session},error:null}),signInWithOtp:async()=>{otpCalls++;return {error:null}},verifyOtp:async()=>{verifyCalls++;session={user:{id:'test-user'}};return {data:{session},error:null}}},from(table){return {
    select(){return {in:async()=>({data:table==='meet_preview_participants'?own:own,error:null})}},
    insert:async row=>{inserts++;own=[row];return {error:null}},
    delete(){return {eq(){return {eq:async()=>{own=[];return {error:null}}}}}}
  }}};
  const inputs={'meet-first-name':{value:'Anna'},'meet-email':{value:'anna@example.com'},'meet-code':{value:'123456'}};
  const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',
    app:{addEventListener:(_event,fn)=>{handler=fn}},document:{getElementById:id=>inputs[id]},
    localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
    setInterval(){},console,Intl,Date,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d};
  vm.createContext(context);vm.runInContext(source,context);
  const click=async (action,slot)=>{handler({target:{closest:()=>({dataset:{action,slot}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  await click('meet-preview');await click('meet-slot','0');await click('meet-show-form');
  assert.equal(inserts,0);await click('meet-send-code');assert.equal(otpCalls,1);assert.equal(inserts,0);
  await click('meet-verify');assert.equal(verifyCalls,1);assert.equal(inserts,1);assert.equal(own[0].first_name,'Anna');
  assert.match(context.renderMeet(),/Anna/);await click('meet-leave');assert.equal(own.length,0);
});

