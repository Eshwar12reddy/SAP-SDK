import pytest

from app.services import chat_service
from app.services.guardrail_service import FALLBACK


@pytest.mark.asyncio
async def test_current_question_is_not_duplicated_in_model_context(monkeypatch):
    supplied = []

    async def fake_context(db, conversation_id):
        return [{"role": "user", "content": "What is SAP BRIM?"}]

    async def fake_complete(messages, settings, intent):
        supplied.extend(messages)
        return "SAP BRIM manages subscription and usage-based revenue processes."

    monkeypatch.setattr(chat_service, "context", fake_context)
    monkeypatch.setattr(chat_service, "complete", fake_complete)
    result = await chat_service.answer(None, 7, "What is SAP BRIM?", object())

    assert result.startswith("SAP BRIM")
    assert supplied == [{"role": "user", "content": "What is SAP BRIM?"}]


@pytest.mark.asyncio
async def test_followup_uses_recent_conversation_context(monkeypatch):
    supplied = []

    async def fake_context(db, conversation_id):
        return [
            {"role": "user", "content": "Explain SAP Convergent Charging."},
            {"role": "assistant", "content": "SAP Convergent Charging rates usage and manages charging services."},
        ]

    async def fake_complete(messages, settings, intent):
        supplied.extend(messages)
        assert intent == "follow_up_question"
        return "It rates usage and calculates charges."

    monkeypatch.setattr(chat_service, "context", fake_context)
    monkeypatch.setattr(chat_service, "complete", fake_complete)
    result = await chat_service.answer(None, 8, "What is its purpose?", object())

    assert result == "It rates usage and calculates charges."
    assert supplied[0]["content"].startswith("Explain SAP Convergent Charging")
    assert supplied[-1] == {"role": "user", "content": "What is its purpose?"}


@pytest.mark.asyncio
async def test_greeting_and_out_of_scope_do_not_call_model(monkeypatch):
    async def fake_context(db, conversation_id):
        return [{"role": "user", "content": "Explain SAP Convergent Charging."}]

    async def fail_complete(*args, **kwargs):
        raise AssertionError("The model should not be called for these messages")

    monkeypatch.setattr(chat_service, "context", fake_context)
    monkeypatch.setattr(chat_service, "complete", fail_complete)
    assert await chat_service.answer(None, 9, "Hi", object()) == "Hi! 👋"
    assert await chat_service.answer(None, 9, "What is the weather today?", object()) == FALLBACK


@pytest.mark.asyncio
async def test_answer_stream_yields_model_chunks_progressively(monkeypatch):
    async def fake_context(db, conversation_id):
        return []

    async def fake_stream(messages, settings, intent):
        assert intent == "definition_or_explanation"
        yield "SAP BRIM manages "
        yield "subscription and usage revenue."

    monkeypatch.setattr(chat_service, "context", fake_context)
    monkeypatch.setattr(chat_service, "stream_complete", fake_stream)
    tokens = [token async for token in chat_service.answer_stream(None, 10, "What is SAP BRIM?", object())]

    assert tokens == ["SAP BRIM manages ", "subscription and usage revenue."]
