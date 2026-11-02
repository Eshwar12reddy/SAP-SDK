from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import MemoryEntry, MemoryPreference, User, get_session
from ..schemas.memory import MemoryPreferenceUpdate, MemoryUpdate
from .deps import current_user

router = APIRouter()


def _serialize(entry: MemoryEntry) -> dict:
    return {
        "id": entry.id,
        "memory_text": entry.memory_text,
        "memory_type": entry.memory_type,
        "source_conversation_id": entry.source_conversation_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "last_used_at": entry.last_used_at.isoformat() if entry.last_used_at else None,
    }


@router.get("/memory/settings")
async def memory_settings(user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    preference = await db.scalar(select(MemoryPreference).where(MemoryPreference.user_id == user.id))
    return {"enabled": True if preference is None else bool(preference.enabled)}


@router.put("/memory/settings")
async def update_memory_settings(body: MemoryPreferenceUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    preference = await db.scalar(select(MemoryPreference).where(MemoryPreference.user_id == user.id))
    if preference is None:
        preference = MemoryPreference(user_id=user.id, enabled=body.enabled)
        db.add(preference)
    else:
        preference.enabled = body.enabled
    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500, "Memory settings could not be saved.") from error
    return {"enabled": preference.enabled}


@router.get("/memory")
async def list_memory(user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    entries = (await db.scalars(select(MemoryEntry).where(MemoryEntry.user_id == user.id, MemoryEntry.status == "active").order_by(MemoryEntry.updated_at.desc(), MemoryEntry.id.desc()))).all()
    return [_serialize(entry) for entry in entries]


@router.patch("/memory/{memory_id}")
async def update_memory(memory_id: int, body: MemoryUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    entry = await db.scalar(select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user.id, MemoryEntry.status == "active"))
    if entry is None:
        raise HTTPException(404, "Memory entry not found")
    entry.memory_text = body.memory_text.strip()
    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500, "Memory entry could not be updated.") from error
    await db.refresh(entry)  # updated_at is a server-side onupdate value and is expired after commit
    return _serialize(entry)


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    entry = await db.scalar(select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user.id))
    if entry is None:
        raise HTTPException(404, "Memory entry not found")
    await db.delete(entry)
    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500, "Memory entry could not be deleted.") from error
    return {"deleted": True}


@router.delete("/memory")
async def clear_memory(user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    await db.execute(delete(MemoryEntry).where(MemoryEntry.user_id == user.id))
    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500, "Memory could not be cleared.") from error
    return {"deleted": True}
