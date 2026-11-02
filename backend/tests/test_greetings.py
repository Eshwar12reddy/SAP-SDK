from app.services.greeting_service import detect_greeting, generate_identity_response, get_greeting_response


def test_greetings_are_short_and_natural():
    assert get_greeting_response("Hi") == "Hi! 👋"
    assert get_greeting_response("Hello") == "Hello! 😊"
    assert get_greeting_response("Thanks") == "You're welcome! 👍"


def test_spelling_variations_are_supported():
    assert get_greeting_response("Hlooo") == "Hello! 😊"
    assert get_greeting_response("Heyyyy") == "Hey! 😄"


def test_greeting_is_not_detected_inside_a_question():
    assert detect_greeting("Hey, explain SAP BRIM") is None
    assert detect_greeting("Hello, who won yesterday's match?") is None


def test_identity_and_capability_questions_are_deterministic():
    assert "SAP BRIM AI" in generate_identity_response("Who are you?")
    assert "SAP BRIM" in generate_identity_response("What can you do?")
