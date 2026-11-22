// Only deliberate native app usage enters this bounded event catalog.
type Props = Record<string,string | number>;
type Sender = (event: string, props: Props) => void;
export function isAnalyticsDevice(platform: string, input: unknown){
  const constants=(input&&typeof input==='object'?input:{}) as {isTesting?: boolean; Model?: string; Fingerprint?: string};
  if(constants.isTesting||!['android','ios'].includes(platform))return false;
  return platform!=='android'||!/(?:sdk_gphone|google_sdk|android sdk built for|emulator|generic)/i.test((constants.Model||'')+' '+(constants.Fingerprint||''));
}
const restaurants=new Set(['mensa','baschly','finn','lia','campus','karmafood','topfdeckel','omakueche','gruenehuette','glashaus','losteria']);
// Ereigniskatalog (erweitert am 17.11.2026 auf Wunsch des Betreibers: Meet to eat, Karte, Links, Teilen).
// Jedes Feld hat eine feste Werteliste – freie Texte (Namen, E-Mail-Adressen, Gerichte, Linkziele) können
// die App so gar nicht verlassen. Ein "?" am Feldnamen heißt: darf fehlen.
type Check=(value: unknown)=>string | number | null;
const oneOf=(...values: (string | number)[]): Check=>value=>{const found=values.find(item=>item===value||String(item)===String(value)&&typeof value!=='object');return found===undefined?null:found;};
const restaurant: Check=value=>restaurants.has(String(value))?String(value):null;
const view=oneOf('menu','info'),slot=oneOf('next','following');
const catalog: Record<string,Record<string,Check>>={
  language_changed:{},
  restaurant_open:{restaurant_id:restaurant,entry:oneOf('list','map','next','previous','deep_link'),view},
  restaurant_view:{restaurant_id:restaurant,view},
  menu_day_changed:{restaurant_id:restaurant,weekday:oneOf(1,2,3,4,5),'method?':oneOf('tap','swipe')},
  home_view:{view:oneOf('list','map')},
  map_pin_selected:{restaurant_id:restaurant},
  restaurant_link:{restaurant_id:restaurant,link:oneOf('menu_source','website','phone','email','maps','source_note')},
  restaurant_shared:{restaurant_id:restaurant},
  footer_link:{link:oneOf('imprint','contact','website')},
  meet_open:{entry:oneOf('list','menu_hint')},
  meet_date_changed:{slot},
  meet_signup_started:{slot},
  meet_input_rejected:{reason:oneOf('name_missing','name_format','name_blocked','email_invalid')},
  meet_code_requested:{resend:oneOf('no','yes')},
  meet_code_result:{result:oneOf('ok','invalid')},
  meet_joined:{slot,weekday:oneOf(1,2,3,4,5)},
  meet_left:{slot},
  meet_maps_opened:{source:oneOf('fact','button')},
  update_notice:{action:oneOf('shown','update','later')},
};
export const usageEvents=Object.keys(catalog);
export function validateUsage(event: unknown, input: unknown): {event: string; props: Props} | null {
  if(!input||typeof input!=='object'||Array.isArray(input))return null;
  const value=input as Record<string,unknown>,props: Props={};
  if(value.language!=='de'&&value.language!=='en')return null;
  props.app_language=value.language;
  const fields=typeof event==='string'&&Object.prototype.hasOwnProperty.call(catalog,event)?catalog[event]:null;
  if(!fields)return null;
  for(const [key,check] of Object.entries(fields)){
    const optional=key.endsWith('?'),name=optional?key.slice(0,-1):key;
    if(value[name]===undefined&&optional)continue;
    const checked=check(value[name]);
    if(checked===null)return null;
    props[name]=checked;
  }
  return {event: event as string,props};
}
export function createUsage(send: Sender){
  let started=false,backgrounded=false;
  const emit=(event: string,props: Props)=>{try{send(event,props);}catch{/* Analytics must never block menus. */}};
  return {
    state(state: string,language: 'de'|'en'){
      if(state==='background')backgrounded=true;
      if(state==='active'&&(!started||backgrounded)){emit('app_open',{entry:started?'foreground':'cold_start',app_language:language});started=true;backgrounded=false;}
    },
    event(event: unknown,props: unknown){const valid=validateUsage(event,props);if(valid)emit(valid.event,valid.props);},
  };
}
