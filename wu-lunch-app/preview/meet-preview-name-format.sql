-- Meet to eat: verbindliche Form des Vornamens. Im Supabase-Projekt (SQL-Editor) einmal ausführen.
-- (Eine Einschränkung auf WU-Mailadressen gibt es nicht: jede bestätigte E-Mail-Adresse darf sich anmelden –
-- Vorgabe des Betreibers vom 17.11.2026.)
-- Vornamen: nur Namensform (ein Name aus Buchstaben oder Doppelname mit Bindestrich, höchstens 20 Zeichen). Die App prüft
-- zusätzlich eine kleine Sperrliste; diese Regel verhindert Sätze, Zahlen, Links und Sonderzeichen auch dann,
-- wenn jemand die App umgeht. "not valid": bestehende Einträge bleiben unberührt.
alter table public.meet_preview_registrations
  add constraint meet_preview_first_name_format check (
    char_length(first_name) between 2 and 20
    and first_name ~ '^[[:alpha:]]{2,}(-[[:alpha:]]{2,})?$'
  ) not valid;
