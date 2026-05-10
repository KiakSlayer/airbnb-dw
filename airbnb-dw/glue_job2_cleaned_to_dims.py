"""
Glue ETL Job 2: Cleaned → Dimensions (Silver → Gold)
Job name: airbnb-cleaned-to-dims

Reads cleaned Parquet from the Silver zone and builds 4 dimension tables:
  dim_listing  — SCD Type 2 tracking: name, price, room_type, host_is_superhost, host_response_rate
  dim_host     — SCD Type 2 tracking: host_is_superhost, host_response_rate, host_acceptance_rate, host_listings_count
  dim_location — SCD Type 1 (city × neighbourhood, centroid lat/lon)
  dim_date     — Generated date spine 2024-01-01 → 2027-12-31

Output: s3://airbnb-dw-856480643132/warehouse/{dim_name}/
"""

import sys
from datetime import date

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DateType, IntegerType, StringType

args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

BUCKET = "airbnb-dw-856480643132"
FAR_FUTURE = "9999-12-31"

# city → (snapshot_1, snapshot_2); Lisbon snap1 is 2025-12, not 2025-09
CITY_SNAPS = {
    "bangkok":   ("2025-09", "2026-03"),
    "lisbon":    ("2025-12", "2026-03"),
    "singapore": ("2025-09", "2026-03"),
    "tokyo":     ("2025-09", "2026-03"),
}

SCD_LISTING_COLS = ["name", "price", "room_type", "host_is_superhost", "host_response_rate"]
SCD_HOST_COLS    = ["host_is_superhost", "host_response_rate", "host_acceptance_rate", "host_listings_count"]

LISTING_COLS = [
    "id", "name", "property_type", "room_type", "accommodates",
    "bathrooms", "bathrooms_text", "bedrooms", "beds", "amenities",
    "price", "minimum_nights", "maximum_nights", "instant_bookable",
    "latitude", "longitude", "neighbourhood_cleansed", "neighbourhood_group_cleansed",
    "host_id", "host_is_superhost", "host_response_rate",
]

