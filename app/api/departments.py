"""Department management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import TimeSlot
from app.models.department import Department, StaffMember
from app.schemas.department import DepartmentCreate, DepartmentResponse, StaffMemberResponse

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.get("")
async def list_departments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
    )
    departments = result.scalars().all()
    return {"departments": [DepartmentResponse.model_validate(d) for d in departments]}


@router.get("/{department_id}")
async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department).where(Department.id == department_id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    staff_result = await db.execute(
        select(StaffMember).where(
            StaffMember.department_id == department_id,
            StaffMember.is_active.is_(True),
        )
    )
    staff = staff_result.scalars().all()

    slots_result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.department_id == department_id,
            TimeSlot.is_active.is_(True),
        )
    )
    time_slots = slots_result.scalars().all()

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


@router.post("", status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
):
    dept = Department(**data.model_dump())
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return {"department": DepartmentResponse.model_validate(dept)}


@router.patch("/{department_id}")
async def update_department(
    department_id: int,
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department).where(Department.id == department_id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(dept, field, value)

    return {"department": DepartmentResponse.model_validate(dept)}
