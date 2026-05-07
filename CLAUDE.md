# Airbnb Cross-City Analytics — Data Warehouse Project

## Project Overview

University group project building an **Airbnb Cross-City Analytics Data Warehouse** on AWS.
Architecture: S3 Medallion (Bronze/Silver/Gold) + RDS PostgreSQL (source DB) + Glue ETL + QuickSight.

**Grading weights:** Data Source 2% · DW & ETL 4% · Big Data 4% · BI Dashboards 4% · Automation 1% · Presentation 5%

---

## Team

| Person | Role | Primary Score Ownership |
|--------|------|------------------------|
| **Kiak** | Data Engineer / Source DB Lead | Data Source (2%) + Automation (1%) |
| **Sun** | ETL Engineer / DW Designer | DW & ETL (4%) |
| **Pluck** | Big Data / Lake Architect | Big Data (4%) + Automation support |
| **Jop** | BI Analyst / QuickSight Lead | BI Dashboards (4%) |

**Presentation (5%) is shared:** Kiak + Sun record Video 1 · Pluck + Jop record Video 2.

---

## Full Phase Tracker

| Phase | Owner | Description | Depends On | Status |
|-------|-------|-------------|------------|--------|
| 1 | Kiak | Download Snapshot 1 from Inside Airbnb (16 files) | — | ✅ Done |
| 2 | Kiak | Generate Snapshot 2 — simulate 6-month drift (SCD Type 2 prep) | Phase 1 | ✅ Done |
| 3 | Kiak | Upload all raw files to S3 with Hive partitioning | Phase 2 | ✅ Done |
| 4 | Kiak | Provision RDS PostgreSQL (db.t3.micro, ap-southeast-1) | — | ✅ Done |
| 5 | Kiak | Run `load_rds.py` — load 1,000 rows/city into `source_listings` | Phase 4 | ✅ Done |
| 6 | Kiak | Write handoff doc for Sun; stop RDS overnight | Phase 5 | ✅ Done |
| 7 | Pluck | Set up three S3 zones (raw/cleaned/warehouse) + Glue Crawlers on raw | Phase 3 | ⬜ Next |
| 8 | Sun | Glue Job 1 — Raw → Cleaned (Parquet, dedup, type cast) | Phase 7 | ⬜ Blocked by Phase 7 |
| 9 | Sun | Glue Job 2 — Cleaned → Dimensions with SCD Type 2 logic | Phase 8 | ⬜ Blocked by Phase 8 |
| 10 | Sun | Glue Job 3 — Cleaned → Fact tables (calendar + review + VADER sentiment) | Phase 9 | ⬜ Blocked by Phase 9 |
| 11 | Pluck | Write Variety justification memo (5 format families, 1-page) | Phase 3 | ⬜ Can start now |
| 12 | Pluck | Configure Athena on cleaned zone; write 5–10 sample queries | Phase 8 | ⬜ Blocked by Phase 8 |
| 13 | Pluck | Build Glue Workflow chaining Job 1 → 2 → 3 with Scheduler (02:00 UTC) | Phase 10 | ⬜ Blocked by Phase 10 |
| 14 | Jop | Configure QuickSight + connect to Athena / RDS DW | Phase 8 | ⬜ Blocked by Phase 8 |
| 15 | Jop | Dashboard 1 — Market Overview (KPI tiles + map + bar charts) | Phase 12 | ⬜ Blocked by Phase 12 |
| 16 | Jop | Dashboard 2 — Pricing & Availability Dynamics (heatmap + histograms) | Phase 15 | ⬜ Blocked by Phase 15 |
| 17 | Jop | Dashboard 3 — Host Quality & Sentiment | Phase 10 | ⬜ Blocked by Phase 10 |
| 18 | Sun | End-to-end pipeline test + row count validation | Phase 13 | ⬜ Blocked by Phase 13 |
| 19 | All | Record Video 1 (Kiak + Sun) and Video 2 (Pluck + Jop) | Phase 18 | ⬜ Blocked by Phase 18 |

---

## Critical Handoffs

| Handoff | From → To | Unblocks | Risk if Missed |
|---------|-----------|----------|----------------|
| Raw S3 data ready | Kiak → Sun & Pluck | Glue Job 1, Crawler setup | Sun can't start ETL |
| Cleaned Parquet ready | Sun → Pluck | Athena setup, lake validation | Pluck can't validate lake |
| Warehouse tables queryable | Sun → Jop | Dashboards 1–3 on real data | Jop stuck on placeholder data |
| Pipeline runs end-to-end via Scheduler | Pluck → Everyone | Automation demo | No automation score |
| All frozen — pipeline + dashboards finalized | All → All | Video recording | Recording delays cascade |

---

## Deliverables by Person

### Kiak — Data Engineer / Source DB Lead ✅ Complete