HOST_COLS = [
    "host_id", "host_name", "host_since", "host_location", "host_response_time",
    "host_response_rate", "host_acceptance_rate", "host_is_superhost",
    "host_listings_count", "host_total_listings_count",
    "host_has_profile_pic", "host_identity_verified",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_parquet(table, city, snapshot):
    """Read a cleaned Parquet table and inject city as a column."""
    path = f"s3://{BUCKET}/cleaned/city={city}/snapshot={snapshot}/{table}/"
    return spark.read.parquet(path).withColumn("city", F.lit(city))


def safe_select(df, cols):
    """Select cols, substituting NULL (as string) for any not present in df."""
    present = set(df.columns)
    return df.select([
        F.col(c) if c in present else F.lit(None).cast(StringType()).alias(c)
        for c in cols
    ])


def apply_scd2(snap1, snap2, key_col, scd_cols, snap1_date, snap2_date):
    """
    SCD Type 2 between two snapshots.

    Outputs one row per snap1 record (plus new/changed snap2 records) with:
      effective_from, effective_to (DateType), is_current (bool)

    Row classification:
      unchanged → snap1 row, effective_to = FAR_FUTURE,  is_current = True
      changed   → snap1 row, effective_to = snap2_date,  is_current = False
                  snap2 row, effective_from = snap2_date, is_current = True
      deleted   → snap1 row, effective_to = snap2_date,  is_current = False
      new       → snap2 row, effective_from = snap2_date, is_current = True
    """
    def with_hash(df, alias):
        existing = [c for c in scd_cols if c in df.columns]
        expr = F.md5(F.concat_ws("|", *[
            F.coalesce(F.col(c).cast(StringType()), F.lit("")) for c in existing
        ]))
        return df.withColumn(alias, expr)

    s1 = with_hash(snap1, "_h1")
    s2 = with_hash(snap2, "_h2")

    # Key-level full outer join to classify each natural key
    s1_keys = s1.select(F.col(key_col).alias("_key"), "_h1")
    s2_keys = s2.select(F.col(key_col).alias("_key"), "_h2")

    status = (
        s1_keys.join(s2_keys, "_key", "full_outer")
        .withColumn("_status",
            F.when(F.col("_h1").isNull(), "new")
             .when(F.col("_h2").isNull(), "deleted")
             .when(F.col("_h1") != F.col("_h2"), "changed")
             .otherwise("unchanged"))
        .select("_key", "_status")
        .cache()
    )

    def keys_of(val):
        return status.filter(F.col("_status") == val).select("_key")

    def scd_row(source_df, hash_alias, keys, eff_from, eff_to, is_curr):
        return (
            source_df
            .join(keys, source_df[key_col] == keys["_key"], "inner")
            .drop("_key", hash_alias)
            .withColumn("effective_from", F.lit(eff_from).cast(DateType()))
            .withColumn("effective_to",   F.lit(eff_to).cast(DateType()))
            .withColumn("is_current",     F.lit(is_curr).cast(BooleanType()))
        )

    result = (
        scd_row(s1, "_h1", keys_of("unchanged"), snap1_date, FAR_FUTURE,  True)
        .union(scd_row(s1, "_h1", keys_of("changed"),   snap1_date, snap2_date, False))
        .union(scd_row(s2, "_h2", keys_of("changed"),   snap2_date, FAR_FUTURE, True))
        .union(scd_row(s1, "_h1", keys_of("deleted"),   snap1_date, snap2_date, False))
        .union(scd_row(s2, "_h2", keys_of("new"),       snap2_date, FAR_FUTURE, True))
    )

    status.unpersist()
    return result


# ---------------------------------------------------------------------------
# dim_listing  (SCD Type 2)
# ---------------------------------------------------------------------------

def build_dim_listing():
    frames = []
    for city, (snap1, snap2) in CITY_SNAPS.items():
        s1 = safe_select(read_parquet("listings", city, snap1), LISTING_COLS + ["city"])
        s2 = safe_select(read_parquet("listings", city, snap2), LISTING_COLS + ["city"])

        scd = apply_scd2(s1, s2, "id", SCD_LISTING_COLS,
                         snap1 + "-01", snap2 + "-01")

        scd = scd.withColumn("listing_sk",
            F.md5(F.concat_ws("|",
                F.col("city"), F.col("id"),
                F.col("effective_from").cast(StringType()))))

        frames.append(scd)

    result = frames[0]
    for f in frames[1:]:
        result = result.union(f)
    return result


# ---------------------------------------------------------------------------
# dim_host  (SCD Type 2)
# ---------------------------------------------------------------------------

def build_dim_host():
    frames = []
    for city, (snap1, snap2) in CITY_SNAPS.items():
        # One record per host per city per snapshot (hosts can have multiple listings)
        s1 = (safe_select(read_parquet("listings", city, snap1), HOST_COLS + ["city"])
              .dropDuplicates(["host_id", "city"]))
        s2 = (safe_select(read_parquet("listings", city, snap2), HOST_COLS + ["city"])
              .dropDuplicates(["host_id", "city"]))

        scd = apply_scd2(s1, s2, "host_id", SCD_HOST_COLS,
                         snap1 + "-01", snap2 + "-01")

        scd = scd.withColumn("host_sk",
            F.md5(F.concat_ws("|",
                F.col("city"), F.col("host_id"),
                F.col("effective_from").cast(StringType()))))

        frames.append(scd)

    result = frames[0]
    for f in frames[1:]:
        result = result.union(f)
    return result


# ---------------------------------------------------------------------------
# dim_location  (SCD Type 1 — latest snapshot, centroid lat/lon per neighbourhood)
# ---------------------------------------------------------------------------

def build_dim_location():
    frames = []
    for city, (_, snap2) in CITY_SNAPS.items():
        df = read_parquet("listings", city, snap2)
        present = set(df.columns)

        group_by = [c for c in ["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"]
                    if c in present]

        agg = df.groupBy(group_by).agg(
            F.avg("latitude").alias("latitude"),
            F.avg("longitude").alias("longitude"),
        )

        # Ensure consistent schema
        for col in ["neighbourhood_cleansed", "neighbourhood_group_cleansed"]:
            if col not in present:
                agg = agg.withColumn(col, F.lit(None).cast(StringType()))

        frames.append(agg)

    result = frames[0]
    for f in frames[1:]:
        result = result.union(f)

    result = result.withColumn("location_sk",
        F.md5(F.concat_ws("|",
            F.col("city"),
            F.coalesce(F.col("neighbourhood_cleansed"), F.lit("")))))
    return result


# ---------------------------------------------------------------------------
# dim_date  (Generated spine 2024-01-01 → 2027-12-31)
# ---------------------------------------------------------------------------

def build_dim_date():
    df = spark.createDataFrame(
        [(date(2024, 1, 1), date(2027, 12, 31))], ["start_dt", "end_dt"]
    )
    return (
        df.select(F.explode(F.sequence("start_dt", "end_dt")).alias("full_date"))
        .withColumn("date_key",    F.date_format("full_date", "yyyyMMdd").cast(IntegerType()))
        .withColumn("year",        F.year("full_date"))
        .withColumn("month",       F.month("full_date"))
        .withColumn("day",         F.dayofmonth("full_date"))
        .withColumn("quarter",     F.quarter("full_date"))
        .withColumn("day_of_week", F.dayofweek("full_date"))   # 1=Sun, 7=Sat
        .withColumn("day_name",    F.date_format("full_date", "EEEE"))
        .withColumn("month_name",  F.date_format("full_date", "MMMM"))
        .withColumn("is_weekend",  F.dayofweek("full_date").isin(1, 7))
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

print("=" * 60)
print("  Airbnb DW — Glue Job 2: Cleaned → Dimensions")
print("=" * 60)

dims = {
    "dim_listing":  build_dim_listing,
    "dim_host":     build_dim_host,
    "dim_location": build_dim_location,
    "dim_date":     build_dim_date,
}

for name, build_fn in dims.items():
    print(f"\n[{name}] Building...")
    df = build_fn()
    df.cache()
    count = df.count()
    out = f"s3://{BUCKET}/warehouse/{name}/"
    df.write.mode("overwrite").parquet(out)
    df.unpersist()
    print(f"[{name}] {count:,} rows → {out}")

job.commit()
print("\nJob 2 complete.")
