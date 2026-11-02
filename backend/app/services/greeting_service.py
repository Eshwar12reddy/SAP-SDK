import re

_RESPONSES = {
    "hi": "Hi! 👋",
    "hii": "Hi! 😊",
    "hiii": "Hiii! 👋",
    "hlo": "Hello! 👋",
    "hello": "Hello! 😊",
    "hey": "Hey! 👋",
    "heyy": "Hey! 😄",
    "good morning": "Good morning! ☀️",
    "good afternoon": "Good afternoon! 🌤️",
    "good evening": "Good evening! 🌆",
    "good night": "Good night! 🌙",
    "gm": "Good morning! ☀️",
    "gn": "Good night! 🌙",
    "hi there": "Hi there! 👋",
    "howdy": "Howdy! 🤠",
    "namaste": "Namaste! 🙏",
    "vanakkam": "Vanakkam! 🙏",
    "how are you": "I'm doing well, thanks! 😊",
    "thank you": "You're welcome! 😊",
    "thanks": "You're welcome! 👍",
    "bye": "Goodbye! 👋",
    "see you": "See you! 😊",
}

IDENTITY_RESPONSE = (
    "I'm SAP BRIM AI, focused on SAP technologies and enterprise solutions. "
    "I can help with SAP architecture, configuration, development, integrations, and troubleshooting."
)
CAPABILITY_RESPONSE = (
    "I can explain and help troubleshoot SAP BRIM, S/4HANA, ABAP, BTP, integrations, "
    "architecture, configuration, and related SAP topics."
)


def normalize_greeting(text: str) -> str:
    """Normalize whitespace, case, and trailing punctuation for exact greeting matching."""
    normalized = text.strip().casefold()
    normalized = re.sub(r"[.!?,;:]+$", "", normalized)
    return re.sub(r"\s+", " ", normalized)


def detect_greeting(text: str) -> str | None:
    """Return a canonical greeting only when the entire message is a greeting or pleasantry."""
    normalized = normalize_greeting(text)
    if normalized in _RESPONSES:
        return normalized
    if re.fullmatch(r"h+i{4,}", normalized):
        return "hiii"
    if re.fullmatch(r"hlo{2,}", normalized):
        return "hello"
    if re.fullmatch(r"hl+o+", normalized):
        return "hlo"
    if re.fullmatch(r"he+y{3,}", normalized):
        return "heyy"
    if re.fullmatch(r"hello+", normalized):
        return "hello"
    return None


def get_greeting_response(text: str) -> str | None:
    greeting = detect_greeting(text)
    return _RESPONSES.get(greeting) if greeting else None


def detect_identity_question(text: str) -> str | None:
    normalized = normalize_greeting(text)
    if re.fullmatch(r"(who are you|what are you|what is your purpose|are you chatgpt)", normalized):
        return normalized
    if normalized in {"what can you do", "what do you do"}:
        return "what can you do"
    return None


def generate_identity_response(text: str) -> str | None:
    kind = detect_identity_question(text)
    if not kind:
        return None
    if kind == "what can you do":
        return CAPABILITY_RESPONSE
    if kind == "are you chatgpt":
        return "I'm SAP BRIM AI, a specialized assistant powered by an AI language model through OpenRouter."
    return IDENTITY_RESPONSE


def detect_pleasantry(text: str) -> str | None:
    normalized = normalize_greeting(text)
    return normalized if normalized in {"how are you", "thank you", "thanks", "bye", "see you"} else None


def classify_sap_question(text: str, context: str = "") -> str:
    from .guardrail_service import classify
    return classify(text, context)
