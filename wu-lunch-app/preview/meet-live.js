/* Meet-to-eat web preview. Uses a separate session from the website admin. */
(() => {
  const returningFromLink = /(?:^|[#&])access_token=/.test(window.location?.hash || '');
  const emailRedirectTo = 'https://phoenixvie.github.io/wu-lunch-app/preview/';
  const client = window.supabase?.createClient(supabase, publishableKey, {
    auth: { storageKey: 'wu-meet-preview-auth-v1', persistSession: true, autoRefreshToken: true }
  });
  // Bestätigung per E-Mail-Code: PAUSIERT (Vorgabe des Betreibers, 17.11.2026). Angemeldet wird vorerst nur mit dem
  // Vornamen direkt auf der Seite von Meet to eat; im Hintergrund entsteht dafür ein anonymes Konto (Supabase
  // „Anonymous sign-ins“), damit jede Person nur ihre eigene Anmeldung sieht und löschen kann. Der komplette Ablauf
  // mit E-Mail-Code bleibt unverändert im Code; true schaltet ihn wieder ein.
  const emailVerification = false;
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
    // Wochentage kommen aus den Einstellungen des Betreibers (Admin), Vorgabe Mittwoch.
    const weekdays = typeof meetWeekdays === 'function' ? meetWeekdays() : [3];
    while (out.length < 5) { if (weekdays.includes(d.getUTCDay())) out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
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
  // Vornamen-Prüfung (Vorgabe 17.11.2026): Der Vorname ist für alle sichtbar. Damit dort keine Botschaften,
  // Beschimpfungen oder Parolen stehen, wird nur eine Namensform angenommen (ein Name aus Buchstaben oder ein
  // Doppelname mit Bindestrich, höchstens 20 Zeichen, keine Leerzeichen) und eine kleine Sperrliste geprüft. Das fängt das Offensichtliche ab,
  // nicht jede kreative Schreibweise – verbindlich ist zusätzlich die Datenbank-Regel in meet-preview-ohne-email.sql.
  const blockedParts = ['nazi','nazis','heil','sieg','hitler','himmler','goebbels','stalin','putin','trump','biden','hamas','afd','fpo','fpoe','ovp','oevp','spo','spoe','kpo','kpoe','neos','antifa','arsch','hure','nutte','sex','porn','porno','anal','idiot','trottel','depp','spast','kanake','kanak','jude','juden','free','palestine','palastina','palaestina','israel','gaza','ukraine','russia','russland','krieg','war','stop','vote','wahl','waehlt','boykott','boycott','fck','acab','maga','blm'];
  const blockedInside = ['fuck','bitch','fotze','wichser','schlampe','schwuchtel','nigger','nigga','hitler','arschloch','hurensohn','scheiss','penis','vagina','faschis','kommunis'];
  const rejection = problem => /nicht möglich/.test(problem) ? 'name_blocked' : /nur deinen Vornamen/.test(problem) ? 'name_format' : 'name_missing';
  // Erster Buchstabe automatisch groß, bei Doppelnamen auch nach dem Bindestrich (anna-lena -> Anna-Lena); der Rest bleibt,
  // wie eingegeben (Vorgabe des Betreibers, 17.11.2026).
  const capitalName = value => String(value || '').replace(/(^|-)(\p{Ll})/gu, (_, start, letter) => start + letter.toLocaleUpperCase('de-AT'));
  const tidyName = value => capitalName(String(value || '').trim().replace(/\s+/g, ' ').slice(0, 60));
  const nameProblem = value => {
    const name = tidyName(value);
    if (!name) return 'Bitte gib deinen Vornamen ein.';
    if (name.length > 20 || !/^\p{L}{2,}(?:-\p{L}{2,})?$/u.test(name)) return 'Bitte gib nur deinen Vornamen ein (nur Buchstaben, höchstens 20 Zeichen, Doppelnamen mit Bindestrich).';
    const plain = name.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss');
    if (plain.split('-').some(part => blockedParts.includes(part)) || blockedInside.some(word => plain.replace(/-/g, '').includes(word))) return 'Dieser Name ist hier nicht möglich. Bitte gib deinen echten Vornamen ein.';
    return '';
  };
  // Anonyme Nutzungsstatistik (nur in der installierten App, feste Wertelisten, nie Namen oder Adressen).
  const track = (event, props = {}) => { try { if (typeof trackUsage === 'function') trackUsage(event, props); } catch {} };
  const slotOf = day => day === dateOptions()[0] ? 'next' : 'following';
  const redraw = () => { if (meetPreviewOpen) render(); };
  // Ladefehler: offline klar benennen und einen Knopf „Erneut versuchen“ anbieten (UX-Test 22.11.2026).
  const showError = e => { console.error('Meet preview:', e); const offline = typeof navigator !== 'undefined' && navigator.onLine === false; state.error = offline ? 'Keine Verbindung. Bitte prüfe dein Internet und versuche es erneut.' : 'Das hat nicht funktioniert. Bitte versuche es erneut.'; state.retry = true; };
  const getName = () => { try { return localStorage.getItem('wu-meet-preview-name') || ''; } catch { return ''; } };
  // Ohne E-Mail-Bestätigung wird der Vorname NICHT gespeichert, sondern jedes Mal neu eingegeben (Vorgabe des
  // Betreibers, 17.11.2026); ein früher gespeicherter Vorname wird entfernt. Mit E-Mail-Bestätigung gilt das alte Verhalten.
  const setName = name => { if (!emailVerification) return; try { localStorage.setItem('wu-meet-preview-name', name); } catch {} };
  if (!emailVerification) { try { localStorage.removeItem('wu-meet-preview-name'); } catch {} }
  // Der Vorname wird auf dem Gerät gemerkt und überall vorausgefüllt (Vorgabe 17.11.2026). Fehlt er lokal
  // (neues Gerät, gelöschte App-Daten), dient der Name einer bestehenden eigenen Anmeldung.
  const knownName = () => getName() || state.own.find(item => item.first_name)?.first_name || '';
  // Anzahl der Angemeldeten für den nächsten Termin, dezent am Eintrag "Meet to eat" in der Liste
  // (Vorgabe 17.11.2026). Ist niemand angemeldet, wird nichts gezeigt.
  const nextCount = () => { const day = dateOptions()[0]; return state.participants.filter(p => p.meeting_date === day).length; };
  meetBadge = () => { const count = nextCount(); return count ? `<span class="meet-count" data-ui-literal aria-label="${esc(text('{count} angemeldet', {count}))}">${icon('person')}${count}</span>` : ''; };
  // Setzt die Zahl in die sichtbare Liste ein, ohne den Bildschirm neu aufzubauen (Scrollposition und Karte bleiben).
  const paintBadge = () => {
    const row = app.querySelector?.('[data-action="meet-preview"].restaurant-row'); if (!row) return;
    row.querySelector('.meet-count')?.remove();
    const html = meetBadge(); if (html) row.lastElementChild?.insertAdjacentHTML('beforebegin', html);
  };
  // Lädt nur die öffentliche Teilnehmerliste (Vornamen je Termin, keine Anmeldung nötig). Fehler bleiben still:
  // die Zahl ist ein Zusatz und darf die Restaurantliste nie stören.
  async function refreshCount() {
    if (!client || meetPreviewOpen) return;
    try {
      const {data: rows, error} = await client.from('meet_preview_participants').select('meeting_date,first_name').in('meeting_date', slotDates());
      if (error) throw error;
      state.participants = rows || []; paintBadge();
    } catch (e) { console.warn('Meet to eat, Anzahl:', e?.message || e); }
  }
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
      state.participants = people.data || []; state.own = own.data || []; state.loaded = true; state.error = ''; state.retry = false;
      meetJoined = !!state.own.find(item => item.meeting_date === date());
    } catch (e) { state.loaded = true; showError(e); }
    redraw();
  }
  const groupArt = '<div class="meet-art"><svg viewBox="0 0 320 146" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Personen kommen an einem Treffpunkt zum gemeinsamen Essen zusammen"><path d="M30 134h260" stroke="#dbe4ee" stroke-width="2" stroke-linecap="round"/><path d="M108 126h30M182 126h30" fill="none" stroke="#9fb3c8" stroke-width="3" stroke-linecap="round" stroke-dasharray="0.1 8"/><circle cx="50" cy="88" r="10" fill="#6f8fb3"/><path d="M36 134V116a14 14 0 0 1 28 0v18z" fill="#6f8fb3"/><circle cx="86" cy="88" r="10" fill="#1f3d5c"/><path d="M72 134V116a14 14 0 0 1 28 0v18z" fill="#1f3d5c"/><circle cx="234" cy="88" r="10" fill="#1f3d5c"/><path d="M220 134V116a14 14 0 0 1 28 0v18z" fill="#1f3d5c"/><circle cx="270" cy="88" r="10" fill="#9fb3c8"/><path d="M256 134V116a14 14 0 0 1 28 0v18z" fill="#9fb3c8"/><ellipse cx="160" cy="134" rx="15" ry="3.5" fill="#c9d6e4"/><path d="M160 132c-20-27-34-45-34-70a34 34 0 1 1 68 0c0 25-14 43-34 70z" fill="#087cf4"/><path d="M142.5 45.1L142.8 45.6L142.9 46.9L143.1 54.2L143.3 55.5L143.4 55.6L143.6 55.5L143.7 54.5L143.8 47.7L143.9 45.4L144.0 45.4L144.1 45.6L144.2 46.5L144.4 53.6L144.6 55.5L144.7 55.6L144.8 55.4L144.9 54.7L145.0 47.9L145.3 45.4L145.4 45.5L145.5 46.4L145.6 52.9L145.8 55.5L146.0 55.7L146.2 55.5L146.3 54.5L146.3 47.2L146.6 45.3L146.7 45.1L146.9 45.3L147.1 46.2L147.4 51.0L147.5 53.7L147.5 60.0L146.9 60.6L146.6 61.2L146.0 62.6L145.6 65.0L145.5 67.2L145.6 71.5L145.9 74.7L146.4 78.7L146.4 80.1L146.3 80.5L146.1 80.8L145.5 81.0L144.1 81.0L143.6 80.8L143.4 80.6L143.2 80.1L143.2 79.3L143.9 71.9L144.0 69.7L143.9 65.2L143.7 63.9L143.4 62.4L142.8 60.9L142.5 60.6L141.9 60.0L141.9 59.0L141.9 51.8L141.9 49.3L142.2 46.3L142.3 45.5L142.5 45.2zM160.5 39.0L161.2 39.0L161.5 39.2L161.8 39.6L161.2 56.5L160.9 67.9L161.0 70.9L161.4 80.2L161.3 80.5L161.0 80.8L160.6 81.0L160.0 81.0L158.7 80.9L158.3 80.6L158.1 80.1L158.5 73.4L158.5 70.5L158.5 68.9L158.2 67.0L157.8 65.4L157.6 64.7L156.6 63.2L156.3 62.2L156.1 60.2L156.0 57.1L156.1 54.7L156.5 50.8L156.9 47.6L157.6 44.4L158.2 42.2L158.8 40.5L159.3 39.8L159.8 39.3L160.5 39.0zM173.1 49.3L174.0 49.4L174.7 49.8L175.5 50.3L176.6 51.6L177.2 52.8L177.7 53.9L177.9 54.9L178.1 56.4L178.1 58.1L177.8 59.3L177.4 60.3L176.9 61.1L176.2 62.0L175.4 62.6L174.7 63.1L174.5 63.2L174.5 63.5L174.3 65.9L174.3 68.2L174.5 73.4L174.9 78.8L174.9 80.3L174.7 80.7L174.5 80.8L173.6 81.0L172.9 81.0L172.4 80.8L172.2 80.6L172.0 80.1L172.6 70.4L172.6 65.5L172.5 63.9L172.3 63.2L171.1 62.4L170.3 61.6L169.6 60.5L169.0 59.2L168.6 57.3L168.6 55.9L168.8 54.5L169.2 53.0L169.7 52.0L170.4 50.9L171.2 50.1L172.1 49.5L172.6 49.4L173.1 49.3z" fill="#fff"/></svg></div>';
  function renderLive() {
    const selected = date(), own = state.own.find(item => item.meeting_date === selected);
    meetJoined = !!own;
    // Eine aktive Anmeldung pro Gerät: Wer für den anderen Termin angemeldet ist, sieht hier einen Hinweis statt des Formulars.
    const elsewhere = own ? null : state.own.find(item => item.meeting_date !== selected && registrationOpen(item.meeting_date));
    const errorHtml = state.error ? `<p class="meet-notice" role="alert">${esc(state.error)}</p>${state.retry ? '<button class="meet-secondary meet-retry" data-action="meet-retry">Erneut versuchen</button>' : ''}` : '';
    // Ohne E-Mail steht die Meldung direkt unter dem Vornamenfeld, damit man sie neben der Eingabe sieht.
    const nameError = !meetForm && !emailVerification && state.error && !state.retry && !own && registrationOpen(selected);
    const error = nameError ? '' : errorHtml;
    const header = `<header class="top detail"><button class="back" data-action="meet-back" aria-label="Zurück">${icon('arrow_back')}</button><h1>${meetForm ? esc(text('Meet to eat: Anmeldung', {}, 'Anmeldung')) : 'Meet to eat'}</h1>${meetForm ? '' : `<button type="button" class="share" data-action="meet-share" aria-label="Teilen">${icon('share')}</button>`}</header>`;
    if (meetForm) return `${header}<div class="body"><div class="scroll meet-content">${error}${state.step === 'code' ? `<p>${esc(text('Wir haben einen Bestätigungscode an {email} gesendet. Bitte gib den Code hier ein. Der Link in der E-Mail und der Code sind nur einmal verwendbar.', {email: state.pendingEmail}))}</p><label>Bestätigungscode<input id="meet-code" inputmode="numeric" autocomplete="one-time-code" maxlength="12"></label><button class="meet-primary" data-action="meet-verify" ${state.busy?'disabled':''}>Code bestätigen und anmelden</button><button class="meet-secondary" data-action="meet-resend-code" ${state.busy?'disabled':''}>Neuen Code anfordern</button>` : state.step === 'name' ? `<p>Deine E-Mail-Adresse ist bestätigt. Nur dein Vorname ist für alle sichtbar.</p><label>Vorname<input id="meet-first-name" autocomplete="given-name" maxlength="20" placeholder="Max" value="${esc(state.pendingName || knownName())}"></label><button class="meet-primary" data-action="meet-confirm-name" ${state.busy?'disabled':''}>Teilnehmen</button>` : `<p>Verifizierung deiner E-Mail-Adresse: Du bekommst einen Code per E-Mail. Nur dein Vorname ist für alle sichtbar.</p><label>Vorname<input id="meet-first-name" autocomplete="given-name" maxlength="20" placeholder="Max" value="${esc(state.pendingName || knownName())}"></label><label>E-Mail-Adresse<input id="meet-email" type="email" autocomplete="email" placeholder="mustermann@email.com" value="${esc(state.pendingEmail)}"></label><button class="meet-primary" data-action="meet-send-code" ${state.busy?'disabled':''}>Verifizierung via Mail starten</button>`}</div></div>`;
    const people = state.participants.filter(p => p.meeting_date === selected);
    let ownRemoved = false;
    const names = people.filter(p => { if (own && !ownRemoved && p.first_name === own.first_name) { ownRemoved = true; return false; } return true; });
    // Aufbau seit 23.11.2026 (Vorgabe des Betreibers, nach mehreren Runden): oben die Zeichnung, dann ein Satz, worum es
    // geht; darunter eine Tabelle mit Datum, Uhrzeit am Treffpunkt, gemeinsamem Losgehen und – als letzte Zeile – dem
    // Treffpunkt, an die das Foto direkt anschließt. Danach, wie viele schon dabei sind, und fest am unteren Rand
    // Vorname und Knopf. „So läuft's ab" ist entfallen (die Tabelle sagt dasselbe). Der Treffpunkt ist kein Link,
    // auch der Google-Maps-Link ist entfallen. Die Namen der anderen erscheinen erst nach der eigenen Anmeldung.
    const entries = names.map(p => `<span class="meet-name" data-ui-literal>${esc(p.first_name)}</span>`).join('') + (own ? `<span class="meet-name meet-own"><span data-ui-literal>${esc(own.first_name)}</span><button class="meet-remove" data-action="meet-leave" aria-label="Meine Anmeldung entfernen">${icon('close')}</button></span>` : '');
    const art = groupArt.replace('aria-label="Personen kommen an einem Treffpunkt zum gemeinsamen Essen zusammen"', `aria-label="${esc(text('Personen kommen an einem Treffpunkt zum gemeinsamen Essen zusammen'))}"`);
    const fact = (symbol, label, value) => `<div class="meet-fact">${icon(symbol)}<div><strong>${label}</strong>${value}</div></div>`;
    const picker = `<span class="meet-date-picker"><select id="meet-date" aria-label="Datum">${dateOptions().map(day => `<option value="${day}" ${day === selected ? 'selected' : ''}>${esc(dateValue(day,{weekday:'long',day:'numeric',month:'long'}))}</option>`).join('')}</select></span>`;
    const photo = `<figure class="meet-place"><img class="meet-photo-visible" src="./meeting-point.webp" width="900" height="1020" alt="${esc(text('Treffpunkt vor dem Baum bei der Mensa'))}" onerror="this.onerror=null;this.src='./meeting-point.png'"></figure>`;
    // Vor der eigenen Anmeldung nur die Zahl – der Grund mitzumachen; danach die Namen (mit Melde-Link). Beides als Tabellenzeile.
    const dabei = own
      ? `<div class="meet-fact meet-people">${icon('group')}<div><strong>Bereits angemeldet</strong><span class="meet-names">${entries}</span>${names.length ? `<a class="meet-report" href="mailto:${esc(contactEmail())}?subject=${encodeURIComponent('WU Food: Namen melden (' + selected + ')')}">Unpassenden Namen melden</a>` : ''}</div></div>`
      : `<div class="meet-fact meet-joined">${icon('group')}<div><strong>Teilnehmer</strong><span class="meet-count">${esc(people.length === 0 ? text('Sei die erste Person.') : people.length === 1 ? text('1 Person ist schon dabei.') : text('{count} sind schon dabei.', {count: String(people.length)}))}</span>${people.length ? `<small>${esc(text('Die Namen siehst du nach deiner Anmeldung.'))}</small>` : ''}</div></div>`;
    // Wie viele dabei sind (nach der eigenen Anmeldung: wer), steht in der Tabelle über dem Treffpunkt – also über dem Foto.
    const facts = `<div class="meet-facts">${fact('calendar_today', 'Datum', picker)}${fact('schedule', 'Uhrzeit am Treffpunkt', '<span>12:00 Uhr</span>')}${fact('directions_walk', 'Gemeinsam losgehen', '<span>12:05 Uhr</span>')}${dabei}${fact('location_on', 'Treffpunkt auf der WU', '<span>Vor dem Baum direkt bei der Mensa</span>')}${photo}</div>`;
    const action = own
      ? '<div class="meet-confirm"><p><svg class="meet-check" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="#2f9e5b"/><path d="M6.8 12.4l3.4 3.4 7-7.2" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg><span>Du bist für diesen Termin angemeldet.</span></p><p><svg class="meet-check" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="#56718c"/><path d="M12 10.6v6.6" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="7.2" r="1.5" fill="#fff"/></svg><span>Bitte melde dich aus Rücksicht auf die anderen ab, wenn du doch nicht kommen kannst.</span></p></div><button class="meet-primary meet-icon-button" data-action="meet-leave">' + icon('logout') + '<span>' + esc(text('Meet to eat: Abmelden', {}, 'Abmelden')) + '</span></button>'
      : (!registrationOpen(selected) ? '<p class="meet-notice">Die Anmeldung für diesen Termin ist geschlossen.</p>'
        : elsewhere ? `<p class="meet-notice">${esc(text('Du bist bereits für {date} angemeldet. Melde dich dort ab, wenn du lieber zu diesem Termin kommst.', {date: dateValue(elsewhere.meeting_date, {weekday: 'long', day: 'numeric', month: 'long'})}))}</p>`
        : '<p class="meet-why">Melde dich bitte an, damit die anderen wissen, dass du kommst. Wenn alle interessiert sind, sich aber niemand anmeldet, funktioniert es nicht ☺︎</p>');
    // Feste Leiste unter dem scrollenden Inhalt (wie der Hinweis unter den Menüs): Vorname und Knopf in einer Zeile,
    // eine Meldung zum Namen direkt darüber. So ist die Anmeldung immer erreichbar.
    const cta = own || !registrationOpen(selected) || elsewhere ? '' : `<div class="meet-cta">${nameError ? errorHtml.replace('class="meet-notice"', 'class="meet-notice meet-name-error"') : ''}<div class="meet-cta-row">${emailVerification ? '' : `<input id="meet-first-name" aria-label="Dein Vorname" autocomplete="off" maxlength="40" placeholder="Dein Vorname" autocapitalize="words" value="${esc(state.pendingName)}">`}<button class="meet-primary" data-action="meet-show-form" ${state.busy || !state.loaded ? 'disabled' : ''}>Teilnehmen</button></div></div>`;
    return `${header}<div class="body"><div class="scroll meet-content" id="meet-screen">${error}${art}<p class="meet-lead">Triff dich mit anderen freundlichen WU-Studierenden am WU Campus und geht gemeinsam als Gruppe Mittag essen. <span data-ui-literal>${esc(typeof meetDaysText === 'function' ? meetDaysText('intro') : 'Findet jeden Mittwoch statt.')}</span></p>${facts}${action}</div>${cta}</div>`;
  }
  async function join(name, meetingDate) {
    if (!emailVerification && (!state.session || nameProblem(name))) { state.error = nameProblem(name) || 'Die Anmeldung ist momentan nicht verfügbar. Bitte versuche es später erneut.'; return; }
    if (!state.session || !name.trim() || nameProblem(name)) { meetForm = true; state.step = state.session ? 'name' : 'form'; if (name.trim()) state.error = nameProblem(name); return; }
    if (!registrationOpen(meetingDate)) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; return; }
    const {error} = await client.from('meet_preview_registrations').insert({user_id:state.session.user.id, meeting_date:meetingDate, first_name:name.trim().slice(0,60)});
    if (error && error.code !== '23505') throw error;
    track('meet_joined', {slot: slotOf(meetingDate), weekday: new Date(meetingDate + 'T12:00:00Z').getUTCDay()});
    setName(name.trim().slice(0,60)); meetForm = false; if (!emailVerification) state.pendingName = ''; await refresh();
  }
  async function action(target) {
    const a = target.dataset.action;
    if (a === 'meet-preview') { track('meet_open', {entry: target.classList?.contains?.('meet-invite') ? 'menu_hint' : 'list'}); meetPreviewOpen=true; meetSlot=0; meetForm=false; state.error=''; state.selectedDate=null; state.pendingName=''; render(); await refresh(); return; }
    if (a === 'meet-share') {
      // Einladung mit dem gewählten Termin; der Link öffnet Meet to eat direkt (wufood.at/?meet=1).
      const day = dateValue(date(), {weekday: 'long', day: 'numeric', month: 'long'});
      const message = text('Kommst du am {date} mit zu Meet to eat? Wir treffen uns um 12:00 Uhr am WU Campus und gehen gemeinsam Mittag essen.', {date: day}) + ' https://wufood.at/?meet=1';
      track('meet_shared', {slot: slotOf(date())});
      if (nativePost('share', {text: message})) return;
      if (navigator.share) { try { await navigator.share({text: message}); } catch {} } else navigator.clipboard?.writeText(message);
      return;
    }
    if (a === 'meet-back') { state.error=''; if (meetForm) meetForm=false; else { meetSlot=null; meetPreviewOpen=false; } render(); return; }
    if (a === 'meet-retry') { state.error=''; state.retry=false; state.loaded=false; render(); await refresh(); return; }
    if (state.busy) return;
    state.error='';
    if (a === 'meet-show-form') { state.registrationDate=date(); track('meet_signup_started', {slot: slotOf(state.registrationDate)}); }
    // Eine aktive Anmeldung pro Gerät (auch wenn der Knopf einmal sichtbar sein sollte).
    if (a === 'meet-show-form' && state.own.some(item => item.meeting_date !== state.registrationDate && registrationOpen(item.meeting_date))) { state.error='Du bist schon für einen anderen Termin angemeldet. Melde dich dort zuerst ab.'; render(); return; }
    if (['meet-show-form','meet-send-code','meet-resend-code','meet-verify','meet-confirm-name'].includes(a) && !registrationOpen(state.registrationDate)) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; render(); return; }
    if (a === 'meet-show-form' && !emailVerification) {
      // Ohne E-Mail: Vorname aus dem Feld auf der Seite prüfen (dieselben Regeln wie bisher) und gleich anmelden.
      state.pendingName = tidyName(document.getElementById('meet-first-name')?.value || '');
      const problem = nameProblem(state.pendingName);
      if (problem) { track('meet_input_rejected', {reason: rejection(problem)}); state.error = problem; render(); return; }
    }
    else if (a === 'meet-show-form' && (!state.session || !knownName())) { state.step=state.session?'name':'form'; meetForm=true; render(); return; }
    if (a === 'meet-confirm-name') { state.pendingName=tidyName(document.getElementById('meet-first-name').value); const problem=nameProblem(state.pendingName); if (problem) { track('meet_input_rejected', {reason: rejection(problem)}); state.error=problem; render(); return; } }
    if (a === 'meet-send-code') {
      state.pendingName = tidyName(document.getElementById('meet-first-name').value);
      { const problem = state.pendingName ? nameProblem(state.pendingName) : ''; if (problem) { track('meet_input_rejected', {reason: rejection(problem)}); state.error = problem; render(); return; } }
      state.pendingEmail = document.getElementById('meet-email').value.trim();
      if (!state.pendingName || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(state.pendingEmail)) { track('meet_input_rejected', {reason: state.pendingName ? 'email_invalid' : 'name_missing'}); state.error='Bitte gib einen Vornamen und eine gültige E-Mail-Adresse ein.'; render(); return; }
      // Vorgabe des Betreibers (17.11.2026): keine Einschränkung auf WU-Adressen – jede gültige E-Mail-Adresse
      // kann verwendet werden. Der Code per E-Mail bestätigt nur, dass die Adresse der Person gehört.
      setName(state.pendingName);
    }
    const code = a === 'meet-verify' ? document.getElementById('meet-code').value.trim() : '';
    state.busy=true; render();
    try {
      if (a === 'meet-show-form' && !emailVerification) {
        if (!state.session) { const {data,error} = await client.auth.signInAnonymously(); if (error) throw error; state.session = data.session; }
        await join(state.pendingName,state.registrationDate);
      }
      else if (a === 'meet-show-form') await join(knownName(),state.registrationDate);
      if (a === 'meet-send-code' || a === 'meet-resend-code') { const {error} = await client.auth.signInWithOtp({email:state.pendingEmail,options:{emailRedirectTo}}); if(error) throw error; track('meet_code_requested', {resend: a === 'meet-resend-code' ? 'yes' : 'no'}); state.step='code'; }
      if (a === 'meet-verify') { const {data,error} = await client.auth.verifyOtp({email:state.pendingEmail,token:code,type:'email'}); if(error) throw error; track('meet_code_result', {result: 'ok'}); state.session=data.session; await join(state.pendingName,state.registrationDate); }
      if (a === 'meet-confirm-name') await join(state.pendingName,state.registrationDate);
      if (a === 'meet-leave') { const {error}=await client.from('meet_preview_registrations').delete().eq('user_id',state.session.user.id).eq('meeting_date',date()); if(error) throw error; track('meet_left', {slot: slotOf(date())}); await refresh(); }
    } catch(e) {
      if (['meet-show-form','meet-send-code','meet-resend-code','meet-verify','meet-confirm-name'].includes(a) && !registrationOpen(state.registrationDate)) {
        state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false;
      }
      else if (a === 'meet-show-form' && /anonymous/i.test(e?.message || '')) { console.error('Meet preview:', e); state.error='Die Anmeldung ist momentan nicht verfügbar. Bitte versuche es später erneut.'; }
      else if (e?.message?.includes('meet_registration_closed')) { state.error='Die Anmeldung für diesen Termin ist geschlossen.'; meetForm=false; }
      else if (e?.message?.includes('meet_active_registration')) { state.error='Du bist schon für einen anderen Termin angemeldet. Melde dich dort zuerst ab.'; meetForm=false; }
      else if (a === 'meet-verify') { track('meet_code_result', {result: 'invalid'}); state.error='Der Code ist ungültig oder bereits verwendet. Bitte fordere einen neuen Code an.'; } else showError(e);
    }
    finally { state.busy=false; render(); }
  }
  renderMeet = renderLive;
  app.addEventListener('click', e => {
    const target=e.target.closest('[data-action]');
    if (!target || !['meet-preview','meet-back','meet-share','meet-retry','meet-show-form','meet-send-code','meet-resend-code','meet-verify','meet-confirm-name','meet-leave','meet-open-url'].includes(target.dataset.action)) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (target.dataset.action === 'meet-open-url') { if (target.dataset.track) track('meet_maps_opened', {source: target.dataset.track}); const url=safeUrl(target.href); if (url && !nativePost('open-source',{url,title:'Meet to eat'})) window.open(url,'_blank','noopener,noreferrer'); return; }
    void action(target);
  }, true);
  // Erster Buchstabe schon beim Tippen groß; die Schreibmarke bleibt an ihrer Stelle.
  app.addEventListener('input', e => {
    if (e.target?.id !== 'meet-first-name') return;
    const field = e.target, next = capitalName(field.value);
    if (next === field.value) return;
    const at = field.selectionStart; field.value = next; try { field.setSelectionRange(at, at); } catch {}
  });
  // Der Betreiber hat die Tage im Admin geändert: Auswahl zurücksetzen und neu laden.
  window.addEventListener?.('wu-settings', () => { state.selectedDate = null; if (meetPreviewOpen) void refresh(); else void refreshCount(); });
  // Auswahl eines anderen Termins im Datumsfeld.
  app.addEventListener('change', e => {
    if (e.target?.id !== 'meet-date') return;
    state.selectedDate = e.target.value; state.error = ''; track('meet_date_changed', {slot: slotOf(date())});
    meetJoined = !!state.own.find(item => item.meeting_date === date());
    render();
  });
  if (returningFromLink || window.WU_START_SCREEN === 'meet' || /[?&]meet=/.test(typeof location === 'undefined' ? '' : location.search || '')) { meetPreviewOpen=true; meetSlot=0; void refresh(); }
  setInterval(() => { if (meetPreviewOpen && !meetForm && !state.busy) void refresh(); }, 30000);
  // Anzahl in der Liste: beim Start, alle fünf Minuten und wenn die App wieder in den Vordergrund kommt.
  if (!returningFromLink) void refreshCount();
  setInterval(() => { if (typeof document === 'undefined' || !document.hidden) void refreshCount(); }, 300000);
  if (typeof document !== 'undefined') document.addEventListener?.('visibilitychange', () => { if (!document.hidden) void refreshCount(); });
})();

