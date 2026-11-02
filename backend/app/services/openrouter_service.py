import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Iterable, AsyncIterator

import httpx

from ..config import Settings
from ..prompts.system_prompt import build_system_prompt

logger = logging.getLogger(__name__)


class OpenRouterError(Exception):
    """Safe, user-facing provider failure without credentials or request content."""


_SENSITIVE_VALUE = re.compile(r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,})", re.I)
_CONTEXT_FAILURE = re.compile(r"context length|too many tokens|maximum context", re.I)
_SCENARIO_WORDS = re.compile(r"scenario|production case|real[- ]world|root cause|charged twice|end[- ]to[- ]end|comprehensive|deep dive|everything", re.I)
_COMPLEX_WORDS = re.compile(r"complex|long response|very detailed|cover all|in depth|thorough", re.I)
_DEEP_REQUEST = re.compile(r"end[- ]to[- ]end|comprehensive|deep dive|in detail|detailed|thorough", re.I)
_MULTI_REQUEST = re.compile(r"\?|\b(and also|also|plus|as well as|along with)\b", re.I)


def _sanitize_provider_message(message: str) -> str:
    message = _SENSITIVE_VALUE.sub("[REDACTED]", message)
    return " ".join(message.replace("\r", " ").replace("\n", " ").split())[:600]


def _provider_error_details(body_text: str) -> tuple[str | None, str]:
    try:
        body = json.loads(body_text or "{}")
    except json.JSONDecodeError:
        return None, _sanitize_provider_message(body_text or "Provider returned an invalid error response.")
    error = body.get("error", body)
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message") or "OpenRouter rejected the request."
        return str(code) if code is not None else None, _sanitize_provider_message(str(message))
    return None, _sanitize_provider_message(str(error))


def _public_provider_error(status_code: int, message: str) -> str:
    if status_code == 400 and _CONTEXT_FAILURE.search(message):
        return "The request is too large for the selected model context window. Start a new chat or shorten the conversation."
    if status_code == 400:
        return "OpenRouter rejected the request. Check the selected model and generation settings."
    if status_code in (401, 403):
        return "OpenRouter authentication failed."
    if status_code == 402:
        return "OpenRouter rejected the request because the account has insufficient credit."
    if status_code == 429:
        return "OpenRouter is rate limiting requests. Please try again shortly."
    if status_code >= 500:
        return "OpenRouter is temporarily unavailable."
    return f"OpenRouter request failed ({status_code})."


def _raise_provider_error(status_code: int, body_text: str, model: str) -> None:
    code, message = _provider_error_details(body_text)
    # Never log the request body, authorization header, prompt, or conversation content.
    logger.warning(
        "OpenRouter request rejected: status=%s model=%s code=%s message=%s",
        status_code,
        model,
        code or "unknown",
        message,
    )
    raise OpenRouterError(_public_provider_error(status_code, message))


def estimate_input_tokens(messages: Iterable[dict]) -> int:
    """Conservative token estimate without adding a tokenizer dependency."""
    items = list(messages)
    characters = 0
    for message in items:
        content = message.get("content", "")
        if isinstance(content, str):
            characters += len(content)
    # Three characters per token is intentionally conservative for Markdown,
    # identifiers, and JSON-heavy SAP context.
    return max(1, math.ceil(characters / 3) + (4 * len(items)))


def response_category(intent: str, question: str) -> str:
    """Combine intent, explicit depth, and request structure into a budget class."""
    if intent in {"greeting", "identity"}:
        return "greeting"
    if _COMPLEX_WORDS.search(question) or (_DEEP_REQUEST.search(question) and intent in {"architecture_or_workflow", "code_generation"}):
        return "complex"
    if _SCENARIO_WORDS.search(question) or len(_MULTI_REQUEST.findall(question)) >= 2:
        return "scenario"
    if intent == "comparison":
        return "comparison"
    if intent == "step_by_step_implementation":
        return "how_to"
    if intent == "technical_troubleshooting":
        return "troubleshooting"
    if intent in {"architecture_or_workflow", "code_generation"}:
        return "technical"
    if intent == "definition_or_explanation":
        return "definition"
    return "simple"


