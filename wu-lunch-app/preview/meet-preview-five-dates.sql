-- Five Monday/Wednesday dates can extend 19 days into the future.
-- Keep the existing ownership and Vienna 12:05 deadline checks.
drop policy meet_preview_insert_own on public.meet_preview_registrations;
create policy meet_preview_insert_own on public.meet_preview_registrations
  for insert to authenticated with check (
    (select auth.uid()) = user_id
    and (auth.jwt() ->> 'email') is not null
    and extract(isodow from meeting_date) in (1, 3)
    and meeting_date between (now() at time zone 'Europe/Vienna')::date
      and (now() at time zone 'Europe/Vienna')::date + 21
    and now() < ((meeting_date + time '12:06') at time zone 'Europe/Vienna')
  );
create or replace view public.meet_preview_participants as
  select meeting_date, first_name from public.meet_preview_registrations
  where meeting_date between (now() at time zone 'Europe/Vienna')::date
    and (now() at time zone 'Europe/Vienna')::date + 21;

