"""Legacy biometric clock report ingestion for Talent attendance.

The current device export is a BIFF8 .xls workbook with these columns:
ID de usuario, Nombre, Fecha/Hora, Dispositivo Nro., Registro, Departamento.

Attendance ingestion deliberately does not depend on facial recognition, QR or kiosk
credentials. Report rows are matched to active Talent employees by normalized full name.
"""

from __future__ import annotations

import hashlib
import struct
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.domains.talent_id.models import (
    TalentAttendanceEvent,
    TalentEmployeeAttendanceSetting,
    TalentSite,
)
from app.models import UserProfile


REPORT_REASON_PREFIX = "BIOMETRIC_REPORT:"
MAX_REPORT_BYTES = 10 * 1024 * 1024
EXPECTED_HEADERS = [
    "ID de usuario",
    "Nombre",
    "Fecha/Hora",
    "Dispositivo Nro.",
    "Registro",
    "Departamento",
]
EVENT_CODE_MAP = {
    "0": "CHECK_IN",
    "1": "CHECK_OUT",
}

_CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_CFB_FREE = 0xFFFFFFFF
_CFB_END = 0xFFFFFFFE


class AttendanceReportError(ValueError):
    pass


@dataclass(frozen=True)
class AttendanceReportRow:
    device_user_id: str
    employee_name: str
    occurred_local: datetime
    device_number: str
    record_code: str
    department: str
    source_row: int


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(ascii_text.upper().split())


def _employee_name(employee: UserProfile) -> str:
    return " ".join(
        part.strip()
        for part in [employee.first_name or "", employee.last_name or ""]
        if part and part.strip()
    ).strip()


def _sector(raw: bytes, sector_size: int, sector_id: int) -> bytes:
    offset = 512 + sector_id * sector_size
    return raw[offset : offset + sector_size]


def _follow_chain(start: int, fat: list[int], *, max_items: int = 200000) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    sector_id = start
    while (
        sector_id not in {_CFB_END, _CFB_FREE}
        and 0 <= sector_id < len(fat)
        and sector_id not in seen
        and len(result) < max_items
    ):
        seen.add(sector_id)
        result.append(sector_id)
        sector_id = fat[sector_id]
    return result


def _extract_workbook_stream(raw: bytes) -> bytes:
    if len(raw) < 512 or raw[:8] != _CFB_SIGNATURE:
        raise AttendanceReportError(
            "El archivo no corresponde al formato .xls esperado del reloj biométrico."
        )

    sector_shift = struct.unpack_from("<H", raw, 30)[0]
    sector_size = 1 << sector_shift
    fat_count = struct.unpack_from("<I", raw, 44)[0]
    first_directory_sector = struct.unpack_from("<I", raw, 48)[0]
    first_difat_sector = struct.unpack_from("<I", raw, 68)[0]
    difat_sector_count = struct.unpack_from("<I", raw, 72)[0]

    if sector_size not in {512, 4096}:
        raise AttendanceReportError("El .xls usa un tamaño de sector no compatible.")

    difat = [
        value
        for value in struct.unpack_from("<109I", raw, 76)
        if value not in {_CFB_FREE, _CFB_END}
    ]

    sector_id = first_difat_sector
    for _ in range(difat_sector_count):
        if sector_id in {_CFB_FREE, _CFB_END}:
            break
        block = _sector(raw, sector_size, sector_id)
        entries = struct.unpack(
            f"<{sector_size // 4 - 1}I",
            block[: sector_size - 4],
        )
        difat.extend(value for value in entries if value != _CFB_FREE)
        sector_id = struct.unpack_from("<I", block, sector_size - 4)[0]

    fat: list[int] = []
    for fat_sector in difat[:fat_count]:
        block = _sector(raw, sector_size, fat_sector)
        fat.extend(struct.unpack(f"<{sector_size // 4}I", block))

    directory_stream = b"".join(
        _sector(raw, sector_size, item)
        for item in _follow_chain(first_directory_sector, fat)
    )

    workbook_start = None
    workbook_size = None
    for offset in range(0, len(directory_stream), 128):
        entry = directory_stream[offset : offset + 128]
        if len(entry) < 128:
            break
        name_length = struct.unpack_from("<H", entry, 64)[0]
        if name_length < 2:
            continue
        name = entry[: name_length - 2].decode("utf-16le", "ignore")
        if name not in {"Workbook", "Book"}:
            continue
        workbook_start = struct.unpack_from("<I", entry, 116)[0]
        workbook_size = struct.unpack_from("<Q", entry, 120)[0]
        break

    if workbook_start is None or workbook_size is None:
        raise AttendanceReportError("No se encontró la hoja de Excel dentro del reporte.")

    workbook_stream = b"".join(
        _sector(raw, sector_size, item)
        for item in _follow_chain(workbook_start, fat)
    )
    return workbook_stream[:workbook_size]


