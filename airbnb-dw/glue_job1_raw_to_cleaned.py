"""
Glue ETL Job 1: Raw → Cleaned (Silver zone)
Job name: airbnb-raw-to-cleaned

Reads each CSV type explicitly by S3 path (not Glue catalog) to avoid the merged-table
heuristic that unions all files under a partition prefix into one 92-col superschema.
Applies cleaning rules, deduplicates, and writes Parquet to the cleaned/ zone.

Output:
  s3://airbnb-dw-856480643132/cleaned/city={city}/snapshot={YYYY-MM}/listings/
  s3://airbnb-dw-856480643132/cleaned/city={city}/snapshot={YYYY-MM}/calendar/
  s3://airbnb-dw-856480643132/cleaned/city={city}/snapshot={YYYY-MM}/reviews/
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, FloatType

args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

BUCKET = "airbnb-dw-856480643132"

# Lisbon snapshot 1 is 2025-12, NOT 2025-09
CITY_SNAPSHOTS = [
    ("bangkok",   "2025-09"),
    ("bangkok",   "2026-03"),
    ("lisbon",    "2025-12"),
    ("lisbon",    "2026-03"),
    ("singapore", "2025-09"),
    ("singapore", "2026-03"),
    ("tokyo",     "2025-09"),
    ("tokyo",     "2026-03"),
]

# Columns where "t"/"f" → boolean
_TF_COLS = [
    "host_is_superhost", "host_has_profile_pic", "host_identity_verified",
    "has_availability", "instant_bookable",
]

# Columns with "$1,200.00" format → float
_PRICE_COLS = ["price", "adjusted_price"]

# Columns with "95%" format → float
_PCT_COLS = ["host_response_rate", "host_acceptance_rate"]

# Columns that should be numeric but arrive as strings
_LISTINGS_NUMERIC = [
    "latitude", "longitude", "accommodates", "bathrooms", "bedrooms", "beds",
    "minimum_nights", "maximum_nights", "minimum_minimum_nights",
    "maximum_minimum_nights", "minimum_maximum_nights", "maximum_maximum_nights",
    "minimum_nights_avg_ntm", "maximum_nights_avg_ntm",
    "availability_30", "availability_60", "availability_90", "availability_365",
    "number_of_reviews", "number_of_reviews_ltm", "number_of_reviews_l30d",
    "review_scores_rating", "review_scores_accuracy", "review_scores_cleanliness",
    "review_scores_checkin", "review_scores_communication",
    "review_scores_location", "review_scores_value",
    "calculated_host_listings_count",
    "calculated_host_listings_count_entire_homes",
    "calculated_host_listings_count_private_rooms",
    "calculated_host_listings_count_shared_rooms",
    "reviews_per_month", "host_listings_count", "host_total_listings_count",
]


def _cast_tf(df, cols):
    for col in cols:
        if col in df.columns:
            df = df.withColumn(
                col,
                F.when(F.col(col) == "t", True)
                 .when(F.col(col) == "f", False)
                 .otherwise(None)
                 .cast(BooleanType()),
            )
    return df


def _strip_price(df, cols):
    for col in cols:
        if col in df.columns:
            df = df.withColumn(
                col,
                F.regexp_replace(F.col(col), r"[\$,]", "").cast(FloatType()),
            )
    return df


def _strip_pct(df, cols):
    for col in cols:
        if col in df.columns:
            df = df.withColumn(
                col,
                F.regexp_replace(F.col(col), r"%", "").cast(FloatType()),
            )
    return df


def _cast_numeric(df, cols):
    for col in cols:
        if col in df.columns:
            df = df.withColumn(col, F.col(col).cast(FloatType()))
    return df


def clean_listings(df):
    # Singapore-specific column — drop if present to normalise schema
    if "host_profile_id" in df.columns:
        df = df.drop("host_profile_id")

    df = _cast_tf(df, _TF_COLS)
    df = _strip_price(df, _PRICE_COLS)
    df = _strip_pct(df, _PCT_COLS)
    df = _cast_numeric(df, _LISTINGS_NUMERIC)

    df = df.dropDuplicates(["id"]).filter(F.col("id").isNotNull())
    return df


def clean_calendar(df):
    df = df.withColumn(
        "available",
        F.when(F.col("available") == "t", True)
         .when(F.col("available") == "f", False)
         .otherwise(None)
         .cast(BooleanType()),
    )
    df = _strip_price(df, _PRICE_COLS)
    df = _cast_numeric(df, ["minimum_nights", "maximum_nights"])

    df = df.dropDuplicates(["listing_id", "date"]).filter(F.col("listing_id").isNotNull())
    return df


def clean_reviews(df):
    for col in ["id", "listing_id", "reviewer_id"]:
        if col in df.columns:
            df = df.withColumn(col, F.col(col).cast(FloatType()))

    df = df.dropDuplicates(["id"]).filter(F.col("id").isNotNull())
    return df


def read_csv(path):
    return (
        spark.read
        .option("header", "true")
        .option("inferSchema", "false")
        .option("multiLine", "true")    # reviews.comments can contain newlines
        .option("escape", '"')
        .csv(path)
    )


def write_parquet(df, path):
    df.cache()
    count = df.count()
    df.write.mode("overwrite").parquet(path)
    df.unpersist()
    return count


print("=" * 60)
print("  Airbnb DW — Glue Job 1: Raw → Cleaned")
print("=" * 60)

summary = []

for city, snapshot in CITY_SNAPSHOTS:
    raw = f"s3://{BUCKET}/raw/city={city}/snapshot={snapshot}"
    out = f"s3://{BUCKET}/cleaned/city={city}/snapshot={snapshot}"
    print(f"\n[{city}/{snapshot}]")

    # listings
    try:
        df_l = read_csv(f"{raw}/listings.csv.gz")
        df_l = clean_listings(df_l)
        n = write_parquet(df_l, f"{out}/listings/")
        print(f"  listings  → {n:,} rows")
        summary.append((city, snapshot, "listings", n))
    except Exception as e:
        print(f"  listings  FAILED: {e}")

    # calendar
    try:
        df_c = read_csv(f"{raw}/calendar.csv.gz")
        df_c = clean_calendar(df_c)
        n = write_parquet(df_c, f"{out}/calendar/")
        print(f"  calendar  → {n:,} rows")
        summary.append((city, snapshot, "calendar", n))
    except Exception as e:
        print(f"  calendar  FAILED: {e}")

    # reviews
    try:
        df_r = read_csv(f"{raw}/reviews.csv.gz")
        df_r = clean_reviews(df_r)
        n = write_parquet(df_r, f"{out}/reviews/")
        print(f"  reviews   → {n:,} rows")
        summary.append((city, snapshot, "reviews", n))
    except Exception as e:
        print(f"  reviews   FAILED: {e}")

print("\n" + "=" * 60)
print("  Summary")
print("=" * 60)
print(f"  {'City':<12} {'Snapshot':<10} {'Table':<10} {'Rows':>10}")
print(f"  {'-'*46}")
for city, snap, tbl, n in summary:
    print(f"  {city:<12} {snap:<10} {tbl:<10} {n:>10,}")
print(f"\n  Total tables written: {len(summary)}")

job.commit()
print("\nJob 1 complete.")