| Deliverable | Status |
|-------------|--------|
| Ingestion scripts (download, simulate, upload) | ✅ Done |
| S3 raw zone with Hive partitioning `/raw/city=X/snapshot=Y/` | ✅ Done |
| RDS PostgreSQL `source_listings` (4,000 rows — 1,000/city) | ✅ Done |
| Source-system architecture diagram (SVG + PNG) | ✅ Done |
| Data dictionary document | ✅ Done |
| Handoff doc for Sun | ✅ Done |
| Glue Python Shell job + Scheduler (Automation 1%) | ⬜ Remaining |

### Sun — ETL Engineer / DW Designer

| Deliverable | Status |
|-------------|--------|
| Star schema DDL (dim + fact CREATE TABLE statements) | ⬜ |
| Conformed bus matrix document | ⬜ |
| Glue Job 1: Raw → Cleaned (Parquet, dedup, type cast) | ⬜ |
| Glue Job 2: Cleaned → Dimensions (SCD Type 2 for listing + host) | ⬜ |
| Glue Job 3: Cleaned → Facts (calendar + reviews + VADER sentiment) | ⬜ |
| ETL architecture diagram | ⬜ |

> **SCD Type 2 pattern:** compare new snapshot → expire changed rows (`effective_to = today`, `is_current = false`) → insert new versions. Columns needed: `effective_from`, `effective_to`, `is_current`.

### Pluck — Big Data / Lake Architect

| Deliverable | Status |
|-------------|--------|
| Three-zone S3 lake (raw/cleaned/warehouse) with partitioning | ⬜ |
| Glue Crawlers on all three zones | ⬜ |
| Athena queries (5–10 proving the lake works) | ⬜ |
| Big Data Variety justification memo (1-page) | ⬜ |
| Glue Scheduler Workflow: Job 1 → Job 2 → Job 3 at 02:00 UTC | ⬜ |

> **Variety memo tip:** Don't just say "we have variety." Show it with screenshots and numbers — "our lake holds 5 distinct format families: structured CSV, semi-structured JSON (amenities), unstructured text (reviews), geospatial GeoJSON, and time-series (calendar) — across 32 files."

### Jop — BI Analyst / QuickSight Lead

| Deliverable | Status |
|-------------|--------|
| QuickSight account configured + connected to Athena/RDS DW | ⬜ |
| Dashboard 1: Market Overview (KPI tiles, city map, bar charts) | ⬜ |
| Dashboard 2: Pricing & Availability Dynamics (heatmap, histograms) | ⬜ |
| Dashboard 3: Host Quality & Sentiment | ⬜ |
| Business insights document (3–5 key findings with screenshots) | ⬜ |
| Video 2 storyline / script | ⬜ |

> **Narrative tip:** Frame findings as business insights, not data operations. "Bangkok hosts with Superhost status command 42% higher nightly rates" not "AVG(price) WHERE host_is_superhost = true".

---

## Video Plan

**Video 1 (≤15 min) — Kiak + Sun**

| Segment | Person | Content |
|---------|--------|---------|
| 0:00–4:00 | Kiak | Business problem, data sources, source DB setup |
| 4:00–8:00 | Kiak | Ingestion to S3, partitioning strategy |
| 8:00–13:00 | Sun | Star schema walkthrough, SCD logic, conformed bus matrix |
| 13:00–15:00 | Sun | Live demo of Glue ETL run |

**Video 2 (≤10 min) — Pluck + Jop**

| Segment | Person | Content |
|---------|--------|---------|
| 0:00–2:00 | Pluck | Lake architecture overview, why Data Lake |
| 2:00–3:00 | Pluck | Live Athena query showing data is alive |
| 3:00–9:00 | Jop | Dashboard 1 → 2 → 3 tour with business narration |
| 9:00–10:00 | Jop | Top 3 findings summary |

---

## AWS Setup

- **Account ID:** `856480643132`
- **Region:** `ap-southeast-1` (Singapore)
- **Auth method:** AWS SSO (`aws configure sso`) — university SCP blocks IAM user creation
- **S3 Bucket:** `airbnb-dw-856480643132`
- **RDS instance:** `airbnb-source-db` (db.t3.micro, PostgreSQL 16.6, `airbnb_source` database)
- **RDS endpoint:** `airbnb-source-db.crw6s6ou8gww.ap-southeast-1.rds.amazonaws.com:5432`
- **RDS user:** `airbnbadmin` / `REDACTED`
- **RDS status:** Stopped (as of 2026-05-07) — run `start-db-instance` before connecting
- **Security group:** `sg-0cc19604b360489bb` — inbound port 5432 open. If your IP changes, add a new inbound rule for port 5432.

> **Cost tip:** Stop RDS when not in use — `aws rds stop-db-instance --db-instance-identifier airbnb-source-db`

---

## Cities & Snapshots

