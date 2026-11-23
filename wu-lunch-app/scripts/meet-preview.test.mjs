import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

// Feste Uhrzeit für die Abläufe: Dienstag, 17.11.2026, 10:00 Uhr Wien. Sonst hingen die Tests von der echten Uhrzeit ab
// (z. B. montags und mittwochs zwischen 12:05 und 14:00 ist die Anmeldung für den angezeigten Termin geschlossen).
const fixedNow = Date.parse('2026-11-17T09:00:00Z');
class FixedDate extends Date { constructor(...args) { super(...(args.length ? args : [fixedNow])); } static now() { return fixedNow; } }

test('paused e-mail flow still works when switched back on (verified email, then sign-up and cancellation)', async () => {
  // Die Bestätigung per E-Mail-Code ist pausiert, nicht gelöscht: Mit eingeschaltetem Schalter läuft der alte Ablauf.
  const source=(await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8')).replace('const emailVerification = false;','const emailVerification = true;');
  const handlers={}; let session=null, own=[], otpCalls=0, verifyCalls=0, inserts=0, openedUrl='', redirectTo='';
  const store=new Map();
  const client={auth:{getSession:async()=>({data:{session},error:null}),signInWithOtp:async({options})=>{otpCalls++;redirectTo=options.emailRedirectTo;return {error:null}},verifyOtp:async({token})=>{verifyCalls++;if(token==='000000')return {data:null,error:new Error('expired')};session={user:{id:'test-user'}};return {data:{session},error:null}}},from(table){return {
    select(){return {in:async()=>({data:own,error:null}),gte:async()=>({data:own,error:null})}},
    insert:async row=>{inserts++;own.push(row);return {error:null}},
    delete(){return {eq(){return {eq:async(_key,date)=>{own=own.filter(item=>item.meeting_date!==date);return {error:null}}}}}}
  }}};
  const inputs={'meet-first-name':{value:'Anna'},'meet-email':{value:'anna@example.com'},'meet-code':{value:'123456'}};
  const context={window:{supabase:{createClient:()=>client},open:url=>{openedUrl=url}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:id=>inputs[id]},
    localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
    setInterval(){},console,Intl,Date:FixedDate,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:'mensa',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d,trackUsage:(event,props)=>tracked.push([event,JSON.stringify(props)])};
  const tracked=[];
  vm.createContext(context);vm.runInContext(source,context);
  const click=async (action,slot)=>{handlers.click({target:{closest:()=>({dataset:{action,slot}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  await click('meet-preview');
  assert.equal(context.meetSlot,0);assert.match(context.renderMeet(),/Meet to eat/);assert.match(context.renderMeet(),/<p class="meet-dabei">[^]*?<strong>Sei die erste Person\.<\/strong><\/span><\/p>/);
  assert.doesNotMatch(context.renderMeet(),/WU-Studenten Gruppe|Info nach Anmeldung/);assert.doesNotMatch(context.renderMeet(),/Testvorschau|Testteilnehmer|Testtermin/);
  // Keine Terminleiste, keine Wischpunkte, kein Wischen. Das Datum ist eine Auswahlliste mit genau
  // zwei Terminen: dem nächsten und dem danach.
  assert.doesNotMatch(context.renderMeet(),/weekday-strip|day-dot|meet-select|data-slot/);
  assert.match(context.renderMeet(),/<select id="meet-date" aria-label="Datum">/);
  assert.equal((context.renderMeet().match(/<option /g)||[]).length,2);
  assert.equal((context.renderMeet().match(/<option [^>]*selected/g)||[]).length,1);
  const later=context.renderMeet().match(/<option value="(\d{4}-\d{2}-\d{2})" >/)[1];
  handlers.change({target:{id:'meet-date',value:later}});
  assert.match(context.renderMeet(),new RegExp('<option value="'+later+'" selected>'));
  handlers.change({target:{id:'something-else',value:'x'}});
  assert.match(context.renderMeet(),new RegExp('<option value="'+later+'" selected>'));
  await click('meet-preview');   // erneutes Öffnen beginnt wieder beim nächsten Termin
  assert.doesNotMatch(context.renderMeet(),new RegExp('<option value="'+later+'" selected>'));
  assert.equal((context.renderMeet().match(/placeholder="Max"/g)||[]).length,0);
  // Aufbau seit 23.11.2026: Satz, Termin in einer Zeile, Foto mit Beschriftung, „… schon dabei", Ablauf, unten die Anmeldung.
  assert.equal((context.renderMeet().match(/class="meet-fact"/g)||[]).length,0);   // keine Tabelle mehr
  const order=['class="meet-lead"','class="meet-when"','class="meet-place"','class="meet-dabei"','class="meet-why"','class="meet-steps"','</div><div class="meet-cta"'].map(part=>context.renderMeet().indexOf(part));
  assert.ok(order.every((at,index)=>at>=0&&(index===0||order[index-1]<at)),'Reihenfolge der Bereiche: '+order);
  // Die Uhrzeit steht im Einleitungssatz ("… um 12:00 Uhr statt."), nicht mehr neben der Terminauswahl.
  assert.match(context.renderMeet(),/<div class="meet-when"><span class="meet-date-picker"><select id="meet-date" aria-label="Datum">[^]*?<\/select><\/span><\/div>/);assert.match(context.renderMeet(),/<figcaption>[^]*?<span><strong>Vor dem Baum direkt bei der Mensa<\/strong><span class="meet-time">Treffpunkt von 12:00 bis 12:05 Uhr<\/span><\/span><\/figcaption>/);
  assert.match(context.renderMeet(),/<section class="meet-steps"><h3>So läuft's ab<\/h3><ol><li>Mit deinem Vornamen anmelden\.<\/li><li>Um 12:00 Uhr beim Baum vor der Mensa treffen\.<\/li><li>Um 12:05 Uhr gemeinsam losgehen und ein Lokal aussuchen\.<\/li><\/ol><\/section>/);
  assert.equal(handlers.touchstart,undefined);assert.equal(handlers.touchend,undefined);
  // Vorgabe vom 23.11.2026: Treffpunkt, Foto und Google-Maps-Link sind schon vor der Anmeldung sichtbar –
  // nichts wird mehr versteckt ("Info nach Anmeldung" gibt es nicht mehr). Keine eingebettete Karte, kein Platzhalter.
  assert.doesNotMatch(context.renderMeet(),/id="meet-map"|meet-locked|Nach Anmeldung sichtbar|Info nach Anmeldung|meet-reveal/);
  // Das Foto steht oben (statt der Zeichnung); der Treffpunkt ist Beschriftung, kein Link. Auch der Google-Maps-Link ist entfallen (Vorgabe 23.11.2026).
  assert.match(context.renderMeet(),/<figure class="meet-place"><img class="meet-photo-visible" src="\.\/meeting-point\.webp"[^>]*><figcaption>[^]*?<strong>Vor dem Baum direkt bei der Mensa<\/strong><span class="meet-time">Treffpunkt von 12:00 bis 12:05 Uhr<\/span><\/span><\/figcaption><\/figure>/);
  assert.doesNotMatch(context.renderMeet(),/google\.com\/maps|Google Maps|meet-map-link/);
  assert.doesNotMatch(context.renderMeet(),/<a [^>]*>Vor dem Baum direkt bei der Mensa<\/a>|meet-art/);
  // Wozu die Anmeldung dient, steht im Text; Vorname und Knopf stehen in einer festen Leiste unter dem scrollenden Inhalt.
  assert.match(context.renderMeet(),/<p class="meet-why">Melde dich bitte an, damit die anderen wissen, dass du kommst\. Wenn alle interessiert sind, sich aber niemand anmeldet, funktioniert es nicht :\)<\/p>/);
  assert.match(context.renderMeet(),/<\/section><\/div><div class="meet-cta"><div class="meet-cta-row"><button class="meet-primary" data-action="meet-show-form"[^>]*>Teilnehmen<\/button><\/div><\/div><\/div>$/);
  // Die Seite beginnt mit dem einen Satz, worum es geht (die Zeichnung ist dem Foto gewichen).
  assert.match(context.renderMeet(),/id="meet-screen"><p class="meet-lead">Triff dich mit anderen freundlichen WU-Studierenden am WU Campus/);
  assert.match(context.renderMeet(),/Findet jeden Mittwoch um 12:00 Uhr statt\./);assert.doesNotMatch(context.renderMeet(),/Montag/);
  await click('meet-show-form');
  assert.match(context.renderMeet(),/Verifizierung deiner E-Mail-Adresse: Du bekommst einen Code per E-Mail\. Nur dein Vorname ist für alle sichtbar\./);
  assert.doesNotMatch(context.renderMeet(),/WU-Mail|WU E-Mail|nur WU Studenten|wu\.ac\.at/);   // keine Einschränkung auf WU-Adressen
  // Jede gültige E-Mail-Adresse kann verwendet werden (eigener Test weiter unten).
  inputs['meet-email'].value='anna@gmail.com';
  // Vornamen-Prüfung greift vor dem Versand des Codes.
  inputs['meet-first-name'].value='Wählt Liste 3!';await click('meet-send-code');assert.equal(otpCalls,0);assert.match(context.renderMeet(),/nur deinen Vornamen/);
  inputs['meet-first-name'].value='Hitler';await click('meet-send-code');assert.equal(otpCalls,0);assert.match(context.renderMeet(),/nicht möglich/);
  inputs['meet-first-name'].value='Anna';
  assert.match(context.renderMeet(),/id="meet-first-name"[^>]*placeholder="Max"/);
  assert.match(context.renderMeet(),/data-action="meet-send-code"[^>]*>Verifizierung via Mail starten</);
  assert.match(context.renderMeet(),/id="meet-email"[^>]*placeholder="mustermann@email\.com"/);
  assert.doesNotMatch(context.renderMeet(),/<h3>/);   // keine Überschrift mehr über dem Formular
  assert.equal(inserts,0);await click('meet-send-code');assert.equal(otpCalls,1);assert.equal(inserts,0);assert.equal(redirectTo,'https://phoenixvie.github.io/wu-lunch-app/preview/');
  assert.doesNotMatch(context.renderMeet(),/outlook|WU-Mail/);assert.match(context.renderMeet(),/Bestätigungscode an anna@gmail\.com gesendet/);
  inputs['meet-code'].value='000000';await click('meet-verify');assert.match(context.renderMeet(),/bereits verwendet/);assert.equal(inserts,0);
  await click('meet-resend-code');assert.equal(otpCalls,2);inputs['meet-code'].value='123456';await click('meet-verify');assert.equal(verifyCalls,2);assert.equal(inserts,1);assert.equal(own[0].first_name,'Anna');
  // Nach der Anmeldung erscheinen Treffpunkt, Foto und Karte.
  assert.match(context.renderMeet(),/Bereits angemeldet/);assert.match(context.renderMeet(),/Anna/);assert.doesNotMatch(context.renderMeet(),/google\.com\/maps/);assert.match(context.renderMeet(),/Vor dem Baum direkt bei der Mensa/);
  assert.match(context.renderMeet(),/<figure class="meet-place">/);assert.doesNotMatch(context.renderMeet(),/id="meet-map"|class="meet-cta"/);   // eingebettete Karte entfernt (17.11.2026)assert.match(context.renderMeet(),/meeting-point\.webp/);
  assert.equal(context.meetJoined,true);
  // Die Bestätigung trägt ein Häkchen-Symbol vor dem Text.
  assert.match(context.renderMeet(),/<div class="meet-confirm"><p><svg class="meet-check"[^>]*>.*?<\/svg><span>Du bist für diesen Termin angemeldet\.<\/span><\/p><p><svg class="meet-check"[^>]*>.*?<\/svg><span>Bitte melde dich aus Rücksicht/);
  // Nach der Anmeldung: Bestätigung, dann die Namen, dann „Abmelden".
  assert.match(context.renderMeet(),/<div class="meet-confirm">[^]*?<div class="meet-fact meet-people">[^]*?<strong>Bereits angemeldet<\/strong><span class="meet-names">[^]*?data-action="meet-leave">/);
  await click('meet-leave');assert.equal(own.length,0);
  assert.doesNotMatch(context.renderMeet(),/id="meet-map"|meet-own/);assert.match(context.renderMeet(),/meet-place/);assert.match(context.renderMeet(),/Sei die erste Person\./);assert.equal(context.meetJoined,false);
  // Abgemeldet, Name lokal gemerkt: erneutes Anmelden braucht kein Formular mehr.
  assert.equal(store.get('wu-meet-preview-name'),'Anna');
  store.clear();await click('meet-show-form');assert.match(context.renderMeet(),/E-Mail-Adresse ist bestätigt/);
  // Der Vorname ist im Bestätigungsschritt schon eingefügt (hier aus der laufenden Sitzung, sonst vom Gerät).
  assert.match(context.renderMeet(),/id="meet-first-name"[^>]*value="Anna"/);await click('meet-confirm-name');assert.equal(inserts,2);await click('meet-leave');
  await click('meet-back');assert.equal(context.meetPreviewOpen,false);assert.equal(context.selectedId,'mensa');  // Anonyme Statistik: Schritte werden gezählt, Eingaben (Name, Adresse, Code) nie mitgeschickt.
  const events=tracked.map(row=>row[0]);
  for(const expected of ['meet_open','meet_date_changed','meet_signup_started','meet_input_rejected','meet_code_requested','meet_code_result','meet_joined','meet_left'])
    assert.ok(events.includes(expected),'Ereignis fehlt: '+expected);
  assert.deepEqual([...new Set(tracked.filter(row=>row[0]==='meet_input_rejected').map(row=>JSON.parse(row[1]).reason))].sort(),['name_blocked','name_format']);
  assert.deepEqual(tracked.filter(row=>row[0]==='meet_code_result').map(row=>JSON.parse(row[1]).result),['invalid','ok']);
  assert.doesNotMatch(JSON.stringify(tracked),/Anna|anna@|123456|000000|example/);
});

test('first names must look like a name; obvious insults and political terms are refused', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const blockedParts ='),source.indexOf('  const redraw ='));
  const context={};vm.createContext(context);vm.runInContext(helper,context);
  const problem=name=>vm.runInContext('nameProblem',context)(name);
  // Echte Vornamen, auch mit Akzent, Bindestrich, zwei Teilen oder Ähnlichkeit zu gesperrten Wörtern.
  for(const name of ['Anna','Max','Jo','Anna-Lena','Jean-Luc','Zoë','Jürgen','Renée','Sieglinde','Siegfried','Ignazio','Nazim','Kanako','Pornthip','Dick','Adolf','Annalena','Heilwig','Mustafa'])
    assert.equal(problem(name),'',name);
  assert.equal(problem(''),'Bitte gib deinen Vornamen ein.');
  // Keine Sätze, Zahlen, Links, Zeichen oder Überlängen – also auch keine Botschaften.
  for(const text of ['Wählt Liste 3!','Free Palestine now','Free Palestine','Sieg Heil','Jean Luc','Max123','www.example.org','Anna 😀','A','Maximilianalexanderxyz','Stop the war','x x x'])
    assert.match(problem(text),/nur deinen Vornamen/,text);
  // Offensichtliche Beschimpfungen und politische Begriffe, auch groß geschrieben, mit Akzent oder als Teil.
  for(const text of ['Nazi','NAZI','Hitler','Sieg-Heil','Heil','Arschloch','Fuck','Fuckyou','Hurensohn','Trump','Putin','AfD','FPÖ','Hamas','Schlampe','Nigger','Idiot','Porno','Free-Palestine','Stop-War','Fck-Afd','Israel','MAGA'])
    assert.match(problem(text),/nicht möglich/,text);
});

test('the next date is shown until 14:00 and the one after it can always be chosen', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const viennaClock'),source.indexOf('  // Texte kommen aus dem gemeinsamen Katalog'));
  let current='2026-11-16T09:00:00Z';   // Montag 10:00 Uhr Wien
  class Clock extends Date { constructor(...args){super(...(args.length?args:[current]));} }
  const state={own:[],selectedDate:null};
  // Die Zeitregeln werden mit zwei Tagen pro Woche geprüft (Montag und Mittwoch, im Admin einstellbar) …
  const context={Intl,Date:Clock,state,meetWeekdays:()=>[1,3]};vm.createContext(context);vm.runInContext(helper,context);
  const shown=()=>vm.runInContext('date()',context);
  const options=()=>[...vm.runInContext('dateOptions()',context)];
  assert.equal(shown(),'2026-11-16');assert.deepEqual(options(),['2026-11-16','2026-11-18']);
  current='2026-11-16T11:06:00Z';assert.equal(shown(),'2026-11-16');     // 12:06: Anmeldung zu, Termin bleibt sichtbar
  assert.equal(vm.runInContext('registrationOpen("2026-11-16")',context),false);
  current='2026-11-16T12:59:00Z';assert.equal(shown(),'2026-11-16');     // 13:59
  current='2026-11-16T13:00:00Z';assert.equal(shown(),'2026-11-18');     // ab 14:00: nächster Termin
  assert.deepEqual(options(),['2026-11-18','2026-11-23']);
  state.selectedDate='2026-11-23';assert.equal(shown(),'2026-11-23');    // gewählter Folgetermin
  state.selectedDate='2026-11-16';assert.equal(shown(),'2026-11-18');    // abgelaufene Auswahl fällt zurück
  state.selectedDate=null;current='2026-11-17T08:00:00Z';assert.equal(shown(),'2026-11-18'); // Dienstag
  current='2026-11-19T08:00:00Z';assert.deepEqual(options(),['2026-11-23','2026-11-25']);   // Donnerstag
  // … und mit der Vorgabe „jeden Mittwoch“: der nächste und der übernächste Mittwoch, Wechsel am Mittwoch um 14:00.
  const wednesday={Intl,Date:Clock,state:{own:[],selectedDate:null}};vm.createContext(wednesday);vm.runInContext(helper,wednesday);
  const next=()=>[...vm.runInContext('dateOptions()',wednesday)];
  current='2026-11-16T09:00:00Z';assert.deepEqual(next(),['2026-11-18','2026-11-25']);      // Montag
  current='2026-11-18T12:59:00Z';assert.deepEqual(next(),['2026-11-18','2026-11-25']);      // Mittwoch 13:59
  current='2026-11-18T13:00:00Z';assert.deepEqual(next(),['2026-11-25','2026-12-02']);      // Mittwoch 14:00
});

test('texts fall back to German and use the shared catalogue for English', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const text = (key'),source.indexOf('  const redraw ='));
  const run=localize=>{const context=localize?{localize}:{};vm.createContext(context);vm.runInContext(helper,context);return (key,values,german)=>vm.runInContext('text',context)(key,values,german);};
  const german=run(null);
  assert.match(german('Wir haben einen Bestätigungscode an {email} gesendet. Bitte gib den Code hier ein. Der Link in der E-Mail und der Code sind nur einmal verwendbar.',{email:'a@wu.ac.at'}),/^Wir haben einen Bestätigungscode an a@wu\.ac\.at gesendet\./);
  assert.equal(german('Meet to eat: Abmelden',{},'Abmelden'),'Abmelden');
  const catalogue=JSON.parse(JSON.stringify((await import('node:module')).createRequire(import.meta.url)('../../wu-lunch/i18n.js')??{}));
  const {ui}=globalThis.WULunchI18n;
  const english=run({label:key=>ui[key]??key});
  assert.match(english('Wir haben einen Bestätigungscode an {email} gesendet. Bitte gib den Code hier ein. Der Link in der E-Mail und der Code sind nur einmal verwendbar.',{email:'a@wu.ac.at'}),/^We have sent a confirmation code to a@wu\.ac\.at\./);
  assert.equal(english('Meet to eat: Abmelden',{},'Abmelden'),'Cancel sign-up');
  // Jeder feste Text des Bildschirms hat eine englische Fassung (sonst "English translation pending").
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  for(const key of ['Datum','Vor dem Baum direkt bei der Mensa','Die Namen siehst du nach deiner Anmeldung.','Melde dich bitte an, damit die anderen wissen, dass du kommst. Wenn alle interessiert sind, sich aber niemand anmeldet, funktioniert es nicht :)','Treffpunkt von 12:00 bis 12:05 Uhr','Sei die erste Person.','1 Person ist schon dabei.','{count} sind schon dabei.',"So läuft's ab",'Mit deinem Vornamen anmelden.','Um 12:00 Uhr beim Baum vor der Mensa treffen.','Um 12:05 Uhr gemeinsam losgehen und ein Lokal aussuchen.','Bereits angemeldet','Teilnehmen','Vorname','Verifizierung via Mail starten','Bestätigungscode','Code bestätigen und anmelden','Neuen Code anfordern','Die Anmeldung für diesen Termin ist geschlossen.','Das hat nicht funktioniert. Bitte versuche es erneut.','Triff dich mit anderen freundlichen WU-Studierenden am WU Campus und geht gemeinsam als Gruppe Mittag essen.']){
    assert.ok(source.includes(key)||app.includes(key),'Text wird verwendet: '+key);
    assert.ok(ui[key]&&ui[key]!==key,'englische Fassung fehlt: '+key);
  }
  // "Anmelden" bleibt für den Admin-Login "Sign in"; Meet to eat nutzt eigene Schlüssel.
  assert.equal(ui.Anmelden,'Sign in');assert.notEqual(ui['Meet to eat: Anmelden'],ui.Anmelden);
});

test('Android back button closes Meet to eat instead of leaving the app, and the icon is mirrored', async () => {
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');
  const back=app.slice(app.indexOf('window.wuFoodBack='),app.indexOf('try{const cached='));
  const messages=[];let renders=0;
  const context={sourceViewUrl:null,meetPreviewOpen:true,meetForm:true,meetSlot:0,meetJoined:true,selectedId:null,selectedMapId:null,homeTab:'list',
    render:()=>{renders++},nativePost:type=>messages.push(type),window:{}};
  vm.createContext(context);vm.runInContext(back,context);
  context.window.wuFoodBack();assert.equal(context.meetForm,false);assert.equal(context.meetPreviewOpen,true);   // Formular -> Terminansicht
  context.window.wuFoodBack();assert.equal(context.meetPreviewOpen,false);assert.equal(context.meetJoined,false); // Terminansicht -> Liste
  assert.deepEqual(messages,[]);assert.equal(renders,2);
  context.window.wuFoodBack();assert.deepEqual(messages,['exit']);                                                // erst in der Liste: App verlassen
  assert.match(css,/\.meet-brand-logo \.material-svg\{[^}]*transform:scaleX\(-1\)/);
});

test('restaurant menu offers an internal Meet-to-eat link above the source note', async () => {
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const menu=source.slice(source.indexOf('function renderMenu('),source.indexOf('function renderInfo('));
  assert.match(menu,/data-action="meet-preview"/);
  // Vorgabe vom 17.11.2026: ein einziger Fließtext unter jedem Menü, an jedem Tag gleich:
  // "Montags & Mittwochs gemeinsam essen gehen. Prüfe die Menüs auf der Restaurantwebseite. Change language."
  const note=menu.slice(menu.indexOf('<div class="source-note">'));
  // Vorgabe vom 23.11.2026: drei Zeilen – "Change language." steht als eigene Zeile über dem Meet-to-eat-Satz.
  // "Change" ist kein Link, nur das Wort "language" (Vorgabe 23.11.2026) – wie bei "Prüfe die Menüs auf der Restaurantwebseite".
  assert.ok(note.startsWith('<div class="source-note">${site.standalone?\'\':`<span data-ui-literal>Change</span> <a href="#" class="source-link" data-change-language>language</a>.<br><span data-ui-literal>${localize.language===\'en\'?\'Send this menu\':\'Dieses Menü\'}</span> <button type="button" class="source-link" data-action="share">an Freunde schicken</button>.<br><span data-ui-literal>${esc(meetDaysText(\'hint\'))}</span> <button type="button" class="source-link meet-invite" data-action="meet-preview">gemeinsam essen</button>${localize.language===\'en\'?\'\':\' <span data-ui-literal>gehen</span>\'}.<br>`}<span>Prüfe die Menüs auf der</span> '));
  // "gehen" ist kein Link (Vorgabe 23.11.2026); im Englischen gibt es das Wort nicht ("Every Wednesday: eat together.").
  assert.equal(note.slice(0,note.indexOf('</section>')).split('data-change-language').length,2);   // genau einmal
  assert.match(source,/const wanted=\(note\.querySelectorAll\?\.\('br'\)\.length\|\|1\)\+1;/);
  assert.doesNotMatch(menu,/\[0,2\]\.includes\(dayIndex\)|Angaben ohne Gewähr|WU Studenten|localize\.language==='en'\?`Every/);
  // Zwei Zeilen, die erste (Meet to eat) immer kürzer als die zweite (Vorgabe 17.11.2026): fester Umbruch nach dem
  // ersten Satz; der zweite Satz ist in beiden Sprachen länger, auf schmalen Handys umbricht er weiter unten.
  for(const lines of [['Change language.','Dieses Menü an Freunde schicken.','Jeden Mittwoch gemeinsam essen gehen.','Prüfe die Menüs auf der Restaurantwebseite.'],['Change language.','Send this menu to friends.','Every Wednesday: eat together.','Check the menus on the restaurant website.']])assert.ok(lines.every((line,index)=>index===0||lines[index-1].length<line.length));
  // Vorgabe vom 23.11.2026: Teilen zusätzlich als Satz unter "Change language" ("Menü an Freunde schicken."); das Symbol oben bleibt.
  assert.equal(globalThis.WULunchI18n.ui['an Freunde schicken'],'to friends');
  assert.match(source,/class="[^"]*" data-action="share"[^>]*>\$\{icon\('share'\)|data-action="share"/);
  // Alles hintereinander: der Meet-Link ist kein eigener Block mehr.
  const css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');
  assert.match(css,/\.meet-invite\{display:inline;/);assert.doesNotMatch(css,/\.meet-invite\{display:block/);
  // Englische Fassungen aller Teile des Satzes.
  const {ui}=globalThis.WULunchI18n;
  assert.deepEqual(['gemeinsam essen','Prüfe die Menüs auf der','Restaurantwebseite'].map(key=>ui[key]),['eat together','Check the menus on the','restaurant website']);
});

test('Vienna dates stay visible until 14:00 and registration closes after 12:05', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const helper=source.slice(source.indexOf('  const viennaClock'),source.indexOf('  const date ='));
  let current='2026-11-15T23:01:00Z';
  class Clock extends Date { constructor(...args){super(...(args.length?args:[current]));} }
  const context={Intl,Date:Clock,meetWeekdays:()=>[1,3]};vm.createContext(context);vm.runInContext(helper,context);
  const days=()=>Array.from(vm.runInContext('slotDates()',context));
  const open=(date)=>vm.runInContext(`registrationOpen('${date}')`,context);
  assert.deepEqual(days(),['2026-11-16','2026-11-18','2026-11-23','2026-11-25','2026-11-30']);assert.equal(open('2026-11-16'),true);
  current='2026-11-16T11:05:59Z';assert.equal(open('2026-11-16'),true);assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T11:06:00Z';assert.equal(open('2026-11-16'),false);assert.equal(days()[0],'2026-11-16');
  current='2026-11-16T12:59:00Z';assert.equal(days()[0],'2026-11-16');   // 13:59 Uhr Wien
  current='2026-11-16T13:00:00Z';assert.deepEqual(days(),['2026-11-18','2026-11-23','2026-11-25','2026-11-30','2026-12-02']);   // 14:00 Uhr
  current='2026-11-18T13:00:00Z';assert.deepEqual(days(),['2026-11-23','2026-11-25','2026-11-30','2026-12-02','2026-12-07']);
  current='2027-03-29T10:05:59Z';assert.equal(open('2027-03-29'),true);
  current='2027-03-29T10:06:00Z';assert.equal(open('2027-03-29'),false);
});


test('Meet to eat icons are bundled as SVG and inherit their screen colours', async () => {
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');
  const match=app.match(/const meetIcons=(\{.*?\});\nconst icon=/);
  assert.ok(match, 'bundled icon map exists');
  const icons=JSON.parse(match[1]);
  for(const name of ['calendar_today','directions_walk','school','lock','person','person_add']) {
    assert.match(icons[name], /<svg/); assert.match(icons[name], /class="material-svg"/);
  }
  assert.match(css,/\.meet-fact>\.material-svg\{[^}]*color:#6f8192/);
  assert.match(css,/\.meet-person \.material-svg\{[^}]*color:#8a98a5/);
  assert.match(css,/\.meet-brand-logo \.material-svg\{[^}]*width:34px/);
});

test('Meet to eat keeps its scroll position during background redraws', async () => {
  const source=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const start=source.indexOf('function renderScreen(){');
  const end=source.indexOf('const r=currentRestaurant();',start);
  assert.ok(start>=0 && end>start);
  let screen={scrollTop:540};
  const app={querySelector:()=>screen, set innerHTML(value){screen={scrollTop:0};}};
  const context={data:{},meetPreviewOpen:true,app,map:null,renderMeet:()=>'<div id="meet-screen"></div>',document:{getElementById:()=>null},Number};
  vm.createContext(context);vm.runInContext(source.slice(start,end)+'}',context);
  context.renderScreen();assert.equal(screen.scrollTop,540);
  screen.scrollTop=320;context.renderScreen();assert.equal(screen.scrollTop,320);
});

test('list entry shows the number of people signed up for the next date, and nothing when nobody is', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const start=async (rowsFor, {fails=false}={})=>{
    const asked=[]; let painted=null, removed=0;
    const row={querySelector:()=>({remove(){removed++}}),lastElementChild:{insertAdjacentHTML:(where,html)=>{painted=[where,html]}}};
    const client={auth:{getSession:async()=>({data:{session:null},error:null})},from(table){return {select(columns){return {in:async(column,days)=>{asked.push([table,columns,column]);return fails?{data:null,error:new Error('offline')}:{data:rowsFor(days),error:null}},gte:async()=>({data:[],error:null})}}}}};
    const warnings=[];
    const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
      app:{addEventListener(){},querySelector:selector=>selector==='[data-action="meet-preview"].restaurant-row'?row:null},document:{getElementById:()=>null,addEventListener(){}},
      localStorage:{getItem:()=>null,setItem(){}},setInterval(){},console:{...console,warn:(...args)=>warnings.push(args.join(' '))},Intl,Date:FixedDate,
      meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:null,meetBadge:()=>'',
      renderMeet(){},render(){},icon:name=>`<i>${name}</i>`,esc:s=>String(s),dateValue:d=>d,contactEmail:()=>'kontakt@example.test',localize:{label:key=>key==='{count} angemeldet'?'{count} signed up':key}};
    vm.createContext(context);vm.runInContext(source,context);
    for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));
    return {context,asked,warnings,get painted(){return painted},get removed(){return removed}};
  };
  // Drei Personen beim nächsten Termin, eine beim übernächsten: gezählt wird nur der nächste.
  const busy=await start(days=>[...['Lena','Jonas','Mia'].map(first_name=>({meeting_date:days[0],first_name})),{meeting_date:days[1],first_name:'Tom'}]);
  // Vor der eigenen Anmeldung steht dort nur die Zahl (Vorgabe 23.11.2026): keine Namen, also auch kein Melde-Link.
  assert.match(busy.context.renderMeet(),/<p class="meet-dabei">[^]*?<strong>3 sind schon dabei\.<\/strong><small>Die Namen siehst du nach deiner Anmeldung\.<\/small><\/span><\/p>/);
  assert.doesNotMatch(busy.context.renderMeet(),/Lena|Jonas|Mia|meet-report|meet-names/);
  // Der Melde-Link gehört zur Namensliste, die erst nach der eigenen Anmeldung erscheint.
  assert.match(source,/<span class="meet-names">\$\{entries\}<\/span>\$\{names\.length \? `<a class="meet-report" href="mailto:\$\{esc\(contactEmail\(\)\)\}\?subject=/);
  assert.deepEqual(busy.asked,[['meet_preview_participants','meeting_date,first_name','meeting_date']],'nur die öffentliche Teilnehmerliste wird gelesen');
  assert.match(busy.context.meetBadge(),/^<span class="meet-count" data-ui-literal aria-label="3 signed up"><i>person<\/i>3<\/span>$/);
  assert.deepEqual(busy.painted,['beforebegin',busy.context.meetBadge()],'Zahl steht vor dem Pfeil des Eintrags');
  assert.equal(busy.removed,1,'eine alte Zahl wird vorher entfernt');
  // Niemand angemeldet (auch wenn beim übernächsten Termin schon jemand steht): nichts anzeigen.
  const empty=await start(days=>[{meeting_date:days[1],first_name:'Tom'}]);
  assert.equal(empty.context.meetBadge(),'');assert.equal(empty.painted,null);
  // Ein Ladefehler bleibt still und zeigt keine Zahl.
  const offline=await start(()=>[],{fails:true});
  assert.equal(offline.context.meetBadge(),'');assert.equal(offline.painted,null);assert.match(offline.warnings.join('\n'),/Anzahl: offline/);
  // Die Liste baut die Zahl über meetBadge() ein; in der Wels-Ausgabe gibt es den Eintrag gar nicht.
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  assert.match(app,/let meetBadge=\(\)=>'';/);assert.match(app,/data-ui-literal>\$\{esc\(meetDaysText\('title'\)\)\}<\/span><\/span>\$\{meetBadge\(\)\}\$\{icon\('chevron_right','chevron'\)\}/);
  const {ui}=globalThis.WULunchI18n;assert.equal(ui['{count} angemeldet'],'{count} signed up');
});

test('any valid e-mail address can be used, there is no WU restriction', async () => {
  const source=(await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8')).replace('const emailVerification = false;','const emailVerification = true;');
  assert.doesNotMatch(source,/wu\.ac\.at|requireWuEmail|email_not_wu|WU-Mail/);
  const handlers={}, tracked=[]; let otpCalls=0;
  const client={auth:{getSession:async()=>({data:{session:null},error:null}),signInWithOtp:async()=>{otpCalls++;return {error:null}}},from(){return {select(){return {in:async()=>({data:[],error:null}),gte:async()=>({data:[],error:null})}}}}};
  const inputs={'meet-first-name':{value:'Anna'},'meet-email':{value:''}};
  const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:id=>inputs[id]},localStorage:{getItem:()=>null,setItem(){}},
    setInterval(){},console,Intl,Date:FixedDate,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:null,meetBadge:()=>'',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d,trackUsage:(event,props)=>tracked.push(event+' '+JSON.stringify(props))};
  vm.createContext(context);vm.runInContext(source,context);
  const click=async action=>{handlers.click({target:{closest:()=>({dataset:{action}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
  await click('meet-preview');await click('meet-show-form');
  const send=async email=>{inputs['meet-email'].value=email;const before=otpCalls;await click('meet-send-code');return otpCalls>before;};
  assert.equal(await send('keine-adresse'),false);                      // ungültige Eingabe: kein Code
  assert.match(tracked.join('\n'),/email_invalid/);
  for(const email of ['anna@gmail.com','anna@s.wu.ac.at','anna@firma.co.at'])assert.equal(await send(email),true,email);
});

test('sign-up with first name only: field above the button, same name checks, no e-mail page', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  assert.equal(source.split('const emailVerification = false;').length,2,'E-Mail-Bestätigung ist pausiert');
  const handlers={}, tracked=[], store=new Map(); let session=null, own=[], anonymous=0, otpCalls=0, failAnonymous=null;
  const client={auth:{getSession:async()=>({data:{session},error:null}),
      signInAnonymously:async()=>{anonymous++;if(failAnonymous)return {data:null,error:new Error(failAnonymous)};session={user:{id:'anon-1'}};return {data:{session},error:null}},
      signInWithOtp:async()=>{otpCalls++;return {error:null}}},
    from:()=>({select(){return {in:async()=>({data:own,error:null}),gte:async()=>({data:own,error:null})}},insert:async row=>{own.push(row);return {error:null}},
      delete(){return {eq(){return {eq:async(_key,date)=>{own=own.filter(item=>item.meeting_date!==date);return {error:null}}}}}}})};
  const inputs={'meet-first-name':{value:''}};store.set('wu-meet-preview-name','Alt');
  const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:id=>inputs[id]},localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
    setInterval(){},console:{...console,error(){}},Intl,Date:FixedDate,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:null,meetBadge:()=>'',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d,trackUsage:(event,props)=>tracked.push(event+' '+JSON.stringify(props))};
  vm.createContext(context);vm.runInContext(source,context);
  const click=async action=>{handlers.click({target:{closest:()=>({dataset:{action}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
  assert.equal(store.has('wu-meet-preview-name'),false,'früher gespeicherter Vorname wird entfernt');
  await click('meet-preview');
  const screen=context.renderMeet();
  assert.match(screen,/id="meet-first-name"[^>]*value=""/);   // leer, nicht vorausgefüllt
  // Vornamenfeld und Knopf stehen in einer Zeile in der angehefteten Leiste, nirgends ist von E-Mail die Rede.
  assert.match(screen,/<div class="meet-cta"><div class="meet-cta-row"><input id="meet-first-name" aria-label="Dein Vorname"[^>]*placeholder="Dein Vorname"[^>]*><button class="meet-primary" data-action="meet-show-form"[^>]*>Teilnehmen<\/button><\/div><\/div>/);
  assert.doesNotMatch(screen,/E-Mail|Verifizierung|meet-email/);
  // Die Vornamen-Prüfung gilt weiter, vor jeder Anmeldung.
  for(const [value,reason] of [['','name_missing'],['Free Palestine','name_format'],['Hitler','name_blocked']]){
    inputs['meet-first-name'].value=value;await click('meet-show-form');
    assert.equal(anonymous,0);assert.equal(own.length,0);assert.equal(context.meetForm,false,'keine Formularseite mehr');
    assert.match(tracked.at(-1),new RegExp('meet_input_rejected .*'+reason));
    // Die Fehlermeldung steht direkt unter dem Feld (nicht oben auf der Seite), die Eingabe bleibt stehen.
    const shown=context.renderMeet();
    assert.match(shown,/<div class="meet-cta"><p class="meet-notice meet-name-error" role="alert">[^<]+<\/p><div class="meet-cta-row"><input id="meet-first-name"[^>]*><button class="meet-primary" data-action="meet-show-form"/);
    assert.equal(shown.split('role="alert"').length,2,'Meldung nur einmal');
    if(value)assert.ok(shown.includes('value="'+value+'"'),'Eingabe bleibt stehen');
  }
  // Gültiger Vorname: anonymes Konto im Hintergrund, Anmeldung, Vorname wird gemerkt. Kein E-Mail-Code.
  inputs['meet-first-name'].value='  anna ';await click('meet-show-form');
  assert.equal(anonymous,1);assert.equal(otpCalls,0);assert.equal(own.length,1);assert.equal(own[0].first_name,'Anna');   // erster Buchstabe automatisch großassert.equal(own[0].user_id,'anon-1');
  assert.equal(store.has('wu-meet-preview-name'),false,'Vorname wird nicht gespeichert');assert.equal(context.meetForm,false);
  assert.match(context.renderMeet(),/Du bist für diesen Termin angemeldet/);assert.match(tracked.join('\n'),/meet_joined/);
  // Melde-Link (App-Store-Richtlinie 1.2): nur, wenn andere Namen zu sehen sind; führt per E-Mail an die Kontaktadresse.
  assert.doesNotMatch(context.renderMeet(),/meet-report/);   // nur der eigene Name steht da
  // Abmelden: blauer Knopf mit Symbol (Vorgabe 17.11.2026).
  assert.match(context.renderMeet(),/<button class="meet-primary meet-icon-button" data-action="meet-leave">[^<]*<span>Abmelden<\/span><\/button>/);
  // Abmelden: Das Feld ist wieder leer (Vorname jedes Mal neu eingeben). Ohne Eingabe keine Anmeldung.
  await click('meet-leave');assert.equal(own.length,0);
  assert.match(context.renderMeet(),/id="meet-first-name"[^>]*value=""/);
  inputs['meet-first-name'].value='';await click('meet-show-form');assert.equal(own.length,0);
  // Erneut anmelden nutzt dasselbe Konto (kein zweites anonymes Konto).
  inputs['meet-first-name'].value='Anna';await click('meet-show-form');assert.equal(anonymous,1);assert.equal(own.length,1);
  await click('meet-preview');assert.match(context.renderMeet(),/Du bist für diesen Termin angemeldet/);
  // Ist die anonyme Anmeldung in Supabase (noch) ausgeschaltet, erscheint ein verständlicher Hinweis (neues Gerät, kein Konto).
  own=[];session=null;failAnonymous='Anonymous sign-ins are disabled';
  const second={...context,app:{addEventListener:(event,fn)=>{handlers[event]=fn}}};vm.createContext(second);vm.runInContext(source,second);
  await click('meet-preview');inputs['meet-first-name'].value='Mia';await click('meet-show-form');
  assert.equal(anonymous,2);assert.equal(own.length,0);assert.match(second.renderMeet(),/Die Anmeldung ist momentan nicht verfügbar/);
});

test('first letter of the first name is capitalised automatically, also while typing', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const handlers={};
  const client={auth:{getSession:async()=>({data:{session:null},error:null})},from:()=>({select(){return {in:async()=>({data:[],error:null}),gte:async()=>({data:[],error:null})}}})};
  const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:()=>null},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
    setInterval(){},console,Intl,Date:FixedDate,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:null,meetBadge:()=>'',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d};
  vm.createContext(context);vm.runInContext(source,context);
  const type=value=>{const field={id:'meet-first-name',value,selectionStart:value.length,setSelectionRange(a){this.cursor=a}};handlers.input({target:field});return field;};
  for(const [typed,shown] of [['a','A'],['anna','Anna'],['anna-lena','Anna-Lena'],['élodie','Élodie'],['ÖZGE','ÖZGE'],['Max','Max'],['','']])assert.equal(type(typed).value,shown,typed);
  const field=type('mia');assert.equal(field.cursor,3,'Schreibmarke bleibt am Ende');
  const other={id:'meet-date',value:'x'};handlers.input({target:other});assert.equal(other.value,'x');   // andere Felder bleiben unberührt
});

test('UX follow-ups: one active sign-up per device, long names get a message, load errors offer a retry, English alt texts', async () => {
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const handlers={}, store=new Map(); let session={user:{id:'anon-1'}}, own=[], failLoad=false, inserts=0;
  const client={auth:{getSession:async()=>({data:{session},error:null}),signInAnonymously:async()=>({data:{session},error:null})},
    from:()=>({select(){return {in:async()=>failLoad?{data:null,error:new Error('Failed to fetch')}:{data:own,error:null},gte:async()=>failLoad?{data:null,error:new Error('Failed to fetch')}:{data:own,error:null}}},insert:async row=>{inserts++;own.push(row);return {error:null}},
      delete(){return {eq(){return {eq:async(_key,date)=>{own=own.filter(item=>item.meeting_date!==date);return {error:null}}}}}}})};
  const inputs={'meet-first-name':{value:''}};
  const context={window:{supabase:{createClient:()=>client}},navigator:{onLine:false},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:id=>inputs[id]},localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
    setInterval(){},console:{...console,error(){}},Intl,Date:FixedDate,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:null,meetBadge:()=>'',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:(d,o)=>o?.weekday?'Mittwoch, 18. November':d,localize:{label:key=>({'Personen kommen an einem Treffpunkt zum gemeinsamen Essen zusammen':'People meet at a meeting point to eat together','Treffpunkt vor dem Baum bei der Mensa':'Meeting point in front of the tree next to the Mensa'}[key]||key)}};
  vm.createContext(context);vm.runInContext(source,context);
  const click=async action=>{handlers.click({target:{closest:()=>({dataset:{action}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
  const change=async value=>{handlers.change({target:{id:'meet-date',value}});for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));};
  // Offline: klare Meldung und Knopf „Erneut versuchen“, der neu lädt.
  failLoad=true;await click('meet-preview');
  assert.match(context.renderMeet(),/Keine Verbindung\. Bitte prüfe dein Internet und versuche es erneut\./);
  assert.match(context.renderMeet(),/<button class="meet-secondary meet-retry" data-action="meet-retry">Erneut versuchen<\/button>/);
  failLoad=false;await click('meet-retry');assert.doesNotMatch(context.renderMeet(),/Keine Verbindung|meet-retry/);
  // 25 Zeichen: Meldung statt stillem Kürzen; das Feld erlaubt die Eingabe (maxlength 40).
  assert.match(context.renderMeet(),/id="meet-first-name"[^>]*maxlength="40"/);
  inputs['meet-first-name'].value='Abcdefghijklmnopqrstuvwxy';await click('meet-show-form');
  assert.equal(inserts,0);assert.match(context.renderMeet(),/höchstens 20 Zeichen/);
  // Anmeldung für den nächsten Termin, dann zum übernächsten wechseln: Hinweis statt Formular, keine zweite Anmeldung.
  inputs['meet-first-name'].value='Testa';await click('meet-show-form');assert.equal(inserts,1);
  const dates=[...context.renderMeet().matchAll(/<option value="(\d{4}-\d\d-\d\d)"/g)].map(m=>m[1]);assert.equal(dates.length,2);
  await change(dates[1]);
  const other=context.renderMeet();
  assert.match(other,/Du bist bereits für Mittwoch, 18\. November angemeldet\. Melde dich dort ab, wenn du lieber zu diesem Termin kommst\./);
  assert.doesNotMatch(other,/id="meet-first-name"|data-action="meet-show-form"/);
  await click('meet-show-form');assert.equal(inserts,1,'keine zweite Anmeldung');
  // Zurück zum ersten Termin: eigene Anmeldung mit Kreuz, Foto mit englischem Alt-Text (Übersetzung aus dem Katalog).
  await change(dates[0]);
  assert.match(context.renderMeet(),/alt="Meeting point in front of the tree next to the Mensa"/);
  // Kreuz zum Abmelden ist groß genug (CSS) und entfernt die Anmeldung.
  const css=await readFile(new URL('../preview/style.css',import.meta.url),'utf8');
  assert.match(css,/\.meet-own \.meet-remove\{[^}]*padding:12px/);
  await click('meet-leave');assert.equal(own.length,0);assert.match(context.renderMeet(),/Sei die erste Person\./);
});

test('Meet-to-eat weekdays come from the operator settings and drive dates and texts; the default is Wednesday', async () => {
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const start=app.indexOf("const settingsKey='wu-food-settings-v1';"), end=app.indexOf('async function loadSettings(');
  const make=(settings,language='de')=>{const context={localStorage:{getItem:()=>JSON.stringify(settings)},localize:{language}};vm.createContext(context);
    vm.runInContext(app.slice(start,end).replace('const meetWeekdays=','var meetWeekdays=').replace('const meetDaysText=','var meetDaysText='),context);return context;};
  assert.deepEqual([...make({}).meetWeekdays()],[3]);                                     // Vorgabe: jeden Mittwoch
  assert.deepEqual([...make({meet_weekdays:[1,3]}).meetWeekdays()],[1,3]);
  assert.deepEqual([...make({meet_weekdays:['4',2,2,9,0,'x']}).meetWeekdays()],[2,4]);    // nur Montag bis Freitag, sortiert, ohne Doppelte
  assert.deepEqual([...make({meet_weekdays:[]}).meetWeekdays()],[3]);                     // leer -> Vorgabe
  // Vorgabe vom 23.11.2026: "Jeden Mittwoch gemeinsam essen gehen" statt "Mittwochs …".
  assert.equal(make({}).meetDaysText('hint'),'Jeden Mittwoch');
  assert.equal(make({}).meetDaysText('intro'),'Findet jeden Mittwoch um 12:00 Uhr statt.');
  assert.equal(make({meet_weekdays:[1,3]}).meetDaysText('hint'),'Jeden Montag und Mittwoch');
  // Listeneintrag (Vorgabe 23.11.2026): Titel "Meet to eat", darunter "Gemeinsam essen gehen" – ohne Wochentag.
  assert.equal(make({}).meetDaysText('title'),'Gemeinsam essen gehen');
  assert.equal(make({meet_weekdays:[1,3]}).meetDaysText('title'),'Gemeinsam essen gehen');
  assert.equal(make({meet_weekdays:[3]},'en').meetDaysText('title'),'Lunch together');
  // Fußzeile der Liste (Vorgabe 23.11.2026): "Change language" mit kleinem l; bei Umbruch immer zwei und zwei.
  // "Change language" steht unter jedem Menü und deshalb nicht mehr in der Fußzeile der Liste (Vorgabe 23.11.2026).
  assert.doesNotMatch(app.slice(app.indexOf('<footer class="list-footer">'),app.indexOf('</footer>',app.indexOf('<footer class="list-footer">'))),/data-change-language/);
  assert.match(app,/function fitListFooter\(\)\{[^}]*classList\.remove\('two-rows'\)/);
  assert.match(app,/localize\.apply\(app\);fitSourceNote\(\);fitListFooter\(\);/);
  assert.match(app,/<span class="restaurant-name">Meet to eat<\/span><span class="restaurant-type" style="display:block" data-ui-literal>\$\{esc\(meetDaysText\('title'\)\)\}<\/span>/);
  assert.equal(make({meet_weekdays:[1,3]}).meetDaysText('intro'),'Findet jeden Montag und Mittwoch um 12:00 Uhr statt.');
  assert.equal(make({meet_weekdays:[3]},'en').meetDaysText('hint'),'Every Wednesday:');
  assert.equal(make({meet_weekdays:[1,3,5]},'en').meetDaysText('intro'),'Takes place every Monday, Wednesday and Friday at 12:00.');
  // Termine in Meet to eat folgen den Einstellungen (feste Uhr: Dienstag, 17.11.2026).
  const source=await readFile(new URL('../preview/meet-live.js',import.meta.url),'utf8');
  const handlers={};
  const client={auth:{getSession:async()=>({data:{session:null},error:null})},from:()=>({select(){return {in:async()=>({data:[],error:null}),gte:async()=>({data:[],error:null})}}})};
  const context={window:{supabase:{createClient:()=>client}},supabase:'https://example.test',publishableKey:'public',nativePost:()=>false,safeUrl:url=>url,
    app:{addEventListener:(event,fn)=>{handlers[event]=fn}},document:{getElementById:()=>null},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
    setInterval(){},console,Intl,Date:FixedDate,meetPreviewOpen:false,meetSlot:null,meetJoined:false,meetForm:false,selectedId:null,meetBadge:()=>'',
    meetWeekdays:()=>[4],meetDaysText:kind=>kind==='intro'?'Findet jeden Donnerstag statt.':'Donnerstags',
    renderMeet(){},render(){},icon:()=>'',esc:s=>String(s),dateValue:d=>d};
  vm.createContext(context);vm.runInContext(source,context);
  handlers.click({target:{closest:()=>({dataset:{action:'meet-preview'}})},preventDefault(){},stopImmediatePropagation(){}});for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));
  const screen=context.renderMeet();
  assert.deepEqual([...screen.matchAll(/<option value="(\d{4}-\d\d-\d\d)"/g)].map(m=>m[1]),['2026-11-19','2026-11-26']);   // nur Donnerstage
  assert.match(screen,/essen\. <span data-ui-literal>Findet jeden Donnerstag statt\.<\/span><\/p>/);
  // Datenbank: der Wochentag wird gegen dieselbe Einstellung geprüft; nur der Admin darf sie ändern.
  const sql=await readFile(new URL('../../wu-lunch/supabase/20261122_settings.sql',import.meta.url),'utf8');
  assert.match(sql,/from public\.lunch_settings where key = 'meet_weekdays'/);
  assert.match(sql,/for insert to authenticated with check \(\(select private\.is_lunch_admin\(\)\)\)/);
  assert.match(sql,/grant select on public\.lunch_settings to anon, authenticated/);
  assert.doesNotMatch(sql,/grant (insert|update|all)[^;]*\banon\b/);
});

test('manual update notice: only in the installed app, only for older versions, dismissible, texts from the operator', async () => {
  const app=await readFile(new URL('../preview/app.js',import.meta.url),'utf8');
  const start=app.indexOf('const versionParts='), end=app.indexOf('function paintUpdateNotice(');
  const make=(notice,info,language='de')=>{const context={appSettings:{update_notice:notice},window:{WU_APP:info},localize:{language},esc:s=>String(s).replace(/</g,'&lt;')};vm.createContext(context);
    vm.runInContext(app.slice(start,end).replace('const versionOlder=','var versionOlder='),context);return context;};
  const on={enabled:true,min_version:'0.5.7',message_de:'',message_en:''};
  const older=make(on,{version:'0.5.6',platform:'android'});
  assert.equal(older.versionOlder('0.5.6','0.5.7'),true);assert.equal(older.versionOlder('0.5.10','0.5.9'),false);assert.equal(older.versionOlder('0.5.7','0.5.7'),false);assert.equal(older.versionOlder('0.9.9','1.0.0'),true);
  assert.match(older.updateNotice(),/Es gibt eine neue Version von WU Food\. Bitte aktualisiere die App\./);
  assert.match(older.updateNotice(),/data-action="update-now">Jetzt aktualisieren<.*data-action="update-later">Später</);
  assert.equal(make(on,{version:'0.5.7',platform:'ios'}).updateNotice(),'');            // aktuelle Version: nichts
  assert.equal(make(on,undefined).updateNotice(),'');                                   // Web-Vorschau ohne Versionsangabe: nichts
  assert.equal(make({...on,enabled:false},{version:'0.5.6'}).updateNotice(),'');        // ausgeschaltet
  assert.equal(make({...on,min_version:'bald'},{version:'0.5.6'}).updateNotice(),'');   // ungültige Angabe
  assert.match(make({...on,message_de:'Wichtig: <b>bitte</b> aktualisieren'},{version:'0.5.6'}).updateNotice(),/Wichtig: &lt;b>bitte&lt;\/b> aktualisieren/);   // eigener Text, als Text ausgegeben
  assert.match(make({...on,message_en:'Please update'},{version:'0.5.6'},'en').updateNotice(),/Please update<\/p>.*Update now<.*Later</);
  // „Später“ blendet bis zum nächsten Start aus; der Store-Link steht fest in der App, nicht in der Nachricht.
  assert.match(app,/case'update-later':[^\n]*updateNoticeDismissed=true/);
  assert.match(app,/case'update-now':[^\n]*nativePost\('open-store'\)/);
  const native=await readFile(new URL('../App.tsx',import.meta.url),'utf8');
  assert.match(native,/window\.WU_APP=\{version:'\$\{appVersion\}'/);
  assert.match(native,/apps\.apple\.com\/app\/id6836345799/);assert.match(native,/market:\/\/details\?id=at\.startit\.wufood/);
});
