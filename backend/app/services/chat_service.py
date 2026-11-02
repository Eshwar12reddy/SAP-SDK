from .guardrail_service import classify, FALLBACK, IDENTITY
from .memory_service import context, cross_chat_context, memory_prompt
from .openrouter_service import complete, stream_complete
from .greeting_service import generate_identity_response, get_greeting_response
from .intent_service import classify_intent
from ..database import Conversation, Message
from sqlalchemy import select


def _relevant_context(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Only use the current conversation's recent turns when the latest topic is SAP-related."""
    for item in reversed(history):
        if item["role"] != "user":
            continue
        if get_greeting_response(item["content"]):
            continue
        if classify(item["content"], "SAP") == "allowed":
            return history[-40:]
        return []
    return []


async def _plan_answer(db, cid, question):
    history = await context(db, cid)
    # Chat API handlers persist the current user turn before asking for its answer.
    # Remove it from prior context so it is sent to the model exactly once.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == question:
        history = history[:-1]

    greeting = get_greeting_response(question)
    if greeting:
        return greeting, [], "greeting"
    identity = generate_identity_response(question)
    if identity:
        return identity, [], "identity"

    recent = _relevant_context(history)
    context_text = " ".join(item["content"] for item in recent)
    kind = classify(question, context_text)
    if kind == "identity":
        return IDENTITY, [], "identity"
    if kind != "allowed":
        return FALLBACK, [], "simple_factual_question"

    intent = classify_intent(question)
    memory_message = None
    if db is not None:
        try:
            owner_id = await db.scalar(select(Conversation.owner_id).where(Conversation.id == cid))
            memory_message = memory_prompt(await cross_chat_context(owner_id, cid, question))
        except Exception:
            # Memory is an enhancement; current-chat answering must remain available if it fails.
            memory_message = None
    prompt_messages = ([memory_message] if memory_message else []) + [*recent, {"role": "user", "content": question}]
    return None, prompt_messages, intent


async def answer(db, cid, question, settings, response_language: str | None = None):
    direct, prompt_messages, intent = await _plan_answer(db, cid, question)
    if direct is not None:
        return direct
    options = {"response_language": response_language} if response_language else {}
    return await complete(prompt_messages, settings, intent=intent, **options)


async def answer_stream(db, cid, question, settings, response_language: str | None = None):
    direct, prompt_messages, intent = await _plan_answer(db, cid, question)
    if direct is not None:
        yield direct
        return
    options = {"response_language": response_language} if response_language else {}
    async for token in stream_complete(prompt_messages, settings, intent=intent, **options):
        yield token


async def save(db, cid, role, content):
    message = Message(conversation_id=cid, role=role, content=content)
    db.add(message)
    return message
