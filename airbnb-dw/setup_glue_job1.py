"""
Setup script: provisions Glue ETL Job 1 (Raw → Cleaned) and updates the IAM inline
policy to grant the existing Glue role write access to the cleaned/ and glue-temp/ zones.

Run once from your local machine:
    cd airbnb-dw
    python setup_glue_job1.py

Re-running is idempotent: it updates existing resources rather than failing.
"""

import json
import os
import sys

import boto3
from botocore.exceptions import ClientError

REGION       = "ap-southeast-1"
ACCOUNT_ID   = "856480643132"
BUCKET       = "airbnb-dw-856480643132"
ROLE_NAME    = "AWSGlueServiceRole-airbnb"
ROLE_ARN     = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
POLICY_NAME  = "AirbnbDWGlueS3Policy"

SCRIPT_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glue_job1_raw_to_cleaned.py")
SCRIPT_KEY   = "glue-scripts/glue_job1_raw_to_cleaned.py"
SCRIPT_URI   = f"s3://{BUCKET}/{SCRIPT_KEY}"
JOB_NAME     = "airbnb-raw-to-cleaned"

session = boto3.Session(region_name=REGION)
s3      = session.client("s3")
glue    = session.client("glue")
iam     = session.client("iam")

# Updated policy: covers original job (source-exports write) + Job 1 (cleaned write + temp)
UPDATED_POLICY_DOC = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ReadSourceZones",
            "Effect": "Allow",
            "Action": ["s3:GetObject"],
            "Resource": [
                f"arn:aws:s3:::{BUCKET}/raw/*",
                f"arn:aws:s3:::{BUCKET}/glue-scripts/*",
            ],
        },
        {
            "Sid": "ListBucketScoped",
            "Effect": "Allow",
            "Action": ["s3:ListBucket"],
            "Resource": f"arn:aws:s3:::{BUCKET}",
            "Condition": {
                "StringLike": {
                    "s3:prefix": [
                        "raw/*",
                        "glue-scripts/*",
                        "source-exports/*",
                        "cleaned/*",
                        "warehouse/*",
                        "glue-temp/*",
                    ]
                }
            },
        },
        {
            "Sid": "WriteSourceExports",
            "Effect": "Allow",
            "Action": ["s3:PutObject"],
            "Resource": f"arn:aws:s3:::{BUCKET}/source-exports/*",
        },
        {
            "Sid": "WriteCleaned",
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:DeleteObject"],
            "Resource": f"arn:aws:s3:::{BUCKET}/cleaned/*",
        },
        {
            "Sid": "WriteGlueTemp",
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
            "Resource": f"arn:aws:s3:::{BUCKET}/glue-temp/*",
        },
    ],
})

MANUAL_POLICY_INSTRUCTIONS = f"""
----------------------------------------------------------------------
ACTION REQUIRED — IAM policy update failed (SCP likely blocking iam:PutRolePolicy)
----------------------------------------------------------------------
Add the following statements to the '{POLICY_NAME}' inline policy manually:

Console:
  IAM → Roles → {ROLE_NAME} → Permissions tab
  → {POLICY_NAME} → Edit → JSON → paste the two new statements → Save

Statements to add inside the "Statement" array:

  {{
    "Sid": "WriteCleaned",
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:DeleteObject"],
    "Resource": "arn:aws:s3:::{BUCKET}/cleaned/*"
  }},
  {{
    "Sid": "WriteGlueTemp",
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
    "Resource": "arn:aws:s3:::{BUCKET}/glue-temp/*"
  }},
  (also add "cleaned/*", "warehouse/*", "glue-temp/*" to the s3:prefix Condition
   in the existing ListBucketScoped statement)
----------------------------------------------------------------------
"""

JOB_CONFIG = dict(
    Name=JOB_NAME,
    Role=ROLE_ARN,
    Command={
        "Name": "glueetl",
        "ScriptLocation": SCRIPT_URI,
        "PythonVersion": "3",
    },
    DefaultArguments={
        "--job-language": "python",
        "--job-bookmark-option": "job-bookmark-disable",
        "--TempDir": f"s3://{BUCKET}/glue-temp/",
        "--enable-glue-datacatalog": "true",
    },
    GlueVersion="4.0",
    WorkerType="G.1X",
    NumberOfWorkers=2,
    Timeout=60,
    MaxRetries=0,
    Description="Phase 8: Raw CSV → Cleaned Parquet (dedup, type cast, schema normalise)",
)


def upload_script():
    print(f"[1/3] Uploading script to s3://{BUCKET}/{SCRIPT_KEY} ...")
    s3.upload_file(SCRIPT_LOCAL, BUCKET, SCRIPT_KEY)
    print(f"      OK — {SCRIPT_URI}")


def update_iam_policy():
    print(f"[2/3] Updating IAM inline policy '{POLICY_NAME}' on role '{ROLE_NAME}' ...")
    try:
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName=POLICY_NAME,
            PolicyDocument=UPDATED_POLICY_DOC,
        )
        print("      Policy updated: cleaned/ and glue-temp/ write access added.")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("AccessDenied", "UnauthorizedAccess", "AccessDeniedException"):
            print(MANUAL_POLICY_INSTRUCTIONS)
            print("      Continuing with job setup — fix IAM before running the job.")
        else:
            raise


def create_or_update_job():
    print(f"[3/3] Creating/updating Glue ETL job '{JOB_NAME}' ...")
    try:
        glue.get_job(JobName=JOB_NAME)
        update_args = {k: v for k, v in JOB_CONFIG.items() if k != "Name"}
        glue.update_job(JobName=JOB_NAME, JobUpdate=update_args)
        print("      Job updated.")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise
        glue.create_job(**JOB_CONFIG)
        print("      Job created.")


def main():
    print("=" * 60)
    print("  Airbnb DW — Glue Job 1 Setup (Raw → Cleaned)")
    print("=" * 60)

    upload_script()
    update_iam_policy()
    create_or_update_job()

    console = f"https://{REGION}.console.aws.amazon.com"
    print("\n" + "=" * 60)
    print("  Setup complete.")
    print("=" * 60)
    print(f"\n  To run the job immediately:")
    print(f"    aws glue start-job-run --job-name {JOB_NAME} --region {REGION}")
    print(f"\n  Monitor in console:")
    print(f"    {console}/glue/home?region={REGION}#/etl/jobs")
    print(f"\n  Check run status (replace <RUN_ID>):")
    print(f"    aws glue get-job-run --job-name {JOB_NAME} --run-id <RUN_ID> --region {REGION} --query \"JobRun.[JobRunState,ErrorMessage]\"")
    print(f"\n  After job succeeds — run the cleaned crawler:")
    print(f"    aws glue start-crawler --name airbnb-crawler-cleaned --region {REGION}")
    print()


if __name__ == "__main__":
    main()
