-- Nur noetig, wenn SUPABASE_AKTIV=true genutzt wird (siehe README.md,
-- Abschnitt "Dauerhafte Supabase-Anbindung") - im Standard-Betrieb (lokale
-- SQLite-Datenbank) uebernimmt backend\app\database.py:run_startup_migrations
-- dieselben Schema-Aenderungen automatisch, dieses Skript ist dafuer NICHT
-- noetig.
--
-- Nachtraege aus version2.1:
--   1. Neues 4-stufiges Rollenmodell (mitarbeiter/disponent/schichtleitung/
--      admin statt vormals mitarbeiter/schichtleitung/admin, siehe
--      backend\app\deps.py) - bestehende Konten mit rolle='schichtleitung'
--      werden auf 'disponent' umbenannt (entspricht fachlich derselben
--      Berechtigungsstufe wie bisher), die neue Stufe 'schichtleitung'
--      startet ungenutzt und kann danach gezielt vergeben werden.
--   2. Sicherheitsfrage/-antwort je Benutzerkonto (Selbstbedienungs-
--      Passwort-Reset, siehe backend\app\routers\auth.py).
--   3. Weich-Loeschen + "manuell hinzugefuegt" je Dienstplan-Eintrag (siehe
--      backend\app\routers\dienstplan.py).
--
-- Vor Ausfuehrung: die bestehenden policies "fkb_write_benutzer" /
-- "fkb_update_benutzer" waren bisher auf die Admin-E-Mail beschraenkt. Ab
-- version2.1 darf auch Schichtleitung Benutzerkonten verwalten - unten
-- durch die neue policy "fkb_write_benutzer_v2_1" ersetzt.

begin;

-- 1. Rollenmodell: bestehende Check-Constraint ersetzen und Datensaetze migrieren.
alter table public.benutzer drop constraint if exists benutzer_rolle_check;
update public.benutzer set rolle = 'disponent' where rolle = 'schichtleitung';
alter table public.benutzer add constraint benutzer_rolle_check
  check (rolle in ('mitarbeiter', 'disponent', 'schichtleitung', 'admin'));

drop policy if exists "fkb_write_benutzer" on public.benutzer;
drop policy if exists "fkb_update_benutzer" on public.benutzer;
create policy "fkb_write_benutzer_v2_1" on public.benutzer for insert to authenticated
  with check ((select auth.jwt()->>'email') in ('bauschke.info@icloud.com', 'dpfkb@gmx.de'));
create policy "fkb_update_benutzer_v2_1" on public.benutzer for update to authenticated
  using ((select auth.jwt()->>'email') in ('bauschke.info@icloud.com', 'dpfkb@gmx.de'));

-- 2. Sicherheitsfrage/-antwort fuer Passwort-Reset.
alter table public.benutzer add column if not exists sicherheitsfrage text not null default '';
alter table public.benutzer add column if not exists sicherheitsantwort_hash text;

-- 3. Dienstplan: Weich-Loeschen + manuell hinzugefuegte Eintraege.
alter table public.dienstplan add column if not exists geloescht boolean not null default false;
alter table public.dienstplan add column if not exists manuell_hinzugefuegt boolean not null default false;

commit;
