"""
Setup script: provisions Glue Data Catalog databases and S3 crawlers for Phase 7.

Run once from your local machine:
    cd airbnb-dw
    python setup_crawlers.py

Re-running is idempotent: it updates existing databases and crawlers rather than
failing. The script also extends the existing inline IAM policy on
AWSGlueServiceRole-airbnb so crawlers can read all four S3 zones.

After provisioning, the script auto-starts only the raw and source-exports
crawlers. The cleaned and warehouse crawlers are deferred until Phase 8/9-10
produce data in those zones.
"""

import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION        = "ap-southeast-1"
ACCOUNT_ID    = "856480643132"
BUCKET        = "airbnb-dw-856480643132"
ROLE_NAME     = "AWSGlueServiceRole-airbnb"
ROLE_ARN      = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
INLINE_POLICY_NAME = "AirbnbDWGlueS3Policy"

DB_RAW             = "airbnb_raw"
DB_SOURCE_EXPORTS  = "airbnb_source_exports"
DB_CLEANED         = "airbnb_cleaned"
DB_WAREHOUSE       = "airbnb_warehouse"

CRAWLER_RAW             = "airbnb-crawler-raw"
CRAWLER_SOURCE_EXPORTS  = "airbnb-crawler-source-exports"
CRAWLER_CLEANED         = "airbnb-crawler-cleaned"
CRAWLER_WAREHOUSE       = "airbnb-crawler-warehouse"

session = boto3.Session(region_name=REGION)
glue    = session.client("glue")
iam     = session.client("iam")

# Expanded least-privilege S3 policy: read raw/, cleaned/, warehouse/,
# source-exports/, glue-scripts/; write to source-exports/ only.
INLINE_POLICY_DOC = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "GlueS3Read",
            "Effect": "Allow",
            "Action": ["s3:GetObject"],
            "Resource": [
                f"arn:aws:s3:::{BUCKET}/raw/*",
                f"arn:aws:s3:::{BUCKET}/cleaned/*",
                f"arn:aws:s3:::{BUCKET}/warehouse/*",
                f"arn:aws:s3:::{BUCKET}/source-exports/*",
                f"arn:aws:s3:::{BUCKET}/glue-scripts/*",
            ],
        },
        {
            "Sid": "GlueS3List",
            "Effect": "Allow",
            "Action": ["s3:ListBucket"],
            "Resource": f"arn:aws:s3:::{BUCKET}",
            "Condition": {
                "StringLike": {
                    "s3:prefix": [
                        "raw/*",
                        "cleaned/*",
                        "warehouse/*",
                        "source-exports/*",
                        "glue-scripts/*",
                    ]
                }
            },
        },
        {
            "Sid": "GlueS3Write",
            "Effect": "Allow",
            "Action": ["s3:PutObject"],
            "Resource": f"arn:aws:s3:::{BUCKET}/source-exports/*",
        },
    ],
})

MANUAL_POLICY_INSTRUCTIONS = f"""
----------------------------------------------------------------------
ACTION REQUIRED — IAM inline policy must be applied manually
----------------------------------------------------------------------
Your account blocks iam:PutRolePolicy via SCP.
Apply the expanded inline policy through the AWS Console:

  1. Go to: https://console.aws.amazon.com/iam/home#/roles/{ROLE_NAME}
  2. Permissions tab -> Add permissions -> Create inline policy
  3. Switch to JSON view and paste the policy printed below
  4. Name it: {INLINE_POLICY_NAME}
  5. Click "Create policy"

Policy JSON to paste:
{INLINE_POLICY_DOC}
----------------------------------------------------------------------
"""


DATABASES = [
    (DB_RAW,            "Bronze zone — raw downloaded Inside Airbnb CSVs partitioned by city/snapshot."),
    (DB_SOURCE_EXPORTS, "Source exports — Glue job output of RDS source_listings, partitioned by city/snapshot."),
    (DB_CLEANED,        "Silver zone — cleaned Parquet outputs from Glue Job 1."),
    (DB_WAREHOUSE,      "Gold zone — dimensional model (dims + facts) from Glue Jobs 2 and 3."),
]


def _crawler_config(database, s3_path, exclusions, recrawl, description):
    # Glue API constraint: CRAWL_NEW_FOLDERS_ONLY requires both UpdateBehavior
    # and DeleteBehavior = LOG. Only CRAWL_EVERYTHING accepts UPDATE_IN_DATABASE.
    if recrawl == "CRAWL_NEW_FOLDERS_ONLY":
        schema_policy = {"UpdateBehavior": "LOG", "DeleteBehavior": "LOG"}
    else:
        schema_policy = {"UpdateBehavior": "UPDATE_IN_DATABASE", "DeleteBehavior": "LOG"}
    return {
        "Role": ROLE_ARN,
        "DatabaseName": database,
        "Targets": {"S3Targets": [{"Path": s3_path, "Exclusions": exclusions}]},
        "SchemaChangePolicy": schema_policy,
        "Configuration": json.dumps({
            "Version": 1.0,
            "CrawlerOutput": {
                "Partitions": {"AddOrUpdateBehavior": "InheritFromTable"},
                "Tables": {"AddOrUpdateBehavior": "MergeNewColumns"},
            },
            "Grouping": {"TableGroupingPolicy": "CombineCompatibleSchemas"},
        }),
        "RecrawlPolicy": {"RecrawlBehavior": recrawl},
        "Description": description,
    }


