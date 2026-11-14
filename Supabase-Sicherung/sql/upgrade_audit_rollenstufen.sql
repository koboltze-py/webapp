-- Einmalig im SQL Editor des bestehenden Supabase-Projekts ausführen,
-- NACHDEM die Einzel-Logins eingerichtet sind (siehe benutzer.sql).
--
-- Hintergrund: Mit den Einzel-Logins heißt die bisherige Rolle "disposition"
-- jetzt "schichtleitung" (deps.py normalisiert alte Sitzungen automatisch
-- darauf um). Die bestehende CHECK-Bedingung auf sick_report_audit.actor_role
-- kennt "schichtleitung" noch nicht und müsste sonst jede neue
-- Krankmeldungs-Änderung mit einem Datenbankfehler ablehnen.

alter table public.sick_report_audit
  drop constraint if exists sick_report_audit_actor_role_check;

alter table public.sick_report_audit
  add constraint sick_report_audit_actor_role_check
  check (actor_role in ('admin', 'disposition', 'schichtleitung'));
