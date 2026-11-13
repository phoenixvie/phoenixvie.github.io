function restaurantDisplayRules(id,raw){
  const rows=raw.map(item=>({...item,allergens:[],name:item.name.replace(/\s*\([ABCDEFGHLMNOPR](?:\s*[,/]\s*[ABCDEFGHLMNOPR])*\)/g,'')}));
  if(id==='campus')return rows.map(item=>({...item,description:'Suppe oder Salat · Dessert',included_choices:[],menu_options:[]}));
  if(id==='lia')return rows.map(item=>({...item,name:item.name.replace(/\s+(?:und|mit)\s+grünem\s+Salat\s*$/i,''),description:'',included_choices:[],menu_options:[]}));
  if(id==='finn')return rows.filter(item=>! /suppe|salat|soup|salad|dessert/i.test(item.category||'')).map(item=>{
    const combo=(item.menu_options||[]).find(option=>/suppe/i.test(option.label||'')&&Number.isFinite(option.total_price));
    const salad=/\s+(?:und|mit)\s+grünem\s+Salat\s*$/i.test(item.name);
    return {...item,name:item.name.replace(/\s+(?:und|mit)\s+grünem\s+Salat\s*$/i,''),price:id==='finn'?(combo?combo.total_price:null):item.price,description:'Mit Tagessuppe'+(salad?' und grünem Salat':''),included_choices:[],menu_options:[]};
  });
  if(id==='karmafood')return rows.map(item=>({...item,description:'',included_choices:[],menu_options:[]}));
  if(id==='omakueche')return rows.map(item=>({...item,name:item.name.replace(/\s*\(Erwachsene\)/gi,''),description:'',included_choices:[],menu_options:[]}));
  if(id==='gruenehuette')return rows.map(item=>/suppe|soup/i.test(item.category||'')?
    {...item,name:item.name.replace(/^Suppen zur Auswahl:\s*/i,'').replace(/\boder,\s*/gi,'oder '),description:'Optional zum Tagesteller',detailInline:true}:
    {...item,description:'',included_choices:[]});
  if(id!=='topfdeckel')return rows;
  const light=rows.find(item=>/light lunch/i.test(item.name)),big=rows.find(item=>/big lunch/i.test(item.name));
  return rows.filter(item=>! /salat|salad|dessert|nachspeise/i.test(item.category||'') && ! /haussalat|dessert des tages/i.test(item.name) && !(light&&big&&item===big)).map(item=>{
    if(item===light||item===big)return {...item,name:'Hauptgericht (klein/groß) + kleine Suppe/Salat, Getränk oder Dessert',description:'',
      price_small:light?.price??null,price_large:big?.price??null,menu_options:[]};
    if(/suppe|soup/i.test(item.category||'')||/suppe/i.test(item.name))return {...item,description:'',price:null,priceLabel:' ',menu_options:[]};
    return {...item,description:'(klein / groß)',included_choices:[],menu_options:[]};
  });
}

function mensaStations(raw){
  if(!raw.length)return [];
  const seen=new Set();
  raw=raw.map(item=>({...item,allergens:[],name:item.name.replace(/\s*\([ABCDEFGHLMNOPR](?:\s*[,/]\s*[ABCDEFGHLMNOPR])*\)/g,'')})).filter(item=>{
    const key=JSON.stringify([item.category,item.name.toLowerCase().replace(/[^a-z0-9äöü]+/g,' ').trim(),item.price]);
    if(seen.has(key))return false;seen.add(key);return true;
  });
  const planted=raw.find(item=>/mensa burger/i.test(item.name)&&/planted.*crispy.*chicken/i.test(item.name)&&! /\bbeef\b/i.test(item.name));
  const beef=raw.find(item=>/mensa burger/i.test(item.name)&&/\bbeef\b/i.test(item.name));
  if(planted&&beef&&planted.category===beef.category&&planted.price===beef.price){
    if(!/planted/i.test(beef.name))beef.name=beef.name.replace(/\bBeef\b/i,"Beef oder "+planted.name.slice(planted.name.toLowerCase().indexOf('planted')));
    beef.description=[...new Set([beef.description,planted.description].filter(Boolean))].join('\n');
    raw=raw.filter(item=>item!==planted);
  }
  const normalize=s=>String(s||'').toLowerCase().replace(/[^a-z0-9äöü]+/g,' ').trim();
  const specs=[['Ausgabe 1+2',['powered by plants veggie','powered by plants','veggie','ausgabe 1 2']],['Ausgabe 3+4',['meaty','ausgabe 3 4']],['Ausgabe 5',['pizza','pizza co','weekly special','ausgabe 5']],['Ausgabe 6',['pasta','pasta co','ausgabe 6']],['Ausgabe 7',['bowls','bowls co','ausgabe 7']],['Ausgabe 8',['global grill','global grills','ausgabe 8']]];
  const assigned=new Set(),out=[];
  const soup=raw.find(item=>/^(tagess?uppe)$/i.test(item.category||''));
  const euro=v=>new Intl.NumberFormat('de-AT',{maximumFractionDigits:2}).format(v)+' €';
  for(const [label,categories] of specs){
    const rows=raw.filter(item=>categories.includes(normalize(item.category)));
    rows.forEach(item=>assigned.add(item));
    if(label==='Ausgabe 5'){out.push({category:label,name:'Pizza',price:null,description:''});continue}
    if(label==='Ausgabe 6'||label==='Ausgabe 7'){out.push({category:label,name:label==='Ausgabe 6'?'Pasta':'Bowl',price:null,priceLabel:' ',description:''});continue}
    if(!rows.length)continue;
    const prices=[...new Set(rows.map(item=>item.price))];
    const common=prices.length===1?prices[0]:null;
    const lines=rows.map(item=>[item.name+(prices.length>1?' – '+(item.price==null?'X €':euro(item.price)):''),item.description,item.energy_kcal?item.energy_kcal+' kcal':''].filter(Boolean).join('\n'));
    out.push({category:label,name:((label==='Ausgabe 1+2'||label==='Ausgabe 3+4')&&soup?soup.name+'\n':'')+lines.join('\n\n'),price:common,priceLabel:prices.length>1?' ':undefined,description:''});
  }
  // Soup and conditional menu offers retain their original terms and prices.
  return [...out.filter(item=>!['Ausgabe 5','Ausgabe 6','Ausgabe 7'].includes(item.category)),...raw.filter(item=>!assigned.has(item)&&! /tagess?uppe|soup deal|menüoption|smart menü/i.test(item.category||item.name))];
}


window.WUMenuRules={restaurantDisplayRules,mensaStations};