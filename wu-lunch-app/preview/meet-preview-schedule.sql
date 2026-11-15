-- Existing rows remain untouched; all new registrations are Monday or Wednesday.
alter table public.meet_preview_registrations
  add constraint meet_preview_monday_wednesday check (extract(isodow from meeting_date) in (1, 3)) not valid;
drop policy meet_preview_insert_own on public.meet_preview_registrations;
create policy meet_preview_insert_own on public.meet_preview_registrations
  for insert to authenticated with check (
    (select auth.uid()) = user_id
    and (auth.jwt() ->> 'email') is not null
    and extract(isodow from meeting_date) in (1, 3)
    and meeting_date between (now() at time zone 'Europe/Vienna')::date
      and (now() at time zone 'Europe/Vienna')::date + 14
    and now() < ((meeting_date + time '12:06') at time zone 'Europe/Vienna')
  );

