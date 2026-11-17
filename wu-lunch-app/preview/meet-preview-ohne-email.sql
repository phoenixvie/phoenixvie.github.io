-- Meet to eat: Anmeldung nur mit Vornamen, ohne Bestätigung per E-Mail (Vorgabe des Betreibers, 17.11.2026).
-- Die App meldet dafür im Hintergrund ein anonymes Konto an (Supabase "Anonymous sign-ins"). Damit sieht und
-- löscht jede Person weiterhin nur ihre eigene Anmeldung; der Admin kann jeden Vornamen löschen.
--
-- Vorher in Supabase einschalten: Authentication -> Sign In / Providers -> "Allow anonymous sign-ins".
-- Dann diesen Block einmal im SQL-Editor ausführen. Er kann gefahrlos mehrfach ausgeführt werden.
-- Bestehende Anmeldungen bleiben unberührt. Die E-Mail-Bestätigung ist nur pausiert: Anmeldungen mit
-- bestätigter E-Mail-Adresse funktionieren weiterhin.

-- 1) Anmelderegel: wie bisher (eigene Zeile, Montag/Mittwoch, höchstens 21 Tage voraus, Schluss um 12:05),
--    aber ohne die Bedingung, dass das Konto eine E-Mail-Adresse hat.
drop policy if exists meet_preview_insert_own on public.meet_preview_registrations;
create policy meet_preview_insert_own on public.meet_preview_registrations
  for insert to authenticated with check (
    (select auth.uid()) = user_id
    and extract(isodow from meeting_date) in (1, 3)
    and meeting_date between (now() at time zone 'Europe/Vienna')::date
      and (now() at time zone 'Europe/Vienna')::date + 21
    and now() < ((meeting_date + time '12:06') at time zone 'Europe/Vienna')
  );

-- 2) Vornamen-Form verbindlich (ohne E-Mail jetzt besonders wichtig): ein Name aus Buchstaben oder ein
--    Doppelname mit Bindestrich, 2 bis 20 Zeichen. "not valid": bestehende Einträge bleiben unberührt.
alter table public.meet_preview_registrations drop constraint if exists meet_preview_first_name_format;
alter table public.meet_preview_registrations
  add constraint meet_preview_first_name_format check (
    char_length(first_name) between 2 and 20
    and first_name ~ '^[[:alpha:]]{2,}(-[[:alpha:]]{2,})?$'
  ) not valid;

-- 3) Aufräumen (Datenschutzerklärung: "spätestens 30 Tage nach dem Termin gelöscht"): Bei jeder neuen Anmeldung
--    werden Anmeldungen gelöscht, deren Termin mehr als 30 Tage zurückliegt, und anonyme technische Konten ohne
--    Anmeldung der letzten 30 Tage. Konten mit E-Mail-Adresse bleiben unberührt.
create or replace function private.meet_preview_cleanup() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  -- Ein Fehler beim Aufräumen darf eine Anmeldung nie verhindern; er wird nur protokolliert.
  begin
    delete from public.meet_preview_registrations
      where meeting_date < (now() at time zone 'Europe/Vienna')::date - 30;
    delete from auth.users u
      where u.is_anonymous and u.created_at < now() - interval '30 days'
        and not exists (select 1 from public.meet_preview_registrations r where r.user_id = u.id);
  exception when others then
    raise warning 'meet_preview_cleanup: %', sqlerrm;
  end;
  return null;
end $$;
revoke all on function private.meet_preview_cleanup() from public, anon, authenticated;
drop trigger if exists meet_preview_cleanup on public.meet_preview_registrations;
create trigger meet_preview_cleanup after insert on public.meet_preview_registrations
  for each statement execute function private.meet_preview_cleanup();
