// Only deliberate native app usage enters this bounded event catalog.
type Props = Record<string,string | number>;
type Sender = (event: string, props: Props) => void;
const restaurants=new Set(['mensa','baschly','finn','lia','campus','karmafood','topfdeckel','omakueche','gruenehuette','glashaus','losteria']);
export function validateUsage(event: unknown, input: unknown): {event: string; props: Props} | null {
  if(!input||typeof input!=='object'||Array.isArray(input))return null;
  const value=input as Record<string,unknown>,props: Props={};
  if(value.language!=='de'&&value.language!=='en')return null;
  props.app_language=value.language;
  if(event==='language_changed')return {event,props};
  if(!restaurants.has(String(value.restaurant_id)))return null;
  props.restaurant_id=String(value.restaurant_id);
  if(event==='restaurant_open'){
    if(!['list','map','next','previous','deep_link'].includes(String(value.entry))||!['menu','info'].includes(String(value.view)))return null;
    props.entry=String(value.entry);props.view=String(value.view);
  }else if(event==='restaurant_view'){
    if(!['menu','info'].includes(String(value.view)))return null;props.view=String(value.view);
  }else if(event==='menu_day_changed'){
    if(!Number.isInteger(value.weekday)||Number(value.weekday)<1||Number(value.weekday)>5)return null;props.weekday=Number(value.weekday);
  }else return null;
  return {event,props};
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
