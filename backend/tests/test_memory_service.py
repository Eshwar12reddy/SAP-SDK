from app.services.memory_service import extract_candidate, memory_disabled, memory_prompt


def test_memory_extraction_keeps_user_stated_project_context():
    result = extract_candidate("My project is implementing SAP BRIM with Convergent Charging and FI-CA.")

    assert result is not None
    assert result[1] == "project_context"
    assert "FI-CA" in result[0]


def test_memory_extraction_rejects_secrets_and_temporary_questions():
    assert extract_candidate("My API key is provider-test-key") is None
    assert extract_candidate("How do I troubleshoot this SAP billing error?") is None


def test_memory_can_be_skipped_and_is_marked_untrusted_for_the_model():
    assert memory_disabled("Ignore my previous chats and answer without memory.")
    prompt = memory_prompt([{"memory_type": "project_context", "memory_text": "The project uses SAP FI-CA", "created_at": ""}])
    assert prompt is not None
    assert "untrusted" in prompt["content"]
    assert "SAP FI-CA" in prompt["content"]
