"""Dienstplan: Anzeige + Excel-Import (siehe app/dienstplan_parser.py) +
Sortierung/Kategorisierung (siehe app/dienstplan_sortierung.py) + manuelle
Korrekturen mit Änderungsprotokoll. Beim Import wird jeder Name zusätzlich
den Personal-Stammdaten zugeordnet (siehe mitarbeiter_matching.py) -
Grundlage für die Mitarbeiter-Historie (mitarbeiter_historie.py)."""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from ..aktivitaet import record_activity
from ..deps import get_current_role, require_admin, require_schichtleitung
from ..dienstplan_export import export_dienstplan_excel
from ..dienstplan_parser import parse_dienstplan_excel
from ..dienstplan_sortierung import kategorisiere_und_sortiere
from ..mitarbeiter_historie import record_ereignis
from ..mitarbeiter_matching import ordne_mitarbeiter_zu
from ..modules_repository import get_dienstplan_repository, get_mitarbeiter_repository
from ..repository import ReportsRepository, get_reports_repository
from ..schemas import (
    DienstplanAuditOut,
    DienstplanEintragOut,
    DienstplanEintragUpdate,
    DienstplanImportResult,
    DienstplanQuelle,
    UnsichereZuordnung,
)

router = APIRouter(prefix="/api/dienstplan", tags=["dienstplan"])

# backend/app/routers/dienstplan.py -> routers -> app -> backend -> Projektordner
PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TAGESDIENSTPLAN_BACKUP_DIR = PROJEKT_ROOT / "Backups" / "Tagesdienstpläne"

# Für die virtuelle Krank-Überlagerung (siehe _virtuelle_krank_eintraege)
# maximal betrachteter Zeitraum, um ausufernde Schleifen bei sehr großen
# von/bis-Bereichen zu vermeiden.
MAX_VIRTUELLE_TAGE = 62


def _row_to_report_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {
        "id": row.id, "employee": row.employee, "sick_from": row.sick_from,
        "sick_to": row.sick_to, "created_at": row.created_at,
    }


def _employee_zu_dienstplan_name(employee: str) -> str:
    """Konvertiert das Krankmeldungs-Namensformat ('Nachname, Vorname') in
    das Dienstplan-Anzeigeformat ('Vorname Nachname'); lässt Namen ohne
    Komma unverändert (z. B. bereits im Dienstplan-Format)."""
    if "," in employee:
        nachname, _, vorname = employee.partition(",")
        return f"{vorname.strip()} {nachname.strip()}".strip()
    return employee.strip()


def _dienstplan_name_zu_employee(mitarbeiter_name: str) -> str:
    """Kehrt obige Konvertierung um ('Vorname Nachname' -> 'Nachname,
    Vorname'), für den Abgleich mit Krankmeldungen beim Entfernen des
    Krank-Status (siehe update_dienstplan_eintrag)."""
    teile = (mitarbeiter_name or "").strip().split(" ", 1)
    if len(teile) == 2:
        return f"{teile[1]}, {teile[0]}"
    return mitarbeiter_name or ""


def _virtuelle_krank_eintraege(
    dienstplan_repo: Any, reports_repo: ReportsRepository, von: Optional[date], bis: Optional[date]
) -> List[dict[str, Any]]:
    """Liefert für Tage OHNE importierten Dienstplan (siehe get_quelle) je
    laufender Krankmeldung einen schreibgeschützten virtuellen Eintrag, damit
    länger andauernde Krankmeldungen auch ohne Excel-Import sichtbar sind."""
    if von is None or bis is None or bis < von:
        return []
    anzahl_tage = (bis - von).days + 1
    if anzahl_tage > MAX_VIRTUELLE_TAGE:
        return []

    tage_ohne_import = [
        von + timedelta(days=i)
        for i in range(anzahl_tage)
        if not dienstplan_repo.get_quelle(von + timedelta(days=i)).get("quelle_datei")
    ]
    if not tage_ohne_import:
        return []

    reports = [_row_to_report_dict(r) for r in reports_repo.list_reports()]
    virtuelle: List[dict[str, Any]] = []
    for tag in tage_ohne_import:
        for report in reports:
            if report["sick_from"] <= tag <= report["sick_to"]:
                virtuelle.append({
                    "id": f"virtual-{report['id']}-{tag.isoformat()}",
                    "datum": tag,
                    "mitarbeiter_name": _employee_zu_dienstplan_name(report["employee"]),
                    "dienst_kategorie": None,
                    "start_zeit": None,
                    "end_zeit": None,
                    "ist_krank": True,
                    "ist_bulmorfahrer": False,
                    "notiz": "",
                    "quelle_datei": "",
                    "created_at": report.get("created_at") or datetime.utcnow(),
                    "virtuell": True,
                })
    return virtuelle