def _parse_label(payload: bytes) -> tuple[int, int, str]:
    if len(payload) < 9:
        raise AttendanceReportError("Se encontró una celda de texto incompleta.")

    row, column, _xf, char_count = struct.unpack_from("<HHHH", payload, 0)
    flags = payload[8]
    offset = 9

    if flags & 0x08:
        if len(payload) < offset + 2:
            raise AttendanceReportError("Texto enriquecido incompleto en el reporte.")
        offset += 2
    if flags & 0x04:
        if len(payload) < offset + 4:
            raise AttendanceReportError("Texto extendido incompleto en el reporte.")
        offset += 4

    use_utf16 = bool(flags & 0x01)
    byte_count = char_count * (2 if use_utf16 else 1)
    raw_text = payload[offset : offset + byte_count]
    encoding = "utf-16le" if use_utf16 else "latin1"
    return row, column, raw_text.decode(encoding, "replace")


def _parse_number(payload: bytes) -> tuple[int, int, float]:
    if len(payload) < 14:
        raise AttendanceReportError("Se encontró una celda numérica incompleta.")
    row, column, _xf = struct.unpack_from("<HHH", payload, 0)
    value = struct.unpack_from("<d", payload, 6)[0]
    return row, column, value


def _parse_biff_cells(workbook_stream: bytes) -> dict[tuple[int, int], str | float]:
    cells: dict[tuple[int, int], str | float] = {}
    offset = 0

    while offset + 4 <= len(workbook_stream):
        record_id, payload_size = struct.unpack_from("<HH", workbook_stream, offset)
        payload_start = offset + 4
        payload_end = payload_start + payload_size
        if payload_end > len(workbook_stream):
            break
        payload = workbook_stream[payload_start:payload_end]

        # LABEL (BIFF8 inline unicode string).
        if record_id == 0x0204:
            row, column, value = _parse_label(payload)
            cells[(row, column)] = value
        # NUMBER (IEEE-754 double).
        elif record_id == 0x0203:
            row, column, value = _parse_number(payload)
            cells[(row, column)] = value

        offset = payload_end

    return cells


def _excel_serial_to_datetime(value: float) -> datetime:
    # Excel's 1900 date system, including the historical leap-year compatibility.
    return datetime(1899, 12, 30) + timedelta(days=float(value))


def parse_biometric_xls(raw: bytes) -> list[AttendanceReportRow]:
    if not raw:
        raise AttendanceReportError("El reporte está vacío.")
    if len(raw) > MAX_REPORT_BYTES:
        raise AttendanceReportError("El reporte excede el límite de 10 MB.")

    cells = _parse_biff_cells(_extract_workbook_stream(raw))
    if not cells:
        raise AttendanceReportError("El reporte no contiene filas legibles.")

    headers = [str(cells.get((0, column), "")).strip() for column in range(6)]
    if headers != EXPECTED_HEADERS:
        raise AttendanceReportError(
            "El reporte no tiene las columnas esperadas: "
            + ", ".join(EXPECTED_HEADERS)
            + "."
        )

    max_row = max(row for row, _column in cells)
    parsed: list[AttendanceReportRow] = []

    for row_index in range(1, max_row + 1):
        values = [cells.get((row_index, column)) for column in range(6)]
        if all(value is None or str(value).strip() == "" for value in values):
            continue

        user_id, name, date_value, device_number, record_code, department = values
        if name is None or date_value is None:
            continue

        if isinstance(date_value, (int, float)):
            occurred_local = _excel_serial_to_datetime(float(date_value))
        else:
            raw_date = str(date_value).strip()
            occurred_local = None
            for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    occurred_local = datetime.strptime(raw_date, pattern)
                    break
                except ValueError:
                    continue
            if occurred_local is None:
                raise AttendanceReportError(
                    f"La fila {row_index + 1} contiene una Fecha/Hora inválida."
                )

        parsed.append(
            AttendanceReportRow(
                device_user_id=str(user_id or "").strip(),
                employee_name=str(name or "").strip(),
                occurred_local=occurred_local,
                device_number=(
                    str(int(device_number))
                    if isinstance(device_number, float) and device_number.is_integer()
                    else str(device_number or "").strip()
                ),
                record_code=str(record_code or "").strip(),
                department=str(department or "").strip(),
                source_row=row_index + 1,
            )
        )

    if not parsed:
        raise AttendanceReportError("El reporte no contiene marcaciones.")
    return parsed


