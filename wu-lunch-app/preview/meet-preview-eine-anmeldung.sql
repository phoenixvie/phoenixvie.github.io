-- Meet to eat: höchstens eine aktive Anmeldung pro Person (UX-Test 22.11.2026: eine zweite Anmeldung für den
-- anderen Termin wurde angenommen). Die App zeigt seit diesem Stand statt des Formulars einen Hinweis; diese Regel
-- macht es in der Datenbank verbindlich. Einmal im SQL-Editor ausführen; kann gefahrlos wiederholt werden.
create or replace function private.enforce_meet_single_active() returns trigger
language plpgsql volatile security definer set search_path = ''
as $$
begin
  if (select auth.uid()) is null or new.user_id <> (select auth.uid()) then
    raise exception using errcode = '42501', message = 'meet_not_owner';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(new.user_id::text, 0));
  if pg_catalog.clock_timestamp() >= ((new.meeting_date + time '12:06') at time zone 'Europe/Vienna') then
    raise exception using errcode = 'P0001', message = 'meet_registration_closed';
  end if;
  if exists (
    select 1 from public.meet_preview_registrations r
    where r.user_id = new.user_id and r.meeting_date <> new.meeting_date
      and pg_catalog.clock_timestamp() < ((r.meeting_date + time '12:06') at time zone 'Europe/Vienna')
  ) then raise exception using errcode = 'P0001', message = 'meet_active_registration'; end if;
  return new;
end $$;
revoke all on function private.enforce_meet_single_active() from public, anon, authenticated;
drop trigger if exists meet_preview_single_active on public.meet_preview_registrations;
create trigger meet_preview_single_active before insert on public.meet_preview_registrations
  for each row execute function private.enforce_meet_single_active();