def _krank_ohne_meldung(
    eintraege: List[dict[str, Any]], tag: date, reports_repo: ReportsRepository
) -> List[dict[str, Any]]:
    """Ermittelt, welche am angegebenen Tag als 'Krank' importierten
    Mitarbeitenden noch KEINE passende Krankmeldung haben (Abgleich per
    Name + Zeitraum sick_from..sick_to). Dient dem Frontend dazu, nach
    einem Excel-Import automatisch das Krank-Popup für genau diese
    Personen anzubieten (dort auch ablehnbar, siehe index.html)."""
    krank_namen = {e["mitarbeiter_name"] for e in eintraege if e.get("ist_krank") and e.get("mitarbeiter_name")}
    if not krank_namen:
        return []
    reports = [_row_to_report_dict(r) for r in reports_repo.list_reports()]
    bereits_gemeldet = {
        _employee_zu_dienstplan_name(r["employee"]).strip().lower()
        for r in reports
        if r["sick_from"] <= tag <= r["sick_to"]
    }
    return [
        {"mitarbeiter_name": name, "datum": tag}
        for name in sorted(krank_namen)
        if name.strip().lower() not in bereits_gemeldet
    ]


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {
        "id": row.id, "datum": row.datum, "mitarbeiter_name": row.mitarbeiter_name,
        "mitarbeiter_id": row.mitarbeiter_id,
        "dienst_kategorie": row.dienst_kategorie, "start_zeit": row.start_zeit, "end_zeit": row.end_zeit,
        "ist_krank": row.ist_krank, "ist_bulmorfahrer": row.ist_bulmorfahrer, "ausgeschlossen": row.ausgeschlossen,
        "notiz": row.notiz, "quelle_datei": row.quelle_datei, "created_at": row.created_at,
    }


def _tagesdaten_sortiert(
    tag: date, repo: Any, reports_repo: ReportsRepository
) -> List[dict[str, Any]]:
    rows = [_row_to_dict(r) for r in repo.list_eintraege(tag, tag)]
    rows.extend(_virtuelle_krank_eintraege(repo, reports_repo, tag, tag))
    return kategorisiere_und_sortiere(rows)


def _sichere_tagesdienstplan_snapshot(
    tag: date, repo: Any, reports_repo: ReportsRepository, ersteller: str
) -> None:
    """Speichert bei jedem Import und jeder manuellen Änderung automatisch
    eine Excel-Kopie des betroffenen Tages unter
    Backups/Tagesdienstpläne/<Datum>/<Datum>_<Uhrzeit>.xlsx - rein
    informativ/als Verlauf gedacht, ein Fehler hierbei darf die eigentliche
    Import-/Änderungs-Operation nicht verhindern."""
    try:
        rows = _tagesdaten_sortiert(tag, repo, reports_repo)
        if not rows:
            return
        inhalt = export_dienstplan_excel(tag, rows, ersteller=ersteller)
        tag_ordner = TAGESDIENSTPLAN_BACKUP_DIR / tag.strftime("%d.%m.%Y")
        tag_ordner.mkdir(parents=True, exist_ok=True)
        dateiname = f"{tag.strftime('%d.%m.%Y')}_{datetime.now().strftime('%H-%M-%S')}.xlsx"
        (tag_ordner / dateiname).write_bytes(inhalt)
    except Exception:  # noqa: BLE001 - Backup ist best-effort, darf Hauptvorgang nicht stoeren
        pass


