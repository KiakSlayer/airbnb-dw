import os
import json
import boto3
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# Credentials loaded from AWS Secrets Manager at runtime — never hardcoded
def _get_rds_secret():
    client = boto3.client("secretsmanager", region_name="ap-southeast-1")
    secret = client.get_secret_value(SecretId="airbnb/rds/airbnbadmin")
    return json.loads(secret["SecretString"])

_secret  = _get_rds_secret()
RDS_HOST = "airbnb-source-db.crw6s6ou8gww.ap-southeast-1.rds.amazonaws.com"
RDS_PORT = 5432
RDS_DB   = "airbnb_source"
RDS_USER = _secret["username"]
RDS_PASS = _secret["password"]
RAW_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS source_listings (
    city                                        TEXT,
    snapshot_date                               TEXT,
    id                                          BIGINT,
    listing_url                                 TEXT,
    scrape_id                                   BIGINT,
    last_scraped                                TEXT,
    source                                      TEXT,
    name                                        TEXT,
    description                                 TEXT,
    neighborhood_overview                       TEXT,
    picture_url                                 TEXT,
    host_id                                     BIGINT,
    host_url                                    TEXT,
    host_name                                   TEXT,
    host_since                                  TEXT,
    host_location                               TEXT,
    host_about                                  TEXT,
    host_response_time                          TEXT,
    host_response_rate                          TEXT,
    host_acceptance_rate                        TEXT,
    host_is_superhost                           BOOLEAN,
    host_thumbnail_url                          TEXT,
    host_picture_url                            TEXT,
    host_neighbourhood                          TEXT,
    host_listings_count                         DOUBLE PRECISION,
    host_total_listings_count                   DOUBLE PRECISION,
    host_verifications                          TEXT,
    host_has_profile_pic                        TEXT,
    host_identity_verified                      TEXT,
    neighbourhood                               TEXT,
    neighbourhood_cleansed                      TEXT,
    neighbourhood_group_cleansed                TEXT,
    latitude                                    DOUBLE PRECISION,
    longitude                                   DOUBLE PRECISION,
    property_type                               TEXT,
    room_type                                   TEXT,
    accommodates                                DOUBLE PRECISION,
    bathrooms                                   DOUBLE PRECISION,
    bathrooms_text                              TEXT,
    bedrooms                                    DOUBLE PRECISION,
    beds                                        DOUBLE PRECISION,
    amenities                                   TEXT,
    price                                       DOUBLE PRECISION,
    minimum_nights                              DOUBLE PRECISION,
    maximum_nights                              DOUBLE PRECISION,
    minimum_minimum_nights                      DOUBLE PRECISION,
    maximum_minimum_nights                      DOUBLE PRECISION,
    minimum_maximum_nights                      DOUBLE PRECISION,
    maximum_maximum_nights                      DOUBLE PRECISION,
    minimum_nights_avg_ntm                      DOUBLE PRECISION,
    maximum_nights_avg_ntm                      DOUBLE PRECISION,
    calendar_updated                            TEXT,
    has_availability                            TEXT,
    availability_30                             DOUBLE PRECISION,
    availability_60                             DOUBLE PRECISION,
    availability_90                             DOUBLE PRECISION,
    availability_365                            DOUBLE PRECISION,
    calendar_last_scraped                       TEXT,
    number_of_reviews                           DOUBLE PRECISION,
    number_of_reviews_ltm                       DOUBLE PRECISION,
    number_of_reviews_l30d                      DOUBLE PRECISION,
    availability_eoy                            DOUBLE PRECISION,
    number_of_reviews_ly                        DOUBLE PRECISION,
    estimated_occupancy_l365d                   DOUBLE PRECISION,
    estimated_revenue_l365d                     DOUBLE PRECISION,
    first_review                                TEXT,
    last_review                                 TEXT,
    review_scores_rating                        DOUBLE PRECISION,
    review_scores_accuracy                      DOUBLE PRECISION,
    review_scores_cleanliness                   DOUBLE PRECISION,
    review_scores_checkin                       DOUBLE PRECISION,
    review_scores_communication                 DOUBLE PRECISION,
    review_scores_location                      DOUBLE PRECISION,
    review_scores_value                         DOUBLE PRECISION,
    license                                     TEXT,
    instant_bookable                            TEXT,
    calculated_host_listings_count              DOUBLE PRECISION,
    calculated_host_listings_count_entire_homes DOUBLE PRECISION,
    calculated_host_listings_count_private_rooms DOUBLE PRECISION,
    calculated_host_listings_count_shared_rooms DOUBLE PRECISION,
    reviews_per_month                           DOUBLE PRECISION
);
"""


def clean_val(v):
    """Convert numpy scalars to Python natives; map NaN/None → None."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, 'item'):  # numpy scalar → Python native
        return v.item()
    return v


