"""
Setup script: provisions Glue Workflow + triggers for Phase 13.

Creates the workflow 'airbnb-etl-workflow' with three triggers:
  1. Schedule trigger  — fires at 02:00 UTC daily → starts Job 1 (Raw → Cleaned)
  2. Conditional trigger — Job 1 SUCCEEDED         → starts Job 2 (Cleaned → Dims)
  3. Conditional trigger — Job 2 SUCCEEDED         → starts Job 3 (Cleaned → Facts)

Run once from your local machine:
    cd airbnb-dw
    python setup_workflow.py

Re-running is idempotent: existing workflow/triggers are updated not recreated.

Prerequisites: Jobs 1, 2, 3 must already exist (run setup_glue_job1/2/3.py first).
"""

import boto3
from botocore.exceptions import ClientError

REGION = "ap-southeast-1"

WORKFLOW_NAME = "airbnb-etl-workflow"

JOB1 = "airbnb-raw-to-cleaned"
JOB2 = "airbnb-cleaned-to-dims"
JOB3 = "airbnb-cleaned-to-facts"

TRIGGER_SCHEDULE = "airbnb-workflow-schedule"      # cron → Job 1
TRIGGER_J1_TO_J2 = "airbnb-workflow-j1-to-j2"     # Job 1 SUCCEEDED → Job 2
TRIGGER_J2_TO_J3 = "airbnb-workflow-j2-to-j3"     # Job 2 SUCCEEDED → Job 3

session = boto3.Session(region_name=REGION)
glue    = session.client("glue")


def ensure_workflow():
    print(f"[1/4] Creating/updating workflow '{WORKFLOW_NAME}' ...")
    try:
        glue.get_workflow(Name=WORKFLOW_NAME)
        glue.update_workflow(
            Name=WORKFLOW_NAME,
            Description="Daily ETL pipeline: Raw → Cleaned → Dims → Facts (02:00 UTC)",
        )
        print(f"      Workflow '{WORKFLOW_NAME}' updated.")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise
        glue.create_workflow(
            Name=WORKFLOW_NAME,
            Description="Daily ETL pipeline: Raw → Cleaned → Dims → Facts (02:00 UTC)",
        )
        print(f"      Workflow '{WORKFLOW_NAME}' created.")


def _upsert_trigger(name, trigger_type, actions, schedule=None, predicate=None, start_on_creation=True):
    kwargs = dict(
        Name=name,
        WorkflowName=WORKFLOW_NAME,
        Type=trigger_type,
        Actions=actions,
        Description=f"Workflow trigger: {name}",
    )
    if schedule:
        kwargs["Schedule"] = schedule
    if predicate:
        kwargs["Predicate"] = predicate

    try:
        glue.get_trigger(Name=name)
        # update_trigger does not accept WorkflowName or Type — only TriggerUpdate body
        update_body = {"Actions": actions, "Description": kwargs["Description"]}
        if schedule:
            update_body["Schedule"] = schedule
        if predicate:
            update_body["Predicate"] = predicate
        glue.update_trigger(Name=name, TriggerUpdate=update_body)
        print(f"      Trigger '{name}' updated.")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityNotFoundException":
            raise
        if start_on_creation:
            kwargs["StartOnCreation"] = True
        glue.create_trigger(**kwargs)
        print(f"      Trigger '{name}' created.")


def ensure_triggers():
    print("[2/4] Creating/updating schedule trigger (02:00 UTC → Job 1) ...")
    _upsert_trigger(
        name=TRIGGER_SCHEDULE,
        trigger_type="SCHEDULED",
        schedule="cron(0 2 * * ? *)",
        actions=[{"JobName": JOB1}],
        start_on_creation=True,
    )

    print("[3/4] Creating/updating conditional trigger (Job 1 → Job 2) ...")
    _upsert_trigger(
        name=TRIGGER_J1_TO_J2,
        trigger_type="CONDITIONAL",
        predicate={
            "Logical": "ANY",
            "Conditions": [
                {
                    "LogicalOperator": "EQUALS",
                    "JobName": JOB1,
                    "State": "SUCCEEDED",
                }
            ],
        },
        actions=[{"JobName": JOB2}],
        start_on_creation=True,
    )

    print("[4/4] Creating/updating conditional trigger (Job 2 → Job 3) ...")
    _upsert_trigger(
        name=TRIGGER_J2_TO_J3,
        trigger_type="CONDITIONAL",
        predicate={
            "Logical": "ANY",
            "Conditions": [
                {
                    "LogicalOperator": "EQUALS",
                    "JobName": JOB2,
                    "State": "SUCCEEDED",
                }
            ],
        },
        actions=[{"JobName": JOB3}],
        start_on_creation=True,
    )


def verify_jobs_exist():
    print("  Verifying prerequisite jobs exist ...")
    missing = []
    for job in (JOB1, JOB2, JOB3):
        try:
            glue.get_job(JobName=job)
            print(f"    ✓ {job}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                missing.append(job)
                print(f"    ✗ {job} — NOT FOUND")
            else:
                raise
    if missing:
        print()
        print("  ERROR: Missing jobs — run the corresponding setup scripts first:")
        for job in missing:
            if job == JOB1:
                print("    python setup_glue_job1.py")
            elif job == JOB2:
                print("    python setup_glue_job2.py")
            elif job == JOB3:
                print("    python setup_glue_job3.py")
        raise SystemExit(1)


def main():
    print("=" * 60)
    print("  Airbnb DW — Glue Workflow Setup (Phase 13)")
    print("=" * 60)

    verify_jobs_exist()
    ensure_workflow()
    ensure_triggers()

    console = f"https://{REGION}.console.aws.amazon.com"
    print()
    print("=" * 60)
    print("  Setup complete.")
    print("=" * 60)
    print()
    print("  Workflow architecture:")
    print(f"    02:00 UTC (daily)")
    print(f"      └─ {TRIGGER_SCHEDULE} → {JOB1}")
    print(f"              └─ {TRIGGER_J1_TO_J2} → {JOB2}")
    print(f"                        └─ {TRIGGER_J2_TO_J3} → {JOB3}")
    print()
    print("  View in console:")
    print(f"    {console}/glue/home?region={REGION}#/etl/workflows")
    print()
    print("  Run the workflow immediately (test):")
    print(f"    aws glue start-workflow-run --name {WORKFLOW_NAME} --region {REGION}")
    print()
    print("  Check latest run status:")
    print(f"    aws glue get-workflow-run --name {WORKFLOW_NAME} --run-id $(")
    print(f"      aws glue list-workflow-runs --name {WORKFLOW_NAME} --region {REGION}")
    print(f"        --query \"Ids[0]\" --output text")
    print(f"    ) --region {REGION} --query \"Run.Statistics\"")
    print()
    print("  Activate / deactivate the schedule trigger:")
    print(f"    aws glue start-trigger --name {TRIGGER_SCHEDULE} --region {REGION}")
    print(f"    aws glue stop-trigger  --name {TRIGGER_SCHEDULE} --region {REGION}")
    print()


if __name__ == "__main__":
    main()
