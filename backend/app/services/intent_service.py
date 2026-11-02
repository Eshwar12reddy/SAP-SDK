import re

from .greeting_service import detect_greeting


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("answer_evaluation", re.compile(r"\b(rate|score|evaluate|grade|assess)\b", re.I)),
    ("interview_question", re.compile(r"\b(interview question|ask me .* question|give me .* question)\b", re.I)),
    ("architecture_or_workflow", re.compile(r"\b(architecture|end[ -]to[ -]end|workflow|data flow|landscape|integration flow)\b", re.I)),
    ("comparison", re.compile(r"\b(compare|comparison|difference between|versus|\bvs\.?\b)\b", re.I)),
    ("technical_troubleshooting", re.compile(r"\b(error|issue|failed|failure|not working|troubleshoot|troubleshooting|root cause|resolve|fix|debug)\b", re.I)),
    ("step_by_step_implementation", re.compile(r"\b(step by step|how do i implement|how can i configure|implementation steps|configure .* step)\b", re.I)),
    ("code_generation", re.compile(r"\b(write|generate|create|show me)\b.{0,50}\b(code|program|class|function|query|abap|sql|snippet|script)\b", re.I)),
    ("follow_up_question", re.compile(r"\b(it|its|they|them|this|that|these|those|previous|above|second|former|latter)\b|\b(what about|why is that|how does that|give an example|explain more|in simple words)\b", re.I)),
    ("definition_or_explanation", re.compile(r"\b(what is|what are|define|explain|meaning of|tell me about)\b", re.I)),
)


def classify_intent(text: str) -> str:
    """Choose a response style with deterministic heuristics; never expose this label."""
    if detect_greeting(text):
        return "greeting"
    for name, pattern in _PATTERNS:
        if pattern.search(text):
            return name
    return "simple_factual_question"


_WORD_LIMIT = re.compile(r"\b(?:in|within|under|about|around|exactly|approximately)?\s*(\d{1,5})\s+words?\b", re.I)
_BRIEF = re.compile(r"\b(briefly|in brief|short answer|be concise|quick answer)\b|\b(answer|respond|explain)\b.{0,24}\b(one sentence|one line)\b", re.I)
_DETAILED = re.compile(r"\b(in detail|detailed|comprehensive|end[ -]to[ -]end|deep dive|architect|10\s*\+?\s*years|production scenario|everything)\b", re.I)


def response_guidance(intent: str, question: str = "") -> str:
    """Build question-specific planning guidance without fixed answer-length bands."""
    guidance = {
        "greeting": "Return only a short, natural greeting.",
        "simple_factual_question": "Answer the fact directly; include only the explanation needed to make it accurate and useful.",
        "definition_or_explanation": "Start with the meaning, then explain relevant responsibilities or context to the depth the question asks for.",
        "technical_troubleshooting": "Diagnose the stated symptoms and give relevant checks and corrective steps; do not force a template if a direct fix is clearer.",
        "step_by_step_implementation": "Give ordered, executable steps and call out prerequisites or release-specific assumptions that matter.",
        "architecture_or_workflow": "Cover the components and workflow actually requested, their handoffs, relevant production considerations, and any necessary integration points.",
        "comparison": "Compare the requested concepts on relevant dimensions; use a table only if it improves clarity.",
        "interview_question": "If the user asks for one interview question, output exactly one challenging question and no answer unless requested.",
        "answer_evaluation": "Evaluate only the answer the user supplied. Give a score out of 100, explain the important strengths and gaps, and suggest improvements. If no answer was supplied, ask them to paste it.",
        "follow_up_question": "Resolve references from the recent conversation, answer the follow-up directly, and do not repeat the earlier explanation.",
        "code_generation": "Provide SAP-related code that answers the requested task. State material assumptions and do not invent APIs or objects.",
    }
    plan = [
        "Infer answer depth from the exact request, technical complexity, expected completeness, and relevant conversation history; do not choose a fixed length by intent label or question length.",
        "Start with the direct answer. Add the necessary explanation, workflow, example, table, or code only when requested or useful. Stop when the question is fully answered; avoid padding and repeated points.",
        guidance.get(intent, "Choose the clearest response structure for the exact question."),
    ]
    word_limit = _WORD_LIMIT.search(question)
    if word_limit:
        plan.append(f"The user explicitly requested {word_limit.group(1)} words; keep the answer close to that limit and do not add material outside it.")
    elif _BRIEF.search(question) and not re.search(r"\b(summary|summarize|summarise|conclusion)\b.{0,40}\b(one sentence|one line)\b", question, re.I):
        plan.append("The user explicitly requested brevity; give the smallest complete answer that satisfies the request.")
    elif _DETAILED.search(question):
        plan.append("The user explicitly asked for depth; cover each requested area thoroughly, using concrete SAP examples when they improve the answer, without repeating information.")
    if re.search(r"\b(example|scenario|real[- ]world|production case)\b", question, re.I):
        plan.append("Include a concrete example or scenario that directly supports the requested explanation.")
    if re.search(r"\bexactly one|one question|give one\b", question, re.I):
        plan.append("Respect the requested count exactly.")
    if re.search(r"\b(summary|conclusion)\b", question, re.I):
        plan.append("Honor any requested summary or conclusion format, including its requested length.")
    if re.search(r"\b(summary|summarize|summarise|conclusion)\b.{0,40}\b(one sentence|one line)\b", question, re.I):
        plan.append("Apply the one-sentence or one-line constraint only to the requested summary or conclusion; keep any separately requested detailed body comprehensive.")
    return "\n- ".join(plan)
