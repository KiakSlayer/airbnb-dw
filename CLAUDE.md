# Airbnb Cross-City Analytics — Claude Working File

> This file is the primary briefing document for Claude Code sessions.
> README.md has the human-readable overview. This file has the operational detail.

---

## Rules for Updating This File

- **After every completed task:** add an entry to the Task Completion Log below.
- **After every session:** update "Current Status" to reflect what's done and what's next.
- **When a gotcha is discovered** (AWS quirk, library limitation, etc.): add it to Known Gotchas.
- **Do not duplicate README.md.** This file is for Claude, not for humans reading the repo.
- **Keep concise.** One line per concept where possible. Long explanations go in separate docs.

---

## Current Status (as of 2026-05-08)

**Kiak** — All deliverables complete ✅
**Sun** — Phase 7 done (catalog ready); ⬜ Phase 8 unblocked — Glue Job 1 Raw → Cleaned
**Pluck** — Phase 7 done ✅; ⬜ Phase 11 (Variety memo) can start now
**Jop** — Still blocked on Phase 8

### Phase Tracker

| Phase | Owner | Task | Status |
|-------|-------|------|--------|
| 1–6 | Kiak | Download, simulate, upload, RDS load, handoff | ✅ Done |
| Kiak-A | Kiak | Glue Python Shell job + daily Scheduler (Automation 1%) | ✅ Done 2026-05-08 |
| 7 | Pluck | S3 lake zones (raw/cleaned/warehouse) + Glue Crawlers | ✅ Done 2026-05-08 |
| 8 | Sun | Glue Job 1: Raw → Cleaned (Parquet, dedup, cast) | ⬜ Next (unblocked) |
| 9 | Sun | Glue Job 2: Cleaned → Dimensions (SCD Type 2) | ⬜ Blocked by 8 |
| 10 | Sun | Glue Job 3: Cleaned → Facts + VADER sentiment | ⬜ Blocked by 9 |
| 11 | Pluck | Variety justification memo (5 format families) | ⬜ Can start now |
| 12 | Pluck | Athena on cleaned zone + 5–10 sample queries | ⬜ Blocked by 8 |
| 13 | Pluck | Glue Workflow Scheduler: Job 1→2→3 at 02:00 UTC | ⬜ Blocked by 10 |
| 14 | Jop | QuickSight connected to Athena/RDS | ⬜ Blocked by 8 |
| 15–17 | Jop | Dashboards 1–3 (Market · Pricing · Sentiment) | ⬜ Blocked by 12 |
| 18 | Sun | End-to-end pipeline test + row count validation | ⬜ Blocked by 13 |
| 19 | All | Record Video 1 (Kiak+Sun) and Video 2 (Pluck+Jop) | ⬜ Blocked by 18 |

---

## Task Completion Log

| Date | Person | Task | Notes |
|------|--------|------|-------|
| 2026-05-07 | Kiak | Phases 1–6 complete | Download, simulate, upload, RDS, handoff doc |
| 2026-05-08 | Kiak | Glue job `airbnb-rds-to-s3-export` + daily trigger | S3 Bronze → source-exports, 8 partitions, 02:00 UTC schedule |
| 2026-05-08 | Pluck | Phase 7 — Glue Data Catalog: 4 DBs + 4 crawlers via `setup_crawlers.py` | Raw + source-exports crawlers ran SUCCEEDED; cleaned + warehouse crawlers deferred until Sun's data lands |

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
- **Security group:** `sg-0cc19604b360489bb` — port 5432 open. Add new inbound rule if your IP changes.
- **Default state:** Stopped. Start before connecting: `aws rds start-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1`
- **Stop after use:** `aws rds stop-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1`
- **Takes ~4 min to start** (passes through `configuring-enhanced-monitoring` before `available`)

### Glue

- **Job:** `airbnb-rds-to-s3-export` (Python Shell, GlueVersion 1.0)
- **Trigger:** `airbnb-rds-export-daily` — `cron(0 2 * * ? *)`, ACTIVATED
- **IAM role:** `AWSGlueServiceRole-airbnb` — inline policy `AirbnbDWGlueS3Policy` (read raw/cleaned/warehouse/source-exports/glue-scripts; write source-exports only)
- **Script on S3:** `s3://airbnb-dw-856480643132/glue-scripts/glue_rds_export.py`

### Glue Data Catalog (Phase 7 — Pluck)

| Database | Source zone | Crawler | State |
|----------|-------------|---------|-------|
| `airbnb_raw` | `s3://.../raw/` | `airbnb-crawler-raw` | crawled ✅ — 1 table `raw` (8 partitions city/snapshot) |
| `airbnb_source_exports` | `s3://.../source-exports/` | `airbnb-crawler-source-exports` | crawled ✅ — 1 table `source_exports` (8 partitions) |
| `airbnb_cleaned` | `s3://.../cleaned/` | `airbnb-crawler-cleaned` | READY — run after Phase 8 lands data |
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
| `amenities` | JSON string | Parse as JSONB array |
| `host_verifications` | JSON string | Parse as JSONB array |

**Schema drift:** `host_profile_id` appears in Singapore CSVs only — normalise to fixed column list in ETL.

**SCD Type 2 pattern:** compare snapshot → expire changed rows (`effective_to = today`, `is_current = false`) → insert new version. Columns needed: `effective_from`, `effective_to`, `is_current`.

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