def completion_budget(settings: Settings, intent: str, question: str, messages: list[dict]) -> int:
    """Return an adaptive, context-safe output ceiling for this turn."""
    category = response_category(intent, question)
    requested = {
        "greeting": settings.openrouter_greeting_max_tokens,
        "simple": settings.openrouter_simple_max_tokens,
        "definition": settings.openrouter_definition_max_tokens,
        "technical": settings.openrouter_technical_max_tokens,
        "comparison": settings.openrouter_comparison_max_tokens,
        "how_to": settings.openrouter_how_to_max_tokens,
        "troubleshooting": settings.openrouter_troubleshooting_max_tokens,
        "scenario": settings.openrouter_scenario_max_tokens,
        "complex": settings.openrouter_complex_max_tokens,
    }[category]

    input_tokens = estimate_input_tokens(messages)
    available = settings.openrouter_context_window - input_tokens - settings.openrouter_context_safety_margin
    budget = min(requested, settings.openrouter_max_tokens, max(0, available))
    if budget < settings.openrouter_min_completion_tokens:
        raise OpenRouterError("The conversation is too long for the selected model. Start a new chat or shorten the conversation.")
    return budget


def build_payload(settings: Settings, messages: list[dict], intent: str, question: str, *, stream: bool, response_language: str | None = None) -> dict:
    prompt_messages = [{"role": "system", "content": build_system_prompt(intent, question, response_language)}, *messages]
    payload = {
        "model": settings.openrouter_model,
        "messages": prompt_messages,
        "temperature": 0.2,
        # OpenRouter documents max_tokens as deprecated; use the current field.
        "max_completion_tokens": completion_budget(settings, intent, question, prompt_messages),
    }
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    # Do not send reasoning or other provider-specific fields unless explicitly configured.
    return payload


def _request_headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json", "X-Title": "SAP BRIM AI"}


def _log_usage(settings: Settings, intent: str, question: str, payload: dict, usage: dict | None, finish_reason: str | None, started_at: float) -> None:
    usage = usage or {}
    logger.info(
        "OpenRouter completion model=%s category=%s budget=%s prompt_tokens=%s completion_tokens=%s finish_reason=%s latency_ms=%s",
        settings.openrouter_model,
        response_category(intent, question),
        payload.get("max_completion_tokens"),
        usage.get("prompt_tokens", usage.get("input_tokens", "unknown")),
        usage.get("completion_tokens", usage.get("output_tokens", "unknown")),
        finish_reason or "unknown",
        round((time.perf_counter() - started_at) * 1000),
    )


async def complete(messages: list[dict], settings: Settings, intent: str = "simple_factual_question", response_language: str | None = None):
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured.")
    question = messages[-1].get("content", "") if messages else ""
    payload = build_payload(settings, messages, intent, question, stream=False, response_language=response_language)
    started_at = time.perf_counter()
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(base_url=settings.openrouter_base_url, timeout=settings.request_timeout) as client:
                response = await client.post("/chat/completions", headers=_request_headers(settings), json=payload)
                if response.status_code == 429 and attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code >= 400:
                    _raise_provider_error(response.status_code, response.text, settings.openrouter_model)
                data = response.json()
                choices = data.get("choices") or []
                finish_reason = choices[0].get("finish_reason") if choices else None
                _log_usage(settings, intent, question, payload, data.get("usage"), finish_reason, started_at)
                return data["choices"][0]["message"].get("content", "")
        except OpenRouterError:
            raise
        except httpx.TimeoutException as error:
            if attempt == 2:
                raise OpenRouterError("OpenRouter request timed out.") from error
        except httpx.RequestError as error:
            raise OpenRouterError("Unable to connect to OpenRouter.") from error
    raise OpenRouterError("OpenRouter is temporarily unavailable.")


async def stream_complete(messages: list[dict], settings: Settings, intent: str = "simple_factual_question", response_language: str | None = None) -> AsyncIterator[str]:
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured.")
    question = messages[-1].get("content", "") if messages else ""
    payload = build_payload(settings, messages, intent, question, stream=True, response_language=response_language)
    started_at = time.perf_counter()
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(base_url=settings.openrouter_base_url, timeout=settings.request_timeout) as client:
                async with client.stream("POST", "/chat/completions", headers=_request_headers(settings), json=payload) as response:
                    if response.status_code == 429 and attempt < 2:
                        await response.aread()
                        await asyncio.sleep(2**attempt)
                        continue
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        _raise_provider_error(response.status_code, body, settings.openrouter_model)
                    usage: dict | None = None
                    finish_reason: str | None = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event.get("usage"), dict):
                            usage = event["usage"]
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        finish_reason = choices[0].get("finish_reason") or finish_reason
                        token = (choices[0].get("delta") or {}).get("content")
                        if isinstance(token, str) and token:
                            yield token
                    _log_usage(settings, intent, question, payload, usage, finish_reason, started_at)
                    return
        except OpenRouterError:
            raise
        except httpx.TimeoutException as error:
            if attempt == 2:
                raise OpenRouterError("OpenRouter request timed out.") from error
        except httpx.RequestError as error:
            raise OpenRouterError("Unable to connect to OpenRouter.") from error
    raise OpenRouterError("OpenRouter is temporarily unavailable.")
