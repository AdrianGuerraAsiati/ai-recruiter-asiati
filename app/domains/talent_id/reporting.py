"""Attendance reporting for Talent ID."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.domains.talent_id.models import (
    TalentAttendanceEvent,
    TalentEmployeeAttendanceSetting,
    TalentSite,
    TalentWorkSchedule,
)
from app.models import UserProfile


MAX_REPORT_DAYS = 93


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _employee_name(employee: UserProfile | None) -> str:
    if employee is None:
        return "Empleado"
    name = " ".join(
        part.strip()
        for part in [employee.first_name or "", employee.last_name or ""]
        if part and part.strip()
    )
    return name or employee.email or "Empleado"


def _minutes_since_midnight(value: datetime) -> int:
    return value.hour * 60 + value.minute


def build_attendance_report(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    employee_id: str | None = None,
) -> dict:
    if end_date < start_date:
        raise ValueError("La fecha final debe ser igual o posterior a la inicial.")
    span_days = (end_date - start_date).days + 1
    if span_days > MAX_REPORT_DAYS:
        raise ValueError(
            f"El reporte admite máximo {MAX_REPORT_DAYS} días por consulta."
        )

    # Pull a small UTC buffer and then filter in each site's local timezone.
    start_bound = datetime.combine(
        start_date - timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    end_bound = datetime.combine(
        end_date + timedelta(days=2),
        time.min,
        tzinfo=timezone.utc,
    )

    query = db.query(TalentAttendanceEvent).filter(
        TalentAttendanceEvent.occurred_at >= start_bound,
        TalentAttendanceEvent.occurred_at < end_bound,
    )
    if employee_id:
        query = query.filter(TalentAttendanceEvent.employee_id == employee_id)

    events = query.order_by(TalentAttendanceEvent.occurred_at.asc()).all()

    employee_ids = {event.employee_id for event in events}
    site_ids = {event.site_id for event in events}

    employees = {
        row.id: row
        for row in (
            db.query(UserProfile)
            .filter(UserProfile.id.in_(employee_ids))
            .all()
            if employee_ids
            else []
        )
    }
    sites = {
        row.id: row
        for row in (
            db.query(TalentSite)
            .filter(TalentSite.id.in_(site_ids))
            .all()
            if site_ids
            else []
        )
    }
    settings = {
        row.employee_id: row
        for row in (
            db.query(TalentEmployeeAttendanceSetting)
            .filter(TalentEmployeeAttendanceSetting.employee_id.in_(employee_ids))
            .all()
            if employee_ids
            else []
        )
    }
    schedule_ids = {
        setting.schedule_id
        for setting in settings.values()
        if setting.schedule_id
    }
    schedules = {
        row.id: row
        for row in (
            db.query(TalentWorkSchedule)
            .filter(TalentWorkSchedule.id.in_(schedule_ids))
            .all()
            if schedule_ids
            else []
        )
    }

    grouped: dict[tuple[str, date], list[tuple[TalentAttendanceEvent, datetime]]] = defaultdict(list)
    filtered_events = []

    for event in events:
        site = sites.get(event.site_id)
        try:
            zone = ZoneInfo((site.timezone if site else None) or "America/Bogota")
        except Exception:
            zone = ZoneInfo("America/Bogota")

        local_time = _aware_utc(event.occurred_at).astimezone(zone)
        if not (start_date <= local_time.date() <= end_date):
            continue

        grouped[(event.employee_id, local_time.date())].append((event, local_time))
        filtered_events.append((event, local_time))

    rows = []
    for (row_employee_id, local_date), day_events in grouped.items():
        employee = employees.get(row_employee_id)
        setting = settings.get(row_employee_id)
        schedule = schedules.get(setting.schedule_id) if setting else None
        site = sites.get(day_events[0][0].site_id)

        check_ins = [
            local_time
            for event, local_time in day_events
            if event.event_type == "CHECK_IN"
        ]
        check_outs = [
            local_time
            for event, local_time in day_events
            if event.event_type == "CHECK_OUT"
        ]

        first_in = min(check_ins) if check_ins else None
        last_out = max(check_outs) if check_outs else None

        late_minutes = 0
        if first_in and schedule:
            threshold_minutes = (
                schedule.start_time.hour * 60
                + schedule.start_time.minute
                + int(schedule.tolerance_minutes or 0)
            )
            late_minutes = max(
                0,
                _minutes_since_midnight(first_in) - threshold_minutes,
            )

        worked_minutes = None
        if first_in and last_out and last_out >= first_in:
            worked_minutes = int((last_out - first_in).total_seconds() // 60)

        status = "OK"
        if not first_in or not last_out:
            status = "INCOMPLETE"
        elif late_minutes > 0:
            status = "LATE"

        confidences = [
            float(event.recognition_confidence)
            for event, _local_time in day_events
            if event.recognition_confidence is not None
        ]

        rows.append(
            {
                "employee_id": row_employee_id,
                "employee_name": _employee_name(employee),
                "employee_email": employee.email if employee else None,
                "date": local_date.isoformat(),
                "site_id": site.id if site else None,
                "site_name": site.name if site else "Sede",
                "schedule_name": schedule.name if schedule else None,
                "scheduled_start": (
                    schedule.start_time.isoformat() if schedule else None
                ),
                "scheduled_end": (
                    schedule.end_time.isoformat() if schedule else None
                ),
                "check_in": first_in.isoformat() if first_in else None,
                "check_out": last_out.isoformat() if last_out else None,
                "late_minutes": late_minutes,
                "worked_minutes": worked_minutes,
                "status": status,
                "event_count": len(day_events),
                "recognition_confidence": (
                    round(sum(confidences) / len(confidences), 2)
                    if confidences
                    else None
                ),
            }
        )

    rows.sort(key=lambda row: (row["date"], row["employee_name"]), reverse=True)

    check_in_count = sum(
        1 for event, _local_time in filtered_events if event.event_type == "CHECK_IN"
    )
    check_out_count = sum(
        1 for event, _local_time in filtered_events if event.event_type == "CHECK_OUT"
    )
    arrivals = [row for row in rows if row["check_in"]]
    late_days = sum(1 for row in arrivals if row["late_minutes"] > 0)
    completed_workdays = [
        row["worked_minutes"] for row in rows if row["worked_minutes"] is not None
    ]

    return {
        "range": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": span_days,
        },
        "summary": {
            "employees_with_activity": len({row["employee_id"] for row in rows}),
            "days_with_activity": len(rows),
            "check_ins": check_in_count,
            "check_outs": check_out_count,
            "late_arrivals": late_days,
            "incomplete_days": sum(1 for row in rows if row["status"] == "INCOMPLETE"),
            "on_time_rate": (
                round(((len(arrivals) - late_days) / len(arrivals)) * 100, 1)
                if arrivals
                else 0.0
            ),
            "average_worked_minutes": (
                round(sum(completed_workdays) / len(completed_workdays))
                if completed_workdays
                else None
            ),
        },
        "rows": rows,
        "total": len(rows),
    }
