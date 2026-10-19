# Step 6: create the Bedrock Agent, its IAM role, associate the KB, attach the
# guardrail, prepare the agent, and create the 'live' alias.
#
# NOTE: Bedrock Agents (classic) is in maintenance mode. If create-agent is not
# available on this account, use 07_invoke_demo.py's retrieve-and-generate fallback.

import json
import os
import time

import config

agent = config.client("bedrock-agent")
iam = config.client("iam")
bedrock = config.client("bedrock")

AGENT_ROLE_NAME = "AmazonBedrockExecutionRoleForAgents-bullbot"


# Pick a current Claude model (prefers an active inference profile from config).
def resolve_model():
    return config.resolve_generation_model()


# Create the agent service role allowing model invoke, KB retrieve, and guardrail apply.
def ensure_agent_role(model_id, is_profile):
    acct = config.account_id()
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": acct},
                "ArnLike": {"aws:SourceArn":
                            f"arn:aws:bedrock:{config.REGION}:{acct}:agent/*"},
            },
        }],
    }
    # Cross-region inference profiles can route to any region, so the model ARN uses *.
    if is_profile:
        model_resources = [
            f"arn:aws:bedrock:{config.REGION}:{acct}:inference-profile/{model_id}",
            f"arn:aws:bedrock:*::foundation-model/*",
        ]
    else:
        model_resources = [
            f"arn:aws:bedrock:{config.REGION}::foundation-model/{model_id}"]

    perms = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow",
             "Action": ["bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"],
             "Resource": model_resources},
            {"Effect": "Allow",
             "Action": ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
             "Resource": [f"arn:aws:bedrock:{config.REGION}:{acct}:knowledge-base/*"]},
            {"Effect": "Allow", "Action": ["bedrock:ApplyGuardrail"],
             "Resource": [f"arn:aws:bedrock:{config.REGION}:{acct}:guardrail/*"]},
        ],
    }
    try:
        iam.create_role(RoleName=AGENT_ROLE_NAME,
                        AssumeRolePolicyDocument=json.dumps(trust),
                        Description="BullBot agent service role")
        print(f"created role: {AGENT_ROLE_NAME}")
        time.sleep(15)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"role exists: {AGENT_ROLE_NAME}")
    iam.put_role_policy(RoleName=AGENT_ROLE_NAME,
                        PolicyName="BullBotAgentPermissions",
                        PolicyDocument=json.dumps(perms))
    return f"arn:aws:iam::{acct}:role/{AGENT_ROLE_NAME}"


# Read the shared instructions file.
def load_instructions():
    path = os.path.join(os.path.dirname(__file__), "agent_instructions.txt")
    with open(path, encoding="utf-8") as f:
        return f.read()


# Create the agent with the persona instructions and attached guardrail.
def create_agent(role_arn, model_id, guardrail_id, guardrail_version):
    for a in agent.list_agents(maxResults=100)["agentSummaries"]:
        if a["agentName"] == config.AGENT_NAME:
            print(f"agent exists: {config.AGENT_NAME}")
            return a["agentId"]
    for attempt in range(3):
        try:
            resp = agent.create_agent(
                agentName=config.AGENT_NAME,
                foundationModel=model_id,
                instruction=load_instructions(),
                agentResourceRoleArn=role_arn,
                idleSessionTTLInSeconds=900,
                guardrailConfiguration={
                    "guardrailIdentifier": guardrail_id,
                    "guardrailVersion": guardrail_version},
            )
            agent_id = resp["agent"]["agentId"]
            print(f"created agent: {agent_id}")
            _wait_status(agent_id, "NOT_PREPARED")
            return agent_id
        except Exception as e:
            print(f"create-agent attempt {attempt + 1} failed: {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("agent creation failed after retries")


# Associate the KB so the agent knows when and what to retrieve.
def associate_kb(agent_id, kb_id):
    description = (
        "Official Sac State documents: CS major catalog and degree roadmap, "
        "community-college to Sac State CS articulation/transfer mapping, Cal Grant B "
        "financial-aid renewal policy, Data Science minor requirements, and campus "
        "advising/financial-aid contacts. Query for any question about transfer "
        "credits, courses, units, GPA or aid eligibility, graduation planning, minors, "
        "or where to get official help.")
    try:
        agent.associate_agent_knowledge_base(
            agentId=agent_id, agentVersion="DRAFT",
            knowledgeBaseId=kb_id, description=description)
        print("associated KB")
    except Exception as e:
        print(f"KB association note: {e}")


# Prepare the agent (required after any change) and wait until PREPARED.
def prepare(agent_id):
    agent.prepare_agent(agentId=agent_id)
    _wait_status(agent_id, "PREPARED")


# Create the live alias used to invoke the agent.
def create_alias(agent_id):
    for al in agent.list_agent_aliases(
            agentId=agent_id)["agentAliasSummaries"]:
        if al["agentAliasName"] == config.AGENT_ALIAS:
            return al["agentAliasId"]
    resp = agent.create_agent_alias(
        agentId=agent_id, agentAliasName=config.AGENT_ALIAS)
    return resp["agentAlias"]["agentAliasId"]


def _wait_status(agent_id, target):
    while True:
        status = agent.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        if status == target:
            print(f"agent {target}")
            return
        if status == "FAILED":
            raise RuntimeError("agent entered FAILED state")
        print(f"agent status {status}, waiting for {target}...")
        time.sleep(10)


def main(kb_id, guardrail_id, guardrail_version):
    model_id, is_profile = resolve_model()
    print(f"using model: {model_id} (inference_profile={is_profile})")
    role_arn = ensure_agent_role(model_id, is_profile)
    agent_id = create_agent(role_arn, model_id, guardrail_id, guardrail_version)
    associate_kb(agent_id, kb_id)
    prepare(agent_id)
    alias_id = create_alias(agent_id)
    print(f"\nAGENT_ID={agent_id}\nAGENT_ALIAS_ID={alias_id}")
    return agent_id, alias_id


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])  # kb_id, guardrail_id, guardrail_version