def _event_key(row: AttendanceReportRow) -> str:
    canonical = "|".join(
        [
            row.device_user_id,
            _normalize_text(row.employee_name),
            row.occurred_local.strftime("%Y-%m-%dT%H:%M:%S"),
            row.device_number,
            row.record_code,
            _normalize_text(row.department),
        ]
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"biometric-report:{digest}"


def _report_reason(row: AttendanceReportRow) -> str:
    return (
        f"{REPORT_REASON_PREFIX}"
        f"user={row.device_user_id};"
        f"device={row.device_number};"
        f"department={row.department};"
        f"row={row.source_row}"
    )


def is_report_event(event: TalentAttendanceEvent) -> bool:
    return (
        event.method == "MANUAL"
        and str(event.manual_reason or "").startswith(REPORT_REASON_PREFIX)
    )


def import_biometric_report(
    db: Session,
    *,
    raw: bytes,
    site_id: str,
    created_by_sub: str,
    filename: str,
) -> dict:
    rows = parse_biometric_xls(raw)

    site = (
        db.query(TalentSite)
        .filter(TalentSite.id == site_id, TalentSite.active.is_(True))
        .one_or_none()
    )
    if site is None:
        raise AttendanceReportError("La sede seleccionada no existe o está inactiva.")

    try:
        zone = ZoneInfo(site.timezone or "America/Bogota")
    except Exception as exc:
        raise AttendanceReportError(
            "La sede tiene una zona horaria inválida."
        ) from exc

    employees = (
        db.query(UserProfile)
        .filter(UserProfile.status == "ACTIVE")
        .all()
    )
    employees_by_name: dict[str, list[UserProfile]] = defaultdict(list)
    for employee in employees:
        normalized = _normalize_text(_employee_name(employee))
        if normalized:
            employees_by_name[normalized].append(employee)

    settings = {
        item.employee_id: item
        for item in db.query(TalentEmployeeAttendanceSetting).all()
    }

    candidate_keys = [_event_key(row) for row in rows if row.record_code in EVENT_CODE_MAP]
    existing_keys = {
        item.idempotency_key
        for item in (
            db.query(TalentAttendanceEvent)
            .filter(TalentAttendanceEvent.idempotency_key.in_(candidate_keys))
            .all()
            if candidate_keys
            else []
        )
    }

    imported = 0
    duplicate_rows = 0
    unsupported_rows = 0
    unmatched_rows = 0
    ineligible_rows = 0
    site_mismatch_rows = 0
    ambiguous_rows = 0
    seen_unmatched: dict[tuple[str, str], dict] = {}
    unsupported_codes: dict[str, int] = defaultdict(int)
    matched_employee_ids: set[str] = set()

    for row in rows:
        event_type = EVENT_CODE_MAP.get(row.record_code)
        if event_type is None:
            unsupported_rows += 1
            unsupported_codes[row.record_code or "(vacío)"] += 1
            continue

        matches = employees_by_name.get(_normalize_text(row.employee_name), [])
        if not matches:
            unmatched_rows += 1
            seen_unmatched.setdefault(
                (row.device_user_id, row.employee_name),
                {
                    "device_user_id": row.device_user_id,
                    "name": row.employee_name,
                    "department": row.department,
                    "reason": "NO_MATCH",
                },
            )
            continue
        if len(matches) > 1:
            ambiguous_rows += 1
            seen_unmatched.setdefault(
                (row.device_user_id, row.employee_name),
                {
                    "device_user_id": row.device_user_id,
                    "name": row.employee_name,
                    "department": row.department,
                    "reason": "AMBIGUOUS_NAME",
                },
            )
            continue

        employee = matches[0]
        setting = settings.get(employee.id)
        if setting is None or not setting.attendance_eligible:
            ineligible_rows += 1
            seen_unmatched.setdefault(
                (row.device_user_id, row.employee_name),
                {
                    "device_user_id": row.device_user_id,
                    "name": row.employee_name,
                    "department": row.department,
                    "reason": "ATTENDANCE_NOT_ENABLED",
                },
            )
            continue
        if setting.site_id != site.id:
            site_mismatch_rows += 1
            seen_unmatched.setdefault(
                (row.device_user_id, row.employee_name),
                {
                    "device_user_id": row.device_user_id,
                    "name": row.employee_name,
                    "department": row.department,
                    "reason": "SITE_MISMATCH",
                },
            )
            continue

        key = _event_key(row)
        if key in existing_keys:
            duplicate_rows += 1
            matched_employee_ids.add(employee.id)
            continue

        local_aware = row.occurred_local.replace(tzinfo=zone)
        event = TalentAttendanceEvent(
            employee_id=employee.id,
            site_id=site.id,
            device_id=None,
            event_type=event_type,
            method="MANUAL",
            occurred_at=local_aware.astimezone(timezone.utc),
            idempotency_key=key,
            recognition_confidence=None,
            manual_reason=_report_reason(row),
            created_by_sub=created_by_sub,
        )
        db.add(event)
        existing_keys.add(key)
        matched_employee_ids.add(employee.id)
        imported += 1

    db.commit()

    source_users = {
        (row.device_user_id, _normalize_text(row.employee_name))
        for row in rows
    }
    return {
        "filename": filename,
        "site_id": site.id,
        "site_name": site.name,
        "rows_total": len(rows),
        "source_users": len(source_users),
        "matched_employees": len(matched_employee_ids),
        "imported_events": imported,
        "duplicate_events": duplicate_rows,
        "unsupported_rows": unsupported_rows,
        "unsupported_codes": dict(sorted(unsupported_codes.items())),
        "unmatched_rows": unmatched_rows,
        "ambiguous_rows": ambiguous_rows,
        "attendance_not_enabled_rows": ineligible_rows,
        "site_mismatch_rows": site_mismatch_rows,
        "unmatched_people": list(seen_unmatched.values())[:100],
        "date_range": {
            "from": min(row.occurred_local for row in rows).isoformat(),
            "to": max(row.occurred_local for row in rows).isoformat(),
        },
    }
