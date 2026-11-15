/* Meet-to-eat web preview. Uses a separate session from the website admin. */
(() => {
  const client = window.supabase?.createClient(supabase, publishableKey, {
    auth: { storageKey: 'wu-meet-preview-auth-v1', persistSession: true, autoRefreshToken: true }
  });
  const state = { session: null, participants: [], own: [], pendingEmail: '', pendingName: '', registrationDate: null, step: 'form', error: '', busy: false, loaded: false };
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
    if (time >= '23:00') d.setUTCDate(d.getUTCDate() + 1);
    while (out.length < 3) { if ([1, 3].includes(d.getUTCDay())) out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
    return out;
  };
  const date = () => slotDates()[meetSlot];
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
        state.session ? client.from('meet_preview_registrations').select('meeting_date,first_name').in('meeting_date', days) : Promise.resolve({data: [], error: null})
      ]);
      if (people.error || own.error) throw people.error || own.error;
      state.participants = people.data || []; state.own = own.data || []; state.loaded = true; state.error = '';
      meetJoined = !!state.own.find(item => item.meeting_date === date());
    } catch (e) { state.loaded = true; showError(e); }
    redraw();
  }
  const fact = (symbol, label, value) => `<div class="meet-fact">${icon(symbol)}<div><strong>${label}</strong><span>${value}</span></div></div>`;
  function renderLive() {
    const days = slotDates(), selected = days[meetSlot], own = state.own.find(item => item.meeting_date === selected);
    meetJoined = !!own;
    const error = state.error ? `<p class="meet-notice" role="alert">${esc(state.error)}</p>` : '';
    const header = `<header class="top detail"><button class="back" data-action="meet-back" aria-label="Zurück">${icon('arrow_back')}</button><h1>${meetSlot === null ? 'Meet to eat' : meetForm ? 'Anmeldung' : 'Gemeinsam essen'}</h1></header>`;
    if (meetSlot === null) return `${header}<div class="body"><div class="scroll meet-slots"><p class="meet-intro">Triff dich am WU Campus mit anderen Studierenden und geht gemeinsam als Gruppe Mittag essen.</p>${error}${days.map((day, i) => `<button class="restaurant-row" data-action="meet-slot" data-slot="${i}"><span class="logo logo-fallback meet-time-logo">${icon('schedule')}</span><span class="restaurant-copy"><span class="restaurant-name">${esc(dateValue(day, {weekday:'long',day:'numeric',month:'long'}))} · 12:00 Uhr</span><span class="restaurant-type" style="display:block">${state.loaded ? state.participants.filter(p => p.meeting_date === day).length + ' Personen angemeldet' : 'Wird geladen …'}</span></span>${icon('chevron_right','chevron')}</button>`).join('')}</div></div>`;
    if (meetForm) return `${header}<div class="body"><div class="scroll meet-content"><h3>Anmelden</h3>${error}${state.step === 'code' ? `<p>Wir haben einen Bestätigungscode an ${esc(state.pendingEmail)} gesendet. Bitte gib ihn hier ein.</p><label>Bestätigungscode<input id="meet-code" inputmode="numeric" autocomplete="one-time-code" maxlength="12"></label><button class="meet-primary" data-action="meet-verify" ${state.busy?'disabled':''}>Code bestätigen und anmelden</button>` : `<p>Wir bestätigen deine E-Mail-Adresse. Eine Prüfung der WU-Zugehörigkeit erfolgt derzeit nicht. Dein Vorname und der Termin sind für alle sichtbar.</p><label>Vorname<input id="meet-first-name" autocomplete="given-name" maxlength="60" value="${esc(state.pendingName || getName())}"></label><label>E-Mail-Adresse<input id="meet-email" type="email" autocomplete="email" value="${esc(state.pendingEmail)}"></label><button class="meet-primary" data-action="meet-send-code" ${state.busy?'disabled':''}>Bestätigungscode senden</button>`}</div></div>`;
    const people = state.participants.filter(p => p.meeting_date === selected);
    let ownRemoved = false;
    const names = people.filter(p => { if (own && !ownRemoved && p.first_name === own.first_name) { ownRemoved = true; return false; } return true; });
    const entries = names.map(p => `<div class="meet-person">${icon('person')}<span>${esc(p.first_name)}</span></div>`).join('') + (own ? `<div class="meet-person">${icon('person')}<span>${esc(own.first_name)}</span><button class="meet-remove" data-action="meet-leave" aria-label="Meine Anmeldung entfernen">${icon('close')}</button></div>` : '');
    const mapLink = 'https://www.google.com/maps/search/?api=1&amp;query=WU%20Mensa%20Welthandelsplatz%201%20Wien';
    const location = own ? `Vor der Mensa · <a href="${mapLink}">Google Maps öffnen</a>` : 'Angabe nach Anmeldung';
    const photos = own ? `<p><strong>Vor der Mensa</strong> · <a href="${mapLink}">Google Maps öffnen</a></p><div class="meet-photo-visible" role="img" aria-label="Symbolbild des Campus"></div><small>Symbolbild</small><div id="meet-map" class="meet-map meet-map-visible"></div>` : `<div class="meet-locked-photo" aria-label="Foto nach Anmeldung sichtbar"><div class="meet-photo"></div><span class="meet-locked-label">${icon('lock')} Nach Anmeldung sichtbar</span></div><div class="meet-locked-map" aria-label="Karte nach Anmeldung sichtbar"><div id="meet-map" class="meet-map"></div><span class="meet-locked-label">${icon('lock')} Karte nach Anmeldung sichtbar</span></div><small>Symbolbild</small>`;
    const tabs = `<div class="weekday-strip" aria-label="Termine">${days.map((day, i) => `<button type="button" class="weekday ${i === meetSlot ? 'active' : ''}" data-action="meet-select" data-slot="${i}" aria-label="${esc(dateValue(day,{weekday:'long',day:'numeric',month:'long'}))}" ${i === meetSlot ? 'aria-current="date"' : ''}><span>${esc(dateValue(day,{weekday:'long'}))}</span><span class="weekday-date">${esc(dateValue(day,{day:'2-digit',month:'2-digit'}))}</span></button>`).join('')}</div><div class="day-dots" aria-label="Wischanzeige">${days.map((day,i) => `<button type="button" class="day-dot ${i === meetSlot ? 'active' : ''}" data-action="meet-select" data-slot="${i}" aria-label="${esc(dateValue(day,{weekday:'long',day:'numeric',month:'long'}))}" ${i === meetSlot ? 'aria-current="date"' : ''}></button>`).join('')}</div>`;
    return `${header}<div class="body"><div class="scroll meet-content" id="meet-screen">${tabs}${error}<h3>Nächstes gemeinsames Essen</h3><p>Triff dich am WU Campus mit anderen Studierenden und geht gemeinsam als Gruppe Mittag essen.</p><section class="meet-facts">${fact('calendar_today','Datum',esc(dateValue(selected,{weekday:'long',day:'numeric',month:'long'})))}${fact('schedule','Uhrzeit am Treffpunkt','12:00 Uhr')}${fact('directions_walk','Gemeinsam losgehen','12:05 Uhr')}${fact('location_on','Treffpunkt auf der WU',location)}${fact('school','Teilnehmer','WU-Studenten Gruppe')}</section>${entries ? `<h3>Bereits angemeldet</h3>${entries}` : ''}${own ? '<p class="meet-confirm">Du bist für diesen Termin angemeldet.</p><button class="meet-secondary" data-action="meet-leave">Abmelden</button>' : registrationOpen(selected) ? `<button class="meet-primary" data-action="meet-show-form" ${state.busy || !state.loaded ? 'disabled' : ''}>Verbindlich anmelden</button>` : '<p class="meet-notice">Die Anmeldung für diesen Termin ist geschlossen.</p>'}<section class="meet-reveal"><h3>Treffpunkt auf der WU</h3>${photos}</section></div></div>`;
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
    if (a === 'meet-preview') { meetPreviewOpen=true; meetSlot=0; meetForm=false; state.error=''; render(); await refresh(); return; }
    if (a === 'meet-back') { state.error=''; if (meetForm) meetForm=false; else { meetSlot=null; meetPreviewOpen=false; } render(); return; }
    if (a === 'meet-slot' || a === 'meet-select') { if (state.busy) return; meetSlot=Math.max(0,Math.min(slotDates().length-1,Number(target.dataset.slot))); meetForm=false; state.error=''; render(); return; }
    if (state.busy) return;
    state.error='';
    if (a === 'meet-show-form') state.registrationDate=date();
    if (['meet-show-form','meet-send-code','meet-verify'].includes(a) && !registrationOpen(state.registrationDate)) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; render(); return; }
    if (a === 'meet-show-form' && (!state.session || !getName())) { state.step='form'; meetForm=true; render(); return; }
    if (a === 'meet-send-code') {
      state.pendingName = document.getElementById('meet-first-name').value.trim();
      state.pendingEmail = document.getElementById('meet-email').value.trim();
      if (!state.pendingName || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(state.pendingEmail)) { state.error='Bitte gib einen Vornamen und eine gültige E-Mail-Adresse ein.'; render(); return; }
    }
    const code = a === 'meet-verify' ? document.getElementById('meet-code').value.trim() : '';
    state.busy=true; render();
    try {
      if (a === 'meet-show-form') await join(getName(),state.registrationDate);
      if (a === 'meet-send-code') { const {error} = await client.auth.signInWithOtp({email:state.pendingEmail}); if(error) throw error; state.step='code'; }
      if (a === 'meet-verify') { const {data,error} = await client.auth.verifyOtp({email:state.pendingEmail,token:code,type:'email'}); if(error) throw error; state.session=data.session; await join(state.pendingName,state.registrationDate); }
      if (a === 'meet-leave') { const {error}=await client.from('meet_preview_registrations').delete().eq('user_id',state.session.user.id).eq('meeting_date',date()); if(error) throw error; await refresh(); }
    } catch(e) {
      if (['meet-show-form','meet-send-code','meet-verify'].includes(a) && !registrationOpen(state.registrationDate)) {
        state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false;
      } else showError(e);
    }
    finally { state.busy=false; render(); }
  }
  renderMeet = renderLive;
  app.addEventListener('click', e => {
    const target=e.target.closest('[data-action]');
    if (!target || !['meet-preview','meet-back','meet-slot','meet-select','meet-show-form','meet-send-code','meet-verify','meet-leave'].includes(target.dataset.action)) return;
    e.preventDefault(); e.stopImmediatePropagation(); void action(target);
  }, true);
  let touch = null;
  app.addEventListener('touchstart', e => {
    touch = meetPreviewOpen && !meetForm && !state.busy && e.touches.length === 1 && e.target.closest('#meet-screen') ? {x:e.changedTouches[0].screenX,y:e.changedTouches[0].screenY} : null;
  }, {passive:true});
  app.addEventListener('touchend', e => {
    if (!touch) return;
    const dx=e.changedTouches[0].screenX-touch.x, dy=e.changedTouches[0].screenY-touch.y;
    touch=null;
    if (Math.abs(dx)>60 && Math.abs(dx)>Math.abs(dy)*1.2) {
      const next=Math.max(0,Math.min(slotDates().length-1,meetSlot+(dx<0?1:-1)));
      if (next!==meetSlot) { e.preventDefault(); meetSlot=next; state.error=''; render(); }
    }
  }, {passive:false});
  app.addEventListener('touchcancel', () => { touch=null; }, {passive:true});
  setInterval(() => { if (meetPreviewOpen && !meetForm && !state.busy) void refresh(); }, 30000);
})();