CRAWLERS = [
    (
        CRAWLER_RAW,
        _crawler_config(
            database=DB_RAW,
            s3_path=f"s3://{BUCKET}/raw/",
            exclusions=["**/.keep", "**/*.geojson"],
            recrawl="CRAWL_EVERYTHING",
            description="Catalog raw Inside Airbnb CSVs in the Bronze zone (city/snapshot partitions).",
        ),
    ),
    (
        CRAWLER_SOURCE_EXPORTS,
        _crawler_config(
            database=DB_SOURCE_EXPORTS,
            s3_path=f"s3://{BUCKET}/source-exports/",
            exclusions=["**/.keep"],
            recrawl="CRAWL_NEW_FOLDERS_ONLY",
            description="Catalog daily RDS source-export files produced by airbnb-rds-to-s3-export.",
        ),
    ),
    (
        CRAWLER_CLEANED,
        _crawler_config(
            database=DB_CLEANED,
            s3_path=f"s3://{BUCKET}/cleaned/",
            exclusions=["**/.keep"],
            recrawl="CRAWL_NEW_FOLDERS_ONLY",
            description="Catalog cleaned Parquet outputs in the Silver zone (Phase 8).",
        ),
    ),
    (
        CRAWLER_WAREHOUSE,
        _crawler_config(
            database=DB_WAREHOUSE,
            s3_path=f"s3://{BUCKET}/warehouse/",
            exclusions=["**/.keep"],
            recrawl="CRAWL_NEW_FOLDERS_ONLY",
            description="Catalog dimensional model Parquet outputs in the Gold zone (Phases 9-10).",
        ),
    ),
]


def ensure_iam_policy_extended():
    print(f"[1/3] Applying expanded inline policy '{INLINE_POLICY_NAME}' to '{ROLE_NAME}' ...")
    try:
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName=INLINE_POLICY_NAME,
            PolicyDocument=INLINE_POLICY_DOC,
        )
        print(f"      Inline policy applied (scoped to {BUCKET}, all four zones).")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("AccessDenied", "UnauthorizedAccess", "AccessDeniedException"):
            print(MANUAL_POLICY_INSTRUCTIONS)
            sys.exit(1)
        raise
    print("      Waiting 5 s for IAM propagation ...")
    time.sleep(5)


def ensure_databases():
    print(f"[2/3] Ensuring {len(DATABASES)} Glue Data Catalog databases ...")
    for name, description in DATABASES:
        try:
            glue.get_database(Name=name)
            print(f"      Database '{name}' already exists.")
            continue
        except ClientError as e:
            if e.response["Error"]["Code"] != "EntityNotFoundException":
                raise
        try:
            glue.create_database(DatabaseInput={"Name": name, "Description": description})
            print(f"      Created database '{name}'.")
        except ClientError as e:
            if e.response["Error"]["Code"] == "AlreadyExistsException":
                print(f"      Database '{name}' already exists (race) — no-op.")
                continue
            raise


def ensure_crawlers():
    print(f"[3/3] Creating/updating {len(CRAWLERS)} Glue crawlers ...")
    for name, config in CRAWLERS:
        try:
            glue.get_crawler(Name=name)
            # update_crawler takes flat kwargs (Name, Role, Targets, ...) — NOT
            # a nested CrawlerUpdate dict like update_job uses.
            glue.update_crawler(Name=name, **config)
            print(f"      Crawler '{name}' updated.")
        except ClientError as e:
            if e.response["Error"]["Code"] != "EntityNotFoundException":
                raise
            glue.create_crawler(Name=name, **config)
            print(f"      Crawler '{name}' created.")

    print()
    print("      Auto-starting crawlers for zones that already have data:")
    for name in (CRAWLER_RAW, CRAWLER_SOURCE_EXPORTS):
        try:
            glue.start_crawler(Name=name)
            print(f"        Started: {name}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "CrawlerRunningException":
                print(f"        Already running: {name}")
                continue
            raise
    print("      Note: '{0}' and '{1}' are deferred until Phase 8/9-10 produce data.".format(
        CRAWLER_CLEANED, CRAWLER_WAREHOUSE
    ))


def main():
    print("=" * 60)
    print("  Airbnb DW — Glue Crawlers Setup")
    print("=" * 60)

    ensure_iam_policy_extended()
    ensure_databases()
    ensure_crawlers()

    console_base = "https://ap-southeast-1.console.aws.amazon.com"
    print("\n" + "=" * 60)
    print("  Setup complete. Useful links:")
    print("=" * 60)
    print("  Data Catalog databases:")
    print(f"    {console_base}/glue/home?region={REGION}#/catalog/databases")
    print("  Crawlers:")
    print(f"    {console_base}/glue/home?region={REGION}#/catalog/crawlers")
    print(f"  Tables in {DB_RAW}:")
    print(f"    {console_base}/glue/home?region={REGION}#/catalog/tables?database={DB_RAW}")
    print()
    print("  Verify resources:")
    print(f"    aws glue get-database --name {DB_RAW} --region {REGION}")
    print(f"    aws glue get-crawler  --name {CRAWLER_RAW} --region {REGION}")
    print(f"    aws glue get-tables   --database-name {DB_RAW} --region {REGION} --query \"TableList[].Name\"")
    print()
    print("  Run a crawler manually:")
    print(f"    aws glue start-crawler --name {CRAWLER_CLEANED} --region {REGION}")
    print()
    print("  Poll status:")
    print(f"    aws glue get-crawler --name {CRAWLER_RAW} --region {REGION} --query \"Crawler.State\"")
    print()


if __name__ == "__main__":
    main()
