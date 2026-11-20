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
from ..deps import get_current_role, require_disponent
from ..dienstplan_auswertung_export import export_dienstplan_auswertung_excel
from ..dienstplan_export import export_dienstplan_excel
from ..dienstplan_parser import BEKANNTE_KUERZEL, parse_dienstplan_excel
from ..dienstplan_sortierung import kategorisiere_und_sortiere
from ..excel_export import export_tabelle_excel
from ..mitarbeiter_historie import record_ereignis
from ..mitarbeiter_matching import ist_mitarbeiter_name_bekannt, ordne_mitarbeiter_zu
from ..modules_repository import get_dienstplan_repository, get_mitarbeiter_repository
from ..repository import ReportsRepository, get_reports_repository
from ..schemas import (
    DienstplanAuditOut,
    DienstplanAuswertungOut,
    DienstplanAuswertungZeile,
    DienstplanEintragCreate,
    DienstplanEintragOut,
    DienstplanEintragUpdate,
    DienstplanImportResult,
    DienstplanQuelle,
    KrankmeldungsEintrag,
    KrankmeldungsZusammenfassung,
    NichtZugeordneterMitarbeiter,
    UnsichereZuordnung,
    VerspaetungsEintrag,
)
from .. import tagesprotokoll

router = APIRouter(prefix="/api/dienstplan", tags=["dienstplan"])

# backend/app/routers/dienstplan.py -> routers -> app -> backend -> Projektordner
PROJEKT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TAGESDIENSTPLAN_BACKUP_DIR = PROJEKT_ROOT / "Backups" / "Tagesdienstpläne"
TAGESPROTOKOLL_BACKUP_DIR = PROJEKT_ROOT / "Backups" / "Tagesprotokoll"
# Automatisch gepflegte Excel-Datei je Tag mit ALLEN Dienstplan-Änderungen
# (Hinzufügen/Bearbeiten/Entfernen/Wiederherstellen, siehe
# _sichere_aenderungen_snapshot) - für den Tab "Änderungen" im Frontend.
AENDERUNGEN_BACKUP_DIR = PROJEKT_ROOT / "Backups" / "Tagesdienstpläne" / "Aenderungen"

# Lesbare Spaltennamen für Änderungs-Beschreibungen (Frontend-Protokoll-Text
# und Excel-Export "Änderungen", siehe _sichere_aenderungen_snapshot) - auch
# die bei Hinzufügen/Entfernen relevanten Felder sind enthalten, nicht nur
# die beim manuellen Bearbeiten üblichen.
FELDNAMEN = {
    "mitarbeiter_name": "Mitarbeiter", "dienst_kategorie": "Dienst",
    "ist_krank": "Krank", "ist_bulmorfahrer": "Bulmor-Fahrer:in", "ausgeschlossen": "Ausgeschlossen",
    "start_zeit": "Beginn", "end_zeit": "Ende", "verspaetung_minuten": "Verspätung (Minuten)",
    "geloescht": "Entfernt", "notiz": "Notiz", "mitarbeiter_id": "Mitarbeiter-Zuordnung (Stammdaten-ID)",
}
AKTION_LABEL = {
    "HINZUGEFÜGT": "Hinzugefügt", "BEARBEITET": "Bearbeitet",
    "ENTFERNT": "Entfernt", "WIEDERHERGESTELLT": "Wiederhergestellt",
    "ZUORDNUNG_BESTAETIGT": "Zuordnung bestätigt", "ZUORDNUNG_ABGELEHNT": "Zuordnung abgelehnt",
}

# Für die virtuelle Krank-Überlagerung (siehe _virtuelle_krank_eintraege)
# maximal betrachteter Zeitraum, um ausufernde Schleifen bei sehr großen
# von/bis-Bereichen zu vermeiden.
MAX_VIRTUELLE_TAGE = 62


