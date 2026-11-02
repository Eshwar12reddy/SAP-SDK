from app.services.guardrail_service import FALLBACK, classify
from app.services.intent_service import classify_intent


def test_requested_intents_are_detected():
    assert classify_intent("Hi") == "greeting"
    assert classify_intent("What is SAP BRIM?") == "definition_or_explanation"
    assert classify_intent("Explain SAP Convergent Charging in 20 words") == "definition_or_explanation"
    assert classify_intent("Explain SAP BRIM architecture in detail") == "architecture_or_workflow"
    assert classify_intent("Compare SAP CC and SAP CI") == "comparison"
    assert classify_intent("How do I troubleshoot a SAP BRIM billing error?") == "technical_troubleshooting"
    assert classify_intent("Show SAP BRIM implementation steps") == "step_by_step_implementation"
    assert classify_intent("Generate ABAP code for this SAP scenario") == "code_generation"
    assert classify_intent("Give one SAP BRIM interview question for 10+ years") == "interview_question"
    assert classify_intent("Rate this SAP BRIM answer out of 100") == "answer_evaluation"
    assert classify_intent("Explain FI-CA with a production example") == "definition_or_explanation"


def test_followups_require_conversation_context():
    assert classify_intent("What is its purpose?") == "follow_up_question"
    assert classify_intent("Explain the previous answer in simple words") == "follow_up_question"


def test_sap_scope_allows_contextual_followup_but_rejects_weather():
    assert classify("What is its purpose?", "SAP Convergent Charging") == "allowed"
    assert classify("What is the weather today?", "SAP Convergent Charging") == "out_of_scope"
    assert FALLBACK == "I specialize in SAP-related topics. Please ask an SAP-related question."


def test_prompt_uses_adaptive_depth_and_honors_word_limits():
    from app.prompts.system_prompt import build_system_prompt

    concise = build_system_prompt("definition_or_explanation", "What is SAP BRIM?")
    detailed = build_system_prompt("architecture_or_workflow", "Explain SAP BRIM end-to-end in detail for 10+ years")
    limited = build_system_prompt("follow_up_question", "Explain the above in 20 words")
    body_and_conclusion = build_system_prompt("simple_factual_question", "Give a detailed answer, but summarize the conclusion in one sentence")

    assert "There are no preset short/medium/long lengths" in concise
    assert "The user explicitly asked for depth" in detailed
    assert "explicitly requested 20 words" in limited
    assert "simple fact is usually" not in concise
    assert "only to the requested summary or conclusion" in body_and_conclusion
    assert "Do not claim to have used a knowledge base" in concise


def test_generation_ceiling_is_configurable_for_the_selected_model():
    from app.config import Settings

    assert Settings(_env_file=None).openrouter_max_tokens == 131072
    assert Settings(_env_file=None, openrouter_max_tokens=32768).openrouter_max_tokens == 32768
