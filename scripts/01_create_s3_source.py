# Step 1: create the S3 source bucket and upload campus documents.
# Safe to re-run: an existing bucket is reused and files are re-uploaded (overwrite).

import os
import config

s3 = config.client("s3")


# Create the bucket if it does not already exist.
def ensure_bucket(name):
    existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if name in existing:
        print(f"bucket exists: {name}")
        return
    if config.REGION == "us-east-1":
        s3.create_bucket(Bucket=name)
    else:
        s3.create_bucket(
            Bucket=name,
            CreateBucketConfiguration={"LocationConstraint": config.REGION},
        )
    s3.put_public_access_block(
        Bucket=name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print(f"created bucket: {name}")


# Upload every file in the local docs folder under the sources/ prefix.
def upload_docs(bucket):
    if not os.path.isdir(config.DOCS_DIR):
        print(f"no local docs folder '{config.DOCS_DIR}' - add campus PDFs/MD there")
        return
    count = 0
    for fname in os.listdir(config.DOCS_DIR):
        path = os.path.join(config.DOCS_DIR, fname)
        if os.path.isfile(path):
            key = config.SOURCE_PREFIX + fname
            s3.upload_file(path, bucket, key)
            print(f"uploaded s3://{bucket}/{key}")
            count += 1
    print(f"uploaded {count} document(s)")


def main():
    bucket = config.source_bucket()
    ensure_bucket(bucket)
    upload_docs(bucket)
    print(f"\nSOURCE_BUCKET={bucket}")


if __name__ == "__main__":
    main()
