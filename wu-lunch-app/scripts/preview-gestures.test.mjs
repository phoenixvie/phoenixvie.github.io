import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

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
  assert.match(app.innerHTML,/DIENSTAG 10\.11\./);
  start();end(100,700);
  assert.match(app.innerHTML,/DIENSTAG 10\.11\./);
  start();actions.get('touchcancel')();end(100,400);
  assert.match(app.innerHTML,/DIENSTAG 10\.11\./);
  start();end(400,400);
  assert.match(app.innerHTML,/MONTAG 09\.11\./);
});
