-- Meet to eat: Der Admin der Webseite darf alle Anmeldungen sehen und einzelne Vornamen löschen
-- (Kontrollmöglichkeit, Vorgabe des Betreibers vom 17.11.2026).
-- Einmal im Supabase-Projekt (SQL-Editor) ausführen. Benötigt die bestehende Funktion private.is_lunch_admin().
-- Für alle anderen ändert sich nichts: Sie sehen und löschen weiterhin nur ihre eigene Anmeldung.
drop policy if exists "lunch admins read meet registrations" on public.meet_preview_registrations;
create policy "lunch admins read meet registrations" on public.meet_preview_registrations
  for select to authenticated using ((select private.is_lunch_admin()));
drop policy if exists "lunch admins delete meet registrations" on public.meet_preview_registrations;
create policy "lunch admins delete meet registrations" on public.meet_preview_registrations
  for delete to authenticated using ((select private.is_lunch_admin()));
