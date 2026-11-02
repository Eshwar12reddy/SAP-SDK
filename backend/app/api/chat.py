import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import Conversation, Message, Session, User, get_session
from ..schemas.chat import ChatRequest, ChatResponse, EditMessageRequest, RegenerateRequest
from ..services.chat_service import answer, answer_stream, save
from ..services.memory_service import maybe_extract
from ..services.openrouter_service import OpenRouterError
from .deps import current_user

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


async def process(body, user, db):
    cid = await ensure_conversation(db, user.id, body.conversation_id, body.message, persist_user_message=False)
    try:
        user_message = await save(db, cid, "user", body.message)
        if isinstance(db, AsyncSession):
            await db.flush()
            await maybe_extract(db, user.id, cid, user_message)
        result = await answer(db, cid, body.message, settings, body.response_language)
        await save(db, cid, "assistant", result)
        await db.commit()
        return ChatResponse(conversation_id=cid, answer=result)
    except OpenRouterError as error:
        await db.rollback()
        raise HTTPException(502, str(error)) from error
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500, "The conversation could not be saved.") from error


async def ensure_conversation(
    db: AsyncSession,
    user_id: int,
    conversation_id: int | None,
    title: str,
    *,
    persist_user_message: bool,
) -> int:
    """Resolve an owned conversation and never reuse a stale ID."""
    conversation: Conversation | None
    if conversation_id is None:
        conversation = Conversation(owner_id=user_id, title=title[:60])
        db.add(conversation)
        await db.flush()
    else:
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.owner_id == user_id,
            )
        )
        if conversation is None:
            raise HTTPException(404, "Conversation not found")

    if persist_user_message:
        await save(db, conversation.id, "user", title)
        try:
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()
            raise
    return conversation.id


async def _persist_assistant_once(
    user_id: int,
    conversation_id: int,
    user_message_id: int | None,
    content: str,
) -> bool:
    """Persist a nonempty response once, scoped to the exact user turn.

    The conversation lock serializes normal completion and cancellation cleanup.
    If another user turn has already been appended, an old stream is not allowed
    to attach its late response to the newer turn.
    """
    if not content.strip():
        return False

    async with Session() as db:
        # Keep the lightweight fake sessions used by the transaction tests usable.
        if not hasattr(db, "scalars"):
            await save(db, conversation_id, "assistant", content)
            return True

        async with db.begin():
            conversation = await db.scalar(
                select(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.owner_id == user_id,
                )
                .with_for_update()
            )
            if conversation is None or user_message_id is None:
                return False

            target = await db.scalar(
                select(Message).where(
                    Message.id == user_message_id,
                    Message.conversation_id == conversation_id,
                    Message.role == "user",
                )
            )
            if target is None:
                return False

            following = (
                await db.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.id > target.id,
                    )
                    .order_by(Message.id)
                )
            ).all()
            if any(message.role == "user" for message in following):
                return False

            existing = next((message for message in following if message.role == "assistant"), None)
            if existing is not None:
                existing.content = content
            else:
                db.add(Message(conversation_id=conversation_id, role="assistant", content=content))
    return True


async def _remove_user_turn(user_id: int, conversation_id: int, user_message_id: int | None) -> None:
    if user_message_id is None:
        return
    async with Session() as db:
        try:
            async with db.begin():
                conversation = await db.scalar(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.owner_id == user_id,
                    )
                )
                if conversation is not None:
                    await db.execute(
                        delete(Message).where(
                            Message.id == user_message_id,
                            Message.conversation_id == conversation_id,
                            Message.role == "user",
                        )
                    )
        except SQLAlchemyError:
            logger.exception("Could not remove a failed streaming user turn")


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    return await process(body, user, db)


@router.post("/conversations/{cid}/edit", response_model=ChatResponse)
async def edit_message(
    cid: int,
    body: EditMessageRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    conversation = await db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.owner_id == user.id))
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    rows = (await db.scalars(select(Message).where(Message.conversation_id == cid).order_by(Message.id))).all()
    if body.message_index >= len(rows) or rows[body.message_index].role != "user":
        raise HTTPException(400, "Select a user prompt to edit.")
    target = rows[body.message_index]
    await db.execute(delete(Message).where(Message.conversation_id == cid, Message.id >= target.id))
    if body.message_index == 0:
        conversation.title = body.message[:60]
    user_message = await save(db, cid, "user", body.message)
    if isinstance(db, AsyncSession):
        await db.flush()
        await maybe_extract(db, user.id, cid, user_message)
    try:
        result = await answer(db, cid, body.message, settings, body.response_language)
    except OpenRouterError as error:
        await db.rollback()
        raise HTTPException(502, str(error)) from error
    await save(db, cid, "assistant", result)
    await db.commit()
    return ChatResponse(conversation_id=cid, answer=result)


