-- Applied to project vswnqdqnohbuzbwmsdvv on 2026-11-08.
-- Requires the existing private.is_lunch_admin() function and restaurant_overrides table.

alter table public.restaurant_overrides
  add column if not exists display_name text,
  add column if not exists restaurant_type text,
  add column if not exists logo_url text,
  add column if not exists phone text,
  add column if not exists email text,
  add column if not exists website_url text,
  add column if not exists address text,
  add column if not exists latitude double precision,
  add column if not exists longitude double precision;

create table if not exists public.menu_day_overrides (
  week_start date not null,
  restaurant_id text not null,
  menu_date date not null,
  dishes jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (week_start, restaurant_id, menu_date),
  constraint menu_day_overrides_array check (jsonb_typeof(dishes) = 'array'),
  constraint menu_day_overrides_in_week check (menu_date between week_start and week_start + 6)
);

alter table public.menu_day_overrides enable row level security;
grant select on public.menu_day_overrides to anon, authenticated;
grant insert, update, delete on public.menu_day_overrides to authenticated;

drop policy if exists "public reads menu day overrides" on public.menu_day_overrides;
create policy "public reads menu day overrides" on public.menu_day_overrides
  for select to anon, authenticated using (true);
drop policy if exists "admins insert menu day overrides" on public.menu_day_overrides;
create policy "admins insert menu day overrides" on public.menu_day_overrides
  for insert to authenticated with check ((select private.is_lunch_admin()));
drop policy if exists "admins update menu day overrides" on public.menu_day_overrides;
create policy "admins update menu day overrides" on public.menu_day_overrides
  for update to authenticated using ((select private.is_lunch_admin()))
  with check ((select private.is_lunch_admin()));
drop policy if exists "admins delete menu day overrides" on public.menu_day_overrides;
create policy "admins delete menu day overrides" on public.menu_day_overrides
  for delete to authenticated using ((select private.is_lunch_admin()));

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('lunch-logos', 'lunch-logos', true, 2097152, array['image/png','image/jpeg','image/webp'])
on conflict (id) do update set public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "admins upload lunch logos" on storage.objects;
create policy "admins upload lunch logos" on storage.objects
  for insert to authenticated with check (bucket_id = 'lunch-logos' and (select private.is_lunch_admin()));
drop policy if exists "admins update lunch logos" on storage.objects;
create policy "admins update lunch logos" on storage.objects
  for update to authenticated using (bucket_id = 'lunch-logos' and (select private.is_lunch_admin()))
  with check (bucket_id = 'lunch-logos' and (select private.is_lunch_admin()));
drop policy if exists "admins delete lunch logos" on storage.objects;
create policy "admins delete lunch logos" on storage.objects
  for delete to authenticated using (bucket_id = 'lunch-logos' and (select private.is_lunch_admin()));
