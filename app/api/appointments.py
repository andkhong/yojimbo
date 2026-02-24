"""Appointment management API endpoints."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    AvailabilityResponse,
    AvailabilitySlot,
)
from app.services import appointment_engine, notification
from app.services.appointment_engine import BookingConflictError, OutsideOperatingHoursError

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def _i18n_error(message_key: str, message: str, **params):
    """Build i18n-ready API error payload with English fallback message."""
    return {"message_key": message_key, "message": message, "params": params}


def _import_row_error(row: int, message_key: str, message: str, **params):
    """Build i18n-ready row error payload for bulk import responses."""
    return {
        "row": row,
        "message_key": message_key,
        "message": message,
        "params": params,
    }


@router.get("")
async def list_appointments(
    db: AsyncSession = Depends(get_db),
    department_id: int | None = None,
    target_date: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(Appointment).order_by(Appointment.scheduled_start)

    if department_id:
        query = query.where(Appointment.department_id == department_id)
    if status:
        query = query.where(Appointment.status == status)
    if target_date:
        try:
            d = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=_i18n_error(
                    "appointments.invalid_date",
                    "Invalid target_date format. Expected YYYY-MM-DD",
                    field="target_date",
                    value=target_date,
                ),
            )
        query = query.where(
            Appointment.scheduled_start >= datetime.combine(d, datetime.min.time()),
            Appointment.scheduled_start < datetime.combine(d, datetime.max.time()),
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    appointments = result.scalars().all()

    return {
        "appointments": [AppointmentResponse.model_validate(a) for a in appointments],
        "total": total,
        "page": page,
    }


@router.post("", status_code=201)
async def create_appointment(
    data: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        appt = await appointment_engine.book_appointment(
            db,
            contact_id=data.contact_id,
            department_id=data.department_id,
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end,
            title=data.title,
            description=data.description,
            language=data.language,
            enforce_operating_hours=True,
        )
    except OutsideOperatingHoursError as exc:
        raise HTTPException(
            status_code=422,
            detail=_i18n_error(
                getattr(exc, "message_key", "appointments.outside_operating_hours"),
                str(exc),
                **getattr(exc, "params", {}),
            ),
        )
    except BookingConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=_i18n_error(
                "appointments.booking_conflict",
                str(exc),
            ),
        )

    await notification.notify_appointment_created(
        {
            "appointment_id": appt.id,
            "department_id": appt.department_id,
            "scheduled_start": appt.scheduled_start.isoformat(),
        }
    )

    return {"appointment": AppointmentResponse.model_validate(appt)}


@router.get("/availability")
async def check_availability(
    department_id: int,
    target_date: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=_i18n_error(
                "appointments.invalid_date",
                "Invalid target_date format. Expected YYYY-MM-DD",
                field="target_date",
                value=target_date,
            ),
        )

    slots = await appointment_engine.get_available_slots(db, department_id, d)

    return AvailabilityResponse(
        department_id=department_id,
        date=target_date,
        slots=[AvailabilitySlot(**s) for s in slots],
    )


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(
            status_code=404,
            detail=_i18n_error(
                "appointments.not_found",
                "Appointment not found",
                appointment_id=appointment_id,
            ),
        )
    return {"appointment": AppointmentResponse.model_validate(appt)}


@router.patch("/{appointment_id}")
async def update_appointment(
    appointment_id: int,
    data: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(
            status_code=404,
            detail=_i18n_error(
                "appointments.not_found",
                "Appointment not found",
                appointment_id=appointment_id,
            ),
        )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(appt, field, value)

    await notification.notify_appointment_updated(
        {
            "appointment_id": appt.id,
            "status": appt.status,
        }
    )

    return {"appointment": AppointmentResponse.model_validate(appt)}


@router.delete("/{appointment_id}")
async def cancel_appointment_endpoint(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
):
    appt = await appointment_engine.cancel_appointment(db, appointment_id)
    if not appt:
        raise HTTPException(
            status_code=404,
            detail=_i18n_error(
                "appointments.not_found",
                "Appointment not found",
                appointment_id=appointment_id,
            ),
        )

    await notification.notify_appointment_updated(
        {
            "appointment_id": appt.id,
            "status": "cancelled",
        }
    )

    return {"appointment": AppointmentResponse.model_validate(appt)}


# ---------------------------------------------------------------------------
# Item 6: Bulk appointment import
# ---------------------------------------------------------------------------


class BulkAppointmentRow(BaseModel):
    contact_phone: str
    department_code: str
    title: str
    scheduled_start: str  # ISO datetime string
    scheduled_end: str | None = None
    description: str | None = None
    language: str = "en"


class BulkImportRequest(BaseModel):
    appointments: list[BulkAppointmentRow]
    skip_duplicates: bool = True
    dry_run: bool = False


@router.post("/import", status_code=201, summary="Bulk-import appointments from CSV-style JSON")
async def bulk_import_appointments(
    data: BulkImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import multiple appointments in a single request.

    Each row references contact by phone number and department by code.
    If skip_duplicates=True, rows where a confirmed appointment for the same
    contact+department+time already exists are skipped rather than failing.
    Set dry_run=True to validate without committing.
    """
    from datetime import timedelta

    from app.models.contact import Contact
    from app.models.department import Department

    # Preload contacts and departments for efficiency
    phones = list({r.contact_phone for r in data.appointments})
    dept_codes = list({r.department_code.upper() for r in data.appointments})

    contact_map = {
        c.phone_number: c
        for c in (await db.execute(
            select(Contact).where(Contact.phone_number.in_(phones))
        )).scalars().all()
    }
    dept_map = {
        d.code.upper(): d
        for d in (await db.execute(
            select(Department).where(func.upper(Department.code).in_(dept_codes))
        )).scalars().all()
    }

    created = []
    skipped = []
    errors = []

    for i, row in enumerate(data.appointments):
        contact = contact_map.get(row.contact_phone)
        dept = dept_map.get(row.department_code.upper())

        if not contact:
            errors.append(
                _import_row_error(
                    i,
                    "appointments.import.contact_not_found",
                    f"Contact not found: {row.contact_phone}",
                    contact_phone=row.contact_phone,
                )
            )
            continue
        if not dept:
            errors.append(
                _import_row_error(
                    i,
                    "appointments.import.department_not_found",
                    f"Department not found: {row.department_code}",
                    department_code=row.department_code,
                )
            )
            continue

        try:
            start = datetime.fromisoformat(row.scheduled_start)
        except ValueError:
            errors.append(
                _import_row_error(
                    i,
                    "appointments.import.invalid_datetime",
                    f"Invalid scheduled_start: {row.scheduled_start}",
                    field="scheduled_start",
                    value=row.scheduled_start,
                )
            )
            continue

        if row.scheduled_end:
            try:
                end = datetime.fromisoformat(row.scheduled_end)
            except ValueError:
                errors.append(
                    _import_row_error(
                        i,
                        "appointments.import.invalid_datetime",
                        f"Invalid scheduled_end: {row.scheduled_end}",
                        field="scheduled_end",
                        value=row.scheduled_end,
                    )
                )
                continue
        else:
            end = start + timedelta(hours=1)

        if end <= start:
            errors.append(
                _import_row_error(
                    i,
                    "appointments.import.invalid_time_window",
                    "scheduled_end must be after scheduled_start",
                    field="scheduled_end",
                    scheduled_start=row.scheduled_start,
                    scheduled_end=row.scheduled_end,
                )
            )
            continue

        if appointment_engine._uses_structured_operating_hours(dept.operating_hours):
            try:
                appointment_engine.check_operating_hours(dept.operating_hours, start, end)
            except OutsideOperatingHoursError as exc:
                errors.append(
                    _import_row_error(
                        i,
                        getattr(exc, "message_key", "appointments.outside_operating_hours"),
                        str(exc),
                        **getattr(exc, "params", {}),
                    )
                )
                continue

        if data.skip_duplicates:
            existing = (await db.execute(
                select(Appointment).where(
                    Appointment.contact_id == contact.id,
                    Appointment.department_id == dept.id,
                    Appointment.scheduled_start == start,
                    Appointment.status == "confirmed",
                )
            )).scalar_one_or_none()
            if existing:
                skipped.append({"row": i, "existing_id": existing.id})
                continue

        if not data.dry_run:
            appt = Appointment(
                contact_id=contact.id,
                department_id=dept.id,
                title=row.title,
                description=row.description,
                scheduled_start=start,
                scheduled_end=end,
                language=row.language,
                status="confirmed",
            )
            db.add(appt)
            await db.flush()
            created.append({"row": i, "appointment_id": appt.id})
        else:
            created.append({"row": i, "appointment_id": None, "dry_run": True})

    return {
        "dry_run": data.dry_run,
        "total_rows": len(data.appointments),
        "created": len(created),
        "skipped": len(skipped),
        "errors": len(errors),
        "results": created,
        "skipped_rows": skipped,
        "error_rows": errors,
    }
