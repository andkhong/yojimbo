"""AI Agent Configuration API — read/write persisted config from DB."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_config import VALID_CONFIG_KEYS, AgentConfig
from app.schemas.agent_config import AgentConfigEntry, AgentConfigResponse, AgentConfigUpdate

router = APIRouter(prefix="/api/config", tags=["agent-config"])


async def _get_all_configs(db: AsyncSession) -> list[AgentConfig]:
    result = await db.execute(select(AgentConfig).order_by(AgentConfig.key))
    return result.scalars().all()


@router.get("/agent", summary="Get all agent configuration values")
async def get_agent_config(db: AsyncSession = Depends(get_db)) -> AgentConfigResponse:
    """Return all persisted agent configuration entries as a dict + list."""
    entries = await _get_all_configs(db)
    config_dict = {e.key: e.value for e in entries}
    return AgentConfigResponse(
        config=config_dict,
        entries=[AgentConfigEntry.model_validate(e) for e in entries],
    )


@router.put("/agent", summary="Update one or more agent configuration values")
async def update_agent_config(
    data: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> AgentConfigResponse:
    """Upsert agent configuration key/value pairs into the database."""
    for key, value in data.updates.items():
        existing = (
            await db.execute(select(AgentConfig).where(AgentConfig.key == key))
        ).scalar_one_or_none()
        if existing:
            existing.value = value
            if data.updated_by:
                existing.updated_by = data.updated_by
        else:
            entry = AgentConfig(key=key, value=value, updated_by=data.updated_by)
            db.add(entry)

    await db.flush()
    entries = await _get_all_configs(db)
    config_dict = {e.key: e.value for e in entries}
    return AgentConfigResponse(
        config=config_dict,
        entries=[AgentConfigEntry.model_validate(e) for e in entries],
    )


@router.get("/agent/keys", summary="List all valid configuration key names")
async def list_config_keys():
    """Return the set of valid configuration key names."""
    return {"valid_keys": sorted(VALID_CONFIG_KEYS)}


@router.get("/agent/{key}", summary="Get a single configuration value by key")
async def get_config_key(key: str, db: AsyncSession = Depends(get_db)):
    """Return a single config entry by key."""
    if key not in VALID_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid config key: {key}")
    entry = (
        await db.execute(select(AgentConfig).where(AgentConfig.key == key))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not set")
    return {"key": key, "value": entry.value, "updated_at": entry.updated_at}


@router.delete("/agent/{key}", status_code=204, summary="Delete a configuration entry")
async def delete_config_key(key: str, db: AsyncSession = Depends(get_db)):
    """Delete a config key from the database (resets to default behaviour)."""
    entry = (
        await db.execute(select(AgentConfig).where(AgentConfig.key == key))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not set")
    await db.delete(entry)
    return None


@router.get("/languages", summary="Get language configuration")
async def get_language_config(db: AsyncSession = Depends(get_db)):
    """Return language-related configuration settings."""
    keys = ["supported_languages", "language_detection_enabled"]
    entries = (
        (await db.execute(select(AgentConfig).where(AgentConfig.key.in_(keys)))).scalars().all()
    )
    return {e.key: e.value for e in entries}


@router.put("/languages", summary="Update language configuration")
async def update_language_config(
    supported_languages: str | None = None,
    language_detection_enabled: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Update language-related configuration."""
    updates = {}
    if supported_languages is not None:
        updates["supported_languages"] = supported_languages
    if language_detection_enabled is not None:
        updates["language_detection_enabled"] = language_detection_enabled

    for key, value in updates.items():
        existing = (
            await db.execute(select(AgentConfig).where(AgentConfig.key == key))
        ).scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            db.add(AgentConfig(key=key, value=value))

    await db.flush()
    return {"updated": list(updates.keys())}


@router.get("/twilio", summary="Get Twilio configuration")
async def get_twilio_config(db: AsyncSession = Depends(get_db)):
    """Return Twilio-related configuration (phone numbers, webhooks)."""
    keys = ["transfer_phone_number"]
    entries = (
        (await db.execute(select(AgentConfig).where(AgentConfig.key.in_(keys)))).scalars().all()
    )
    return {e.key: e.value for e in entries}
