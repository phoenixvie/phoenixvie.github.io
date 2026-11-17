/* Meet-to-eat web preview. Uses a separate session from the website admin. */
(() => {
  const returningFromLink = /(?:^|[#&])access_token=/.test(window.location?.hash || '');
  const emailRedirectTo = 'https://phoenixvie.github.io/wu-lunch-app/preview/';
  const client = window.supabase?.createClient(supabase, publishableKey, {
    auth: { storageKey: 'wu-meet-preview-auth-v1', persistSession: true, autoRefreshToken: true }
  });
  const state = { session: null, participants: [], own: [], pendingEmail: '', pendingName: '', registrationDate: null, selectedDate: null, step: 'form', error: '', busy: false, loaded: false };
  const viennaClock = (now = new Date()) => ({
    today: new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Vienna', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now),
    time: new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Vienna', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now)
  });
  const registrationOpen = (day, now = new Date()) => {
    const {today,time}=viennaClock(now);
    return !!day && (day > today || (day === today && time < '12:06'));
  };
  const slotDates = () => {
    const {today,time}=viennaClock();
    const d = new Date(today + 'T12:00:00Z'), out = [];
    if (time >= '14:00') d.setUTCDate(d.getUTCDate() + 1);
    while (out.length < 5) { if ([1, 3].includes(d.getUTCDay())) out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
    return out;
  };
  // Vorgabe des Betreibers (17.11.2026): Gezeigt wird der nächste Termin – am Termintag bis
  // 14:00 Uhr, auch wenn die Anmeldung schon um 12:05 schließt; danach rückt der folgende nach.
  // Im Datumsfeld (Auswahlliste) ist immer auch der Termin danach wählbar.
  const dateOptions = () => slotDates().slice(0, 2);
  const date = () => {
    const options = dateOptions();
    return options.includes(state.selectedDate) ? state.selectedDate : options[0];
  };
  // Texte kommen aus dem gemeinsamen Katalog (wu-lunch/i18n.js): Deutsch ist die
  // Vorlage, Englisch und Admin-Änderungen werden dort gepflegt. {platzhalter}
  // werden hier eingesetzt.
  const text = (key, values = {}, german = key) => {
    const found = typeof localize !== 'undefined' ? localize?.label?.(key) : null;
    let value = found && found !== key ? found : german;
    for (const [name, replacement] of Object.entries(values)) value = value.replace('{' + name + '}', replacement);
    return value;
  };
  const redraw = () => { if (meetPreviewOpen) render(); };
  const showError = e => { console.error('Meet preview:', e); state.error = 'Das hat nicht funktioniert. Bitte versuche es erneut.'; };
  const getName = () => { try { return localStorage.getItem('wu-meet-preview-name') || ''; } catch { return ''; } };
  const setName = name => { try { localStorage.setItem('wu-meet-preview-name', name); } catch {} };
  async function refresh() {
    if (!client) { state.error = 'Die Anmeldung ist derzeit nicht verfügbar.'; state.loaded = true; redraw(); return; }
    try {
      const auth = await client.auth.getSession(); if (auth.error) throw auth.error;
      state.session = auth.data.session;
      const days = slotDates();
      const [people, own] = await Promise.all([
        client.from('meet_preview_participants').select('meeting_date,first_name').in('meeting_date', days),
        state.session ? client.from('meet_preview_registrations').select('meeting_date,first_name').gte('meeting_date', viennaClock().today) : Promise.resolve({data: [], error: null})
      ]);
      if (people.error || own.error) throw people.error || own.error;
      state.participants = people.data || []; state.own = own.data || []; state.loaded = true; state.error = '';
      meetJoined = !!state.own.find(item => item.meeting_date === date());
    } catch (e) { state.loaded = true; showError(e); }
    redraw();
  }
  const dateField = selected => `<div class="meet-fact">${icon('calendar_today')}<div><strong><label for="meet-date">Datum</label></strong><span class="meet-date-picker"><select id="meet-date">${dateOptions().map(day => `<option value="${day}" ${day === selected ? 'selected' : ''}>${esc(dateValue(day,{weekday:'long',day:'numeric',month:'long'}))}</option>`).join('')}</select></span></div></div>`;
  // Schlichte Zeichnung über dem Text (Vorgabe 17.11.2026): Personen stehen zusammen und reden über Essen;
  // bewusst zurückhaltend in Blau- und Grautönen, weißer Grund.
  const groupArt = '<div class="meet-art"><svg viewBox="0 0 320 146" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Vier Personen stehen zusammen und unterhalten sich über Essen"><path d="M56 142h208" stroke="#dbe4ee" stroke-width="2" stroke-linecap="round"/><circle cx="88" cy="64" r="12" fill="#1f3d5c"/><path d="M71 142V98a17 17 0 0 1 34 0V142z" fill="#1f3d5c"/><circle cx="132" cy="60" r="12" fill="#087cf4"/><path d="M115 142V94a17 17 0 0 1 34 0V142z" fill="#087cf4"/><circle cx="188" cy="62" r="12" fill="#6f8fb3"/><path d="M171 142V96a17 17 0 0 1 34 0V142z" fill="#6f8fb3"/><circle cx="232" cy="66" r="12" fill="#b3c4d6"/><path d="M215 142V100a17 17 0 0 1 34 0V142z" fill="#b3c4d6"/><rect x="71" y="5" width="66" height="38" rx="12" fill="#fff" stroke="#9fb3c8" stroke-width="1.5"/><path d="M112 43.5l6 9 6-9" fill="#fff" stroke="#9fb3c8" stroke-width="1.5" stroke-linejoin="round"/><path d="M113.2 43h9.6" stroke="#fff" stroke-width="2.6"/><path d="M94 13v7a4 4 0 0 0 8 0v-7M98 13v23M114 36V13c-5 3-6 10-1 13" fill="none" stroke="#1f3d5c" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><rect x="181" y="5" width="66" height="38" rx="12" fill="#fff" stroke="#9fb3c8" stroke-width="1.5"/><path d="M196 43.5l6 9 6-9" fill="#fff" stroke="#9fb3c8" stroke-width="1.5" stroke-linejoin="round"/><path d="M197.2 43h9.6" stroke="#fff" stroke-width="2.6"/><path d="M199 24h30a15 15 0 0 1-30 0zM207 12c-2 2 2 4 0 6M214 12c-2 2 2 4 0 6M221 12c-2 2 2 4 0 6" fill="none" stroke="#1f3d5c" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>';
  const fact = (symbol, label, value) => `<div class="meet-fact">${icon(symbol)}<div><strong>${label}</strong><span>${value}</span></div></div>`;
  function renderLive() {
    const selected = date(), own = state.own.find(item => item.meeting_date === selected);
    meetJoined = !!own;
    const error = state.error ? `<p class="meet-notice" role="alert">${esc(state.error)}</p>` : '';
    const header = `<header class="top detail"><button class="back" data-action="meet-back" aria-label="Zurück">${icon('arrow_back')}</button><h1>${meetForm ? esc(text('Meet to eat: Anmeldung', {}, 'Anmeldung')) : 'Meet to eat'}</h1></header>`;
    if (meetForm) return `${header}<div class="body"><div class="scroll meet-content">${error}${state.step === 'code' ? `<p>${esc(text('Wir haben einen Bestätigungscode an {email} gesendet. Bitte gib den Code hier ein. Der Link in der E-Mail und der Code sind nur einmal verwendbar.', {email: state.pendingEmail}))}</p><a href="https://outlook.cloud.microsoft" data-action="meet-open-url" class="meet-mail-link" target="_blank" rel="noopener noreferrer">WU-Mail öffnen</a><label>Bestätigungscode<input id="meet-code" inputmode="numeric" autocomplete="one-time-code" maxlength="12"></label><button class="meet-primary" data-action="meet-verify" ${state.busy?'disabled':''}>Code bestätigen und anmelden</button><button class="meet-secondary" data-action="meet-resend-code" ${state.busy?'disabled':''}>Neuen Code anfordern</button>` : state.step === 'name' ? `<p>Deine E-Mail-Adresse ist bestätigt. Dein Vorname und der Termin sind für alle sichtbar.</p><label>Vorname<input id="meet-first-name" autocomplete="given-name" maxlength="60" placeholder="Max" value="${esc(state.pendingName || getName())}"></label><button class="meet-primary" data-action="meet-confirm-name" ${state.busy?'disabled':''}>Verbindlich anmelden</button>` : `<p>Gib deinen Vornamen und deine E-Mail-Adresse ein. Du bekommst einen Code per E-Mail und gibst ihn hier ein. Erst dann bist du angemeldet. Dein Vorname und der Termin sind für alle sichtbar.</p><label>Vorname<input id="meet-first-name" autocomplete="given-name" maxlength="60" placeholder="Max" value="${esc(state.pendingName || getName())}"></label><label>E-Mail-Adresse<input id="meet-email" type="email" autocomplete="email" placeholder="mustermann@wu.ac.at" value="${esc(state.pendingEmail)}"></label><button class="meet-primary" data-action="meet-send-code" ${state.busy?'disabled':''}>Verifizierung via Mail starten</button>`}</div></div>`;
    const people = state.participants.filter(p => p.meeting_date === selected);
    let ownRemoved = false;
    const names = people.filter(p => { if (own && !ownRemoved && p.first_name === own.first_name) { ownRemoved = true; return false; } return true; });
    const entries = names.map(p => `<div class="meet-person">${icon('person')}<span data-ui-literal>${esc(p.first_name)}</span></div>`).join('') + (own ? `<div class="meet-person">${icon('person')}<span data-ui-literal>${esc(own.first_name)}</span><button class="meet-remove" data-action="meet-leave" aria-label="Meine Anmeldung entfernen">${icon('close')}</button></div>` : '');
    const mapLink = 'https://www.google.com/maps/search/?api=1&amp;query=48.21289788048291%2C16.409449359855884';
    // Vor der Anmeldung steht der Hinweis fett da, damit klar ist, dass hier noch etwas folgt.
    const location = own ? 'Vor dem Baum direkt bei der Mensa' : '<b>Info nach Anmeldung</b>';
    // Foto und Karte des Treffpunkts erscheinen erst nach der eigenen Anmeldung;
    // vorher wird der Bereich gar nicht angezeigt (kein unscharfer Platzhalter mehr).
    const reveal = own ? `<section class="meet-reveal"><h3>Treffpunkt auf der WU</h3><p><strong>Vor dem Baum direkt bei der Mensa</strong></p><img class="meet-photo-visible" src="./meeting-point.webp" width="1200" height="1361" alt="Treffpunkt vor dem Baum bei der Mensa" onerror="this.onerror=null;this.src='./meeting-point.png'"><div id="meet-map" class="meet-map meet-map-visible"></div><a class="meet-map-button" data-action="meet-open-url" href="${mapLink}" target="_blank" rel="noopener noreferrer">Google Maps öffnen</a></section>` : '';
    return `${header}<div class="body"><div class="scroll meet-content" id="meet-screen">${error}${groupArt}<p>Triff dich am WU Campus mit anderen Studierenden und geht gemeinsam als Gruppe Mittag essen. Findet jeden Montag und Mittwoch statt.</p><section class="meet-facts">${dateField(selected)}${fact('schedule','Uhrzeit am Treffpunkt','12:00 Uhr')}${fact('directions_walk','Gemeinsam losgehen','12:05 Uhr')}${fact('location_on','Treffpunkt auf der WU',location)}${fact('school','Teilnehmer','WU-Studenten Gruppe')}</section>${entries ? `<h3>Bereits angemeldet</h3>${entries}` : ''}${own ? '<p class="meet-confirm">Du bist für diesen Termin angemeldet. Bitte melde dich aus Rücksicht auf die anderen ab, wenn du doch nicht kommen kannst.</p><button class="meet-secondary" data-action="meet-leave">' + esc(text('Meet to eat: Abmelden', {}, 'Abmelden')) + '</button>' : !registrationOpen(selected) ? '<p class="meet-notice">Die Anmeldung für diesen Termin ist geschlossen.</p>' : `<button class="meet-primary" data-action="meet-show-form" ${state.busy || !state.loaded ? 'disabled' : ''}>Verbindlich anmelden</button>`}${reveal}</div></div>`;
  }
  async function join(name, meetingDate) {
    if (!state.session || !name.trim()) { meetForm = true; state.step = 'form'; return; }
    if (!registrationOpen(meetingDate)) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; return; }
    const {error} = await client.from('meet_preview_registrations').insert({user_id:state.session.user.id, meeting_date:meetingDate, first_name:name.trim().slice(0,60)});
    if (error && error.code !== '23505') throw error;
    setName(name.trim().slice(0,60)); meetForm = false; await refresh();
  }
  async function action(target) {
    const a = target.dataset.action;
    if (a === 'meet-preview') { meetPreviewOpen=true; meetSlot=0; meetForm=false; state.error=''; state.selectedDate=null; render(); await refresh(); return; }
    if (a === 'meet-back') { state.error=''; if (meetForm) meetForm=false; else { meetSlot=null; meetPreviewOpen=false; } render(); return; }
    if (state.busy) return;
    state.error='';
    if (a === 'meet-show-form') state.registrationDate=date();
    if (['meet-show-form','meet-send-code','meet-resend-code','meet-verify','meet-confirm-name'].includes(a) && !registrationOpen(state.registrationDate)) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; render(); return; }
    if (a === 'meet-show-form' && (!state.session || !getName())) { state.step=state.session?'name':'form'; meetForm=true; render(); return; }
    if (a === 'meet-confirm-name') { state.pendingName=document.getElementById('meet-first-name').value.trim(); if (!state.pendingName) { state.error='Bitte gib deinen Vornamen ein.'; render(); return; } }
    if (a === 'meet-send-code') {
      state.pendingName = document.getElementById('meet-first-name').value.trim();
      state.pendingEmail = document.getElementById('meet-email').value.trim();
      if (!state.pendingName || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(state.pendingEmail)) { state.error='Bitte gib einen Vornamen und eine gültige E-Mail-Adresse ein.'; render(); return; }
    }
    const code = a === 'meet-verify' ? document.getElementById('meet-code').value.trim() : '';
    state.busy=true; render();
    try {
      if (a === 'meet-show-form') await join(getName(),state.registrationDate);
      if (a === 'meet-send-code' || a === 'meet-resend-code') { const {error} = await client.auth.signInWithOtp({email:state.pendingEmail,options:{emailRedirectTo}}); if(error) throw error; state.step='code'; }
      if (a === 'meet-verify') { const {data,error} = await client.auth.verifyOtp({email:state.pendingEmail,token:code,type:'email'}); if(error) throw error; state.session=data.session; await join(state.pendingName,state.registrationDate); }
      if (a === 'meet-confirm-name') await join(state.pendingName,state.registrationDate);
      if (a === 'meet-leave') { const {error}=await client.from('meet_preview_registrations').delete().eq('user_id',state.session.user.id).eq('meeting_date',date()); if(error) throw error; await refresh(); }
    } catch(e) {
      if (['meet-show-form','meet-send-code','meet-resend-code','meet-verify','meet-confirm-name'].includes(a) && !registrationOpen(state.registrationDate)) {
        state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false;
      }
      else if (e?.message?.includes('meet_registration_closed')) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; }
      else if (a === 'meet-verify') { state.error='Der Code ist ungültig oder bereits verwendet. Bitte fordere einen neuen Code an.'; } else showError(e);
    }
    finally { state.busy=false; render(); }
  }
  renderMeet = renderLive;
  app.addEventListener('click', e => {
    const target=e.target.closest('[data-action]');
    if (!target || !['meet-preview','meet-back','meet-show-form','meet-send-code','meet-resend-code','meet-verify','meet-confirm-name','meet-leave','meet-open-url'].includes(target.dataset.action)) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (target.dataset.action === 'meet-open-url') { const url=safeUrl(target.href); if (url && !nativePost('open-source',{url,title:'Meet to eat'})) window.open(url,'_blank','noopener,noreferrer'); return; }
    void action(target);
  }, true);
  // Auswahl eines anderen Termins im Datumsfeld.
  app.addEventListener('change', e => {
    if (e.target?.id !== 'meet-date') return;
    state.selectedDate = e.target.value; state.error = '';
    meetJoined = !!state.own.find(item => item.meeting_date === date());
    render();
  });
  if (returningFromLink) { meetPreviewOpen=true; meetSlot=0; void refresh(); }
  setInterval(() => { if (meetPreviewOpen && !meetForm && !state.busy) void refresh(); }, 30000);
})();

