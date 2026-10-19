# Step 2: create the OpenSearch Serverless collection and the vector index.
# Order matters: encryption + network + data-access policies, then the collection,
# then the knn vector index. The KB (step 4) depends on this index existing.

import json
import time

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

import config

aoss = config.client("opensearchserverless")


# Create the three AOSS policies the collection needs before it can be used.
def ensure_policies(role_arn):
    name = config.COLLECTION_NAME
    coll = f"collection/{name}"

    _put_policy(aoss.create_security_policy, "encryption", {
        "Rules": [{"ResourceType": "collection", "Resource": [coll]}],
        "AWSOwnedKey": True,
    })
    _put_policy(aoss.create_security_policy, "network", [{
        "Rules": [
            {"ResourceType": "collection", "Resource": [coll]},
            {"ResourceType": "dashboard", "Resource": [coll]},
        ],
        "AllowFromPublic": True,
    }])
    aoss_access = [{
        "Rules": [
            {"ResourceType": "collection", "Resource": [coll],
             "Permission": ["aoss:*"]},
            {"ResourceType": "index", "Resource": [f"index/{name}/*"],
             "Permission": ["aoss:*"]},
        ],
        "Principal": [role_arn, _caller_arn()],
    }]
    try:
        aoss.create_access_policy(name=f"{name}-access", type="data",
                                  policy=json.dumps(aoss_access))
    except aoss.exceptions.ConflictException:
        pass


def _put_policy(fn, kind, policy_doc):
    try:
        fn(name=f"{config.COLLECTION_NAME}-{kind}", type=kind,
           policy=json.dumps(policy_doc))
    except Exception as e:
        if "Conflict" not in type(e).__name__:
            raise


def _caller_arn():
    return boto3.client("sts", region_name=config.REGION).get_caller_identity()["Arn"]


# Create the collection and wait until it is ACTIVE, returning its endpoint + arn.
def ensure_collection():
    name = config.COLLECTION_NAME
    found = aoss.list_collections(
        collectionFilters={"name": name})["collectionSummaries"]
    if not found:
        aoss.create_collection(name=name, type="VECTORSEARCH")
        print(f"creating collection: {name}")

    while True:
        detail = aoss.batch_get_collection(names=[name])["collectionDetails"][0]
        if detail["status"] == "ACTIVE":
            print("collection ACTIVE")
            return detail["collectionEndpoint"], detail["arn"]
        print("waiting for collection...")
        time.sleep(15)


# Create the knn vector index whose fields match the KB field mapping.
def ensure_index(endpoint):
    host = endpoint.replace("https://", "")
    auth = AWSV4SignerAuth(
        boto3.Session().get_credentials(), config.REGION, "aoss")
    os_client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth, use_ssl=True, verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    body = {
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {
            config.VECTOR_FIELD: {
                "type": "knn_vector",
                "dimension": config.EMBED_DIMENSION,
                "method": {"name": "hnsw", "engine": "faiss",
                           "space_type": "l2"},
            },
            config.TEXT_FIELD: {"type": "text"},
            config.METADATA_FIELD: {"type": "text", "index": False},
        }},
    }
    if os_client.indices.exists(index=config.VECTOR_INDEX_NAME):
        print(f"index exists: {config.VECTOR_INDEX_NAME}")
    else:
        os_client.indices.create(index=config.VECTOR_INDEX_NAME, body=body)
        print(f"created index: {config.VECTOR_INDEX_NAME}")
        # AOSS index creation is eventually consistent; give it time before the KB uses it.
        time.sleep(60)


# role_arn is the KB service role (created in step 3) that must access the collection.
def main(role_arn):
    ensure_policies(role_arn)
    endpoint, arn = ensure_collection()
    ensure_index(endpoint)
    print(f"\nCOLLECTION_ARN={arn}")
    return arn


if __name__ == "__main__":
    import sys
    main(sys.argv[1])  # pass the KB role ARN printed by step 3
