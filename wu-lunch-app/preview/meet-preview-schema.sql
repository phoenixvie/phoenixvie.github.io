-- Isolated preview data. Only the participant's own row is writable/readable;
-- the public view deliberately exposes first names and dates, never identities or email.
create table public.meet_preview_registrations (
  user_id uuid not null references auth.users(id) on delete cascade,
  meeting_date date not null,
  first_name text not null check (char_length(trim(first_name)) between 1 and 60),
  created_at timestamptz not null default now(),
  primary key (user_id, meeting_date),
  check (extract(isodow from meeting_date) in (1, 3, 5))
);
alter table public.meet_preview_registrations enable row level security;
revoke all on public.meet_preview_registrations from public, anon, authenticated;
grant select, insert, delete on public.meet_preview_registrations to authenticated;
create policy meet_preview_read_own on public.meet_preview_registrations for select to authenticated using ((select auth.uid()) = user_id);
create policy meet_preview_insert_own on public.meet_preview_registrations for insert to authenticated with check (
  (select auth.uid()) = user_id and
  (auth.jwt() ->> 'email') is not null and
  meeting_date between (now() at time zone 'Europe/Vienna')::date and (now() at time zone 'Europe/Vienna')::date + 14
);
create policy meet_preview_delete_own on public.meet_preview_registrations for delete to authenticated using ((select auth.uid()) = user_id);
-- Intentionally owner-backed: this narrow projection is the only public
-- access to other participants, and contains no user IDs or email addresses.
create view public.meet_preview_participants as
select meeting_date, first_name from public.meet_preview_registrations
where meeting_date between (now() at time zone 'Europe/Vienna')::date and (now() at time zone 'Europe/Vienna')::date + 14;
revoke all on public.meet_preview_participants from public, anon, authenticated;
grant select on public.meet_preview_participants to anon, authenticated;

