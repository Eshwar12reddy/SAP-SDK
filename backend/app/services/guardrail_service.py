import re

FALLBACK = "I specialize in SAP-related topics. Please ask an SAP-related question."
IDENTITY = "I’m SAP BRIM AI, focused on SAP technologies and enterprise solutions."
TERMS = {
    "sap", "brim", "som", "convergent", "charging", "invoicing", "fi-ca", "fica", "billing", "revenue",
    "s/4hana", "ecc", "btp", "abap", "hana", "fiori", "ui5", "fi", "co", "mm", "sd", "pp", "qm",
    "pm", "ewm", "basis", "integration suite", "successfactors", "ariba", "idoc", "odata", "rfc",
    "billable", "rating", "contract account", "business partner", "cds", "rap", "cap", "sap crm", "sap ci",
    "sap cc", "sap ci", "sap s/4", "sap ecc", "sap hana", "sap commerce", "sap analytics", "sap bw",
    "sap datasphere", "sap build", "sap integration", "sap launchpad", "sap gui",
}
_INJECTION = re.compile(r"ignore\s+(all\s+)?previous|reveal\s+(your|the)\s+prompt|system\s+message|developer\s+message|bypass\s+(the\s+)?rules|jailbreak", re.I)
_IDENTITY = re.compile(r"\b(who are you|what are you|your identity)\b", re.I)
_UNRELATED = re.compile(r"\b(weather|forecast|cricket|football|soccer|basketball|election|politics|celebrity|recipe|horoscope)\b", re.I)
_FOLLOW_UP = re.compile(r"\b(it|its|they|them|this|that|these|those|previous|above|second|former|latter|purpose|components|benefits)\b|\b(what about|why is that|how does that|give an example|explain more|in simple words)\b", re.I)


def _contains_sap_term(text: str) -> bool:
    normalized = text.casefold()
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized) for term in TERMS)


def classify(text: str, context: str = "") -> str:
    low = " ".join(text.strip().split()).casefold()
    if _INJECTION.search(low):
        return "out_of_scope"
    if re.fullmatch(r"(hi|hello|hey|good morning|good afternoon|good evening)[!. ]*", low):
        return "greeting"
    if _IDENTITY.search(low):
        return "identity"
    # A fresh, clearly unrelated topic must not inherit an SAP scope from old history.
    if _UNRELATED.search(low):
        return "out_of_scope"
    if _contains_sap_term(low):
        return "allowed"
    if context and _FOLLOW_UP.search(low) and _contains_sap_term(context):
        return "allowed"
    return "out_of_scope"
