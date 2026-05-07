# Airbnb DW — Phase 6 Handoff to Sun (ETL Engineer)

**Prepared by:** Kiak (Data Engineer / Source DB Lead)  
**Date:** 2026-05-07  
**Status:** Phases 1–5 complete. RDS stopped (cost-saving). Ready for Glue ETL work.

---

## What's Done (Phases 1–5)

| Phase | Description | Result |
|-------|-------------|--------|
| 1 | Download Snapshot 1 from Inside Airbnb | 4 cities downloaded locally |
| 2 | Generate Snapshot 2 (SCD Type 2 simulation) | Mutations applied (seed=42), written as `2026-03` |
| 3 | Upload all raw data to S3 Bronze layer | 40 objects, **1.1 GiB** in `s3://airbnb-dw-856480643132/raw/` |
| 4 | Create RDS PostgreSQL instance | `airbnb-source-db`, PostgreSQL 16.6, `db.t3.micro` |
| 5 | Load first 1,000 rows/city into `source_listings` | 4,000 rows total, price and superhost cleaned |

---

## AWS Account

| Setting | Value |
|---------|-------|
| Account ID | `856480643132` |
| Region | `ap-southeast-1` (Singapore) |
| Auth | AWS SSO — `aws sso login` to authenticate |

---

## S3 Bronze Layer (your primary input)

**Bucket:** `s3://airbnb-dw-856480643132`

### Layout (Hive-partitioned for Glue/Athena)

```
s3://airbnb-dw-856480643132/
└── raw/
    └── city={city}/
        └── snapshot={YYYY-MM}/
            ├── listings.csv.gz
            ├── calendar.csv.gz
            ├── reviews.csv.gz
            └── neighbourhoods.geojson
```

### File Inventory

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

Verify with:
```bash
aws s3 ls s3://airbnb-dw-856480643132/raw/ --recursive --human-readable --summarize
```

> **Note on Lisbon:** Snapshot 1 is `2025-12` (not `2025-09`) — Inside Airbnb published it later.  
> **Note on Snapshot 2:** The `2026-03` files are programmatically simulated to demonstrate SCD Type 2. They are _not_ real data.

---

## RDS Source DB (reference / spot-checks only)

The RDS instance holds the first 1,000 rows per city for quick SQL validation. **It is stopped — start it before connecting.**

| Setting | Value |
|---------|-------|
| Instance ID | `airbnb-source-db` |
| Engine | PostgreSQL 16.6 |
| Database | `airbnb_source` |
| Table | `source_listings` (4,000 rows — 1,000 per city, latest snapshot) |
| Endpoint | `airbnb-source-db.crw6s6ou8gww.ap-southeast-1.rds.amazonaws.com` |
| Port | `5432` |
| User | `airbnbadmin` |
| Password | `REDACTED` |
| Security group | `sg-0cc19604b360489bb` |

Start/stop commands:
```bash
# Start
aws rds start-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1

# Stop when done
aws rds stop-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1
```

> **Important:** If your machine's public IP differs from Kiak's (`101.51.52.178`), you need an inbound rule on `sg-0cc19604b360489bb` for port 5432 from your IP:
> ```bash
> MY_IP=$(curl -s https://checkip.amazonaws.com)
> aws ec2 authorize-security-group-ingress \
>   --group-id sg-0cc19604b360489bb \
>   --protocol tcp --port 5432 \
>   --cidr "${MY_IP}/32" \
>   --region ap-southeast-1
> ```

---

## Data Quality — What Glue ETL Must Handle

These are raw-layer issues. Fix them in the Silver layer transformation.

| Field | Raw value example | Required fix |
|-------|-------------------|--------------|
| `price` | `"$1,595.00"` | Strip `$` and `,`, cast to `DOUBLE` / `NUMERIC` |
| `host_is_superhost` | `"t"` / `"f"` | Map to `true` / `false` boolean |
| `host_response_rate` | `"95%"` | Strip `%`, cast to `FLOAT` (0–100 scale) |
| `host_acceptance_rate` | `"80%"` | Same as above |
| `amenities` | `'["Wifi", "Kitchen"]'` | Parse as JSON array |
| `host_verifications` | `'["email", "phone"]'` | Parse as JSON array |
| `last_scraped` / `host_since` / dates | `"2025-09-26"` string | Cast to `DATE` |
| Nulls | `NaN`, empty string | Normalize to SQL `NULL` |

---

## SCD Type 2 Design (listings table)

The two snapshots per city (`2025-09`/`2025-12` and `2026-03`) are designed to drive **SCD Type 2** slowly-changing dimensions on `source_listings`.

**Columns that change between snapshots** (mutations applied in Phase 2):

| Column | Change rate | Notes |
|--------|-------------|-------|
| `price` | ~15% of rows | ±10–25% random delta |
| `host_is_superhost` | ~8% of rows | Status flip |
| `host_response_rate` | ~10% of rows | Drift ±5–15 pp |
| `room_type` | ~5% of rows | Category change |
| `name` | ~3% of rows | Appended `"[Renovated]"` suffix |

In the Silver/Gold layer, track these changes with `valid_from`, `valid_to`, `is_current` columns.

---

## Expected Architecture (Glue / Silver / Gold)

```
Bronze (S3 raw/)
    └─► Silver  ─ Glue Job: clean + cast + dedupe + SCD Type 2 merge
                  Output: s3://airbnb-dw-.../silver/listings_scd/
                          s3://airbnb-dw-.../silver/calendar/
                          s3://airbnb-dw-.../silver/reviews/
        └─► Gold ─ Glue Job: dimensional model aggregations
                   Output: dim_listing, dim_host, dim_location,
                           fact_availability, fact_review_summary
```

Suggested Glue job names: `airbnb-silver-listings`, `airbnb-silver-calendar`, `airbnb-gold-dims`.

---

## Cities Reference

| City | Snapshot 1 | Snapshot 2 |
|------|-----------|------------|
| Bangkok | 2025-09 | 2026-03 |
| Singapore | 2025-09 | 2026-03 |
| Tokyo | 2025-09 | 2026-03 |
| Lisbon | 2025-12 | 2026-03 |

---

## Re-authentication (SSO)

If your session expires mid-work:
```bash
aws sso login
# then verify:
aws sts get-caller-identity
```

---

## Files in This Repo

```
Project/
├── CLAUDE.md                        — full project notes and common commands
├── handoff.md                       — this file
└── airbnb-dw/
    ├── download.py                  — Phase 1: download raw data
    ├── generate_snapshot2.py        — Phase 2: simulate Snapshot 2
    ├── upload_to_s3.py              — Phase 3: upload to S3
    └── load_rds.py                  — Phase 5: load source_listings into RDS
```

Raw data lives at `.\airbnb-dw\raw\` (relative to project root, not in git — too large).

---

_Kiak — ready for Sun to pick up from here. Ping if the SG rule for your IP needs adding._