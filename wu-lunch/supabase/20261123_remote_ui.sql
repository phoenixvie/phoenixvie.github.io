-- WU Food: Schalter „App-Oberfläche nachladen" (Stand 23.11.2026).
-- Erlaubt in der Einstellungstabelle den zusätzlichen Schlüssel remote_ui. Ohne diese Zeilen funktioniert das
-- Nachladen trotzdem (Vorgabe: eingeschaltet) – nur das Abschalten im Admin lässt sich dann nicht speichern.
-- Einmal im Supabase-Projekt (SQL-Editor) ausführen; kann gefahrlos wiederholt werden.
alter table public.lunch_settings drop constraint if exists lunch_settings_key_check;
alter table public.lunch_settings add constraint lunch_settings_key_check
  check (key in ('meet_weekdays', 'update_notice', 'remote_ui'));
