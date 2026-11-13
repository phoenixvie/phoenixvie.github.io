// Collect the final German presentation, plus profile/announcement text. This
// uses the same restaurant rules as the app, without executing browser/network UI.
const fs=require('fs'),vm=require('vm');
const [menu,profiles,manual,contact,announcements]=JSON.parse(fs.readFileSync(0,'utf8'));
const source=fs.readFileSync('wu-lunch-app/preview/app.js','utf8');
const c={URL,URLSearchParams,Intl,Date,console,navigator:{language:'de-AT'},location:{hostname:'phoenixvie.github.io',search:''},document:{getElementById:()=>({innerHTML:'',addEventListener(){}}),addEventListener(){}},fetch:()=>new Promise(()=>{}),setInterval(){},setTimeout(){},localStorage:{getItem:()=>null}};
c.window=c;vm.createContext(c);vm.runInContext(source+'\nrender=()=>{};',c);
c.payload=[menu,profiles.map(p=>({...p,is_enabled:true})),manual,contact];vm.runInContext('applyPayload(...payload)',c);
const texts=new Set();const add=v=>{if(typeof v==='string'&&v.trim()&&!/^https?:/i.test(v)){texts.add(v.trim());if(v.includes('\n'))for(const line of v.split('\n'))if(line.trim())texts.add(line.trim());}};
const visit=d=>{for(const field of ['name','description','included_starter','included_soup','included_dessert'])add(d[field]);add(d.name?.replace(/\s+Allergene:\s*.*$/i,'').replace(/:\s*[ABCDEFGHLMNOPR](?:\s*,\s*[ABCDEFGHLMNOPR])*\s*$/,''));for(const option of d.menu_options||[])add(option.label);for(const v of d.included_choices||[])add(v);if(d.included_choices?.length)add('Mit '+d.included_choices.join(' oder '));};
for(const r of menu.restaurants){for(const day of Object.values(r.days||{}))for(const dish of day)visit(dish);for(const dish of r.seasonal||[])visit(dish);}
const dishes=vm.runInContext('data.restaurants.flatMap(r=>dates().flatMap(date=>dishes(r,date)))',c);
for(const d of dishes){visit(d);const p=c.mealPresentation(d);add(p.starter);add(p.starter.replace(/kleinem Salat/g,'kleiner Salat').replace(/grünem Salat/g,'grüner Salat'));add(p.detail);add(p.dessert);}
const website=fs.readFileSync('wu-lunch/index.html','utf8'),w={Intl,LOCALE:'de-AT',dishesForRestaurant:()=>[]};vm.createContext(w);vm.runInContext(website.slice(website.indexOf('    function includedDetail('),website.indexOf('    function escapeHtml(')),w);
for(const r of vm.runInContext('data.restaurants',c))for(const date of vm.runInContext('dates()',c)){w.dishesForRestaurant=()=>r.days?.[date]||r.seasonal||[];for(const row of w.visibleDishes(r))visit({name:row.name,description:row.detail});}
for(const p of profiles){add(p.restaurant_type);for(const value of p.opening_hours||[])add(value);}
for(const a of announcements||[]){add(a.desktop_message);add(a.mobile_message);}
process.stdout.write(JSON.stringify([...texts].sort()));
