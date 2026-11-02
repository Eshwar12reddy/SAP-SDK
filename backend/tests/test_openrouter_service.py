import pytest

from app.config import Settings
from app.services import openrouter_service


def settings(**overrides):
    values = {"openrouter_api_key": "test-key", "_env_file": None}
    values.update(overrides)
    return Settings(**values)


def test_adaptive_budgets_are_configurable_and_context_safe():
    configured = settings()
    assert openrouter_service.completion_budget(configured, "greeting", "Hi", [{"role": "user", "content": "Hi"}]) == 100
    assert openrouter_service.completion_budget(configured, "simple_factual_question", "How are you?", [{"role": "user", "content": "How are you?"}]) == 300
    assert openrouter_service.completion_budget(configured, "definition_or_explanation", "What is SAP BRIM?", [{"role": "user", "content": "What is SAP BRIM?"}]) == 600
    assert openrouter_service.completion_budget(configured, "comparison", "Compare SAP CC and SAP CI.", [{"role": "user", "content": "Compare SAP CC and SAP CI."}]) == 2000
    assert openrouter_service.completion_budget(configured, "step_by_step_implementation", "How do I configure SAP BRIM step by step?", [{"role": "user", "content": "How do I configure SAP BRIM step by step?"}]) == 2500
    assert openrouter_service.completion_budget(configured, "technical_troubleshooting", "How do I troubleshoot an SAP error?", [{"role": "user", "content": "How do I troubleshoot an SAP error?"}]) == 3500
    assert openrouter_service.completion_budget(configured, "architecture_or_workflow", "Explain SAP BRIM architecture.", [{"role": "user", "content": "Explain SAP BRIM architecture."}]) == 1500
    assert openrouter_service.completion_budget(configured, "technical_troubleshooting", "Explain the production root cause scenario.", [{"role": "user", "content": "Explain the production root cause scenario."}]) == 5000
    assert openrouter_service.completion_budget(configured, "architecture_or_workflow", "Explain SAP BRIM end-to-end in detail.", [{"role": "user", "content": "Explain SAP BRIM end-to-end in detail."}]) == 8000

    constrained = settings(openrouter_context_window=700)
    long_prompt = [{"role": "user", "content": "x" * 1000}]
    assert openrouter_service.completion_budget(constrained, "definition_or_explanation", "What is SAP BRIM?", long_prompt) < constrained.openrouter_definition_max_tokens


def test_payload_uses_current_output_parameter_and_no_reasoning_override():
    payload = openrouter_service.build_payload(settings(), [{"role": "user", "content": "Hi"}], "greeting", "Hi", stream=True)

    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1] == {"role": "user", "content": "Hi"}
    assert payload["max_completion_tokens"] == 100
    assert "max_tokens" not in payload
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert "reasoning" not in payload


def test_payload_adds_multilingual_policy_without_changing_message_roles():
    payload = openrouter_service.build_payload(
        settings(),
        [{"role": "user", "content": "اشرح SAP BRIM"}],
        "definition_or_explanation",
        "اشرح SAP BRIM",
        stream=False,
        response_language="Arabic",
    )

    system_message = payload["messages"][0]["content"]
    assert "CONFIGURED RESPONSE LANGUAGE" in system_message
    assert "Arabic" in system_message
    assert payload["messages"][1] == {"role": "user", "content": "اشرح SAP BRIM"}


def test_provider_context_error_is_sanitized_for_users_and_logs(caplog):
    body = '{"error":{"message":"This endpoint maximum context length is 131072; Bearer secret-value; provider-test-key","code":400}}'

    with caplog.at_level("WARNING"):
        with pytest.raises(openrouter_service.OpenRouterError) as error:
            openrouter_service._raise_provider_error(400, body, "openai/gpt-oss-120b")

    assert "too large" in str(error.value)
    assert "secret-value" not in caplog.text
    assert "Bearer secret-value" not in caplog.text


@pytest.mark.asyncio
async def test_complete_surfaces_sanitized_provider_400(monkeypatch):
    class Response:
        status_code = 400
        text = '{"error":{"message":"Invalid max_completion_tokens","code":400}}'

        def json(self):
            return {"error": {"message": "Invalid max_completion_tokens", "code": 400}}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(openrouter_service.httpx, "AsyncClient", lambda **_kwargs: Client())

    with pytest.raises(openrouter_service.OpenRouterError, match="rejected the request"):
        await openrouter_service.complete([{"role": "user", "content": "Hi"}], settings(), intent="greeting")


@pytest.mark.asyncio
async def test_streaming_400_is_reported_before_any_tokens(monkeypatch):
    class Response:
        status_code = 400

        async def aread(self):
            return b'{"error":{"message":"Invalid max_completion_tokens","code":400}}'

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_lines(self):
            yield ""

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(openrouter_service.httpx, "AsyncClient", lambda **_kwargs: Client())

    with pytest.raises(openrouter_service.OpenRouterError, match="rejected the request"):
        async for _token in openrouter_service.stream_complete([{"role": "user", "content": "Hi"}], settings(), intent="greeting"):
            raise AssertionError("No token should be yielded after a provider 400")
