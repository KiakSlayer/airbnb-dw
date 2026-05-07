"""
Setup script: provisions the Glue Python Shell job and daily Scheduler trigger.

Run once from your local machine:
    cd airbnb-dw
    python setup_glue_job.py

Re-running is idempotent: it updates existing resources rather than failing.
"""

import json
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION        = "ap-southeast-1"
ACCOUNT_ID    = "856480643132"
BUCKET        = "airbnb-dw-856480643132"
SCRIPT_LOCAL  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glue_rds_export.py")
SCRIPT_S3_KEY = "glue-scripts/glue_rds_export.py"
SCRIPT_S3_URI = f"s3://{BUCKET}/{SCRIPT_S3_KEY}"
JOB_NAME      = "airbnb-rds-to-s3-export"
TRIGGER_NAME  = "airbnb-rds-export-daily"
ROLE_NAME     = "AWSGlueServiceRole-airbnb"
ROLE_ARN      = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
CRON_SCHEDULE = "cron(0 2 * * ? *)"  # 02:00 UTC daily

RDS_HOST  = "airbnb-source-db.crw6s6ou8gww.ap-southeast-1.rds.amazonaws.com"
RDS_PORT  = "5432"
RDS_DB    = "airbnb_source"
RDS_USER  = "airbnbadmin"
RDS_PASS  = "REDACTED"
S3_PREFIX = "source-exports"

session = boto3.Session(region_name=REGION)
s3      = session.client("s3")
glue    = session.client("glue")
iam     = session.client("iam")

TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "glue.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
})

MANAGED_POLICIES = [
    "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
]

MANUAL_ROLE_INSTRUCTIONS = f"""
----------------------------------------------------------------------
ACTION REQUIRED — IAM Role must be created manually
----------------------------------------------------------------------
Your university account blocks iam:CreateRole via SCP.
Create the role through the AWS Console:

  1. Go to: https://console.aws.amazon.com/iam/home#/roles
  2. Click "Create role"
  3. Trusted entity type: AWS service -> Glue
  4. Add these managed policies:
       - AWSGlueServiceRole
       - AmazonS3FullAccess
  5. Role name: {ROLE_NAME}
  6. Click "Create role"

Then re-run:
    python setup_glue_job.py
----------------------------------------------------------------------
"""


def upload_script():
    print(f"[1/4] Uploading script to s3://{BUCKET}/{SCRIPT_S3_KEY} ...")
    s3.upload_file(SCRIPT_LOCAL, BUCKET, SCRIPT_S3_KEY)
    print(f"      OK — {SCRIPT_S3_URI}")


def ensure_iam_role():
    print(f"[2/4] Checking IAM role '{ROLE_NAME}' ...")
    try:
        iam.get_role(RoleName=ROLE_NAME)
        print("      Role already exists — OK")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntityException" and \
                e.response["Error"]["Code"] != "NoSuchEntity":
            raise

    print(f"      Role not found. Attempting to create '{ROLE_NAME}' ...")
    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=TRUST_POLICY,
            Description="Glue service role for Airbnb DW project",
        )
        for policy_arn in MANAGED_POLICIES:
            iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy_arn)
            print(f"      Attached: {policy_arn}")
        print("      Role created. Waiting 15 s for IAM propagation ...")
        time.sleep(15)
    except ClientError as create_err:
        code = create_err.response["Error"]["Code"]
        if code in ("AccessDenied", "UnauthorizedAccess", "AccessDeniedException"):
            print(MANUAL_ROLE_INSTRUCTIONS)
            sys.exit(1)
        raise


JOB_DEFAULT_ARGS = {
    "--enable-job-insights": "false",
}

JOB_CONFIG = dict(
    Name=JOB_NAME,
    Role=ROLE_ARN,
    Command={
        "Name": "pythonshell",
        "ScriptLocation": SCRIPT_S3_URI,
        "PythonVersion": "3",
    },
    DefaultArguments=JOB_DEFAULT_ARGS,
    MaxCapacity=0.0625,
    GlueVersion="1.0",
    Timeout=30,
    Description="Export source_listings from RDS to S3 source-exports zone, partitioned by city/snapshot.",
)


def create_or_update_job():
    print(f"[3/4] Creating/updating Glue job '{JOB_NAME}' ...")
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


def create_or_update_trigger():
    print(f"[4/4] Creating/updating Glue trigger '{TRIGGER_NAME}' ...")
    try:
        existing = glue.get_trigger(Name=TRIGGER_NAME)
        state = existing["Trigger"]["State"]
        print(f"      Trigger already exists (state: {state}).")
        if state == "ACTIVATED":
            print("      Stopping for update ...")
            glue.stop_trigger(Name=TRIGGER_NAME)
        glue.update_trigger(
            Name=TRIGGER_NAME,
            TriggerUpdate={
                "Schedule": CRON_SCHEDULE,
                "Actions": [{"JobName": JOB_NAME}],
                "Description": "Daily 02:00 UTC export of RDS source_listings to S3",
            },
        )
        glue.start_trigger(Name=TRIGGER_NAME)
        print("      Trigger updated and activated.")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise
        glue.create_trigger(
            Name=TRIGGER_NAME,
            Type="SCHEDULED",
            Schedule=CRON_SCHEDULE,
            Actions=[{"JobName": JOB_NAME}],
            Description="Daily 02:00 UTC export of RDS source_listings to S3",
            StartOnCreation=True,
        )
        print("      Trigger created and activated.")


def main():
    print("=" * 60)
    print("  Airbnb DW — Glue Job Setup")
    print("=" * 60)

    upload_script()
    ensure_iam_role()
    create_or_update_job()
    create_or_update_trigger()

    console_base = "https://ap-southeast-1.console.aws.amazon.com"
    print("\n" + "=" * 60)
    print("  Setup complete. Useful links:")
    print("=" * 60)
    print(f"  Glue job console:")
    print(f"    {console_base}/glue/home?region={REGION}#/etl/jobs/scriptJob?jobName={JOB_NAME}")
    print(f"  Glue triggers console:")
    print(f"    {console_base}/glue/home?region={REGION}#/etl/triggers/schedule")
    print(f"  Script on S3:")
    print(f"    {SCRIPT_S3_URI}")
    print(f"  Output zone:")
    print(f"    s3://{BUCKET}/{S3_PREFIX}/")
    print()
    print("  To run the job immediately (one-off test):")
    print(f"    aws glue start-job-run --job-name {JOB_NAME} --region {REGION}")
    print()
    print("  To check last run status (replace <RUN_ID>):")
    print(f"    aws glue get-job-run --job-name {JOB_NAME} --run-id <RUN_ID> --region {REGION} --query \"JobRun.JobRunState\"")
    print()


if __name__ == "__main__":
    main()
