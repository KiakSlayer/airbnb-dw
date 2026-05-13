"""
Setup script: provisions Athena workgroup for Phase 12 and triggers the
cleaned + warehouse Glue crawlers so their tables are queryable in Athena.

Run once from your local machine:
    cd airbnb-dw
    python setup_athena.py

Re-running is idempotent. After this script succeeds:
  1. Run the sample queries in athena_queries.sql via the Athena console
     (select workgroup "airbnb-analytics") or copy-paste into the query editor.
  2. Results land in s3://airbnb-dw-856480643132/athena-results/
"""

import time

import boto3
from botocore.exceptions import ClientError

REGION        = "ap-southeast-1"
ACCOUNT_ID    = "856480643132"
BUCKET        = "airbnb-dw-856480643132"
WORKGROUP     = "airbnb-analytics"
RESULTS_LOC   = f"s3://{BUCKET}/athena-results/"
CRAWLER_CLEANED   = "airbnb-crawler-cleaned"
CRAWLER_WAREHOUSE = "airbnb-crawler-warehouse"

session = boto3.Session(region_name=REGION)
athena  = session.client("athena")
glue    = session.client("glue")


def ensure_workgroup():
    print(f"[1/3] Creating/updating Athena workgroup '{WORKGROUP}' ...")
    config = {
        "ResultConfiguration": {
            "OutputLocation": RESULTS_LOC,
            "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"},
        },
        "PublishCloudWatchMetricsEnabled": False,
        "EnforceWorkGroupConfiguration": False,
    }
    try:
        athena.get_work_group(WorkGroup=WORKGROUP)
        athena.update_work_group(
            WorkGroup=WORKGROUP,
            ConfigurationUpdates={
                "ResultConfigurationUpdates": {
                    "OutputLocation": RESULTS_LOC,
                    "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"},
                },
                "PublishCloudWatchMetricsEnabled": False,
                "EnforceWorkGroupConfiguration": False,
            },
        )
        print(f"      Workgroup '{WORKGROUP}' updated.")
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidRequestException":
            raise
        athena.create_work_group(
            Name=WORKGROUP,
            Configuration=config,
            Description="Athena workgroup for Airbnb DW Phase 12 analytics",
        )
        print(f"      Workgroup '{WORKGROUP}' created.")
    print(f"      Query results → {RESULTS_LOC}")


def start_crawler_if_ready(name):
    try:
        resp = glue.get_crawler(Name=name)
        state = resp["Crawler"]["State"]
        if state == "RUNNING":
            print(f"        Already running: {name}")
            return
        glue.start_crawler(Name=name)
        print(f"        Started: {name}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "CrawlerRunningException":
            print(f"        Already running: {name}")
        elif code == "EntityNotFoundException":
            print(f"        Crawler not found: {name} — run setup_crawlers.py first")
        else:
            raise


def trigger_crawlers():
    print("[2/3] Triggering Glue crawlers for cleaned/ and warehouse/ zones ...")
    start_crawler_if_ready(CRAWLER_CLEANED)
    start_crawler_if_ready(CRAWLER_WAREHOUSE)
    print("      Crawlers started — tables will appear in Glue Data Catalog once complete (~1–2 min).")
    print("      Poll status:")
    print(f"        aws glue get-crawler --name {CRAWLER_CLEANED}   --region {REGION} --query \"Crawler.State\"")
    print(f"        aws glue get-crawler --name {CRAWLER_WAREHOUSE} --region {REGION} --query \"Crawler.State\"")


def print_instructions():
    console = f"https://{REGION}.console.aws.amazon.com"
    print("\n[3/3] Instructions for running sample queries ...")
    print()
    print("  Option A — Athena Console:")
    print(f"    {console}/athena/home?region={REGION}#/query-editor")
    print(f"    Select workgroup: {WORKGROUP}")
    print(f"    Database: airbnb_cleaned")
    print(f"    Copy-paste queries from: athena_queries.sql")
    print()
    print("  Option B — AWS CLI (one-shot query):")
    print(f"    aws athena start-query-execution \\")
    print(f"      --query-string \"SELECT city, COUNT(*) FROM airbnb_cleaned.listings GROUP BY city\" \\")
    print(f"      --work-group {WORKGROUP} \\")
    print(f"      --query-execution-context Database=airbnb_cleaned \\")
    print(f"      --region {REGION}")
    print()
    print("  Verify tables after crawlers finish:")
    print(f"    aws glue get-tables --database-name airbnb_cleaned   --region {REGION} --query \"TableList[].Name\"")
    print(f"    aws glue get-tables --database-name airbnb_warehouse  --region {REGION} --query \"TableList[].Name\"")
    print()
    print("  Expected tables in airbnb_cleaned:  listings, calendar, reviews")
    print("  Expected tables in airbnb_warehouse: dim_listing, dim_host, dim_location,")
    print("                                        dim_date, fact_listing_snapshot,")
    print("                                        fact_calendar, fact_review")
    print()


def main():
    print("=" * 60)
    print("  Airbnb DW — Athena Setup (Phase 12)")
    print("=" * 60)

    ensure_workgroup()
    trigger_crawlers()
    print_instructions()

    print("=" * 60)
    print("  Setup complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
