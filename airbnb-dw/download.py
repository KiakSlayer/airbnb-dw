import urllib.request
import os

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')

files = [
    # BANGKOK
    ("bangkok", "2025-09", "listings",       "https://data.insideairbnb.com/thailand/central-thailand/bangkok/2025-09-26/data/listings.csv.gz"),
    ("bangkok", "2025-09", "calendar",       "https://data.insideairbnb.com/thailand/central-thailand/bangkok/2025-09-26/data/calendar.csv.gz"),
    ("bangkok", "2025-09", "reviews",        "https://data.insideairbnb.com/thailand/central-thailand/bangkok/2025-09-26/data/reviews.csv.gz"),
    ("bangkok", "2025-09", "neighbourhoods", "https://data.insideairbnb.com/thailand/central-thailand/bangkok/2025-09-26/visualisations/neighbourhoods.geojson"),

    # SINGAPORE
    ("singapore", "2025-09", "listings",       "https://data.insideairbnb.com/singapore/sg/singapore/2025-09-28/data/listings.csv.gz"),
    ("singapore", "2025-09", "calendar",       "https://data.insideairbnb.com/singapore/sg/singapore/2025-09-28/data/calendar.csv.gz"),
    ("singapore", "2025-09", "reviews",        "https://data.insideairbnb.com/singapore/sg/singapore/2025-09-28/data/reviews.csv.gz"),
    ("singapore", "2025-09", "neighbourhoods", "https://data.insideairbnb.com/singapore/sg/singapore/2025-09-28/visualisations/neighbourhoods.geojson"),

    # TOKYO
    ("tokyo", "2025-09", "listings",       "https://data.insideairbnb.com/japan/kant%C5%8D/tokyo/2025-09-29/data/listings.csv.gz"),
    ("tokyo", "2025-09", "calendar",       "https://data.insideairbnb.com/japan/kant%C5%8D/tokyo/2025-09-29/data/calendar.csv.gz"),
    ("tokyo", "2025-09", "reviews",        "https://data.insideairbnb.com/japan/kant%C5%8D/tokyo/2025-09-29/data/reviews.csv.gz"),
    ("tokyo", "2025-09", "neighbourhoods", "https://data.insideairbnb.com/japan/kant%C5%8D/tokyo/2025-09-29/visualisations/neighbourhoods.geojson"),

    # LISBON
    ("lisbon", "2025-12", "listings",       "https://data.insideairbnb.com/portugal/lisbon/lisbon/2025-12-25/data/listings.csv.gz"),
    ("lisbon", "2025-12", "calendar",       "https://data.insideairbnb.com/portugal/lisbon/lisbon/2025-12-25/data/calendar.csv.gz"),
    ("lisbon", "2025-12", "reviews",        "https://data.insideairbnb.com/portugal/lisbon/lisbon/2025-12-25/data/reviews.csv.gz"),
    ("lisbon", "2025-12", "neighbourhoods", "https://data.insideairbnb.com/portugal/lisbon/lisbon/2025-12-25/visualisations/neighbourhoods.geojson"),
]

for city, snapshot, filetype, url in files:
    ext = "geojson" if filetype == "neighbourhoods" else "csv.gz"
    local_dir = os.path.join(RAW_DIR, city, snapshot)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{filetype}.{ext}")

    if os.path.exists(local_path):
        print(f"[SKIP] Already exists: {local_path}")
        continue

    print(f"[DOWNLOAD] {city} / {snapshot} / {filetype} ...")
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://insideairbnb.com/get-the-data/'
        })
        with urllib.request.urlopen(req, timeout=120) as response, \
             open(local_path, 'wb') as out_file:
            out_file.write(response.read())
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        print(f"[OK] {local_path} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"[ERROR] {city}/{snapshot}/{filetype}: {e}")

print("\nAll downloads complete.")