-- WU Food: Einstellungen des Betreibers, die ohne neue App-Version wirken (Stand 22.11.2026):
--   meet_weekdays   Wochentage von Meet to eat (1 = Montag … 5 = Freitag), Vorgabe Mittwoch
--   update_notice   manuell ausgelöster Update-Hinweis für ältere App-Versionen
-- Einmal im Supabase-Projekt (SQL-Editor) ausführen; kann gefahrlos wiederholt werden.
-- Alle dürfen lesen (die App braucht die Werte), nur der Admin darf schreiben.
create table if not exists public.lunch_settings (
  key text primary key check (key in ('meet_weekdays', 'update_notice')),
  value jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.lunch_settings enable row level security;
revoke all on public.lunch_settings from public, anon, authenticated;
grant select on public.lunch_settings to anon, authenticated;
grant insert, update on public.lunch_settings to authenticated;
drop policy if exists "everyone reads lunch settings" on public.lunch_settings;
create policy "everyone reads lunch settings" on public.lunch_settings for select to anon, authenticated using (true);
drop policy if exists "lunch admins insert settings" on public.lunch_settings;
create policy "lunch admins insert settings" on public.lunch_settings for insert to authenticated with check ((select private.is_lunch_admin()));
drop policy if exists "lunch admins update settings" on public.lunch_settings;
create policy "lunch admins update settings" on public.lunch_settings for update to authenticated
  using ((select private.is_lunch_admin())) with check ((select private.is_lunch_admin()));
insert into public.lunch_settings (key, value) values
  ('meet_weekdays', '[3]'::jsonb),
  ('update_notice', '{"enabled": false, "min_version": "", "message_de": "", "message_en": ""}'::jsonb)
on conflict (key) do nothing;

-- Meet to eat: Anmeldungen sind an den eingestellten Wochentagen möglich (bisher fest Montag und Mittwoch).
-- Wurde diese Datei schon einmal mit der alten Vorgabe ausgeführt, den Tag im Admin unter „Meet to eat: Wochentage“ umstellen.
alter table public.meet_preview_registrations drop constraint if exists meet_preview_monday_wednesday;
alter table public.meet_preview_registrations drop constraint if exists meet_preview_registrations_meeting_date_check;
alter table public.meet_preview_registrations drop constraint if exists meet_preview_weekday;
alter table public.meet_preview_registrations
  add constraint meet_preview_weekday check (extract(isodow from meeting_date) between 1 and 5) not valid;
drop policy if exists meet_preview_insert_own on public.meet_preview_registrations;
create policy meet_preview_insert_own on public.meet_preview_registrations
  for insert to authenticated with check (
    (select auth.uid()) = user_id
    and extract(isodow from meeting_date)::int in (
      select (jsonb_array_elements_text(value))::int from public.lunch_settings where key = 'meet_weekdays'
    )
    and meeting_date between (now() at time zone 'Europe/Vienna')::date
      and (now() at time zone 'Europe/Vienna')::date + 21
    and now() < ((meeting_date + time '12:06') at time zone 'Europe/Vienna')
  );
