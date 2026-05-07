"""
Glue Python Shell Job: S3 Bronze listings -> S3 source-exports zone
Job name: airbnb-rds-to-s3-export

Scans the S3 Bronze zone for all listing snapshots, applies data-type cleaning
(price normalisation, boolean cast, rate parsing), and writes validated exports to:
  s3://airbnb-dw-856480643132/source-exports/city={city}/snapshot={YYYY-MM}/listings.csv.gz

Uses only boto3 + pandas (pre-installed in Glue Python Shell 1.0). No extra deps.
Runs daily at 02:00 UTC via Glue Scheduler trigger.
"""

import gzip
import io
from datetime import datetime, timezone

import boto3
import pandas as pd

S3_BUCKET      = "airbnb-dw-856480643132"
S3_INPUT_PRE   = "raw"
S3_OUTPUT_PRE  = "source-exports"
REGION         = "ap-southeast-1"

CITIES    = ["bangkok", "singapore", "tokyo", "lisbon"]
# Lisbon Snapshot 1 is 2025-12; others are 2025-09. Script silently skips missing combinations.
SNAPSHOTS = ["2025-09", "2025-12", "2026-03"]


def read_listing(s3_client, city, snapshot):
    key = "{prefix}/city={city}/snapshot={snap}/listings.csv.gz".format(
        prefix=S3_INPUT_PRE, city=city, snap=snapshot
    )
    print("[S3]  Reading s3://{}/{}" .format(S3_BUCKET, key))
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        raw = obj["Body"].read()
        df = pd.read_csv(io.BytesIO(raw), compression="gzip", low_memory=False)
        df["city"] = city
        df["snapshot_date"] = snapshot
        return df
    except Exception as exc:
        print("[WARN] Could not read {}: {}".format(key, exc))
        return None


def clean_df(df):
    # Normalise price: strip "$" and "," then cast to float
    if "price" in df.columns:
        df["price"] = (
            df["price"]
            .astype(str)
            .str.replace(r"[\$,]", "")
            .pipe(pd.to_numeric, errors="coerce")
        )

    # Normalise boolean superhost "t"/"f" -> True/False
    if "host_is_superhost" in df.columns:
        df["host_is_superhost"] = df["host_is_superhost"].map(
            {"t": True, "f": False, True: True, False: False}
        )

    # Strip "%" from rate columns
    for col in ("host_response_rate", "host_acceptance_rate"):
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("%", "")
                .pipe(pd.to_numeric, errors="coerce")
            )

    # Add processing timestamp
    df["exported_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def write_partition(s3_client, city, snapshot, df):
    snap_key = str(snapshot)[:7]
    key = "{prefix}/city={city}/snapshot={snap}/listings.csv.gz".format(
        prefix=S3_OUTPUT_PRE, city=city, snap=snap_key
    )
    # Write gzip CSV using gzip module (compatible with pandas 0.23.x)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(df.to_csv(index=False).encode("utf-8"))
    buf.seek(0)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/gzip",
    )
    print("[S3]  Wrote s3://{bucket}/{key}  ({rows:,} rows)".format(
        bucket=S3_BUCKET, key=key, rows=len(df)
    ))
    return key


def main():
    s3 = boto3.client("s3", region_name=REGION)

    print("=" * 60)
    print("  Airbnb DW -- Glue Export Job")
    print("  Started: {}".format(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")))
    print("=" * 60)

    summary = []
    for city in CITIES:
        for snapshot in SNAPSHOTS:
            df = read_listing(s3, city, snapshot)
            if df is None:
                continue
            df = clean_df(df)
            key = write_partition(s3, city, snapshot, df)
            summary.append({"city": city, "snapshot": snapshot, "rows": len(df)})

    print("\n[SUMMARY] Export complete.")
    print("{:<12} {:<12} {:>6}".format("City", "Snapshot", "Rows"))
    print("-" * 34)
    total = 0
    for row in summary:
        print("{:<12} {:<12} {:>6}".format(row["city"], row["snapshot"], row["rows"]))
        total += row["rows"]
    print("-" * 34)
    print("{:<12} {:<12} {:>6}".format("TOTAL", "", total))


if __name__ == "__main__":
    main()
