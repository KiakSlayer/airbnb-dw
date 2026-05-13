"""
Glue ETL Job 3: Cleaned → Facts + VADER Sentiment (Silver → Gold)
Job name: airbnb-cleaned-to-facts

Requires job parameter: --additional-python-modules vaderSentiment

Builds 3 fact tables:
  fact_listing_snapshot — one row per listing per city per snapshot
  fact_calendar         — one row per listing per date (availability + pricing)
  fact_review           — one row per review with VADER compound/pos/neg/neu scores

Output: s3://airbnb-dw-856480643132/warehouse/{fact_name}/
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DateType, FloatType, StringType, StructField, StructType

args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

BUCKET = "airbnb-dw-856480643132"
FAR_FUTURE = "9999-12-31"

CITY_SNAPS = {
    "bangkok":   ("2025-09", "2026-03"),
    "lisbon":    ("2025-12", "2026-03"),
    "singapore": ("2025-09", "2026-03"),
    "tokyo":     ("2025-09", "2026-03"),
}

NUMERIC_MEASURES = [
    "price", "accommodates", "minimum_nights", "maximum_nights",
    "availability_30", "availability_60", "availability_90", "availability_365",
    "number_of_reviews", "number_of_reviews_ltm", "number_of_reviews_l30d",
    "review_scores_rating", "review_scores_accuracy", "review_scores_cleanliness",
    "review_scores_checkin", "review_scores_communication",
    "review_scores_location", "review_scores_value",
    "reviews_per_month", "calculated_host_listings_count",
]
BOOL_MEASURES = ["instant_bookable"]

# ---------------------------------------------------------------------------
# VADER UDF — singleton per executor process (avoids reloading lexicon each row)
# ---------------------------------------------------------------------------

_VADER_SCHEMA = StructType([
    StructField("compound", FloatType()),
    StructField("pos",      FloatType()),
    StructField("neg",      FloatType()),
    StructField("neu",      FloatType()),
])


@F.udf(_VADER_SCHEMA)
def vader_udf(text):
    import vaderSentiment.vaderSentiment as _vs
    if not hasattr(_vs, "_analyzer"):
        _vs._analyzer = _vs.SentimentIntensityAnalyzer()
    if not text or not str(text).strip():
        return (0.0, 0.0, 0.0, 0.0)
    s = _vs._analyzer.polarity_scores(str(text))
    return (float(s["compound"]), float(s["pos"]), float(s["neg"]), float(s["neu"]))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_parquet(table, city, snapshot):
    path = f"s3://{BUCKET}/cleaned/city={city}/snapshot={snapshot}/{table}/"
    return spark.read.parquet(path).withColumn("city", F.lit(city))


def load_dims():
    dim_l = (spark.read.parquet(f"s3://{BUCKET}/warehouse/dim_listing/")
             .select("listing_sk", "id", "city", "effective_from", "effective_to")
             .cache())

    dim_h = (spark.read.parquet(f"s3://{BUCKET}/warehouse/dim_host/")
             .filter(F.col("is_current") == True)
             .select("host_sk", F.col("host_id").alias("_h_id"), F.col("city").alias("_h_city"))
             .cache())

    dim_loc = (spark.read.parquet(f"s3://{BUCKET}/warehouse/dim_location/")
               .select("location_sk",
                       F.col("city").alias("_loc_city"),
                       F.col("neighbourhood_cleansed").alias("_loc_nb"))
               .cache())

    dim_d = (spark.read.parquet(f"s3://{BUCKET}/warehouse/dim_date/")
             .select("date_key", F.col("full_date").alias("_dim_date"))
             .cache())

    return dim_l, dim_h, dim_loc, dim_d


def join_listing_sk_range(fact, dim_l, id_col, date_col):
    """SCD2-correct SK: effective_from <= date < effective_to."""
    d = (dim_l
         .withColumnRenamed("id",   "_dl_id")
         .withColumnRenamed("city", "_dl_city"))
    return (
        fact.join(d,
                  (fact[id_col].cast(StringType()) == F.col("_dl_id").cast(StringType())) &
                  (fact["city"]       == F.col("_dl_city")) &
                  (fact[date_col]     >= F.col("effective_from")) &
                  (fact[date_col]     <  F.col("effective_to")),
                  "left")
        .drop("_dl_id", "_dl_city", "effective_from", "effective_to")
    )


def join_listing_sk_current(fact, dim_l, id_col):
    """Use current (is_current=True) listing_sk — for calendar/review facts."""
    d = (dim_l
         .filter(F.col("effective_to") == F.lit(FAR_FUTURE).cast(DateType()))
         .select("listing_sk",
                 F.col("id").alias("_dl_id"),
                 F.col("city").alias("_dl_city")))
    return (
        fact.join(d,
                  (fact[id_col].cast(StringType()) == F.col("_dl_id").cast(StringType())) &
                  (fact["city"] == F.col("_dl_city")),
                  "left")
        .drop("_dl_id", "_dl_city")
    )


def join_date_key(fact, dim_d, date_col):
    return (
        fact.join(dim_d, fact[date_col] == F.col("_dim_date"), "left")
        .drop("_dim_date")
    )


# ---------------------------------------------------------------------------
# fact_listing_snapshot
# ---------------------------------------------------------------------------

def build_fact_listing_snapshot(dim_l, dim_h, dim_loc, dim_d):
    frames = []
    for city, (snap1, snap2) in CITY_SNAPS.items():
        for snap in [snap1, snap2]:
            df = read_parquet("listings", city, snap)
            present = set(df.columns)

            exprs = (
                [F.col("id"), F.col("city"),
                 F.col("host_id") if "host_id" in present else F.lit(None).cast(StringType()).alias("host_id"),
                 F.col("neighbourhood_cleansed") if "neighbourhood_cleansed" in present
                     else F.lit(None).cast(StringType()).alias("neighbourhood_cleansed")] +
                [F.col(c) if c in present else F.lit(None).cast(FloatType()).alias(c)
                 for c in NUMERIC_MEASURES] +
                [F.col(c) if c in present else F.lit(None).cast(BooleanType()).alias(c)
                 for c in BOOL_MEASURES] +
                [F.lit(snap + "-01").cast(DateType()).alias("snap_date"),
                 F.lit(snap).alias("snapshot")]
            )
            frames.append(df.select(exprs))

    fact = frames[0]
    for f in frames[1:]:
        fact = fact.union(f)

    # Surrogate key joins
    fact = join_listing_sk_range(fact, dim_l, "id", "snap_date")
    fact = fact.join(dim_h, (fact["host_id"] == F.col("_h_id")) & (fact["city"] == F.col("_h_city")), "left") \
               .drop("_h_id", "_h_city")
    fact = fact.join(dim_loc,
                     (fact["city"] == F.col("_loc_city")) &
                     (F.coalesce(fact["neighbourhood_cleansed"], F.lit("")) ==
                      F.coalesce(F.col("_loc_nb"), F.lit(""))),
                     "left").drop("_loc_city", "_loc_nb")
    fact = join_date_key(fact, dim_d, "snap_date")

    return fact.drop("id", "host_id", "neighbourhood_cleansed", "snap_date")


# ---------------------------------------------------------------------------
# fact_calendar
# ---------------------------------------------------------------------------

CALENDAR_COLS = ["available", "price", "adjusted_price", "minimum_nights", "maximum_nights"]


def build_fact_calendar(dim_l, dim_d):
    frames = []
    for city, (snap1, snap2) in CITY_SNAPS.items():
        for snap in [snap1, snap2]:
            df = read_parquet("calendar", city, snap)
            present = set(df.columns)
            exprs = (
                [F.col("listing_id"), F.col("city"),
                 F.to_date(F.col("date")).alias("cal_date")] +
                [F.col(c) if c in present else F.lit(None).cast(FloatType()).alias(c)
                 for c in CALENDAR_COLS if c != "available"] +
                [F.col("available") if "available" in present
                 else F.lit(None).cast(BooleanType()).alias("available")] +
                [F.lit(snap).alias("snapshot")]
            )
            frames.append(df.select(exprs))

    fact = frames[0]
    for f in frames[1:]:
        fact = fact.union(f)

    fact = join_listing_sk_current(fact, dim_l, "listing_id")
    fact = join_date_key(fact, dim_d, "cal_date")

    return fact.drop("listing_id", "cal_date")


# ---------------------------------------------------------------------------
# fact_review  (with VADER)
# ---------------------------------------------------------------------------

def build_fact_review(dim_l, dim_d):
    frames = []
    for city, (snap1, snap2) in CITY_SNAPS.items():
        # Reviews don't change between snapshots — read snap1 only per city
        df = read_parquet("reviews", city, snap1)
        frames.append(df)

    fact = frames[0]
    for f in frames[1:]:
        fact = fact.union(f)

    # Dedup on (id, city) in case snap2 was accidentally included
    fact = fact.dropDuplicates(["id", "city"])

    # VADER sentiment
    fact = (fact
            .withColumn("_vader",         vader_udf(F.col("comments")))
            .withColumn("vader_compound",  F.col("_vader.compound"))
            .withColumn("vader_pos",       F.col("_vader.pos"))
            .withColumn("vader_neg",       F.col("_vader.neg"))
            .withColumn("vader_neu",       F.col("_vader.neu"))
            .drop("_vader"))

    fact = fact.withColumn("review_date", F.to_date(F.col("date")))
    fact = join_listing_sk_current(fact, dim_l, "listing_id")
    fact = join_date_key(fact, dim_d, "review_date")

    return fact.drop("listing_id", "date", "review_date")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

print("=" * 60)
print("  Airbnb DW — Glue Job 3: Cleaned → Facts + VADER")
print("=" * 60)

print("\nLoading dimension tables...")
dim_l, dim_h, dim_loc, dim_d = load_dims()

facts = {
    "fact_listing_snapshot": lambda: build_fact_listing_snapshot(dim_l, dim_h, dim_loc, dim_d),
    "fact_calendar":         lambda: build_fact_calendar(dim_l, dim_d),
    "fact_review":           lambda: build_fact_review(dim_l, dim_d),
}

for name, build_fn in facts.items():
    print(f"\n[{name}] Building...")
    df = build_fn()
    df.cache()
    count = df.count()
    out = f"s3://{BUCKET}/warehouse/{name}/"
    df.write.mode("overwrite").parquet(out)
    df.unpersist()
    print(f"[{name}] {count:,} rows → {out}")

# Release cached dims
dim_l.unpersist()
dim_h.unpersist()
dim_loc.unpersist()
dim_d.unpersist()

job.commit()
print("\nJob 3 complete.")
