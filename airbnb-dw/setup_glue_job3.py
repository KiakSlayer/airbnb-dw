"""
Setup script: provisions Glue ETL Job 3 (Cleaned → Facts + VADER).

IAM policy does NOT need updating — warehouse/ write was added in Phase 9.
The only new requirement is the --additional-python-modules job parameter
which installs vaderSentiment on each Glue worker at runtime.

Run once from your local machine (with venv active):
    cd airbnb-dw
    python setup_glue_job3.py

Or follow the printed console instructions.
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

SCRIPT_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glue_job3_cleaned_to_facts.py")
SCRIPT_KEY   = "glue-scripts/glue_job3_cleaned_to_facts.py"
SCRIPT_URI   = f"s3://{BUCKET}/{SCRIPT_KEY}"
JOB_NAME     = "airbnb-cleaned-to-facts"

JOB_CONFIG = dict(
    Name=JOB_NAME,
    Role=ROLE_ARN,
    Command={
        "Name": "glueetl",
        "ScriptLocation": SCRIPT_URI,
        "PythonVersion": "3",
    },
    DefaultArguments={
        "--job-language":             "python",
        "--job-bookmark-option":      "job-bookmark-disable",
        "--TempDir":                  f"s3://{BUCKET}/glue-temp/",
        "--enable-glue-datacatalog":  "true",
        "--additional-python-modules": "vaderSentiment",
    },
    GlueVersion="4.0",
    WorkerType="G.1X",
    NumberOfWorkers=4,   # More workers — fact_review VADER scoring is CPU-intensive
    Timeout=90,
    MaxRetries=0,
    Description="Phase 10: Cleaned Parquet → fact_listing_snapshot, fact_calendar, fact_review (VADER)",
)

CONSOLE_INSTRUCTIONS = f"""
╔══════════════════════════════════════════════════════════════╗
  MANUAL CONSOLE STEPS — Phase 10 (Cleaned → Facts + VADER)
╚══════════════════════════════════════════════════════════════╝

NO IAM CHANGES NEEDED — warehouse/ write was already added in Phase 9.

STEP 1 — Upload script to S3
  Console: S3 → {BUCKET} → glue-scripts/ → Upload
  File: {SCRIPT_LOCAL}

STEP 2 — Create Glue ETL job
  Console: Glue → ETL Jobs → Create job → Script editor
           → Upload script → select glue_job3_cleaned_to_facts.py

  Job details:
    Name:              {JOB_NAME}
    IAM Role:          {ROLE_NAME}
    Type:              Spark
    Glue version:      Glue 4.0
    Language:          Python 3
    Worker type:       G.1X
    Number of workers: 4         ← more than Jobs 1&2; VADER is CPU-heavy
    Timeout (min):     90
    Max retries:       0

  Advanced properties → Script path:
    {SCRIPT_URI}

  Advanced properties → Temporary path:
    s3://{BUCKET}/glue-temp/

  Job parameters (add ALL four):
    --job-bookmark-option       job-bookmark-disable
    --TempDir                   s3://{BUCKET}/glue-temp/
    --enable-glue-datacatalog   true
    --additional-python-modules vaderSentiment    ← installs VADER on workers

  Click Save, then Run.

STEP 3 — After job succeeds (~15–25 min), verify in S3:
  S3 → {BUCKET} → warehouse/
  Should now contain: fact_listing_snapshot/ fact_calendar/ fact_review/
                      dim_date/ dim_host/ dim_listing/ dim_location/

STEP 4 — Run the warehouse crawler:
  Glue → Crawlers → airbnb-crawler-warehouse → Run
  This catalogs all 7 tables for Athena + QuickSight (Jop's Phase 14).
"""


def main():
    print("=" * 60)
    print("  Airbnb DW — Glue Job 3 Setup (Cleaned → Facts)")
    print("=" * 60)

    try:
        session = boto3.Session(region_name=REGION)
        s3   = session.client("s3")
        glue = session.client("glue")

        print("[1/2] Uploading script ...")
        s3.upload_file(SCRIPT_LOCAL, BUCKET, SCRIPT_KEY)
        print(f"      OK — {SCRIPT_URI}")

        print(f"[2/2] Creating/updating Glue job '{JOB_NAME}' ...")
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

        print(f"\n  Run: aws glue start-job-run --job-name {JOB_NAME} --region {REGION}")

    except Exception as e:
        print(f"\n  Automated setup failed: {e}")
        print(CONSOLE_INSTRUCTIONS)


if __name__ == "__main__":
    main()
