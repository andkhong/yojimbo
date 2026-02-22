"""Department management API endpoints — Full CRUD + stats + phone number assignment."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment, TimeSlot
from app.models.call import Call
from app.models.department import Department, StaffMember
from app.schemas.department import (
    BulkSlotGenerateRequest,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentStatsResponse,
    DepartmentUpdate,
    PhoneNumberAssignRequest,
    StaffMemberCreate,
    StaffMemberResponse,
    TimeSlotCreate,
    TimeSlotResponse,
    TimeSlotUpdate,
)

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.get("", summary="List all active departments")
async def list_departments(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Return all departments, optionally including inactive ones."""
    query = select(Department).order_by(Department.name)
    if not include_inactive:
        query = query.where(Department.is_active.is_(True))
    departments = (await db.execute(query)).scalars().all()
    return {"departments": [DepartmentResponse.model_validate(d) for d in departments]}


@router.get("/{department_id}", summary="Get a department by ID")
async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return a department with its staff members and time slots."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    staff = (await db.execute(
        select(StaffMember).where(
            StaffMember.department_id == department_id,
            StaffMember.is_active.is_(True),
        )
    )).scalars().all()

    time_slots = (await db.execute(
        select(TimeSlot).where(
            TimeSlot.department_id == department_id,
            TimeSlot.is_active.is_(True),
        )
    )).scalars().all()

    return {
        "department": DepartmentResponse.model_validate(dept),
        "staff": [StaffMemberResponse.model_validate(s) for s in staff],
        "time_slots": [
            {
                "id": ts.id,
                "day_of_week": ts.day_of_week,
                "start_time": ts.start_time.isoformat(),
                "end_time": ts.end_time.isoformat(),
                "slot_duration_minutes": ts.slot_duration_minutes,
            }
            for ts in time_slots
        ],
    }


