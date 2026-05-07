import boto3
import os

BUCKET = "airbnb-dw-856480643132"
s3 = boto3.client("s3", region_name="ap-southeast-1")

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')
total_files = 0
total_mb = 0

for city in os.listdir(base):
    city_path = os.path.join(base, city)
    if not os.path.isdir(city_path):
        continue
    for snapshot in os.listdir(city_path):
        snap_path = os.path.join(city_path, snapshot)
        if not os.path.isdir(snap_path):
            continue
        for filename in os.listdir(snap_path):
            local_path = os.path.join(snap_path, filename)
            s3_key = f"raw/city={city}/snapshot={snapshot}/{filename}"
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            print(f"[UPLOAD] {s3_key} ({size_mb:.1f} MB)...")
            s3.upload_file(local_path, BUCKET, s3_key)
            total_files += 1
            total_mb += size_mb
            print(f"  [OK]")

print(f"\nDone! {total_files} files uploaded ({total_mb:.1f} MB total)")