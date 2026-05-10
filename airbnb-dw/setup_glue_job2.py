"""
Setup script: provisions Glue ETL Job 2 (Cleaned → Dimensions).

Since AWS CLI / IAM may be unavailable, this script prints console instructions
for all steps that require AWS access.

Run once from your local machine (with venv active):
    cd airbnb-dw
    python setup_glue_job2.py

Or follow the printed console instructions to do it manually.
"""

import json
import os
import sys

import boto3
from botocore.exceptions import ClientError

REGION     = "ap-southeast-1"
ACCOUNT_ID = "856480643132"
BUCKET     = "airbnb-dw-856480643132"
ROLE_NAME  = "AWSGlueServiceRole-airbnb"
ROLE_ARN   = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
POLICY_NAME = "AirbnbDWGlueS3Policy"

SCRIPT_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glue_job2_cleaned_to_dims.py")
SCRIPT_KEY   = "glue-scripts/glue_job2_cleaned_to_dims.py"
SCRIPT_URI   = f"s3://{BUCKET}/{SCRIPT_KEY}"
JOB_NAME     = "airbnb-cleaned-to-dims"

# Full updated policy — adds warehouse/ write on top of Phase 8 policy
UPDATED_POLICY_DOC = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ReadSourceZones",
            "Effect": "Allow",
            "Action": ["s3:GetObject"],
            "Resource": [
                f"arn:aws:s3:::{BUCKET}/raw/*",
                f"arn:aws:s3:::{BUCKET}/cleaned/*",
                f"arn:aws:s3:::{BUCKET}/warehouse/*",
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
                        "raw/*", "cleaned/*", "warehouse/*",
                        "source-exports/*", "glue-scripts/*", "glue-temp/*",
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
            "Sid": "WriteWarehouse",
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:DeleteObject"],
            "Resource": f"arn:aws:s3:::{BUCKET}/warehouse/*",
        },
        {
            "Sid": "WriteGlueTemp",
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
            "Resource": f"arn:aws:s3:::{BUCKET}/glue-temp/*",
        },
    ],
})

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
    Description="Phase 9: Cleaned Parquet → Dimension tables with SCD Type 2",
)

CONSOLE_INSTRUCTIONS = f"""
╔══════════════════════════════════════════════════════════════╗
  MANUAL CONSOLE STEPS — Phase 9 (Cleaned → Dimensions)
╚══════════════════════════════════════════════════════════════╝

STEP 1 — Update IAM policy (add warehouse/ write access)
  Console: IAM → Roles → {ROLE_NAME}
           → Permissions tab → {POLICY_NAME} → Edit → JSON
  Paste the full policy below, then Save:

{UPDATED_POLICY_DOC}

STEP 2 — Upload script to S3
  Console: S3 → {BUCKET} → glue-scripts/ → Upload
  File: {SCRIPT_LOCAL}

STEP 3 — Create Glue ETL job
  Console: Glue → ETL Jobs → Create job → Script editor → Create
  Paste the script content, then set Job details:

    Name:              {JOB_NAME}
    IAM Role:          {ROLE_NAME}
    Type:              Spark
    Glue version:      Glue 4.0
    Language:          Python 3
    Worker type:       G.1X
    Number of workers: 2
    Timeout (min):     60
    Max retries:       0

  Advanced properties → Script path:
    {SCRIPT_URI}

  Advanced properties → Job parameters (add each):
    --job-bookmark-option   job-bookmark-disable
    --TempDir               s3://{BUCKET}/glue-temp/

  Click Save, then Run.

STEP 4 — After job succeeds, run the warehouse crawler:
  Glue → Crawlers → airbnb-crawler-warehouse → Run
"""


def main():
    print("=" * 60)
    print("  Airbnb DW — Glue Job 2 Setup (Cleaned → Dimensions)")
    print("=" * 60)

    # Try automated path first; fall back to console instructions
    try:
        session = boto3.Session(region_name=REGION)
        s3   = session.client("s3")
        glue = session.client("glue")
        iam  = session.client("iam")

        print("[1/3] Uploading script ...")
        s3.upload_file(SCRIPT_LOCAL, BUCKET, SCRIPT_KEY)
        print(f"      OK — {SCRIPT_URI}")

        print("[2/3] Updating IAM policy ...")
        try:
            iam.put_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME,
                                PolicyDocument=UPDATED_POLICY_DOC)
            print("      Policy updated: warehouse/ write access added.")
        except ClientError as e:
            if e.response["Error"]["Code"] in ("AccessDenied", "UnauthorizedAccess", "AccessDeniedException"):
                print("      IAM update blocked — follow console instructions printed below.")
            else:
                raise

        print(f"[3/3] Creating/updating Glue job '{JOB_NAME}' ...")
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

        print("\n" + "=" * 60)
        print(f"  Setup complete.")
        print(f"  Run: aws glue start-job-run --job-name {JOB_NAME} --region {REGION}")

    except Exception as e:
        print(f"\n  Automated setup failed: {e}")
        print(CONSOLE_INSTRUCTIONS)


if __name__ == "__main__":
    main()
