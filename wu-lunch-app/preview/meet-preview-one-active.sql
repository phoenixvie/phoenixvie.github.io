-- Keep existing registrations. Refuse the change if data already violates it.
do $$
begin
  if exists (
    select user_id from public.meet_preview_registrations
    where pg_catalog.clock_timestamp() < ((meeting_date + time '12:06') at time zone 'Europe/Vienna')
    group by user_id having count(*) > 1
  ) then raise exception 'Existing users have more than one active registration'; end if;
end $$;

create function private.enforce_meet_single_active() returns trigger
language plpgsql volatile security definer set search_path = ''
as $$
begin
  if (select auth.uid()) is null or new.user_id <> (select auth.uid()) then
    raise exception using errcode = '42501', message = 'meet_not_owner';
  end if;
  -- Serialise attempts by the same account, even across multiple devices.
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
create trigger meet_preview_single_active before insert on public.meet_preview_registrations
  for each row execute function private.enforce_meet_single_active();

