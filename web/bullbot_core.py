# Reusable BullBot chat logic for the web backend.
# Refactored from scripts/bullbot_chat.py so the web app and CLI share one code path.
#
# Two permanent operating modes:
#   - Live mode (default): uses Amazon Bedrock (Knowledge Base + Guardrail). AWS
#     clients and model resolution are lazy, so importing this module is free and
#     needs no credentials until the first live request.
#   - Demo mode (BULLBOT_DEMO_MODE=1): answers from a local JSON fixture only. Makes
#     NO AWS calls and needs NO credentials. Its keyword safety checks are a
#     demonstration and are NOT equivalent to Amazon Bedrock Guardrails.

import json
import os
import sys

# Reuse the existing config and agent instructions from scripts/ without duplicating them.
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
sys.path.insert(0, SCRIPTS_DIR)
import config  # noqa: E402

INSTRUCTIONS_PATH = os.path.join(SCRIPTS_DIR, "agent_instructions.txt")
DEMO_RESPONSES_PATH = os.path.join(os.path.dirname(__file__), "demo_responses.json")


# True when offline demo mode is enabled. Read live so tests can toggle it.
def demo_mode_enabled():
    return os.environ.get("BULLBOT_DEMO_MODE", "").strip() in ("1", "true", "True")

# Tailored safety messages per block reason (same wording as the CLI client).
PII_MSG = ("For your privacy, I can't accept personal identifiers like SSNs, student "
           "ID numbers, phone numbers, or email addresses. Please re-ask without them.")
TOPIC_MSG = ("I can only help with Sac State academics, transfer credits, degree "
             "planning, and financial aid. Try asking me about one of those.")

# Lazily-initialized singletons so repeated requests reuse one client each.
_runtime = None
_guard = None
_model_arn = None
_instructions = None


# Create (once) and return the Bedrock agent-runtime client.
def _runtime_client():
    global _runtime
    if _runtime is None:
        _runtime = config.client("bedrock-agent-runtime")
    return _runtime


# Create (once) and return the Bedrock runtime client used for ApplyGuardrail.
def _guard_client():
    global _guard
    if _guard is None:
        _guard = config.client("bedrock-runtime")
    return _guard


# Resolve (once) the generation model ARN for the current account/region.
def _model():
    global _model_arn
    if _model_arn is None:
        model_id, is_profile = config.resolve_generation_model()
        _model_arn = config.model_arn(model_id, is_profile)
    return _model_arn


# Load (once) the shared persona/grounding instructions.
def _load_instructions():
    global _instructions
    if _instructions is None:
        with open(INSTRUCTIONS_PATH, encoding="utf-8") as f:
            _instructions = f.read()
    return _instructions


# Build the retrieve_and_generate prompt template with required Bedrock placeholders.
def _prompt_template():
    return (_load_instructions()
            + "\n\nRetrieved official documents:\n$search_results$\n\n"
            + "Student question: $query$\n\n"
            + "Answer following all rules above. Cite every claim and end with a "
            + "Sources list. If the documents do not support an answer, route the "
            + "student to the correct office instead of guessing.")


# Pre-screen input with the guardrail. Returns a tailored message if blocked, else None.
def precheck(guardrail_id, guardrail_version, text):
    r = _guard_client().apply_guardrail(
        guardrailIdentifier=guardrail_id, guardrailVersion=guardrail_version,
        source="INPUT", content=[{"text": {"text": text}}])
    if r["action"] != "GUARDRAIL_INTERVENED":
        return None
    for a in r.get("assessments", []):
        if a.get("sensitiveInformationPolicy"):
            return PII_MSG
        if a.get("topicPolicy"):
            return TOPIC_MSG
    return TOPIC_MSG


# Load (once) the offline demo fixtures.
_demo_data = None


def _demo_fixtures():
    global _demo_data
    if _demo_data is None:
        with open(DEMO_RESPONSES_PATH, encoding="utf-8") as f:
            _demo_data = json.load(f)
    return _demo_data


# Match input text against a fixture list by keyword; return the entry or None.
def _match(text, entries):
    low = text.lower()
    for entry in entries:
        if any(kw.lower() in low for kw in entry.get("match_any", [])):
            return entry
    return None


# Offline answer: safety checks first (keyword-based, NOT Bedrock Guardrails), then
# prepared scenarios, then a fallback. Makes no AWS calls.
def ask_demo(text):
    data = _demo_fixtures()
    hit = _match(text, data.get("safety", [])) or _match(text, data.get("scenarios", []))
    if hit:
        return hit["answer"], None, bool(hit.get("blocked", False))
    fb = data["fallback"]
    return fb["answer"], None, bool(fb.get("blocked", False))


# One chat turn. Returns (answer_text, session_id, blocked_flag).
# session_id threads multi-turn context; blocked_flag marks a guardrail refusal.
# In demo mode this returns a prepared offline answer and never touches AWS.
def ask(kb_id, guardrail_id, guardrail_version, text, session_id=None):
    if demo_mode_enabled():
        return ask_demo(text)

    blocked = precheck(guardrail_id, guardrail_version, text)
    if blocked:
        return blocked, session_id, True

    cfg = {
        "type": "KNOWLEDGE_BASE",
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": kb_id,
            "modelArn": _model(),
            "generationConfiguration": {
                "promptTemplate": {"textPromptTemplate": _prompt_template()},
                "guardrailConfiguration": {
                    "guardrailId": guardrail_id,
                    "guardrailVersion": guardrail_version},
            },
        },
    }
    kwargs = {"input": {"text": text}, "retrieveAndGenerateConfiguration": cfg}
    if session_id:
        kwargs["sessionId"] = session_id
    resp = _runtime_client().retrieve_and_generate(**kwargs)
    return resp["output"]["text"], resp.get("sessionId"), False
