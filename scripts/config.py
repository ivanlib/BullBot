# Central config and shared boto3 clients for all BullBot setup scripts.
# Edit values here once; every script reads from this module.

import boto3

REGION = "us-east-1"

# Core resource names. Keep these stable so re-runs find existing resources.
SOURCE_BUCKET_PREFIX = "bullbot-sources"          # account id + region appended at runtime
SOURCE_PREFIX = "sources/"
COLLECTION_NAME = "bullbot-vec"
VECTOR_INDEX_NAME = "bullbot-index"
KB_NAME = "bullbot-kb"
DATA_SOURCE_NAME = "bullbot-s3-source"
GUARDRAIL_NAME = "bullbot-guardrail"
AGENT_NAME = "BullBot"
AGENT_ALIAS = "live"

# Models.
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIMENSION = 1024

# Vector index field names shared by the AOSS index and the KB field mapping.
VECTOR_FIELD = "bedrock-knowledge-base-default-vector"
TEXT_FIELD = "AMAZON_BEDROCK_TEXT_CHUNK"
METADATA_FIELD = "AMAZON_BEDROCK_METADATA"

# Local folder of campus documents uploaded to S3.
DOCS_DIR = "docs"


# Returns the current AWS account id.
def account_id():
    return boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]


# Returns the globally-unique source bucket name for this account and region.
def source_bucket():
    return f"{SOURCE_BUCKET_PREFIX}-{account_id()}-{REGION}"


# Shared client factory so every script uses the same region.
def client(service):
    return boto3.client(service, region_name=REGION)


# Preferred generation models, best first. The resolver picks the first one that
# is actually available in this account/region as an active inference profile.
PREFERRED_MODELS = [
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-3-5-sonnet-20240620-v1:0",
]


# Return (model_id, is_inference_profile) for the best available Claude model.
def resolve_generation_model():
    bedrock = client("bedrock")
    profiles = {p["inferenceProfileId"]
                for p in bedrock.list_inference_profiles().get(
                    "inferenceProfileSummaries", [])
                if p.get("status") == "ACTIVE"}
    for candidate in PREFERRED_MODELS:
        if candidate in profiles:
            return candidate, True
    # Fall back to any active Claude inference profile.
    for pid in sorted(profiles):
        if "claude" in pid.lower():
            return pid, True
    raise RuntimeError("No active Claude inference profile available in region")


# Build the ARN for a resolved model (inference profile or base model).
def model_arn(model_id, is_profile):
    if is_profile:
        return (f"arn:aws:bedrock:{REGION}:{account_id()}:"
                f"inference-profile/{model_id}")
    return f"arn:aws:bedrock:{REGION}::foundation-model/{model_id}"
