-- OPTIONAL: nur nötig, wenn das Löschen von Krankmeldungen in der neuen
-- FastAPI-Webapp genutzt werden soll. Die alte Netlify-Webapp hatte absichtlich
-- keine Löschfunktion (siehe ..\..\Background\README.txt), daher existiert in
-- sick_reports bislang vermutlich keine DELETE-Policy.
--
-- Einmalig im SQL Editor des bestehenden Supabase-Projekts ausführen, falls
-- der Löschen-Button in der neuen App mit "HTTP 403" fehlschlägt.

create policy "fkb_delete_reports" on public.sick_reports for delete to authenticated
  using ((select auth.jwt()->>'email') in ('dpfkb@gmx.de', 'bauschke.info@icloud.com'));