@router.get("/{department_id}/stats", summary="Department call & appointment statistics")
async def get_department_stats(
    department_id: int,
    db: AsyncSession = Depends(get_db),
) -> DepartmentStatsResponse:
    """Return call counts, appointment counts, and resolution rate for a department."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    now = datetime.utcnow()

    # Call counts
    total_calls = (await db.execute(
        select(func.count()).where(Call.department_id == department_id)
    )).scalar() or 0

    active_calls = (await db.execute(
        select(func.count()).where(
            Call.department_id == department_id,
            Call.status.in_(["ringing", "in_progress"]),
        )
    )).scalar() or 0

    resolved_calls = (await db.execute(
        select(func.count()).where(
            Call.department_id == department_id,
            Call.resolution_status == "resolved",
        )
    )).scalar() or 0

    escalated_calls = (await db.execute(
        select(func.count()).where(
            Call.department_id == department_id,
            Call.resolution_status == "escalated",
        )
    )).scalar() or 0

    # Appointment counts
    total_appts = (await db.execute(
        select(func.count()).where(Appointment.department_id == department_id)
    )).scalar() or 0

    upcoming_appts = (await db.execute(
        select(func.count()).where(
            Appointment.department_id == department_id,
            Appointment.scheduled_start >= now,
            Appointment.status == "confirmed",
        )
    )).scalar() or 0

    # Resolution rate: resolved / (resolved + escalated + abandoned) * 100
    completed_calls = (await db.execute(
        select(func.count()).where(
            Call.department_id == department_id,
            Call.status == "completed",
        )
    )).scalar() or 0

    resolution_rate = 0.0
    if completed_calls > 0:
        resolution_rate = round((resolved_calls / completed_calls) * 100, 1)

    return DepartmentStatsResponse(
        department_id=department_id,
        department_name=dept.name,
        total_calls=total_calls,
        active_calls=active_calls,
        total_appointments=total_appts,
        upcoming_appointments=upcoming_appts,
        resolved_calls=resolved_calls,
        escalated_calls=escalated_calls,
        resolution_rate=resolution_rate,
    )


@router.post("", status_code=201, summary="Create a new department")
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new department. Code and name must be unique."""
    # Check uniqueness
    existing = (await db.execute(
        select(Department).where(
            (Department.code == data.code) | (Department.name == data.name)
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Department with that code or name already exists")

    dept = Department(**data.model_dump())
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return {"department": DepartmentResponse.model_validate(dept)}


@router.put("/{department_id}", summary="Full update of a department")
async def replace_department(
    department_id: int,
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Replace all fields of a department."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    for field, value in data.model_dump().items():
        setattr(dept, field, value)

    return {"department": DepartmentResponse.model_validate(dept)}


@router.patch("/{department_id}", summary="Partial update of a department")
async def update_department(
    department_id: int,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update one or more fields of a department."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(dept, field, value)

    return {"department": DepartmentResponse.model_validate(dept)}


@router.delete("/{department_id}", status_code=204, summary="Soft-delete a department")
async def delete_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a department by marking it inactive."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    dept.is_active = False
    return None


@router.post("/{department_id}/phone-number", summary="Assign a Twilio phone number to a department")
async def assign_phone_number(
    department_id: int,
    data: PhoneNumberAssignRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign a Twilio phone number to a department for call routing."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check if phone number is already assigned to another department
    existing = (await db.execute(
        select(Department).where(
            Department.twilio_phone_number == data.phone_number,
            Department.id != department_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Phone number already assigned to department: {existing.name}",
        )

    dept.twilio_phone_number = data.phone_number
    return {"department": DepartmentResponse.model_validate(dept)}


@router.post("/{department_id}/staff", status_code=201, summary="Add staff member to department")
async def add_staff_member(
    department_id: int,
    data: StaffMemberCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a staff member to a department."""
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    staff = StaffMember(department_id=department_id, **{k: v for k, v in data.model_dump().items() if k != "department_id"})
    db.add(staff)
    await db.flush()
    await db.refresh(staff)
    return {"staff_member": StaffMemberResponse.model_validate(staff)}


# ---------------------------------------------------------------------------
# Item 12: Department Time Slot Management
# ---------------------------------------------------------------------------


async def _get_dept_or_404(department_id: int, db: AsyncSession) -> Department:
    dept = (await db.execute(
        select(Department).where(Department.id == department_id)
    )).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept


@router.get("/{department_id}/slots", summary="List time slots for a department")
async def list_time_slots(
    department_id: int,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Return all time slots for a department."""
    await _get_dept_or_404(department_id, db)
    query = select(TimeSlot).where(TimeSlot.department_id == department_id).order_by(
        TimeSlot.day_of_week, TimeSlot.start_time
    )
    if not include_inactive:
        query = query.where(TimeSlot.is_active.is_(True))
    slots = (await db.execute(query)).scalars().all()
    return {"slots": [TimeSlotResponse.model_validate(s) for s in slots]}


@router.post("/{department_id}/slots", status_code=201, summary="Add a time slot to a department")
async def create_time_slot(
    department_id: int,
    data: TimeSlotCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new time slot for a department."""
    await _get_dept_or_404(department_id, db)
    slot = TimeSlot(department_id=department_id, **data.model_dump())
    db.add(slot)
    await db.flush()
    await db.refresh(slot)
    return {"slot": TimeSlotResponse.model_validate(slot)}


@router.put("/{department_id}/slots/{slot_id}", summary="Update a time slot")
async def update_time_slot(
    department_id: int,
    slot_id: int,
    data: TimeSlotUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update one or more fields on a time slot."""
    await _get_dept_or_404(department_id, db)
    slot = (await db.execute(
        select(TimeSlot).where(
            TimeSlot.id == slot_id,
            TimeSlot.department_id == department_id,
        )
    )).scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(slot, field, value)

    return {"slot": TimeSlotResponse.model_validate(slot)}


@router.delete("/{department_id}/slots/{slot_id}", status_code=204, summary="Delete a time slot")
async def delete_time_slot(
    department_id: int,
    slot_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a time slot by marking it inactive."""
    await _get_dept_or_404(department_id, db)
    slot = (await db.execute(
        select(TimeSlot).where(
            TimeSlot.id == slot_id,
            TimeSlot.department_id == department_id,
        )
    )).scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    slot.is_active = False
    return None


@router.post("/{department_id}/slots/bulk", status_code=201, summary="Bulk-generate time slots")
async def bulk_generate_slots(
    department_id: int,
    data: BulkSlotGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bulk-generate time slots for a department.

    Example: create 30-min slots from 9am-5pm Mon-Fri.
    If replace_existing=True, any existing active slots for those days are deactivated first.
    """

    await _get_dept_or_404(department_id, db)

    created = []
    for day in data.days_of_week:
        if day < 0 or day > 6:
            raise HTTPException(status_code=422, detail=f"Invalid day_of_week: {day}. Must be 0-6.")

        if data.replace_existing:
            # Deactivate existing slots for this day
            existing = (await db.execute(
                select(TimeSlot).where(
                    TimeSlot.department_id == department_id,
                    TimeSlot.day_of_week == day,
                    TimeSlot.is_active.is_(True),
                )
            )).scalars().all()
            for s in existing:
                s.is_active = False

        # Generate slots
        from datetime import datetime as _dt

        base = _dt.combine(_dt.today(), data.start_time)
        end_bound = _dt.combine(_dt.today(), data.end_time)
        current = base
        while current < end_bound:
            slot_end = current + __import__("datetime").timedelta(minutes=data.slot_duration_minutes)
            if slot_end > end_bound:
                break
            slot = TimeSlot(
                department_id=department_id,
                day_of_week=day,
                start_time=current.time(),
                end_time=slot_end.time(),
                slot_duration_minutes=data.slot_duration_minutes,
                max_concurrent=data.max_concurrent,
            )
            db.add(slot)
            created.append({"day": day, "start": current.strftime("%H:%M"), "end": slot_end.strftime("%H:%M")})
            current = slot_end

    await db.flush()
    return {
        "created": len(created),
        "slots": created,
    }


@router.get("/{department_id}/slots/availability", summary="Check slot availability for a date")
async def check_slot_availability(
    department_id: int,
    date: str,
    db: AsyncSession = Depends(get_db),
):
    """Return available appointment slots for a specific date (YYYY-MM-DD format)."""
    import datetime as _datetime

    await _get_dept_or_404(department_id, db)

    try:
        target_date = _datetime.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    day_of_week = target_date.weekday()  # 0=Monday

    slots = (await db.execute(
        select(TimeSlot).where(
            TimeSlot.department_id == department_id,
            TimeSlot.day_of_week == day_of_week,
            TimeSlot.is_active.is_(True),
        ).order_by(TimeSlot.start_time)
    )).scalars().all()

    # Count existing confirmed appointments for each slot
    from app.models.appointment import Appointment

    availability = []
    for slot in slots:
        slot_start = _datetime.datetime.combine(target_date, slot.start_time)
        slot_end = _datetime.datetime.combine(target_date, slot.end_time)

        booked = (await db.execute(
            select(func.count()).where(
                Appointment.department_id == department_id,
                Appointment.scheduled_start >= slot_start,
                Appointment.scheduled_start < slot_end,
                Appointment.status == "confirmed",
            )
        )).scalar() or 0

        available_slots = max(0, slot.max_concurrent - booked)
        availability.append({
            "slot_id": slot.id,
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "max_concurrent": slot.max_concurrent,
            "booked": booked,
            "available": available_slots,
            "is_available": available_slots > 0,
        })

    return {
        "department_id": department_id,
        "date": date,
        "day_of_week": day_of_week,
        "slots": availability,
    }