def _row_to_report_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {
        "id": row.id, "employee": row.employee, "sick_from": row.sick_from,
        "sick_to": row.sick_to, "reported_at": row.reported_at, "accepted_by": row.accepted_by,
        "created_at": row.created_at,
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
        "geloescht": row.geloescht, "geloescht_am": row.geloescht_am, "geloescht_durch": row.geloescht_durch,
        "wiederhergestellt_am": row.wiederhergestellt_am, "wiederhergestellt_durch": row.wiederhergestellt_durch,
        "manuell_hinzugefuegt": row.manuell_hinzugefuegt, "hinzugefuegt_durch": row.hinzugefuegt_durch,
        "verspaetung_minuten": row.verspaetung_minuten,
        "verspaetung_erfasst_von": row.verspaetung_erfasst_von, "verspaetung_erfasst_am": row.verspaetung_erfasst_am,
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
    Backups/Tagesdienstpläne/<Jahr>/<MM>_<Monat>/<Tag>.xlsx - überschreibt
    dabei bewusst den vorherigen Stand desselben Tages (kein Verlauf mehr,
    siehe Tagesprotokoll für den Änderungsverlauf), damit nicht für jede
    Änderung/jeden Tag eine eigene Datei/ein eigener Ordner entsteht. Ein
    Fehler hierbei darf die eigentliche Import-/Änderungs-Operation nicht
    verhindern."""
    try:
        rows = _tagesdaten_sortiert(tag, repo, reports_repo)
        if not rows:
            return
        inhalt = export_dienstplan_excel(tag, rows, ersteller=ersteller)
        datei = tagesprotokoll.pfad(TAGESDIENSTPLAN_BACKUP_DIR, tag)
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(inhalt)
    except Exception:  # noqa: BLE001 - Backup ist best-effort, darf Hauptvorgang nicht stoeren
        pass


def _protokolliere_tagesaenderung(
    tag: date, *, aktion: str, mitarbeiter_name: str = "", actor_username: str = "", actor_role: str = "",
    beschreibung: str = "",
) -> None:
    """Hängt eine Zeile an Backups/Tagesprotokoll/<Jahr>/<MM>_<Monat>/<Tag>.xlsx
    an - ein lückenloses, menschenlesbares Protokoll aller Dienstplan-
    Änderungen DIESES Tages (siehe tagesprotokoll.py)."""
    tagesprotokoll.protokolliere(
        TAGESPROTOKOLL_BACKUP_DIR, tag, aktion=aktion, mitarbeiter_name=mitarbeiter_name,
        actor_username=actor_username, actor_role=actor_role, beschreibung=beschreibung,
    )


def _audit_zu_dict(a: Any) -> dict[str, Any]:
    if isinstance(a, dict):
        return dict(a)
    return {
        "event_at": a.event_at, "datum": a.datum, "mitarbeiter_name": a.mitarbeiter_name, "action": a.action,
        "actor_role": a.actor_role, "actor_username": a.actor_username,
        "old_data": a.old_data, "new_data": a.new_data,
    }


def _aenderungen_text(old_data: Optional[dict], new_data: Optional[dict]) -> str:
    """Menschenlesbare Zusammenfassung einer alt/neu-Differenz (siehe
    FELDNAMEN) - für die Excel-Spalte "Änderungen" (Export und automatische
    Tagesdatei, siehe _sichere_aenderungen_snapshot)."""
    before, after = old_data or {}, new_data or {}
    teile = [
        f"{FELDNAMEN.get(k, k)}: {before.get(k)!r} → {after.get(k)!r}"
        for k in FELDNAMEN if k in after and before.get(k) != after.get(k)
    ]
    return "; ".join(teile) if teile else "Keine Feldänderung erfasst."


def _aenderungen_zeilen(audit_rows: list[Any]) -> list[dict[str, Any]]:
    """Wandelt DienstplanAudit-Zeilen (ORM-Objekte oder Supabase-Dicts) in
    für Tabelle/Excel-Export aufbereitete Zeilen um - gemeinsam genutzt von
    der automatischen Tagesdatei (_sichere_aenderungen_snapshot) und dem
    Export-Endpunkt /api/dienstplan/audit/export."""
    eintraege = sorted((_audit_zu_dict(a) for a in audit_rows), key=lambda a: a["event_at"])
    return [
        {
            "event_at": a["event_at"],
            "datum": a.get("datum"),
            "aktion": AKTION_LABEL.get(a["action"], a["action"]),
            "mitarbeiter_name": a.get("mitarbeiter_name") or "",
            "actor_username": a.get("actor_username") or "",
            "actor_role": a.get("actor_role") or "",
            "aenderungen": _aenderungen_text(a.get("old_data"), a.get("new_data")),
        }
        for a in eintraege
    ]


AENDERUNGEN_SPALTEN = [
    ("datum", "Tag"), ("event_at", "Zeitpunkt"), ("aktion", "Aktion"), ("mitarbeiter_name", "Mitarbeiter:in"),
    ("actor_username", "Durchgeführt von"), ("actor_role", "Rolle"), ("aenderungen", "Änderungen"),
]


def _sichere_aenderungen_snapshot(tag: date, repo: Any) -> None:
    """Erstellt/überschreibt bei jeder Dienstplan-Änderung (Hinzufügen/
    Bearbeiten/Entfernen/Wiederherstellen) eine Excel-Datei unter
    Backups/Tagesdienstpläne/Aenderungen/<Jahr>/<MM>_<Monat>/<Tag>.xlsx mit
    ALLEN bisherigen Änderungen dieses Tages. Anders als das wachsende
    Tagesprotokoll (siehe _protokolliere_tagesaenderung) wird diese Datei
    bei jeder weiteren Änderung komplett neu geschrieben (überschrieben) -
    da sie dabei aber immer aus der vollständigen, in DienstplanAudit
    gespeicherten Historie dieses Tages neu aufgebaut wird, bleibt trotzdem
    alles lückenlos nachvollziehbar. Ein Fehler hierbei darf die eigentliche
    Änderungs-Operation nicht verhindern."""
    try:
        zeilen = _aenderungen_zeilen(repo.list_audit(von=tag, bis=tag))
        if not zeilen:
            return
        inhalt = export_tabelle_excel(
            titel=f"Dienstplan-Änderungen {tag.strftime('%d.%m.%Y')}",
            blattname="Änderungen",
            spalten=AENDERUNGEN_SPALTEN,
            zeilen=zeilen,
        )
        datei = tagesprotokoll.pfad(AENDERUNGEN_BACKUP_DIR, tag)
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(inhalt)
    except Exception:  # noqa: BLE001 - best-effort, darf Hauptvorgang nicht stoeren
        pass


@router.get("", response_model=List[DienstplanEintragOut])
def list_dienstplan(
    von: Optional[date] = None,
    bis: Optional[date] = None,
    mit_geloeschten: bool = False,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(get_current_role),
):
    rows = [_row_to_dict(r) for r in repo.list_eintraege(von, bis, mit_geloeschten)]
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
    von: Optional[date] = None,
    bis: Optional[date] = None,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(get_current_role),
):
    """Änderungsprotokoll (siehe Tab "Änderungen" im Frontend) - optional auf
    einen einzelnen Tag (von=bis) oder einen Zeitraum eingegrenzt. Für ALLE
    angemeldeten Rollen einsehbar."""
    if von and bis and bis < von:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'Bis' darf nicht vor 'Von' liegen.")
    return repo.list_audit(von, bis)


@router.get("/audit/export")
def export_dienstplan_audit(
    von: date,
    bis: date,
    repo=Depends(get_dienstplan_repository),
    role: str = Depends(get_current_role),
):
    if bis < von:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'Bis' darf nicht vor 'Von' liegen.")
    zeilen = _aenderungen_zeilen(repo.list_audit(von, bis))
    inhalt = export_tabelle_excel(
        titel=f"Dienstplan-Änderungen {von.strftime('%d.%m.%Y')} – {bis.strftime('%d.%m.%Y')}",
        blattname="Änderungen",
        spalten=AENDERUNGEN_SPALTEN,
        zeilen=zeilen,
    )
    dateiname = f"Dienstplan-Aenderungen_{von.isoformat()}_{bis.isoformat()}.xlsx"
    return Response(
        content=inhalt,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


@router.get("/bekannte-kuerzel", response_model=List[str])
def get_bekannte_kuerzel(role: str = Depends(get_current_role)):
    """Dienst-Kürzel, die das System vollständig kennt (siehe
    dienstplan_parser.BEKANNTE_KUERZEL) - Grundlage für die Markierung
    unbekannter Kürzel in der Dienstplan-Tabelle im Frontend."""
    return sorted(BEKANNTE_KUERZEL)


def _verspaetungen_erfassen(
    von: date, bis: date, repo
) -> tuple[List[VerspaetungsEintrag], List[DienstplanAuswertungZeile]]:
    """Liefert jeden einzelnen Verspätungs-Vorfall (mit Tag + erfassendem
    Account, siehe models.py:DienstplanEintrag.verspaetung_erfasst_von/_am)
    sowie eine Zusammenfassung je Mitarbeiter:in über den Zeitraum."""
    rows = [_row_to_dict(r) for r in repo.list_eintraege(von, bis)]
    detail: List[VerspaetungsEintrag] = []
    aggregiert: dict[str, dict[str, int]] = {}
    for r in rows:
        minuten = r.get("verspaetung_minuten") or 0
        if minuten <= 0:
            continue
        detail.append(VerspaetungsEintrag(
            dienstplan_id=r["id"], datum=r["datum"], mitarbeiter_name=r["mitarbeiter_name"],
            dienst_kategorie=r.get("dienst_kategorie"), geplanter_beginn=r.get("start_zeit"),
            verspaetung_minuten=minuten, erfasst_von=r.get("verspaetung_erfasst_von") or "",
            erfasst_am=r.get("verspaetung_erfasst_am"),
        ))
        eintrag = aggregiert.setdefault(r["mitarbeiter_name"], {"anzahl": 0, "summe": 0})
        eintrag["anzahl"] += 1
        eintrag["summe"] += minuten
    detail.sort(key=lambda z: (z.datum, z.mitarbeiter_name), reverse=True)
    zusammenfassung = [
        DienstplanAuswertungZeile(
            mitarbeiter_name=name, anzahl_verspaetungen=werte["anzahl"], summe_verspaetung_minuten=werte["summe"],
        )
        for name, werte in aggregiert.items()
    ]
    zusammenfassung.sort(key=lambda z: (-z.summe_verspaetung_minuten, z.mitarbeiter_name))
    return detail, zusammenfassung


def _krankmeldungen_erfassen(
    von: date, bis: date, reports_repo: ReportsRepository
) -> tuple[List[KrankmeldungsEintrag], List[KrankmeldungsZusammenfassung]]:
    """Liefert jede Krankmeldung, deren Zeitraum sich mit [von, bis]
    überschneidet, sowie eine Zusammenfassung je Mitarbeiter:in. Kranktage
    werden - wie in der Mitarbeiter-Historie (routers/mitarbeiter.py) -
    über den VOLLEN gemeldeten Zeitraum gezählt, nicht auf [von, bis]
    zugeschnitten."""
    alle = [_row_to_report_dict(r) for r in reports_repo.list_reports()]
    detail: List[KrankmeldungsEintrag] = []
    aggregiert: dict[str, dict[str, int]] = {}
    for r in alle:
        if r["sick_from"] > bis or r["sick_to"] < von:
            continue
        name = _employee_zu_dienstplan_name(r["employee"])
        kranktage = max((r["sick_to"] - r["sick_from"]).days + 1, 0)
        detail.append(KrankmeldungsEintrag(
            report_id=r["id"], mitarbeiter_name=name, sick_from=r["sick_from"], sick_to=r["sick_to"],
            kranktage=kranktage, accepted_by=r.get("accepted_by") or "", reported_at=r["reported_at"],
        ))
        eintrag = aggregiert.setdefault(name, {"anzahl": 0, "tage": 0})
        eintrag["anzahl"] += 1
        eintrag["tage"] += kranktage
    detail.sort(key=lambda z: (z.sick_from, z.mitarbeiter_name), reverse=True)
    zusammenfassung = [
        KrankmeldungsZusammenfassung(
            mitarbeiter_name=name, anzahl_krankmeldungen=werte["anzahl"], kranktage_gesamt=werte["tage"],
        )
        for name, werte in aggregiert.items()
    ]
    zusammenfassung.sort(key=lambda z: (-z.kranktage_gesamt, z.mitarbeiter_name))
    return detail, zusammenfassung


@router.get("/auswertung", response_model=DienstplanAuswertungOut)
def get_dienstplan_auswertung(
    von: date,
    bis: date,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    """Komplette Auswertung für einen frei wählbaren Zeitraum (siehe Tab
    'Dienstplan Auswertung' im Frontend): Verspätungen (einzeln mit Tag +
    erfassendem Account, siehe "Ver."-Popup) UND Krankmeldungen, jeweils
    als Einzel-Vorfälle und als Zusammenfassung je Mitarbeiter:in. Ab Rolle
    Disponent (wie die Krankmeldungs-Übersicht selbst)."""
    if bis < von:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'Bis' darf nicht vor 'Von' liegen.")
    verspaetungen, verspaetungen_zsf = _verspaetungen_erfassen(von, bis, repo)
    krankmeldungen, krankmeldungen_zsf = _krankmeldungen_erfassen(von, bis, reports_repo)
    return DienstplanAuswertungOut(
        von=von, bis=bis, verspaetungen=verspaetungen, verspaetungen_zusammenfassung=verspaetungen_zsf,
        krankmeldungen=krankmeldungen, krankmeldungen_zusammenfassung=krankmeldungen_zsf,
    )


@router.get("/auswertung/export")
def export_dienstplan_auswertung(
    von: date,
    bis: date,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    if bis < von:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'Bis' darf nicht vor 'Von' liegen.")
    verspaetungen, _ = _verspaetungen_erfassen(von, bis, repo)
    krankmeldungen, _ = _krankmeldungen_erfassen(von, bis, reports_repo)
    inhalt = export_dienstplan_auswertung_excel(
        von, bis,
        [z.model_dump() for z in verspaetungen],
        [z.model_dump() for z in krankmeldungen],
    )
    dateiname = f"Dienstplan-Auswertung_{von.isoformat()}_{bis.isoformat()}.xlsx"
    return Response(
        content=inhalt,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


@router.post("", response_model=DienstplanEintragOut, status_code=status.HTTP_201_CREATED)
def create_dienstplan_eintrag(
    payload: DienstplanEintragCreate,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    mitarbeiter_repo=Depends(get_mitarbeiter_repository),
    role: str = Depends(require_disponent),
):
    """Fügt eine einzelne Person manuell zu einem (bereits bestehenden)
    Tagesdienstplan hinzu, unabhängig von einem Excel-Import (siehe
    DienstplanEintragOut.manuell_hinzugefuegt - im Frontend als Hinweis
    sichtbar). Der Name muss exakt einem aktiven Mitarbeiter-Stammdatensatz
    entsprechen (siehe mitarbeiter_matching.ist_mitarbeiter_name_bekannt) -
    Excel-Importe bleiben davon unberührt (dort bewusst tolerant, siehe
    import_dienstplan/unsichere_zuordnungen)."""
    if not ist_mitarbeiter_name_bekannt(payload.mitarbeiter_name, mitarbeiter_repo.list_mitarbeiter()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{payload.mitarbeiter_name}' ist kein aktiver Mitarbeiter-Stammdatensatz. "
            "Bitte aus den Mitarbeiter-Stammdaten auswählen (ggf. dort zuerst anlegen).",
        )
    actor_username = request.session.get("username", role)
    data = payload.model_dump(exclude={"datum"})
    data["hinzugefuegt_durch"] = actor_username
    row = repo.create_eintrag(payload.datum, data, role, actor_username)
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(payload.datum, repo, reports_repo, actor_username)
    _sichere_aenderungen_snapshot(payload.datum, repo)
    _protokolliere_tagesaenderung(
        payload.datum, aktion="HINZUGEFÜGT", mitarbeiter_name=payload.mitarbeiter_name,
        actor_username=actor_username, actor_role=role,
        beschreibung=f"'{payload.mitarbeiter_name}' manuell zum Dienstplan hinzugefügt.",
    )
    record_activity(
        request, aktion="CREATE", bereich="Dienstplan",
        entity_typ="dienstplan", entity_id=ergebnis["id"], entity_bezeichnung=payload.mitarbeiter_name,
        beschreibung=f"'{payload.mitarbeiter_name}' manuell zum Dienstplan vom {payload.datum} hinzugefügt.",
    )
    return ergebnis


@router.delete("/{eintrag_id}", response_model=DienstplanEintragOut)
def delete_dienstplan_eintrag(
    eintrag_id: str,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    """Entfernt eine Person weich (nicht endgültig) aus einem Tagesdienstplan
    - bleibt in der Datenbank erhalten und als 'gelöscht' gekennzeichnet
    (siehe DienstplanEintragOut.geloescht), damit im Frontend nachvollziehbar
    bleibt, dass/wer sie entfernt hat; über /wiederherstellen rückgängig
    machbar. Siehe auch Tagesprotokoll für die laufende Protokollierung."""
    actor_username = request.session.get("username", role)
    vorher = _row_to_dict(repo.get_eintrag(eintrag_id))
    row = repo.update_eintrag(
        eintrag_id,
        {"geloescht": True, "geloescht_am": datetime.utcnow(), "geloescht_durch": actor_username},
        role, actor_username, aktion="ENTFERNT",
    )
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(ergebnis["datum"], repo, reports_repo, actor_username)
    _sichere_aenderungen_snapshot(ergebnis["datum"], repo)
    _protokolliere_tagesaenderung(
        ergebnis["datum"], aktion="ENTFERNT", mitarbeiter_name=ergebnis["mitarbeiter_name"],
        actor_username=actor_username, actor_role=role,
        beschreibung=f"'{ergebnis['mitarbeiter_name']}' aus dem Dienstplan vom {ergebnis['datum']} entfernt.",
    )
    record_activity(
        request, aktion="DELETE", bereich="Dienstplan",
        entity_typ="dienstplan", entity_id=eintrag_id, entity_bezeichnung=ergebnis["mitarbeiter_name"],
        beschreibung=f"'{ergebnis['mitarbeiter_name']}' aus dem Dienstplan vom {ergebnis['datum']} entfernt (weich gelöscht).",
    )
    return ergebnis


@router.post("/{eintrag_id}/wiederherstellen", response_model=DienstplanEintragOut)
def restore_dienstplan_eintrag(
    eintrag_id: str,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    """Macht ein vorheriges delete_dienstplan_eintrag rückgängig."""
    actor_username = request.session.get("username", role)
    row = repo.update_eintrag(
        eintrag_id,
        {"geloescht": False, "wiederhergestellt_am": datetime.utcnow(), "wiederhergestellt_durch": actor_username},
        role, actor_username, aktion="WIEDERHERGESTELLT",
    )
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(ergebnis["datum"], repo, reports_repo, actor_username)
    _sichere_aenderungen_snapshot(ergebnis["datum"], repo)
    _protokolliere_tagesaenderung(
        ergebnis["datum"], aktion="WIEDERHERGESTELLT", mitarbeiter_name=ergebnis["mitarbeiter_name"],
        actor_username=actor_username, actor_role=role,
        beschreibung=f"'{ergebnis['mitarbeiter_name']}' im Dienstplan vom {ergebnis['datum']} wiederhergestellt.",
    )
    record_activity(
        request, aktion="UPDATE", bereich="Dienstplan",
        entity_typ="dienstplan", entity_id=eintrag_id, entity_bezeichnung=ergebnis["mitarbeiter_name"],
        beschreibung=f"'{ergebnis['mitarbeiter_name']}' im Dienstplan vom {ergebnis['datum']} wiederhergestellt.",
    )
    return ergebnis


@router.put("/{eintrag_id}", response_model=DienstplanEintragOut)
def update_dienstplan_eintrag(
    eintrag_id: str,
    payload: DienstplanEintragUpdate,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    auch_krankmeldung_loeschen = bool(payload.auch_krankmeldung_loeschen)
    data = payload.model_dump(exclude_unset=True, exclude_none=True, exclude={"auch_krankmeldung_loeschen"})
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Änderungen übermittelt.")
    actor_username = request.session.get("username", role)

    vorher = _row_to_dict(repo.get_eintrag(eintrag_id))
    war_krank = bool(vorher.get("ist_krank"))

    # Verspätung wird (siehe "Ver."-Popup im Frontend) immer zusammen mit
    # wer/wann gespeichert, damit das in der Auswertung nachvollziehbar ist
    # (siehe models.py:DienstplanEintrag.verspaetung_erfasst_von/_am).
    if "verspaetung_minuten" in data:
        data["verspaetung_erfasst_von"] = actor_username
        data["verspaetung_erfasst_am"] = datetime.utcnow()

    row = repo.update_eintrag(eintrag_id, data, role, actor_username, aktion="BEARBEITET")
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(ergebnis["datum"], repo, reports_repo, actor_username)
    _sichere_aenderungen_snapshot(ergebnis["datum"], repo)

    aenderungen = [
        f"{FELDNAMEN.get(k, k)}: {vorher.get(k)!r} → {v!r}"
        for k, v in data.items() if k in FELDNAMEN and vorher.get(k) != v
    ]
    if aenderungen:
        _protokolliere_tagesaenderung(
            ergebnis["datum"], aktion="BEARBEITET", mitarbeiter_name=ergebnis["mitarbeiter_name"],
            actor_username=actor_username, actor_role=role,
            beschreibung=f"'{ergebnis['mitarbeiter_name']}': " + "; ".join(aenderungen),
        )

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


@router.post("/{eintrag_id}/zuordnung/bestaetigen", response_model=DienstplanEintragOut)
def zuordnung_bestaetigen(
    eintrag_id: str,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    """Bestätigt eine beim Import nur unscharf (Tippfehler/Dreher) erkannte
    Mitarbeiter-Zuordnung (siehe UnsichereZuordnung/import_dienstplan) als
    richtig. Ändert an der bereits übernommenen Zuordnung nichts, schreibt
    aber - anders als vorher, wo die Übernahme stillschweigend geschah -
    einen Änderungsprotokoll-Eintrag mit Wer/Wann, damit die Bestätigung
    selbst nachvollziehbar bleibt."""
    actor_username = request.session.get("username", role)
    vorher = _row_to_dict(repo.get_eintrag(eintrag_id))
    row = repo.update_eintrag(eintrag_id, {}, role, actor_username, aktion="ZUORDNUNG_BESTAETIGT")
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(ergebnis["datum"], repo, reports_repo, actor_username)
    _sichere_aenderungen_snapshot(ergebnis["datum"], repo)
    _protokolliere_tagesaenderung(
        ergebnis["datum"], aktion="ZUORDNUNG_BESTAETIGT", mitarbeiter_name=ergebnis["mitarbeiter_name"],
        actor_username=actor_username, actor_role=role,
        beschreibung=f"Automatische Mitarbeiter-Zuordnung von '{vorher['mitarbeiter_name']}' bestätigt.",
    )
    record_activity(
        request, aktion="UPDATE", bereich="Dienstplan",
        entity_typ="dienstplan", entity_id=eintrag_id, entity_bezeichnung=ergebnis["mitarbeiter_name"],
        beschreibung=f"Automatische Mitarbeiter-Zuordnung von '{ergebnis['mitarbeiter_name']}' am {ergebnis['datum']} bestätigt.",
    )
    return ergebnis


@router.post("/{eintrag_id}/zuordnung/ablehnen", response_model=DienstplanEintragOut)
def zuordnung_ablehnen(
    eintrag_id: str,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    role: str = Depends(require_disponent),
):
    """Macht eine beim Import nur unscharf (Tippfehler/Dreher) erkannte
    Mitarbeiter-Zuordnung rückgängig (siehe UnsichereZuordnung/
    import_dienstplan): der Dienstplan-Eintrag bleibt bestehen, verliert
    aber die mitarbeiter_id - der Name gilt danach wie bei einem von
    vornherein nicht zugeordneten Import-Eintrag (z. B. über "Jetzt
    anlegen" in den Mitarbeiter-Stammdaten nachpflegbar)."""
    actor_username = request.session.get("username", role)
    vorher = _row_to_dict(repo.get_eintrag(eintrag_id))
    row = repo.update_eintrag(eintrag_id, {"mitarbeiter_id": None}, role, actor_username, aktion="ZUORDNUNG_ABGELEHNT")
    ergebnis = kategorisiere_und_sortiere([_row_to_dict(row)])[0]
    _sichere_tagesdienstplan_snapshot(ergebnis["datum"], repo, reports_repo, actor_username)
    _sichere_aenderungen_snapshot(ergebnis["datum"], repo)
    _protokolliere_tagesaenderung(
        ergebnis["datum"], aktion="ZUORDNUNG_ABGELEHNT", mitarbeiter_name=ergebnis["mitarbeiter_name"],
        actor_username=actor_username, actor_role=role,
        beschreibung=f"Automatische Mitarbeiter-Zuordnung von '{vorher['mitarbeiter_name']}' abgelehnt "
        "(gilt jetzt als nicht zugeordnet).",
    )
    record_activity(
        request, aktion="UPDATE", bereich="Dienstplan",
        entity_typ="dienstplan", entity_id=eintrag_id, entity_bezeichnung=ergebnis["mitarbeiter_name"],
        beschreibung=f"Automatische Mitarbeiter-Zuordnung von '{ergebnis['mitarbeiter_name']}' am {ergebnis['datum']} abgelehnt.",
    )
    return ergebnis


@router.post("/import", response_model=DienstplanImportResult)
async def import_dienstplan(
    datei: UploadFile,
    request: Request,
    repo=Depends(get_dienstplan_repository),
    reports_repo: ReportsRepository = Depends(get_reports_repository),
    mitarbeiter_repo=Depends(get_mitarbeiter_repository),
    role: str = Depends(require_disponent),
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
    # Sammelt pro betroffenem Index in `eintraege` die Zusatzinfos für die
    # Rückmeldung ans Frontend - die passende Dienstplan-ID ist erst nach
    # repo.replace_tag() bekannt (siehe unten), daher zunächst nur der Index.
    nicht_zugeordnet_info: list[dict[str, Any]] = []
    unsicher_info: list[dict[str, Any]] = []
    eintraege = []
    for e in ergebnis["eintraege"]:
        treffer = ordne_mitarbeiter_zu(e["mitarbeiter_name"], mitarbeiter_liste)
        if treffer is None:
            nicht_zugeordnet_info.append({
                "index": len(eintraege), "mitarbeiter_name": e["mitarbeiter_name"],
                "vorname": e.get("vorname", ""), "nachname": e.get("nachname", ""),
            })
            mitarbeiter_id = None
        else:
            mitarbeiter_id = treffer.mitarbeiter.id if not isinstance(treffer.mitarbeiter, dict) else treffer.mitarbeiter["id"]
            if treffer.fuzzy:
                vorschlag_vorname = treffer.mitarbeiter["vorname"] if isinstance(treffer.mitarbeiter, dict) else treffer.mitarbeiter.vorname
                vorschlag_nachname = treffer.mitarbeiter["nachname"] if isinstance(treffer.mitarbeiter, dict) else treffer.mitarbeiter.nachname
                unsicher_info.append({
                    "index": len(eintraege), "mitarbeiter_name": e["mitarbeiter_name"],
                    "vorname": e.get("vorname", ""), "nachname": e.get("nachname", ""),
                    "vorschlag": f"{vorschlag_vorname} {vorschlag_nachname}", "vorgeschlagene_mitarbeiter_id": mitarbeiter_id,
                })
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
    rows = repo.replace_tag(tag, eintraege, datei.filename)
    nicht_zugeordnet = [
        NichtZugeordneterMitarbeiter(
            mitarbeiter_name=info["mitarbeiter_name"], vorname=info["vorname"], nachname=info["nachname"],
            eintrag_id=_row_to_dict(rows[info["index"]])["id"],
        )
        for info in nicht_zugeordnet_info
    ]
    unsicher = [
        UnsichereZuordnung(
            mitarbeiter_name=info["mitarbeiter_name"], vorname=info["vorname"], nachname=info["nachname"],
            vorschlag=info["vorschlag"],
            eintrag_id=_row_to_dict(rows[info["index"]])["id"],
            vorgeschlagene_mitarbeiter_id=info["vorgeschlagene_mitarbeiter_id"],
        )
        for info in unsicher_info
    ]
    actor_username = request.session.get("username", role)
    _sichere_tagesdienstplan_snapshot(tag, repo, reports_repo, actor_username)
    _protokolliere_tagesaenderung(
        tag, aktion="IMPORT", actor_username=actor_username, actor_role=role,
        beschreibung=f"Dienstplan aus '{datei.filename}' importiert ({len(eintraege)} Einträge, "
        f"{len(nicht_zugeordnet)} nicht zugeordnet) - ersetzt den bisherigen Stand dieses Tages.",
    )
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

