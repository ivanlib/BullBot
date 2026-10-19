# Step 4: create the Knowledge Base, the S3 data source (hierarchical chunking),
# then run ingestion and poll until it finishes.

import time

import config

agent = config.client("bedrock-agent")


# Create the KB backed by Titan V2 embeddings and the AOSS collection.
def create_kb(role_arn, collection_arn):
    for existing in agent.list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]:
        if existing["name"] == config.KB_NAME:
            print(f"KB exists: {config.KB_NAME}")
            return existing["knowledgeBaseId"]

    embed_arn = (f"arn:aws:bedrock:{config.REGION}::"
                 f"foundation-model/{config.EMBED_MODEL_ID}")
    # IAM role creation is eventually consistent; retry if Bedrock cannot assume it yet.
    for attempt in range(3):
        try:
            resp = agent.create_knowledge_base(
                name=config.KB_NAME,
                roleArn=role_arn,
                knowledgeBaseConfiguration={
                    "type": "VECTOR",
                    "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": embed_arn},
                },
                storageConfiguration={
                    "type": "OPENSEARCH_SERVERLESS",
                    "opensearchServerlessConfiguration": {
                        "collectionArn": collection_arn,
                        "vectorIndexName": config.VECTOR_INDEX_NAME,
                        "fieldMapping": {
                            "vectorField": config.VECTOR_FIELD,
                            "textField": config.TEXT_FIELD,
                            "metadataField": config.METADATA_FIELD,
                        },
                    },
                },
            )
            kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
            print(f"created KB: {kb_id}")
            return kb_id
        except Exception as e:
            print(f"KB create attempt {attempt + 1} failed: {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("KB creation failed after retries")


# Create the S3 data source with hierarchical chunking (irreversible once set).
def create_data_source(kb_id):
    for existing in agent.list_data_sources(
            knowledgeBaseId=kb_id)["dataSourceSummaries"]:
        if existing["name"] == config.DATA_SOURCE_NAME:
            print(f"data source exists: {config.DATA_SOURCE_NAME}")
            return existing["dataSourceId"]

    bucket_arn = f"arn:aws:s3:::{config.source_bucket()}"
    resp = agent.create_data_source(
        knowledgeBaseId=kb_id,
        name=config.DATA_SOURCE_NAME,
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": bucket_arn,
                "inclusionPrefixes": [config.SOURCE_PREFIX]},
        },
        vectorIngestionConfiguration={
            "chunkingConfiguration": {
                "chunkingStrategy": "HIERARCHICAL",
                "hierarchicalChunkingConfiguration": {
                    "levelConfigurations": [
                        {"maxTokens": 1500}, {"maxTokens": 300}],
                    "overlapTokens": 60,
                },
            },
        },
    )
    ds_id = resp["dataSource"]["dataSourceId"]
    print(f"created data source: {ds_id}")
    return ds_id


# Start ingestion and poll until COMPLETE or FAILED.
def ingest(kb_id, ds_id):
    job = agent.start_ingestion_job(
        knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]
    job_id = job["ingestionJobId"]
    print(f"ingestion started: {job_id}")
    while True:
        job = agent.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id,
            ingestionJobId=job_id)["ingestionJob"]
        status = job["status"]
        if status in ("COMPLETE", "FAILED"):
            print(f"ingestion {status}: {job.get('statistics', {})}")
            return status
        print(f"ingestion {status}...")
        time.sleep(15)


def main(role_arn, collection_arn):
    kb_id = create_kb(role_arn, collection_arn)
    ds_id = create_data_source(kb_id)
    ingest(kb_id, ds_id)
    print(f"\nKB_ID={kb_id}\nDATA_SOURCE_ID={ds_id}")
    return kb_id


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2])  # KB role ARN, collection ARN