@router.get("", response_model=List[DienstplanEintragOut])
def list_dienstplan(
    von: Optional[date] = None,
    bis: Optional[date] = None,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    rows = [_row_to_dict(r) for r in repo.list_eintraege(von, bis)]
    rows.extend(_virtuelle_krank_eintraege(repo, reports_repo, von, bis))
    return kategorisiere_und_sortiere(rows)


@router.get("/quelle", response_model=DienstplanQuelle)
def get_quelle(
    datum: date,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(get_current_role),
):
    """Woher die angezeigten Daten stammen (Excel-Dateiname + Importzeitpunkt),
    damit sichtbar ist, dass von der importierten Datenbank gearbeitet wird."""
    return repo.get_quelle(datum)


@router.get("/export")
def export_dienstplan(
    datum: date,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    """Gibt den Dienstplan eines Tages als Excel-Datei zurück (identisch zum
    Format der echten Tagesdienstplan-Vorlage, siehe dienstplan_export.py)."""
    sortierte_rows = _tagesdaten_sortiert(datum, repo, reports_repo)
    if not sortierte_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Für diesen Tag liegen keine Dienstplan-Daten vor.")
    actor_username = request.session.get("username", role)
    inhalt = export_dienstplan_excel(datum, sortierte_rows, ersteller=actor_username)
    dateiname = f"Dienstplan_{datum.strftime('%d.%m.%Y')}.xlsx"
    return Response(
        content=inhalt,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


@router.get("/audit", response_model=List[DienstplanAuditOut])
def list_dienstplan_audit(
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(require_admin),
):
    return repo.list_audit()


@router.put("/{eintrag_id}", response_model=DienstplanEintragOut)
def update_dienstplan_eintrag(
    eintrag_id: str,
    payload: DienstplanEintragUpdate,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_schichtleitung),
):
    auch_krankmeldung_loeschen = bool(payload.auch_krankmeldung_loeschen)
    data = payload.model_dump(exclude_unset=True, exclude_none=True, exclude={"auch_krankmeldung_loeschen"})
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Änderungen übermittelt.")
    actor_username = request.session.get("username", role)

    vorher = _row_to_dict(repo.get_eintrag(eintrag_id))
    war_krank = bool(vorher.get("ist_krank"))

    row = repo.update_eintrag(eintrag_id, data, role, actor_username)
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(ergebnis["datum"], repo, reports_repo, actor_username)

    # Krank-Status wurde gerade entfernt (true -> false): optional die
    # passende(n) laufende(n) Krankmeldung(en) dieser Person mit löschen
    # (Nutzer wurde im Frontend vorher gefragt, siehe index.html). Sonst nur
    # zur Nachvollziehbarkeit in der Mitarbeiter-Historie vermerken.
    if war_krank and data.get("ist_krank") is False:
        if auch_krankmeldung_loeschen:
            employee_name = _dienstplan_name_zu_employee(ergebnis["mitarbeiter_name"]).strip().casefold()
            alle_reports = [_row_to_report_dict(r) for r in reports_repo.list_reports()]
            passende = [
                r for r in alle_reports
                if r["employee"].strip().casefold() == employee_name
                and r["sick_from"] <= ergebnis["datum"] <= r["sick_to"]
            ]
            for r in passende:
                reports_repo.delete_report(r["id"], role, actor_username)
        else:
            record_ereignis(
                mitarbeiter_id=ergebnis.get("mitarbeiter_id"),
                mitarbeiter_name=ergebnis["mitarbeiter_name"],
                ereignis_typ="dienstplan_krank_aufgehoben",
                beschreibung=f"Krank-Status im Dienstplan vom {ergebnis['datum']} aufgehoben (Krankmeldung bewusst nicht gelöscht).",
                bezug_typ="dienstplan", bezug_id=eintrag_id,
                actor_username=actor_username, actor_role=role,
            )

    record_activity(
        request, aktion="UPDATE", bereich="Dienstplan",
        entity_typ="dienstplan", entity_id=eintrag_id, entity_bezeichnung=ergebnis["mitarbeiter_name"],
        beschreibung=f"Dienstplan-Eintrag von '{ergebnis['mitarbeiter_name']}' am {ergebnis['datum']} bearbeitet.",
    )
    return ergebnis


@router.post("/import", response_model=DienstplanImportResult)
async def import_dienstplan(
    datei: UploadFile,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    mitarbeiter_repo=Depends(get_mitarbeiter_repository),
    role: str = Depends(require_schichtleitung),
):
    if not datei.filename or not datei.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bitte eine Excel-Datei (.xlsx) hochladen.")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await datei.read())
        tmp_path = Path(tmp.name)

    try:
        ergebnis = parse_dienstplan_excel(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not ergebnis["success"]:
        return DienstplanImportResult(success=False, error=ergebnis["error"])

    tag = ergebnis["datum"] or date.today()
    mitarbeiter_liste = mitarbeiter_repo.list_mitarbeiter()
    nicht_zugeordnet: list[str] = []
    unsicher: list[UnsichereZuordnung] = []
    eintraege = []
    for e in ergebnis["eintraege"]:
        treffer = ordne_mitarbeiter_zu(e["mitarbeiter_name"], mitarbeiter_liste)
        if treffer is None:
            nicht_zugeordnet.append(e["mitarbeiter_name"])
            mitarbeiter_id = None
        else:
            mitarbeiter_id = treffer.mitarbeiter.id if not isinstance(treffer.mitarbeiter, dict) else treffer.mitarbeiter["id"]
            if treffer.fuzzy:
                vorname = treffer.mitarbeiter["vorname"] if isinstance(treffer.mitarbeiter, dict) else treffer.mitarbeiter.vorname
                nachname = treffer.mitarbeiter["nachname"] if isinstance(treffer.mitarbeiter, dict) else treffer.mitarbeiter.nachname
                unsicher.append(UnsichereZuordnung(mitarbeiter_name=e["mitarbeiter_name"], vorschlag=f"{vorname} {nachname}"))
        eintraege.append({
            "mitarbeiter_name": e["mitarbeiter_name"],
            "mitarbeiter_id": mitarbeiter_id,
            "dienst_kategorie": e["dienst_kategorie"],
            "start_zeit": e["start_zeit"],
            "end_zeit": e["end_zeit"],
            "ist_krank": e["ist_krank"],
            "ist_bulmorfahrer": e["ist_bulmorfahrer"],
            "notiz": e["notiz"],
        })
    repo.replace_tag(tag, eintraege, datei.filename)
    actor_username = request.session.get("username", role)
    _sichere_tagesdienstplan_snapshot(tag, repo, reports_repo, actor_username)
    record_activity(
        request, aktion="IMPORT", bereich="Dienstplan",
        entity_typ="dienstplan", entity_bezeichnung=datei.filename,
        beschreibung=f"Dienstplan für {tag} aus '{datei.filename}' importiert ({len(eintraege)} Einträge, {len(nicht_zugeordnet)} nicht zugeordnet).",
    )

    return DienstplanImportResult(
        success=True,
        datum=tag,
        anzahl_eintraege=len(eintraege),
        anzahl_krank=sum(1 for e in eintraege if e["ist_krank"]),
        anzahl_bulmorfahrer=sum(1 for e in eintraege if e["ist_bulmorfahrer"]),
        unbekannte_dienste=ergebnis["unbekannte_dienste"],
        krank_ohne_meldung=_krank_ohne_meldung(eintraege, tag, reports_repo),
        nicht_zugeordnete_mitarbeiter=nicht_zugeordnet,
        unsichere_zuordnungen=unsicher,
    )

