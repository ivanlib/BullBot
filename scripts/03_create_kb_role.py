# Step 3: create the IAM service role the Knowledge Base assumes.
# Grants model invocation (Titan V2), S3 read on the source bucket, and AOSS access.

import json
import time

import config

iam = config.client("iam")

ROLE_NAME = "AmazonBedrockExecutionRoleForKB-bullbot"


# Trust policy: only Bedrock can assume the role, scoped to this account's KBs.
def trust_policy(acct):
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": acct},
                "ArnLike": {"aws:SourceArn":
                            f"arn:aws:bedrock:{config.REGION}:{acct}:knowledge-base/*"},
            },
        }],
    }


# Inline permissions: embed model, S3 source read, AOSS collection access.
def permissions_policy(acct, bucket):
    model_arn = (f"arn:aws:bedrock:{config.REGION}::"
                 f"foundation-model/{config.EMBED_MODEL_ID}")
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["bedrock:ListFoundationModels"],
             "Resource": "*"},
            {"Effect": "Allow", "Action": ["bedrock:InvokeModel"],
             "Resource": [model_arn]},
            {"Effect": "Allow",
             "Action": ["s3:ListBucket", "s3:GetObject"],
             "Resource": [f"arn:aws:s3:::{bucket}",
                          f"arn:aws:s3:::{bucket}/*"]},
            {"Effect": "Allow", "Action": ["aoss:APIAccessAll"],
             "Resource": [f"arn:aws:aoss:{config.REGION}:{acct}:collection/*"]},
        ],
    }


def main():
    acct = config.account_id()
    bucket = config.source_bucket()
    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy(acct)),
            Description="BullBot Knowledge Base service role",
        )
        print(f"created role: {ROLE_NAME}")
        # New IAM roles are eventually consistent; wait before Bedrock assumes it.
        time.sleep(15)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"role exists: {ROLE_NAME}")

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="BullBotKBPermissions",
        PolicyDocument=json.dumps(permissions_policy(acct, bucket)),
    )
    arn = f"arn:aws:iam::{acct}:role/{ROLE_NAME}"
    print(f"\nKB_ROLE_ARN={arn}")
    return arn


if __name__ == "__main__":
    main()
