"""Staff Management API — full CRUD on DashboardUser with role-based access."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.database import get_db
from app.models.user import DashboardUser
from app.schemas.user import VALID_ROLES, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])

# Role hierarchy: higher index = more privileged
ROLE_ORDER = ["readonly", "operator", "supervisor", "admin"]


def _role_level(role: str) -> int:
    """Return numeric privilege level for a role."""
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return -1


@router.get("", summary="List all staff users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    role: str | None = None,
    department_id: int | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Return paginated staff list with optional filters."""
    query = select(DashboardUser).order_by(DashboardUser.name)

    if role is not None:
        query = query.where(DashboardUser.role == role)
    if department_id is not None:
        query = query.where(DashboardUser.department_id == department_id)
    if is_active is not None:
        query = query.where(DashboardUser.is_active.is_(is_active))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    users = (await db.execute(query.offset((page - 1) * per_page).limit(per_page))).scalars().all()

    return {
        "users": [UserResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("", status_code=201, summary="Create a new staff user")
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new staff/admin user. Username must be unique."""
    if data.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{data.role}'. Must be one of: {sorted(VALID_ROLES)}",
        )

    existing = (
        await db.execute(select(DashboardUser).where(DashboardUser.username == data.username))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    user = DashboardUser(
        username=data.username,
        password_hash=hash_password(data.password),
        name=data.name,
        role=data.role,
        department_id=data.department_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return {"user": UserResponse.model_validate(user)}


@router.get("/{user_id}", summary="Get a staff user by ID")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Return a staff user by their ID."""
    user = (
        await db.execute(select(DashboardUser).where(DashboardUser.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": UserResponse.model_validate(user)}


@router.patch("/{user_id}", summary="Partial update of a staff user")
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update one or more fields on a staff user."""
    user = (
        await db.execute(select(DashboardUser).where(DashboardUser.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)

    if "role" in update_data and update_data["role"] not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{update_data['role']}'. Must be one of: {sorted(VALID_ROLES)}",
        )

    # Hash password if being updated
    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    return {"user": UserResponse.model_validate(user)}


@router.delete("/{user_id}", status_code=204, summary="Deactivate a staff user")
async def deactivate_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Soft-delete (deactivate) a staff user. Cannot deactivate the last admin."""
    user = (
        await db.execute(select(DashboardUser).where(DashboardUser.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Guard: don't deactivate last admin
    if user.role == "admin" and user.is_active:
        admin_count = (
            await db.execute(
                select(func.count()).where(
                    DashboardUser.role == "admin",
                    DashboardUser.is_active.is_(True),
                )
            )
        ).scalar() or 0
        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="Cannot deactivate the last active admin user",
            )

    user.is_active = False
    return None


@router.post("/{user_id}/activate", summary="Re-activate a deactivated staff user")
async def activate_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Re-activate a previously deactivated staff user."""
    user = (
        await db.execute(select(DashboardUser).where(DashboardUser.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    return {"user": UserResponse.model_validate(user)}


@router.get("/by-role/{role}", summary="List users by role")
async def list_users_by_role(role: str, db: AsyncSession = Depends(get_db)):
    """Return all active users with a specific role."""
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}",
        )
    users = (
        (
            await db.execute(
                select(DashboardUser)
                .where(DashboardUser.role == role, DashboardUser.is_active.is_(True))
                .order_by(DashboardUser.name)
            )
        )
        .scalars()
        .all()
    )
    return {"users": [UserResponse.model_validate(u) for u in users], "role": role}
