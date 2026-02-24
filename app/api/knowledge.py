"""Knowledge Base API — FAQ/knowledge entries for AI agent context injection."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.knowledge import KnowledgeEntry
from app.schemas.knowledge import KnowledgeCreate, KnowledgeResponse, KnowledgeUpdate

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _localized_error(message_key: str, message: str, **params: object) -> dict[str, object]:
    """Return i18n-ready API error payload with stable translation key and params."""
    return {
        "message_key": message_key,
        "message": message,
        "params": params,
    }


@router.get("", summary="List knowledge base entries")
async def list_knowledge(
    db: AsyncSession = Depends(get_db),
    department_id: int | None = None,
    language: str | None = None,
    category: str | None = None,
    is_active: bool | None = True,
    search: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Return paginated knowledge base entries with optional filters."""
    query = select(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc())

    if department_id is not None:
        # Include global (null department) + department-specific
        query = query.where(
            (KnowledgeEntry.department_id == department_id)
            | (KnowledgeEntry.department_id.is_(None))
        )
    if language:
        query = query.where(KnowledgeEntry.language == language)
    if category:
        query = query.where(KnowledgeEntry.category == category)
    if is_active is not None:
        query = query.where(KnowledgeEntry.is_active.is_(is_active))
    if search:
        query = query.where(
            KnowledgeEntry.question.ilike(f"%{search}%")
            | KnowledgeEntry.answer.ilike(f"%{search}%")
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    entries = (
        (await db.execute(query.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    )

    return {
        "entries": [KnowledgeResponse.model_validate(e) for e in entries],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("", status_code=201, summary="Create a new knowledge base entry")
async def create_knowledge(
    data: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new FAQ/knowledge entry to the knowledge base."""
    entry = KnowledgeEntry(**data.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return {"entry": KnowledgeResponse.model_validate(entry)}


@router.get("/categories", summary="List distinct knowledge categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Return a list of unique categories in the knowledge base."""
    rows = (
        (
            await db.execute(
                select(KnowledgeEntry.category)
                .where(KnowledgeEntry.category.isnot(None))
                .distinct()
                .order_by(KnowledgeEntry.category)
            )
        )
        .scalars()
        .all()
    )
    return {"categories": rows}


@router.get("/context", summary="Get knowledge context for AI agent")
async def get_agent_context(
    db: AsyncSession = Depends(get_db),
    department_id: int | None = None,
    language: str = Query("en"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return formatted knowledge entries for injection into AI agent context.

    Returns active entries for the given department + language, formatted
    for use in the AI system prompt.
    """
    query = select(KnowledgeEntry).where(
        KnowledgeEntry.is_active.is_(True),
        KnowledgeEntry.language == language,
    )
    if department_id:
        query = query.where(
            (KnowledgeEntry.department_id == department_id)
            | (KnowledgeEntry.department_id.is_(None))
        )

    query = query.limit(limit)
    entries = (await db.execute(query)).scalars().all()

    # Format for AI injection
    formatted = "\n\n".join(f"Q: {e.question}\nA: {e.answer}" for e in entries)

    return {
        "department_id": department_id,
        "language": language,
        "entry_count": len(entries),
        "context": formatted,
        "entries": [KnowledgeResponse.model_validate(e) for e in entries],
    }


@router.get("/{entry_id}", summary="Get a knowledge entry by ID")
async def get_knowledge(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Return a single knowledge base entry by ID."""
    entry = (
        await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=_localized_error(
                "knowledge.not_found",
                "Knowledge entry not found",
                entry_id=entry_id,
            ),
        )
    return {"entry": KnowledgeResponse.model_validate(entry)}


@router.patch("/{entry_id}", summary="Update a knowledge entry")
async def update_knowledge(
    entry_id: int,
    data: KnowledgeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update one or more fields on a knowledge base entry."""
    entry = (
        await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=_localized_error(
                "knowledge.not_found",
                "Knowledge entry not found",
                entry_id=entry_id,
            ),
        )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)

    return {"entry": KnowledgeResponse.model_validate(entry)}


@router.delete("/{entry_id}", status_code=204, summary="Soft-delete a knowledge entry")
async def delete_knowledge(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate a knowledge base entry (soft delete)."""
    entry = (
        await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=_localized_error(
                "knowledge.not_found",
                "Knowledge entry not found",
                entry_id=entry_id,
            ),
        )
    entry.is_active = False
    return None


@router.post("/{entry_id}/restore", summary="Restore a deactivated knowledge entry")
async def restore_knowledge(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Reactivate a previously deactivated knowledge base entry."""
    entry = (
        await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=_localized_error(
                "knowledge.not_found",
                "Knowledge entry not found",
                entry_id=entry_id,
            ),
        )
    entry.is_active = True
    return {"entry": KnowledgeResponse.model_validate(entry)}