| City | Snapshot 1 (real) | Snapshot 2 (simulated) | Inside Airbnb URL path |
|------|-------------------|------------------------|------------------------|
| Bangkok | 2025-09 | 2026-03 | thailand/central-thailand/bangkok/2025-09-26 |
| Singapore | 2025-09 | 2026-03 | singapore/sg/singapore/2025-09-28 |
| Tokyo | 2025-09 | 2026-03 | japan/kant%C5%8D/tokyo/2025-09-29 |
| Lisbon | 2025-12 | 2026-03 | portugal/lisbon/lisbon/2025-12-25 |

**Why simulated Snapshot 2?** Inside Airbnb only publishes the latest snapshot per city; older ones return 403. Snapshot 2 is programmatically generated to demonstrate SCD Type 2 slowly-changing dimensions.

---

## S3 Layout

```
s3://airbnb-dw-856480643132/
├── raw/          ← Bronze — Kiak owns this ✅
│   └── city={city}/snapshot={YYYY-MM}/
│       ├── listings.csv.gz
│       ├── calendar.csv.gz
│       ├── reviews.csv.gz
│       └── neighbourhoods.geojson
├── cleaned/      ← Silver — Sun + Pluck own this ⬜
│   └── city={city}/snapshot={YYYY-MM}/{table}/
│       └── *.parquet
└── warehouse/    ← Gold — Sun + Pluck own this ⬜
    └── {dim_or_fact}/{table}/
        └── *.parquet
```

---

## Repository Structure

```
Project/
├── CLAUDE.md                           ← this file
├── handoff.md                          ← Phase 6: handoff doc for Sun
├── diagram/
│   ├── architecture.svg                ← AWS architecture diagram
│   └── architecture.png                ← PNG export (2x resolution)
└── airbnb-dw/
    ├── download.py                     ← Phase 1: download raw data
    ├── generate_snapshot2.py           ← Phase 2: simulate Snapshot 2
    ├── upload_to_s3.py                 ← Phase 3: upload to S3
    ├── load_rds.py                     ← Phase 5: load source_listings into RDS
    └── Inside Airbnb Data Dictionary.xlsx
```

---

## Scripts

### `download.py` — Phase 1
Downloads 16 files (4 cities × 4 file types) as Snapshot 1.

```bash
cd .\airbnb-dw
python download.py
```

- Uses `User-Agent` + `Referer` headers to avoid 403s from Inside Airbnb
- Skips already-downloaded files
- Tokyo URL requires `kant%C5%8D` encoding (not `kantō`)

### `generate_snapshot2.py` — Phase 2
Reads Snapshot 1, applies realistic mutations, writes Snapshot 2 (`2026-03`).

```bash
cd .\airbnb-dw
python generate_snapshot2.py
```

| File | Change |
|------|--------|
| listings | ~15% price ±10–25%, ~8% superhost flip, ~10% response rate drift, ~5% room_type change, ~3% name += "[Renovated]" |
| calendar | ~20% price ±15–20%, ~5% availability flip |
| reviews | Copied as-is |
| neighbourhoods.geojson | Copied unchanged |

> **Known warning:** `FutureWarning` on `host_response_rate` (pandas dtype mismatch). Non-fatal.

### `upload_to_s3.py` — Phase 3

```bash
cd .\airbnb-dw
python upload_to_s3.py
```

### `load_rds.py` — Phase 5

```bash
cd .\airbnb-dw
python load_rds.py
```

Normalises to a fixed schema — extra columns (e.g. `host_profile_id` in Singapore) are dropped.

---

## Data Dictionary Notes

| Field | Issue | Fix |
|-------|-------|-----|
| `price` | Has `$` prefix and commas (e.g. `$1,200.00`) | Strip `[^\d.]`, cast to NUMERIC |
| `host_is_superhost` | Boolean stored as `t` / `f` strings | Map to TRUE / FALSE |
| `host_response_rate` | Percentage string (e.g. `"95%"`) | Strip `%`, cast to FLOAT |
| `amenities` | JSON array stored as string | Parse as JSONB or array |
| `host_verifications` | JSON array stored as string | Parse as JSONB or array |

> **Schema drift:** `host_profile_id` appears in Singapore but not other cities. Always normalise to a fixed column list in ETL jobs.

`amenities` and `host_verifications` justify the **Variety** dimension of Big Data.

---

## Common Commands

```bash
# Check AWS identity
aws sts get-caller-identity

# Re-login if SSO session expired
aws sso login --profile default

# Fix region if misconfigured
aws configure set region ap-southeast-1

# List S3 raw zone
aws s3 ls s3://airbnb-dw-856480643132/raw/ --recursive --human-readable --summarize

# Stop RDS to save cost
aws rds stop-db-instance --db-instance-identifier airbnb-source-db

# Start RDS when needed
aws rds start-db-instance --db-instance-identifier airbnb-source-db
```

---

## Dependencies

```bash
pip install pandas numpy boto3 psycopg2-binary openpyxl requests vaderSentiment
```

Python 3.8+ required.
