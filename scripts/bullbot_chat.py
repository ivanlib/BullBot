# BullBot demo client (fallback orchestration).
# Used when the account blocks bedrock:CreateAgent (classic agents). Drives the same
# Knowledge Base + Guardrail directly via retrieve_and_generate: the agent instructions
# become the generation prompt, the guardrail is attached, and session state is kept
# client-side so Maria's three questions stay in one conversation.
#
# Usage:
#   python bullbot_chat.py --demo <KB_ID> <GUARDRAIL_ID> <GUARDRAIL_VERSION>
#   python bullbot_chat.py --chat <KB_ID> <GUARDRAIL_ID> <GUARDRAIL_VERSION>

import os
import sys

import config

# Force UTF-8 so Spanish text and em-dashes print on Windows consoles.
sys.stdout.reconfigure(encoding="utf-8")

runtime = config.client("bedrock-agent-runtime")
guard = config.client("bedrock-runtime")

# Tailored messages per block reason so the demo shows the right response.
PII_MSG = ("For your privacy, I can't accept personal identifiers like SSNs, student "
           "ID numbers, phone numbers, or email addresses. Please re-ask without them.")
TOPIC_MSG = ("I can only help with Sac State academics, transfer credits, degree "
             "planning, and financial aid. Try asking me about one of those.")


# Pre-screen input with the guardrail; return a tailored message if it blocks,
# else None so the normal retrieve+generate path runs.
def precheck(guardrail_id, guardrail_version, text):
    r = guard.apply_guardrail(
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


# Load the shared persona/grounding instructions.
def load_instructions():
    path = os.path.join(os.path.dirname(__file__), "agent_instructions.txt")
    with open(path, encoding="utf-8") as f:
        return f.read()


# Build the prompt template for retrieve_and_generate. $search_results$ and
# $query$ are the required Bedrock placeholders the service fills at runtime.
def prompt_template():
    return (load_instructions()
            + "\n\nRetrieved official documents:\n$search_results$\n\n"
            + "Student question: $query$\n\n"
            + "Answer following all rules above. Cite every claim and end with a "
            + "Sources list. If the documents do not support an answer, route the "
            + "student to the correct office instead of guessing.")


# One turn: pre-screen input, then retrieve + generate with the guardrail attached.
def ask(kb_id, model_arn, guardrail_id, guardrail_version, text, session_id=None):
    blocked = precheck(guardrail_id, guardrail_version, text)
    if blocked:
        return blocked, session_id
    config_block = {
        "type": "KNOWLEDGE_BASE",
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": kb_id,
            "modelArn": model_arn,
            "generationConfiguration": {
                "promptTemplate": {"textPromptTemplate": prompt_template()},
                "guardrailConfiguration": {
                    "guardrailId": guardrail_id,
                    "guardrailVersion": guardrail_version},
            },
        },
    }
    kwargs = {"input": {"text": text},
              "retrieveAndGenerateConfiguration": config_block}
    if session_id:
        kwargs["sessionId"] = session_id
    resp = runtime.retrieve_and_generate(**kwargs)
    return resp["output"]["text"], resp.get("sessionId")


# Maria's three questions in one session, plus two guardrail safety checks.
def run_demo(kb_id, model_arn, guardrail_id, guardrail_version):
    maria = [
        "I'm a transfer student from a California community college. Do my CC credits "
        "count toward the Sac State Computer Science major, and which ones transfer?",
        "Do I qualify to renew my Cal Grant B? What are the renewal requirements?",
        "Can you give me a plan to add a Data Science minor without delaying my graduation?",
    ]
    session_id = None
    print("================ MARIA'S WORKFLOW (one session) ================")
    for q in maria:
        print(f"\n>>> {q}\n")
        answer, session_id = ask(kb_id, model_arn, guardrail_id,
                                 guardrail_version, q, session_id)
        print(answer)

    print("\n\n================ SPANISH CHECK ================")
    q = ("Soy estudiante de transferencia. Mis creditos del colegio comunitario "
         "cuentan para la carrera de Computer Science en Sac State?")
    print(f"\n>>> {q}\n")
    answer, _ = ask(kb_id, model_arn, guardrail_id, guardrail_version, q)
    print(answer)

    print("\n\n================ SAFETY: PII (should be blocked) ================")
    q = "My SSN is 123-45-6789, can you look up my aid status?"
    print(f"\n>>> {q}\n")
    answer, _ = ask(kb_id, model_arn, guardrail_id, guardrail_version, q)
    print(answer)

    print("\n\n================ SAFETY: OFF-TOPIC (should be blocked) ================")
    q = "Who won the Sacramento Kings game last night?"
    print(f"\n>>> {q}\n")
    answer, _ = ask(kb_id, model_arn, guardrail_id, guardrail_version, q)
    print(answer)


# Interactive loop for live Q&A during the demo.
def run_chat(kb_id, model_arn, guardrail_id, guardrail_version):
    print("BullBot ready. Ask a question (or 'quit').")
    session_id = None
    while True:
        text = input("\nyou> ").strip()
        if text.lower() in ("quit", "exit"):
            return
        answer, session_id = ask(kb_id, model_arn, guardrail_id,
                                 guardrail_version, text, session_id)
        print(f"\nBullBot> {answer}")


def main():
    mode = sys.argv[1]
    kb_id, guardrail_id, guardrail_version = sys.argv[2], sys.argv[3], sys.argv[4]
    model_id, is_profile = config.resolve_generation_model()
    model_arn = config.model_arn(model_id, is_profile)
    print(f"model: {model_id}\n")
    if mode == "--demo":
        run_demo(kb_id, model_arn, guardrail_id, guardrail_version)
    elif mode == "--chat":
        run_chat(kb_id, model_arn, guardrail_id, guardrail_version)
    else:
        print("usage: python bullbot_chat.py --demo|--chat <KB_ID> <GUARDRAIL_ID> <VERSION>")


if __name__ == "__main__":
    main()
