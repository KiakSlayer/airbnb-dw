# Airbnb Cross-City Analytics — Claude Working File

> This file is the primary briefing document for Claude Code sessions.
> README.md has the human-readable overview. This file has the operational detail.

---

## Rules for Updating This File

- **After every completed task:** add an entry to the Task Completion Log below.
- **After every session:** update "Current Status" to reflect what's done and what's next.
- **When a gotcha is discovered** (AWS quirk, library limitation, etc.): add it to Known Gotchas.
- **When a new script is added or removed:** update the **Scripts** table — this is the canonical index; README points here.
- **Do not duplicate README.md.** This file is for Claude, not for humans reading the repo.
- **Keep concise.** One line per concept where possible. Long explanations go in separate docs.

### When README.md needs updating
README is intentionally stable — most session work updates only this file. Touch README **only** when one of these changes:
- Team roster or score ownership (Team table)
- High-level architecture (medallion layers, BI tool)
- Cities or snapshot dates
- AWS account / region / bucket / RDS instance identifiers
- Quick Start prerequisites (new pip dep, new auth flow)

Per-phase scripts, AWS resource details, and gotchas all stay in CLAUDE.md — do NOT mirror them into README.

---

## Current Status (as of 2026-05-14)

**Kiak** — All deliverables complete ✅
**Sun** — Phase 10 done ✅; ⬜ Phase 18 unblocked after Phase 13 (Pluck's Workflow Scheduler)
**Pluck** — Phases 11–13 done ✅; ⬜ Phase 12 needs `python setup_athena.py` + crawler run to land tables before running queries
**Jop** — ⬜ Phase 14 (QuickSight) now unblocked; Phase 15–17 unblocked after Pluck runs setup_athena.py

### Phase Tracker

| Phase | Owner | Task | Status |
|-------|-------|------|--------|
| 1–6 | Kiak | Download, simulate, upload, RDS load | ✅ Done |
| Kiak-A | Kiak | Glue Python Shell job + daily Scheduler (Automation 1%) | ✅ Done 2026-05-08 |
| 7 | Pluck | S3 lake zones (raw/cleaned/warehouse) + Glue Crawlers | ✅ Done 2026-05-08 |
| 8 | Sun | Glue Job 1: Raw → Cleaned (Parquet, dedup, cast) | ✅ Done 2026-05-10 |
| 9 | Sun | Glue Job 2: Cleaned → Dimensions (SCD Type 2) | ✅ Done 2026-05-11 |
| 10 | Sun | Glue Job 3: Cleaned → Facts + VADER sentiment | ✅ Done 2026-05-11 |
| 11 | Pluck | Variety justification memo (5 format families) | ✅ Done 2026-05-14 |
| 12 | Pluck | Athena on cleaned zone + 5–10 sample queries | ✅ Done 2026-05-14 — run `python setup_athena.py` to activate |
| 13 | Pluck | Glue Workflow Scheduler: Job 1→2→3 at 02:00 UTC | ✅ Done 2026-05-14 — run `python setup_workflow.py` to activate |
| 14 | Jop | QuickSight connected to Athena/RDS | ⬜ Can start now |
| 15–17 | Jop | Dashboards 1–3 (Market · Pricing · Sentiment) | ⬜ Blocked by 12 |
| 18 | Sun | End-to-end pipeline test + row count validation | ⬜ Blocked by 13 |
| 19 | All | Record Video 1 (Kiak+Sun) and Video 2 (Pluck+Jop) | ⬜ Blocked by 18 |

---

## Task Completion Log

| Date | Person | Task | Notes |
|------|--------|------|-------|
| 2026-05-07 | Kiak | Phases 1–6 complete | Download, simulate, upload, RDS load |
| 2026-05-08 | Kiak | Glue job `airbnb-rds-to-s3-export` + daily trigger | S3 Bronze → source-exports, 8 partitions, 02:00 UTC schedule |
| 2026-05-08 | Pluck | Phase 7 — Glue Data Catalog: 4 DBs + 4 crawlers via `setup_crawlers.py` | Raw + source-exports crawlers ran SUCCEEDED; cleaned + warehouse crawlers deferred until Sun's data lands |
| 2026-05-10 | Sun | Phase 8 — Glue Job 1 `airbnb-raw-to-cleaned` | ETL Spark GlueVersion 4.0; all 8 city/snapshot pairs; listings/calendar/reviews → Parquet in cleaned/; run SUCCEEDED |
| 2026-05-11 | Sun | Phase 9 — Glue Job 2 `airbnb-cleaned-to-dims` | dim_listing + dim_host (SCD Type 2), dim_location (SCD Type 1), dim_date (generated); output verified in warehouse/ |
| 2026-05-11 | Sun | Phase 10 — Glue Job 3 `airbnb-cleaned-to-facts` | fact_listing_snapshot, fact_calendar, fact_review + VADER sentiment; IAM fix needed (warehouse/* GetObject missing) |
| 2026-05-14 | Pluck | Phase 11 — Variety memo | `variety_memo.md` — 5 format families: CSV.gz, Parquet, GeoJSON, PostgreSQL/RDS, embedded JSON arrays |
| 2026-05-14 | Pluck | Phase 12 — Athena setup + 10 sample queries | `setup_athena.py` (workgroup + crawler triggers) + `athena_queries.sql` (Q1–Q10 on airbnb_cleaned) |
| 2026-05-14 | Pluck | Phase 13 — Glue Workflow `airbnb-etl-workflow` | `setup_workflow.py` — schedule trigger (02:00 UTC) → Job 1 → Job 2 → Job 3; conditional triggers on SUCCEEDED |

---

## AWS Infrastructure

- **Account:** `856480643132` · **Region:** `ap-southeast-1`
- **S3 Bucket:** `airbnb-dw-856480643132`
- **Auth:** AWS SSO — `aws sso login --profile default`; check with `aws sts get-caller-identity`

### RDS

- **Instance:** `airbnb-source-db` (db.t3.micro, PostgreSQL 16.6)
- **Endpoint:** `airbnb-source-db.crw6s6ou8gww.ap-southeast-1.rds.amazonaws.com:5432`
- **DB / User:** `airbnb_source` / `airbnbadmin`
- **Password:** stored in AWS Secrets Manager — `airbnb/rds/airbnbadmin` (region ap-southeast-1). Retrieve with: `aws secretsmanager get-secret-value --secret-id airbnb/rds/airbnbadmin --region ap-southeast-1 --query SecretString --output text`
- **Security group:** `sg-0cc19604b360489bb` — port 5432 open. Add inbound rule if your IP changes:
  ```bash
  MY_IP=$(curl -s https://checkip.amazonaws.com)
  aws ec2 authorize-security-group-ingress --group-id sg-0cc19604b360489bb --protocol tcp --port 5432 --cidr "${MY_IP}/32" --region ap-southeast-1
  ```
- **Default state:** Stopped. Start before connecting: `aws rds start-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1`
- **Stop after use:** `aws rds stop-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1`
- **Takes ~4 min to start** (passes through `configuring-enhanced-monitoring` before `available`)

### Glue

- **Job (Kiak):** `airbnb-rds-to-s3-export` (Python Shell, GlueVersion 1.0) — RDS → source-exports
- **Job (Sun):** `airbnb-raw-to-cleaned` (ETL Spark, GlueVersion 4.0, G.1X × 2) — Raw CSV → Cleaned Parquet
- **Trigger:** `airbnb-rds-export-daily` — `cron(0 2 * * ? *)`, ACTIVATED (Kiak job only; Phase 13 will add workflow scheduler for Jobs 1–3)
- **IAM role:** `AWSGlueServiceRole-airbnb` — inline policy `AirbnbDWGlueS3Policy` (read raw/glue-scripts; list raw/source-exports/cleaned/warehouse/glue-temp; write source-exports + cleaned + glue-temp)
- **Scripts on S3:** `s3://airbnb-dw-856480643132/glue-scripts/glue_rds_export.py` · `glue_job1_raw_to_cleaned.py`

### Glue Data Catalog (Phase 7 — Pluck)

| Database | Source zone | Crawler | State |
|----------|-------------|---------|-------|
| `airbnb_raw` | `s3://.../raw/` | `airbnb-crawler-raw` | crawled ✅ — 1 table `raw` (8 partitions city/snapshot) |
| `airbnb_source_exports` | `s3://.../source-exports/` | `airbnb-crawler-source-exports` | crawled ✅ — 1 table `source_exports` (8 partitions) |
| `airbnb_cleaned` | `s3://.../cleaned/` | `airbnb-crawler-cleaned` | Run now — Phase 8 data landed ✅ |
| `airbnb_warehouse` | `s3://.../warehouse/` | `airbnb-crawler-warehouse` | READY — run after Phases 9–10 land data |

Run a deferred crawler manually: `aws glue start-crawler --name airbnb-crawler-cleaned --region ap-southeast-1`

### S3 Layout

```
s3://airbnb-dw-856480643132/
├── raw/            ← Bronze (Kiak) — Hive: city={city}/snapshot={YYYY-MM}/
├── cleaned/        ← Silver (Sun+Pluck) — Parquet, city/snapshot/{table}/
├── warehouse/      ← Gold (Sun+Pluck) — Parquet, {dim_or_fact}/{table}/
├── source-exports/ ← Glue job output — city={city}/snapshot={YYYY-MM}/listings.csv.gz
└── glue-scripts/   ← Glue Python Shell scripts
```

### S3 Bronze File Inventory

| City | Snapshot | listings | calendar | reviews | geojson |
|------|----------|----------|----------|---------|---------|
| bangkok | 2025-09 | 14.2 MiB | 23.9 MiB | 71.5 MiB | 1.8 MiB |
| bangkok | 2026-03 | 14.3 MiB | 25.1 MiB | 71.5 MiB | 1.8 MiB |
| lisbon | 2025-12 | 11.2 MiB | 21.2 MiB | 230.5 MiB | 4.1 MiB |
| lisbon | 2026-03 | 11.2 MiB | 22.2 MiB | 230.6 MiB | 4.1 MiB |
| singapore | 2025-09 | 1.3 MiB | 2.9 MiB | 4.3 MiB | 838 KiB |
| singapore | 2026-03 | 1.3 MiB | 3.1 MiB | 4.3 MiB | 838 KiB |
| tokyo | 2025-09 | 16.4 MiB | 23.1 MiB | 121.4 MiB | 100 KiB |
| tokyo | 2026-03 | 16.5 MiB | 24.2 MiB | 121.4 MiB | 100 KiB |

Total: 40 objects, ~1.1 GiB. Verify: `aws s3 ls s3://airbnb-dw-856480643132/raw/ --recursive --human-readable --summarize`

---

## Cities & Snapshots

| City | Snapshot 1 | Snapshot 2 |
|------|-----------|-----------|
| Bangkok | 2025-09 | 2026-03 |
| Singapore | 2025-09 | 2026-03 |
| Tokyo | 2025-09 | 2026-03 |
| Lisbon | **2025-12** | 2026-03 |

> Lisbon Snapshot 1 is 2025-12, NOT 2025-09. This trips up hardcoded snapshot lists.

---

## Data Quality Notes (ETL cleaning rules)

| Field | Raw format | Fix |
|-------|-----------|-----|
| `price` | `"$1,200.00"` | Strip `[\$,]`, cast to NUMERIC/FLOAT |
| `host_is_superhost` | `"t"` / `"f"` | Map to TRUE/FALSE |
| `host_response_rate` | `"95%"` | Strip `%`, cast to FLOAT |
| `host_acceptance_rate` | `"80%"` | Strip `%`, cast to FLOAT |
| `amenities` | JSON string | Parse as JSONB array |
| `host_verifications` | JSON string | Parse as JSONB array |

**Schema drift:** `host_profile_id` appears in Singapore CSVs only — normalise to fixed column list in ETL.

**SCD Type 2 pattern:** compare snapshot → expire changed rows (`effective_to = today`, `is_current = false`) → insert new version. Columns needed: `effective_from`, `effective_to`, `is_current`.

**SCD mutation rates (Snapshot 2 simulation, seed=42):**

| Column | Change rate | Notes |
|--------|-------------|-------|
| `price` | ~15% of rows | ±10–25% random delta |
| `host_is_superhost` | ~8% of rows | Status flip |
| `host_response_rate` | ~10% of rows | Drift ±5–15 pp |
| `room_type` | ~5% of rows | Category change |
| `name` | ~3% of rows | Appended `"[Renovated]"` suffix |

---

## Known Gotchas

### Glue Python Shell (GlueVersion 1.0)
- **No psycopg2 or pg8000** — neither is pre-installed; pip install via subprocess is also blocked
- **No `--additional-python-modules`** — only supported in GlueVersion 3.0+
- **GlueVersion "3.0" is invalid** for Python Shell in ap-southeast-1 — use `"1.0"`
- **`getResolvedOptions` fails** if any listed arg is absent from the job's DefaultArguments — either pass all args or skip it and hardcode constants
- **Pre-installed:** `boto3`, `pandas` (0.23.4), `numpy`, `scipy` — use these only

### boto3 / AWS CLI
- IAM `get_role` raises error code `"NoSuchEntity"` (not `"NoSuchEntityException"`) when role is missing
- Glue trigger methods: `start_trigger()` / `stop_trigger()` — NOT `activate_trigger`/`deactivate_trigger`
- Git Bash converts leading `/` paths to Windows paths — use PowerShell for AWS CLI calls with log group names like `/aws-glue/...`
- University SCP may block `iam:CreateRole` — `setup_glue_job.py` handles this with console instructions

### IAM Policy
- `warehouse/*` needs **both** `s3:GetObject` (read) AND `s3:PutObject`/`s3:DeleteObject` (write) — Jobs 2 and 3 write dims/facts to warehouse/, and Job 3 reads dims back. A write-only policy on warehouse/ causes `RESOURCE_NOT_FOUND_ERROR` when Job 3 tries to load dimensions. The final policy in `setup_glue_job2.py` / `setup_glue_job3.py` is correct — always use that as the source of truth.

### Glue Crawlers
- `update_crawler` takes **flat kwargs** (`Name=, Role=, Targets=, ...`) — NOT a nested `CrawlerUpdate` dict like `update_job`. Copy/pasting the job pattern raises `InvalidInputException`.
- `RecrawlBehavior=CRAWL_NEW_FOLDERS_ONLY` requires `SchemaChangePolicy.UpdateBehavior=LOG` AND `DeleteBehavior=LOG`. Only `CRAWL_EVERYTHING` accepts `UPDATE_IN_DATABASE`.
- `start_crawler` raises `CrawlerRunningException` if already running — catch it as a no-op rather than re-raise.
- **Merged-table heuristic:** when multiple file types (`listings.csv.gz`, `calendar.csv.gz`, `reviews.csv.gz`) share the same partition leaf prefix (`raw/city=X/snapshot=Y/`), Glue's default `CombineCompatibleSchemas` grouping unions them into ONE table with a 92-col superschema instead of 3 separate tables. Outcome: `airbnb_raw.raw` is the single merged table. **Mitigation for Phase 8:** in Glue Job 1, read each CSV explicitly by path (`connection_options={"paths": ["s3://.../listings.csv.gz", ...]}`) instead of relying on the catalog table — sidesteps the merged schema. The partition keys (`city`, `snapshot`) on the merged table are still useful for Athena WHERE filters.

---

## Scripts

| Script | Command | Purpose |
|--------|---------|---------|
| `download.py` | `python download.py` | Phase 1: download 16 raw files |
| `generate_snapshot2.py` | `python generate_snapshot2.py` | Phase 2: simulate SCD mutations |
| `upload_to_s3.py` | `python upload_to_s3.py` | Phase 3: upload Bronze to S3 |
| `load_rds.py` | `python load_rds.py` | Phase 5: load 4,000 rows into RDS |
| `glue_rds_export.py` | Deploy via `setup_glue_job.py` | Glue job script (S3 Bronze → source-exports) |
| `setup_glue_job.py` | `python setup_glue_job.py` | Provision/update Glue job + trigger (idempotent) |
| `setup_crawlers.py` | `python setup_crawlers.py` | Phase 7: provision 4 Glue DBs + 4 crawlers (idempotent); auto-runs raw + source-exports crawlers |
| `glue_job1_raw_to_cleaned.py` | Deploy via `setup_glue_job1.py` | Phase 8 Glue ETL script (Raw CSV → Cleaned Parquet, all cities/snapshots) |
| `setup_glue_job1.py` | `python setup_glue_job1.py` | Phase 8: provision Glue ETL job `airbnb-raw-to-cleaned` + update IAM policy for cleaned/ write |
| `glue_job2_cleaned_to_dims.py` | Deploy via `setup_glue_job2.py` | Phase 9 Glue ETL script (Cleaned → dim_listing, dim_host, dim_location, dim_date) |
| `setup_glue_job2.py` | `python setup_glue_job2.py` | Phase 9: provision Glue ETL job `airbnb-cleaned-to-dims` + update IAM for warehouse/ write |
| `glue_job3_cleaned_to_facts.py` | Deploy via `setup_glue_job3.py` | Phase 10 Glue ETL script (Cleaned → fact_listing_snapshot, fact_calendar, fact_review + VADER) |
| `setup_glue_job3.py` | `python setup_glue_job3.py` | Phase 10: provision Glue ETL job `airbnb-cleaned-to-facts` (no IAM changes needed) |
| `variety_memo.md` | — (document) | Phase 11: Big Data Variety justification — 5 format families |
| `setup_athena.py` | `python setup_athena.py` | Phase 12: create Athena workgroup `airbnb-analytics`, trigger cleaned+warehouse crawlers |
| `athena_queries.sql` | Paste into Athena console | Phase 12: 10 sample queries on airbnb_cleaned (listings/calendar/reviews) |
| `setup_workflow.py` | `python setup_workflow.py` | Phase 13: provision Glue Workflow `airbnb-etl-workflow` — Job 1→2→3 at 02:00 UTC |

All scripts run from `cd airbnb-dw`.

```bash
pip install pandas numpy boto3 psycopg2-binary openpyxl requests vaderSentiment
```

---

## Grading Weights

| Category | Weight | Owner |
|----------|--------|-------|
| Data Source | 2% | Kiak |
| DW & ETL | 4% | Sun |
| Big Data | 4% | Pluck |
| BI Dashboards | 4% | Jop |
| Automation | 1% | Kiak + Pluck |
| Presentation | 5% | All |