def find_latest_snapshot(city_dir):
    snapshots = sorted(
        d for d in os.listdir(city_dir)
        if os.path.isdir(os.path.join(city_dir, d))
    )
    return snapshots[-1] if snapshots else None


def load_city_df(city, snapshot_date, listings_path):
    df = pd.read_csv(listings_path, nrows=1000)
    df.insert(0, 'snapshot_date', snapshot_date)
    df.insert(0, 'city', city)

    # Clean price: "$1,595.00" → 1595.0
    df['price'] = (
        df['price']
        .astype(str)
        .str.replace(r'[\$,]', '', regex=True)
        .replace('nan', None)
        .pipe(pd.to_numeric, errors='coerce')
    )

    # Clean host_is_superhost: "t"/"f" → True/False
    df['host_is_superhost'] = df['host_is_superhost'].map({'t': True, 'f': False})

    return df


SCHEMA_COLS = [
    'city', 'snapshot_date', 'id', 'listing_url', 'scrape_id', 'last_scraped',
    'source', 'name', 'description', 'neighborhood_overview', 'picture_url',
    'host_id', 'host_url', 'host_name', 'host_since', 'host_location',
    'host_about', 'host_response_time', 'host_response_rate',
    'host_acceptance_rate', 'host_is_superhost', 'host_thumbnail_url',
    'host_picture_url', 'host_neighbourhood', 'host_listings_count',
    'host_total_listings_count', 'host_verifications', 'host_has_profile_pic',
    'host_identity_verified', 'neighbourhood', 'neighbourhood_cleansed',
    'neighbourhood_group_cleansed', 'latitude', 'longitude', 'property_type',
    'room_type', 'accommodates', 'bathrooms', 'bathrooms_text', 'bedrooms',
    'beds', 'amenities', 'price', 'minimum_nights', 'maximum_nights',
    'minimum_minimum_nights', 'maximum_minimum_nights', 'minimum_maximum_nights',
    'maximum_maximum_nights', 'minimum_nights_avg_ntm', 'maximum_nights_avg_ntm',
    'calendar_updated', 'has_availability', 'availability_30', 'availability_60',
    'availability_90', 'availability_365', 'calendar_last_scraped',
    'number_of_reviews', 'number_of_reviews_ltm', 'number_of_reviews_l30d',
    'availability_eoy', 'number_of_reviews_ly', 'estimated_occupancy_l365d',
    'estimated_revenue_l365d', 'first_review', 'last_review',
    'review_scores_rating', 'review_scores_accuracy', 'review_scores_cleanliness',
    'review_scores_checkin', 'review_scores_communication',
    'review_scores_location', 'review_scores_value', 'license',
    'instant_bookable', 'calculated_host_listings_count',
    'calculated_host_listings_count_entire_homes',
    'calculated_host_listings_count_private_rooms',
    'calculated_host_listings_count_shared_rooms', 'reviews_per_month',
]


def main():
    print(f"Connecting to {RDS_HOST}...")
    conn = psycopg2.connect(
        host=RDS_HOST, port=RDS_PORT, dbname=RDS_DB,
        user=RDS_USER, password=RDS_PASS,
        connect_timeout=15,
    )
    cur = conn.cursor()

    print("Creating table source_listings if not exists...")
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()

    cities = sorted(
        d for d in os.listdir(RAW_DIR)
        if os.path.isdir(os.path.join(RAW_DIR, d))
    )

    total = 0
    for city in cities:
        city_dir = os.path.join(RAW_DIR, city)
        snapshot_date = find_latest_snapshot(city_dir)
        if not snapshot_date:
            print(f"  {city}: no snapshot dirs found, skipping")
            continue

        listings_path = os.path.join(city_dir, snapshot_date, 'listings.csv.gz')
        if not os.path.exists(listings_path):
            print(f"  {city}/{snapshot_date}: listings.csv.gz missing, skipping")
            continue

        df = load_city_df(city, snapshot_date, listings_path)

        # Keep only columns present in both the schema and the dataframe
        cols = [c for c in SCHEMA_COLS if c in df.columns]
        # Fill any schema cols missing from this city's CSV with None
        for c in SCHEMA_COLS:
            if c not in df.columns:
                df[c] = None
        df = df[SCHEMA_COLS]

        rows = [tuple(clean_val(v) for v in row) for row in df.itertuples(index=False, name=None)]

        execute_values(cur, f"INSERT INTO source_listings ({', '.join(SCHEMA_COLS)}) VALUES %s", rows)
        conn.commit()
        print(f"  {city}/{snapshot_date}: {len(df)} rows loaded")
        total += len(df)

    cur.close()
    conn.close()
    print(f"\nDone. Total rows inserted: {total}")


if __name__ == '__main__':
    main()