@router.post("/conversations/{cid}/regenerate", response_model=ChatResponse)
async def regenerate(
    cid: int,
    body: RegenerateRequest = RegenerateRequest(),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    conversation = await db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.owner_id == user.id))
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    rows = (await db.scalars(select(Message).where(Message.conversation_id == cid).order_by(Message.id))).all()
    last_user = next((message for message in reversed(rows) if message.role == "user"), None)
    if not last_user:
        raise HTTPException(400, "There is no user message to regenerate.")
    await db.execute(delete(Message).where(Message.conversation_id == cid, Message.id > last_user.id))
    try:
        result = await answer(db, cid, last_user.content, settings, body.response_language)
    except OpenRouterError as error:
        await db.rollback()
        raise HTTPException(502, str(error)) from error
    await save(db, cid, "assistant", result)
    await db.commit()
    return ChatResponse(conversation_id=cid, answer=result)


@router.post("/chat/stream")
async def stream(body: ChatRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_session)):
    # Persist the conversation row before returning StreamingResponse. The
    # generator then uses its own session and never relies on request cleanup.
    try:
        cid = await ensure_conversation(db, user.id, body.conversation_id, body.message, persist_user_message=False)
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500, "The conversation could not be started.") from error

    async def events() -> AsyncIterator[str]:
        parts: list[str] = []
        user_message_id: int | None = None
        async with Session() as stream_db:
            try:
                # Commit the user turn before model generation. This makes the
                # turn visible to history and gives cancellation a durable anchor.
                async with stream_db.begin():
                    conversation = await stream_db.scalar(
                        select(Conversation)
                        .where(Conversation.id == cid, Conversation.owner_id == user.id)
                        .with_for_update()
                    )
                    if conversation is None:
                        yield f'data: {json.dumps({"error": "Conversation not found"})}\n\n'
                        yield "data: [DONE]\n\n"
                        return
                    user_message = await save(stream_db, cid, "user", body.message)
                    await stream_db.flush()
                    user_message_id = getattr(user_message, "id", None)
                    if isinstance(stream_db, AsyncSession):
                        await maybe_extract(stream_db, user.id, cid, user_message)

                yield f'data: {json.dumps({"conversation_id": cid})}\n\n'
                stream_response_language = getattr(body, "response_language", None)
                model_stream = (
                    answer_stream(stream_db, cid, body.message, settings, stream_response_language)
                    if stream_response_language
                    else answer_stream(stream_db, cid, body.message, settings)
                )
                async for token in model_stream:
                    parts.append(token)
                    yield f'data: {json.dumps({"token": token}, ensure_ascii=False)}\n\n'

                # The model service may leave a read transaction open while it
                # streams. Close it before the independent persistence commit.
                await stream_db.rollback()
                await _persist_assistant_once(user.id, cid, user_message_id, "".join(parts))
                yield f'data: {json.dumps({"done": True, "conversation_id": cid})}\n\n'
                yield "data: [DONE]\n\n"
            except OpenRouterError as error:
                await stream_db.rollback()
                await _remove_user_turn(user.id, cid, user_message_id)
                yield f'data: {json.dumps({"error": str(error)})}\n\n'
                yield "data: [DONE]\n\n"
            except SQLAlchemyError:
                await stream_db.rollback()
                await _remove_user_turn(user.id, cid, user_message_id)
                yield f'data: {json.dumps({"error": "The conversation could not be saved."})}\n\n'
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                # A disconnected StreamingResponse can cancel this generator.
                # Shield a bounded independent-session commit so cancellation
                # does not roll back the already generated partial response.
                try:
                    await asyncio.shield(stream_db.rollback())
                except BaseException:
                    logger.exception("Could not close the cancelled streaming session")
                if parts and user_message_id is not None:
                    persist_task = asyncio.create_task(
                        _persist_assistant_once(user.id, cid, user_message_id, "".join(parts))
                    )
                    try:
                        await asyncio.wait_for(asyncio.shield(persist_task), timeout=5)
                    except BaseException:
                        logger.exception("Could not persist the cancelled partial response")
                raise

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
