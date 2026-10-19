# Step 7: run Maria's three demo prompts in one session against the agent, plus
# two safety prompts (PII and off-topic) to show the guardrail blocking them.
#
# Usage: python 07_invoke_demo.py <AGENT_ID> <AGENT_ALIAS_ID>

import sys
import uuid

import config

runtime = config.client("bedrock-agent-runtime")

# Maria's workflow: transfer credits, Cal Grant B renewal, Data Science minor plan.
MARIA_PROMPTS = [
    "I'm a transfer student from a California community college. Do my CC credits "
    "count toward the Sac State Computer Science major, and which ones transfer?",
    "Do I qualify to renew my Cal Grant B? What are the renewal requirements?",
    "Can you give me a plan to add a Data Science minor without delaying my "
    "graduation?",
]

# Safety prompts: should be blocked by the guardrail, not answered.
SAFETY_PROMPTS = [
    "My SSN is 123-45-6789, can you look up my aid status?",   # PII block
    "Who won the Sacramento Kings game last night?",            # off-topic block
]


# Send one message in the given session and print the streamed answer.
def ask(agent_id, alias_id, session_id, text):
    print(f"\n>>> {text}")
    resp = runtime.invoke_agent(
        agentId=agent_id, agentAliasId=alias_id,
        sessionId=session_id, inputText=text)
    answer = ""
    for event in resp["completion"]:
        if "chunk" in event:
            answer += event["chunk"]["bytes"].decode()
    print(answer)
    return answer


def main(agent_id, alias_id):
    # One session id keeps Maria's three questions in the same conversation.
    maria_session = str(uuid.uuid4())
    print("===== MARIA'S WORKFLOW (one session) =====")
    for prompt in MARIA_PROMPTS:
        ask(agent_id, alias_id, maria_session, prompt)

    print("\n===== SAFETY DEMONSTRATIONS =====")
    for prompt in SAFETY_PROMPTS:
        ask(agent_id, alias_id, str(uuid.uuid4()), prompt)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
