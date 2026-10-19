# Teardown: delete demo resources to avoid lingering charges after the hackathon.
# Deletes in reverse dependency order. Ignores "not found" errors so it is re-runnable.

import config

agent = config.client("bedrock-agent")
bedrock = config.client("bedrock")
aoss = config.client("opensearchserverless")
iam = config.client("iam")
s3 = config.client("s3")


# Call a delete function and ignore errors (resource may already be gone).
def safe(label, fn):
    try:
        fn()
        print(f"deleted {label}")
    except Exception as e:
        print(f"skip {label}: {e}")


def delete_agent():
    for a in agent.list_agents(maxResults=100)["agentSummaries"]:
        if a["agentName"] == config.AGENT_NAME:
            agent.delete_agent(agentId=a["agentId"], skipResourceInUseCheck=True)


def delete_kb():
    for kb in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]:
        if kb["name"] == config.KB_NAME:
            agent.delete_knowledge_base(knowledgeBaseId=kb["knowledgeBaseId"])


def delete_guardrail():
    for g in bedrock.list_guardrails(maxResults=100)["guardrails"]:
        if g["name"] == config.GUARDRAIL_NAME:
            bedrock.delete_guardrail(guardrailIdentifier=g["id"])


def delete_collection():
    found = aoss.list_collections(
        collectionFilters={"name": config.COLLECTION_NAME})["collectionSummaries"]
    for c in found:
        aoss.delete_collection(id=c["id"])


def empty_and_delete_bucket():
    bucket = config.source_bucket()
    objs = s3.list_objects_v2(Bucket=bucket).get("Contents", [])
    for o in objs:
        s3.delete_object(Bucket=bucket, Key=o["Key"])
    s3.delete_bucket(Bucket=bucket)


def delete_roles():
    for role in ["AmazonBedrockExecutionRoleForAgents-bullbot",
                 "AmazonBedrockExecutionRoleForKB-bullbot"]:
        for p in iam.list_role_policies(RoleName=role).get("PolicyNames", []):
            iam.delete_role_policy(RoleName=role, PolicyName=p)
        iam.delete_role(RoleName=role)


def main():
    safe("agent", delete_agent)
    safe("knowledge base", delete_kb)
    safe("guardrail", delete_guardrail)
    safe("collection", delete_collection)
    safe("source bucket", empty_and_delete_bucket)
    safe("iam roles", delete_roles)
    print("\nteardown complete")


if __name__ == "__main__":
    main()
