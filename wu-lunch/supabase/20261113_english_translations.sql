create table if not exists public.lunch_translations (
  source_text text check(length(source_text) between 1 and 6000),
  english_text text not null check(length(english_text) between 1 and 12000),
  source_sha256 text primary key check(source_sha256 ~ '^[0-9a-f]{64}$'),
  origin text not null check(origin in ('ai','manual')),
  model text,
  updated_at timestamptz not null default now()
);
alter table public.lunch_translations enable row level security;
grant select on public.lunch_translations to anon, authenticated;
grant insert, update, delete on public.lunch_translations to authenticated;
create policy "public reads translations" on public.lunch_translations for select to anon, authenticated using (true);
create policy "admins insert translations" on public.lunch_translations for insert to authenticated with check ((select private.is_lunch_admin()));
create policy "admins update translations" on public.lunch_translations for update to authenticated using ((select private.is_lunch_admin())) with check ((select private.is_lunch_admin()));
create policy "admins delete translations" on public.lunch_translations for delete to authenticated using ((select private.is_lunch_admin()));

create or replace function private.touch_lunch_translation_timestamp() returns trigger language plpgsql set search_path='' as $$ begin new.updated_at=now(); return new; end $$;
create trigger lunch_translation_timestamp before update on public.lunch_translations for each row execute function private.touch_lunch_translation_timestamp();
