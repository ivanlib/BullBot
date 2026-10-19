# Step 5: create the guardrail (PII block/anonymize, denied topics, grounding checks)
# and publish a numbered version. The agent uses the numbered version, never DRAFT.

import config

bedrock = config.client("bedrock")

INPUT_BLOCKED = (
    "For your privacy, I can't accept personal identifiers like SSNs, student ID "
    "numbers, phone numbers, or email addresses. Please re-ask without them.")
OUTPUT_BLOCKED = (
    "I couldn't confirm that from official Sac State documents. Please contact "
    "Academic Advising (for courses/transfer/degree planning) or the Financial Aid "
    "& Scholarships Office (for aid and grants) so a staff member can help.")


# Find an existing guardrail by name so re-runs do not duplicate it.
def find_guardrail():
    for g in bedrock.list_guardrails(maxResults=100)["guardrails"]:
        if g["name"] == config.GUARDRAIL_NAME:
            return g["id"]
    return None


# Create the guardrail with PII, topic, and contextual-grounding policies.
def create_guardrail():
    resp = bedrock.create_guardrail(
        name=config.GUARDRAIL_NAME,
        description="BullBot safety: block student PII, stay on-topic, enforce grounding.",
        blockedInputMessaging=INPUT_BLOCKED,
        blockedOutputsMessaging=OUTPUT_BLOCKED,
        sensitiveInformationPolicyConfig={
            "piiEntitiesConfig": [
                {"type": "US_SOCIAL_SECURITY_NUMBER", "action": "BLOCK"},
                {"type": "EMAIL", "action": "ANONYMIZE"},
                {"type": "PHONE", "action": "ANONYMIZE"},
            ],
            "regexesConfig": [
                {"name": "sacstate_student_id",
                 "description": "Sac State 9-digit student ID",
                 "pattern": r"\b\d{9}\b", "action": "BLOCK"},
            ],
        },
        topicPolicyConfig={
            "topicsConfig": [
                # Define forbidden subjects POSITIVELY. A negated definition
                # ("anything not about...") makes the classifier block legitimate
                # on-topic questions, so list the actual off-topic subjects instead.
                {"name": "GeneralChitChat", "type": "DENY",
                 "definition": ("Entertainment, sports, celebrities, politics, "
                                "general trivia, jokes, creative writing, and "
                                "requests for general programming or coding help "
                                "unrelated to a Sac State course."),
                 "examples": ["Who won the Sacramento Kings game last night?",
                              "Write me a poem about summer",
                              "Help me debug my Python script",
                              "What's the weather tomorrow?"]},
                {"name": "ProfessionalAdvice", "type": "DENY",
                 "definition": ("Personal medical, legal, or investment advice "
                                "about the student's own situation."),
                 "examples": ["Should I invest my refund in stocks?",
                              "Is this apartment contract legally binding?",
                              "What medication should I take for stress?"]},
            ],
        },
        # NOTE: Contextual grounding is intentionally OMITTED for the demo. The
        # placeholder docs carry "illustrative, not official" disclaimers that depress
        # grounding scores and cause the filter to block otherwise-correct, cited
        # answers (especially table-based course mappings). Grounding and citations are
        # enforced through the agent instructions instead. Re-enable this block (start
        # at 0.5 and tune up) once real, authoritative campus documents are ingested:
        #
        # contextualGroundingPolicyConfig={
        #     "filtersConfig": [
        #         {"type": "GROUNDING", "threshold": 0.5},
        #         {"type": "RELEVANCE", "threshold": 0.5},
        #     ],
        # },
    )
    print(f"created guardrail: {resp['guardrailId']}")
    return resp["guardrailId"]


# Publish an immutable numbered version for production/demo use.
def publish_version(guardrail_id):
    resp = bedrock.create_guardrail_version(
        guardrailIdentifier=guardrail_id,
        description="BullBot v1 for demo")
    version = resp["version"]
    print(f"published guardrail version: {version}")
    return version


def main():
    guardrail_id = find_guardrail() or create_guardrail()
    version = publish_version(guardrail_id)
    print(f"\nGUARDRAIL_ID={guardrail_id}\nGUARDRAIL_VERSION={version}")
    return guardrail_id, version


if __name__ == "__main__":
    main()
