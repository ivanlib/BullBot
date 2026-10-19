# Verification: confirm the Knowledge Base returns relevant, grounded results before
# building the agent. Runs raw `retrieve` (passages + scores) and `retrieve_and_generate`
# (a cited answer) for a known question.
#
# Usage: python verify_retrieval.py <KB_ID> [MODEL_ARN]
#   MODEL_ARN is optional; if omitted a Claude model/profile is auto-resolved.

import sys

import config

runtime = config.client("bedrock-agent-runtime")
bedrock = config.client("bedrock")

# A question we know the ingested docs can answer (transfer credit mapping).
TEST_QUESTION = ("Do my community college credits transfer to the Sac State Computer "
                 "Science major, and which courses map over?")


# Pick a current Claude model ARN for answer generation if the caller did not pass one.
def resolve_model_arn():
    model_id, is_profile = config.resolve_generation_model()
    return config.model_arn(model_id, is_profile)


# Raw retrieval: show which chunks come back and their relevance scores.
def check_retrieve(kb_id):
    print("=== retrieve (raw passages + scores) ===")
    resp = runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": TEST_QUESTION},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": 4}},
    )
    results = resp.get("retrievalResults", [])
    if not results:
        print("NO RESULTS - ingestion may be empty or the query is off-topic.")
        return False
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        source = r.get("location", {}).get(
            "s3Location", {}).get("uri", "unknown")
        snippet = r["content"]["text"][:160].replace("\n", " ")
        print(f"[{i}] score={score:.3f} source={source}")
        print(f"    {snippet}...")
    return True


# End-to-end: a grounded answer that should carry citations.
def check_generate(kb_id, model_arn):
    print("\n=== retrieve_and_generate (grounded answer) ===")
    resp = runtime.retrieve_and_generate(
        input={"text": TEST_QUESTION},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": kb_id,
                "modelArn": model_arn},
        },
    )
    print(resp["output"]["text"])
    citations = resp.get("citations", [])
    print(f"\ncitations returned: {len(citations)}")
    for c in citations:
        for ref in c.get("retrievedReferences", []):
            uri = ref.get("location", {}).get(
                "s3Location", {}).get("uri", "unknown")
            print(f"  - {uri}")
    return len(citations) > 0


def main(kb_id, model_arn=None):
    model_arn = model_arn or resolve_model_arn()
    print(f"KB_ID={kb_id}\nMODEL_ARN={model_arn}\nQUESTION={TEST_QUESTION}\n")
    got_passages = check_retrieve(kb_id)
    got_citations = check_generate(kb_id, model_arn)
    print("\n=== RESULT ===")
    if got_passages and got_citations:
        print("PASS: KB returns relevant passages and a cited answer. Ready for the agent.")
    else:
        print("CHECK: review ingestion status, S3 permissions, and the 1024-dim index.")


if __name__ == "__main__":
    main(*sys.argv[1:])
