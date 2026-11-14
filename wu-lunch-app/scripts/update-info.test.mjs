import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const policy=JSON.parse(await readFile(new URL('../../wu-lunch/update-policy.json',import.meta.url)));
const source=await readFile(new URL('../../wu-lunch/update-info.js',import.meta.url),'utf8'),context={Intl,Date};vm.runInNewContext(source,context);
test('original third-party pages remain downloadable from GitHub and are excluded from the app/Admin site build',async()=>{
  const configuration=await readFile(new URL('../../_config.yml',import.meta.url),'utf8');
  assert.ok(JSON.parse(configuration.match(/^exclude:\s*(\[.*\])/m)[1]).includes('wu-lunch/source-archive'));
});
test('next displayed checks follow Vienna windows in winter, summer and after a Saturday final slot',()=>{
  const next=(at,task='menus')=>context.WULunchUpdateInfo.nextRun(policy,task,new Date(at))?.toISOString();
  assert.equal(next('2026-11-14T17:16:00Z'),'2026-11-16T05:15:00.000Z');
  assert.equal(next('2027-07-05T03:00:00Z'),'2027-07-05T04:15:00.000Z');
  assert.equal(next('2026-11-16T06:16:00Z','topf_browser'),'2026-11-16T10:15:00.000Z');
  assert.equal(next('2026-12-04T06:00:00Z','observation'),undefined);
});
test('display uses actual successful fetches across import, observation and PDF snapshot; never a planned or failed fetch',async()=>{
  const elements={nextUpdate:{},lastImport:{}};
  const fixtures={'update-policy.json':policy,'data/update-status.json':{last_source_fetch:'2026-11-14T10:00:00Z',source_checks:{mensa:{last_fetched:'2026-11-14T10:00:00Z'}}},'status.json':{sources:{mensa:{state:'ok'}}},'data/publication-observations.json':{sources:{mensa:{observations:[{at:'2026-11-14T11:50:00+01:00',sha256:'original'},{at:'2026-11-14T13:00:00+01:00',error:'failed'}]}}},'ai-pilot/source/mensa-latest.json':{http_status:200,fetched_at:'2026-11-14T11:20:00+01:00'}};
  const c={Intl,Date,document:{getElementById:id=>elements[id],addEventListener(){}},addEventListener(){},fetch:async path=>({ok:true,json:async()=>fixtures[path.split('?')[0]]})};vm.runInNewContext(source,c);
  await c.WULunchUpdateInfo.refresh();assert.match(elements.lastImport.textContent,/11:50/);assert.ok(!elements.lastImport.textContent.includes('13:00'));assert.ok(!elements.lastImport.textContent.includes('geändert'));
});
