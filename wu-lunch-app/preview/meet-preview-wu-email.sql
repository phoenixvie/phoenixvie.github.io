-- Meet to eat: Anmeldung nur mit WU-Mailadresse (…@wu.ac.at und Unterdomänen wie …@s.wu.ac.at).
-- Die App prüft das bereits im Formular; diese Regel macht es verbindlich, auch wenn jemand die App umgeht.
-- Im Supabase-Projekt (SQL-Editor) einmal ausführen. Bestehende Anmeldungen bleiben unberührt.
drop policy meet_preview_insert_own on public.meet_preview_registrations;
create policy meet_preview_insert_own on public.meet_preview_registrations
  for insert to authenticated with check (
    (select auth.uid()) = user_id
    and (auth.jwt() ->> 'email') ~* '^[^[:space:]@]+@([a-z0-9-]+\.)*wu\.ac\.at$'
    and extract(isodow from meeting_date) in (1, 3)
    and meeting_date between (now() at time zone 'Europe/Vienna')::date
      and (now() at time zone 'Europe/Vienna')::date + 14
    and now() < ((meeting_date + time '12:06') at time zone 'Europe/Vienna')
  );

-- Vornamen: nur Namensform (ein Name aus Buchstaben oder Doppelname mit Bindestrich, höchstens 20 Zeichen). Die App prüft
-- zusätzlich eine kleine Sperrliste; diese Regel verhindert Sätze, Zahlen, Links und Sonderzeichen auch dann,
-- wenn jemand die App umgeht. "not valid": bestehende Einträge bleiben unberührt.
alter table public.meet_preview_registrations
  add constraint meet_preview_first_name_format check (
    char_length(first_name) between 2 and 20
    and first_name ~ '^[[:alpha:]]{2,}(-[[:alpha:]]{2,})?$'
  ) not valid;
