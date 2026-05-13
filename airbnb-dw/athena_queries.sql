-- Airbnb DW — Athena Sample Queries (Phase 12)
-- Database: airbnb_cleaned
-- Tables: listings, calendar, reviews
-- All tables are partitioned by city and snapshot.
-- Run in the Athena console or via the airbnb-analytics workgroup.
-- Always include partition filters (city, snapshot) to avoid full-table scans.


-- ─────────────────────────────────────────────────────────────────────────────
-- Q1. Listing count by city across all snapshots
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    snapshot,
    COUNT(*) AS listing_count
FROM airbnb_cleaned.listings
GROUP BY city, snapshot
ORDER BY city, snapshot;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q2. Average nightly price by city and room type (latest snapshot)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    room_type,
    ROUND(AVG(price), 2)   AS avg_price,
    ROUND(MIN(price), 2)   AS min_price,
    ROUND(MAX(price), 2)   AS max_price,
    COUNT(*)               AS listing_count
FROM airbnb_cleaned.listings
WHERE snapshot = '2026-03'
  AND price IS NOT NULL
GROUP BY city, room_type
ORDER BY city, avg_price DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q3. Superhost percentage by city (latest snapshot)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    COUNT(*) AS total_listings,
    SUM(CASE WHEN host_is_superhost = true THEN 1 ELSE 0 END) AS superhost_listings,
    ROUND(
        100.0 * SUM(CASE WHEN host_is_superhost = true THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS superhost_pct
FROM airbnb_cleaned.listings
WHERE snapshot = '2026-03'
GROUP BY city
ORDER BY superhost_pct DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q4. Top 10 highest-rated listings per city (latest snapshot, ≥ 10 reviews)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    id                     AS listing_id,
    name,
    room_type,
    price,
    review_scores_rating,
    number_of_reviews
FROM airbnb_cleaned.listings
WHERE snapshot = '2026-03'
  AND review_scores_rating IS NOT NULL
  AND number_of_reviews >= 10
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY city
    ORDER BY review_scores_rating DESC, number_of_reviews DESC
) <= 10
ORDER BY city, review_scores_rating DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q5. Price change between snapshots — per-listing delta (Bangkok example)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    s1.id                                      AS listing_id,
    s1.name,
    s1.price                                   AS price_snap1,
    s2.price                                   AS price_snap2,
    ROUND(s2.price - s1.price, 2)              AS price_delta,
    ROUND(100.0 * (s2.price - s1.price) / NULLIF(s1.price, 0), 1) AS price_pct_change
FROM airbnb_cleaned.listings s1
JOIN airbnb_cleaned.listings s2
    ON s1.id = s2.id
   AND s1.city = s2.city
WHERE s1.city = 'bangkok'
  AND s1.snapshot = '2025-09'
  AND s2.snapshot = '2026-03'
  AND s1.price IS NOT NULL
  AND s2.price IS NOT NULL
ORDER BY ABS(s2.price - s1.price) DESC
LIMIT 20;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q6. Calendar occupancy rate by city (% of days unavailable) — latest month
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    COUNT(*)                                                          AS total_day_slots,
    SUM(CASE WHEN available = false THEN 1 ELSE 0 END)               AS booked_days,
    ROUND(
        100.0 * SUM(CASE WHEN available = false THEN 1 ELSE 0 END) / COUNT(*),
        1
    )                                                                  AS occupancy_rate_pct
FROM airbnb_cleaned.calendar
WHERE snapshot = '2026-03'
GROUP BY city
ORDER BY occupancy_rate_pct DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q7. Review volume by city — comparison between snapshots
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    snapshot,
    COUNT(*) AS review_count
FROM airbnb_cleaned.reviews
GROUP BY city, snapshot
ORDER BY city, snapshot;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q8. Average host response rate by city and superhost status
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    host_is_superhost,
    ROUND(AVG(host_response_rate), 1) AS avg_response_rate,
    ROUND(AVG(host_acceptance_rate), 1) AS avg_acceptance_rate,
    COUNT(DISTINCT host_id) AS host_count
FROM airbnb_cleaned.listings
WHERE snapshot = '2026-03'
  AND host_response_rate IS NOT NULL
GROUP BY city, host_is_superhost
ORDER BY city, host_is_superhost DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q9. Distribution of listings by number of bedrooms (latest snapshot)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    CAST(bedrooms AS INTEGER) AS bedrooms,
    COUNT(*) AS listing_count,
    ROUND(AVG(price), 2) AS avg_price
FROM airbnb_cleaned.listings
WHERE snapshot = '2026-03'
  AND bedrooms IS NOT NULL
  AND bedrooms <= 10
GROUP BY city, CAST(bedrooms AS INTEGER)
ORDER BY city, bedrooms;


-- ─────────────────────────────────────────────────────────────────────────────
-- Q10. Amenity keyword frequency — JSON string search (no array unnest needed)
-- Shows how many listings mention common amenities in their amenities column.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    city,
    SUM(CASE WHEN amenities LIKE '%Wifi%'            THEN 1 ELSE 0 END) AS has_wifi,
    SUM(CASE WHEN amenities LIKE '%Kitchen%'         THEN 1 ELSE 0 END) AS has_kitchen,
    SUM(CASE WHEN amenities LIKE '%Air conditioning%' THEN 1 ELSE 0 END) AS has_ac,
    SUM(CASE WHEN amenities LIKE '%Pool%'            THEN 1 ELSE 0 END) AS has_pool,
    SUM(CASE WHEN amenities LIKE '%Washer%'          THEN 1 ELSE 0 END) AS has_washer,
    COUNT(*) AS total_listings
FROM airbnb_cleaned.listings
WHERE snapshot = '2026-03'
GROUP BY city
ORDER BY city;
