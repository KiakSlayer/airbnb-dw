import pandas as pd
import numpy as np
import os
import shutil
import random

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')

random.seed(42)
np.random.seed(42)

# Snapshot 1 source → Snapshot 2 destination
CITIES = [
    ("bangkok",   "2025-09", "2026-03"),
    ("singapore", "2025-09", "2026-03"),
    ("tokyo",     "2025-09", "2026-03"),
    ("lisbon",    "2025-12", "2026-03"),
]

def simulate_listings(df):
    """Simulate ~6 months of change on listings data"""
    df = df.copy()
    n = len(df)

    # ~15% of listings change price (±10–25%)
    price_mask = np.random.random(n) < 0.15
    if 'price' in df.columns:
        def adjust_price(val):
            try:
                import re
                cleaned = float(re.sub(r'[^\d.]', '', str(val)))
                factor = np.random.uniform(0.75, 1.25)
                return f"${cleaned * factor:.2f}"
            except:
                return val
        df.loc[price_mask, 'price'] = df.loc[price_mask, 'price'].apply(adjust_price)

    # ~8% of hosts flip superhost status
    if 'host_is_superhost' in df.columns:
        superhost_mask = np.random.random(n) < 0.08
        df.loc[superhost_mask, 'host_is_superhost'] = df.loc[superhost_mask, 'host_is_superhost'].apply(
            lambda x: 'f' if str(x).strip().lower() == 't' else 't'
        )

    # ~10% change response rate slightly
    if 'host_response_rate' in df.columns:
        response_mask = np.random.random(n) < 0.10
        def adjust_rate(val):
            try:
                cleaned = float(str(val).replace('%', '').strip())
                delta = np.random.randint(-10, 11)
                new_val = max(0, min(100, cleaned + delta))
                return f"{new_val}%"
            except:
                return val
        df.loc[response_mask, 'host_response_rate'] = df.loc[response_mask, 'host_response_rate'].apply(adjust_rate)

    # ~5% of listings change room_type
    if 'room_type' in df.columns:
        room_types = ['Entire home/apt', 'Private room', 'Shared room', 'Hotel room']
        room_mask = np.random.random(n) < 0.05
        df.loc[room_mask, 'room_type'] = np.random.choice(room_types, room_mask.sum())

    # ~3% of listings change name (simulate rebrand)
    if 'name' in df.columns:
        name_mask = np.random.random(n) < 0.03
        df.loc[name_mask, 'name'] = df.loc[name_mask, 'name'].apply(
            lambda x: str(x) + " [Renovated]" if pd.notna(x) else x
        )

    return df

def simulate_calendar(df):
    """Simulate calendar changes — price drift and availability shifts"""
    df = df.copy()
    n = len(df)

    if 'price' in df.columns:
        price_mask = np.random.random(n) < 0.20
        def adjust_price(val):
            try:
                import re
                cleaned = float(re.sub(r'[^\d.]', '', str(val)))
                factor = np.random.uniform(0.85, 1.20)
                return f"${cleaned * factor:.2f}"
            except:
                return val
        df.loc[price_mask, 'price'] = df.loc[price_mask, 'price'].apply(adjust_price)

    if 'available' in df.columns:
        avail_mask = np.random.random(n) < 0.05
        df.loc[avail_mask, 'available'] = df.loc[avail_mask, 'available'].apply(
            lambda x: 'f' if str(x).strip().lower() == 't' else 't'
        )

    return df

for city, snap1, snap2 in CITIES:
    src_dir = os.path.join(RAW_DIR, city, snap1)
    dst_dir = os.path.join(RAW_DIR, city, snap2)
    os.makedirs(dst_dir, exist_ok=True)
    print(f"\n[{city.upper()}] Generating snapshot {snap2} from {snap1}...")

    for filetype in ['listings', 'calendar', 'reviews']:
        src = os.path.join(src_dir, f"{filetype}.csv.gz")
        dst = os.path.join(dst_dir, f"{filetype}.csv.gz")

        if not os.path.exists(src):
            print(f"  [SKIP] {filetype} — source not found")
            continue

        print(f"  [READ] {filetype}...")
        df = pd.read_csv(src, compression='gzip', low_memory=False)

        if filetype == 'listings':
            df = simulate_listings(df)
        elif filetype == 'calendar':
            df = simulate_calendar(df)
        # reviews — copy as-is (new reviews would come naturally)

        df.to_csv(dst, compression='gzip', index=False)
        size_mb = os.path.getsize(dst) / (1024 * 1024)
        print(f"  [OK] {dst} ({size_mb:.1f} MB)")

    # Copy neighbourhoods.geojson unchanged (boundaries don't change)
    geo_src = os.path.join(src_dir, 'neighbourhoods.geojson')
    geo_dst = os.path.join(dst_dir, 'neighbourhoods.geojson')
    if os.path.exists(geo_src):
        shutil.copy2(geo_src, geo_dst)
        print(f"  [OK] neighbourhoods.geojson copied")

print("\nSnapshot 2 generation complete.")
print("Your raw folder now has 2 snapshots per city — ready for S3 upload.")