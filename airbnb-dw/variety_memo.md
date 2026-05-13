# Data Variety Justification Memo

**Project:** Airbnb Cross-City Analytics Data Warehouse  
**Author:** Pluck  
**Date:** 2026-05-14  
**Phase:** 11 — Big Data Variety

---

## Purpose

This memo demonstrates that the Airbnb DW project satisfies the **Variety** dimension of Big Data by ingesting and processing data from five distinct format families. Each family differs in its data model, encoding, and access pattern.

---

## Format Family 1 — Compressed Delimited Text (CSV.gz)

**Where used:** Bronze / Raw zone — `s3://airbnb-dw-856480643132/raw/`

**Files:** `listings.csv.gz`, `calendar.csv.gz`, `reviews.csv.gz` per city/snapshot (40 objects, ~1.1 GiB total)

**Characteristics:**
- Row-oriented, human-readable, schema inferred at read time
- Gzip-compressed to reduce storage cost (~5–10× compression ratio on text)
- Heterogeneous column types stored as raw strings (prices as `"$1,200.00"`, booleans as `"t"`/`"f"`, percentages as `"95%"`)

**Why it matters:** This is the authoritative source format from Inside Airbnb. The pipeline must parse and normalise it before any analytics can run — demonstrating ingestion of unclean, mixed-type text data at scale.

---

## Format Family 2 — Columnar Binary (Apache Parquet)

**Where used:** Silver zone (`cleaned/`) and Gold zone (`warehouse/`)

**Files:** All output from Glue Jobs 1, 2, and 3 — listings, calendar, reviews, plus four dimension tables and three fact tables

**Characteristics:**
- Column-oriented: entire columns stored contiguously — ideal for analytical scans that touch only a subset of columns
- Self-describing schema embedded in the file footer (no external DDL needed)
- Predicate pushdown and partition pruning via Hive-style partitioning (`city=X/snapshot=Y/`)
- Typically 5–10× smaller than equivalent CSV after type-aware encoding + Snappy compression

**Why it matters:** Parquet is the standard columnar format for cloud data lakes. Athena and Glue both leverage it for cost-efficient, high-performance queries. Choosing Parquet over CSV for the Silver/Gold zones directly reduces scan time and cost.

---

## Format Family 3 — Geospatial (GeoJSON)

**Where used:** Bronze zone — `s3://airbnb-dw-856480643132/raw/city={city}/snapshot={YYYY-MM}/neighbourhoods.geojson`

**Files:** One `.geojson` file per city/snapshot (8 files, 1.8 MiB–4.1 MiB each)

**Characteristics:**
- Semi-structured, hierarchical JSON with a standardised geospatial schema (RFC 7946)
- Each feature is a `Polygon` or `MultiPolygon` geometry tagged with neighbourhood name and city
- Cannot be loaded by standard CSV parsers; requires a GeoJSON-aware library (e.g., `geopandas`, `shapely`) or a geospatial query engine

**Why it matters:** Geospatial data is a distinct variety because its value is encoded in geometry (coordinates), not scalar attributes. These files enable neighbourhood-level market analysis and spatial joins that flat CSV cannot express.

---

## Format Family 4 — Relational / Transactional (PostgreSQL on RDS)

**Where used:** AWS RDS instance `airbnb-source-db` — database `airbnb_source`, table `source_listings`

**Volume:** 4,000 rows (500 listings × 4 cities × 2 snapshots, simulated SCD mutations)

**Characteristics:**
- Structured, strongly-typed schema enforced by the database engine
- ACID transactions ensure consistency under concurrent writes
- Row-oriented storage, indexed on primary keys — optimised for OLTP (point lookups, small updates)
- Accessed via JDBC/psycopg2 connection; exported to S3 daily by Glue Job `airbnb-rds-to-s3-export`

**Why it matters:** Operational source systems live in relational databases, not flat files. Integrating RDS represents the **Lambda Architecture** source layer: the pipeline must bridge OLTP (normalised rows, live updates) to OLAP (denormalised stars, batch scans).

---

## Format Family 5 — Embedded Semi-Structured (JSON arrays within CSV)

**Where used:** Bronze `listings.csv.gz` → columns `amenities` and `host_verifications`

**Examples:**
```
amenities:          ["TV", "Wifi", "Kitchen", "Free parking on premises"]
host_verifications: ["email", "phone", "work_email"]
```

**Characteristics:**
- JSON arrays encoded as plain strings inside a CSV column — a common pattern when source APIs serialize nested data before writing to tabular exports
- Schema is implicit; element count varies per row (0–60 amenities observed)
- Cannot be queried with standard SQL without parsing; Athena supports `json_extract` / `json_array_length` once stored as Parquet strings

**Why it matters:** This hybrid format (structured container, semi-structured payload) is typical of real-world data pipelines. Handling it correctly — preserving the raw string through ETL, then using `json_extract` in Athena rather than flattening prematurely — demonstrates proper treatment of nested data variety.

---

## Summary Table

| # | Format Family | Zone | Volume | Access Pattern |
|---|---------------|------|--------|----------------|
| 1 | Compressed CSV (CSV.gz) | Bronze/Raw | 40 files, ~1.1 GiB | Spark `read.csv` with multiLine |
| 2 | Columnar Binary (Parquet) | Silver + Gold | All cleaned/warehouse | Athena scan, Glue DynamicFrame |
| 3 | Geospatial (GeoJSON) | Bronze/Raw | 8 files, up to 4.1 MiB | geopandas / spatial engine |
| 4 | Relational / SQL (PostgreSQL) | RDS source | 4,000 rows | JDBC, daily Glue export |
| 5 | Embedded JSON arrays in CSV | Bronze/Raw (listings) | 2 columns per row | `json_extract` after load |

These five families span the structured–semi-structured–geospatial spectrum and represent both batch-file and live-database ingestion patterns — satisfying the Variety dimension of Big Data.
