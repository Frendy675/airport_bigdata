from pathlib import Path
from io import BytesIO
import json
import time

import boto3
import pandas as pd
from botocore.client import Config
from pymongo import MongoClient, ReplaceOne
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
CSV_FILE = ROOT / "data" / "flight_schedule.csv"
CHUNK_SIZE = 5000

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:8333",
    aws_access_key_id="admin",
    aws_secret_access_key="secret",
    region_name="us-east-1",
    config=Config(s3={"addressing_style": "path"}),
)

mongo = MongoClient("mongodb://127.0.0.1:27018", serverSelectionTimeoutMS=5000)
db = mongo["airport_database"]
collection = db["flight_records"]

def wait_for_services():
    for attempt in range(30):
        try:
            s3.list_buckets()
            mongo.admin.command("ping")
            print("S3 Gateway dan MongoDB siap.")
            return
        except Exception as exc:
            print(f"Menunggu layanan siap ({attempt + 1}/30): {exc}")
            time.sleep(2)
    raise RuntimeError("Layanan belum siap. Periksa docker compose logs.")

def ensure_bucket(name):
    try:
        s3.create_bucket(Bucket=name)
        print(f"Bucket '{name}' berhasil dibuat.")

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")

        if error_code in [
            "BucketAlreadyOwnedByYou",
            "BucketAlreadyExists"
        ]:
            print(f"Bucket '{name}' sudah tersedia, dilewati.")
        else:
            raise

def make_json_safe(df):
    # MongoDB tidak menerima NaN/NaT; ubah nilai kosong menjadi null.
    records = json.loads(df.to_json(orient="records", date_format="iso"))
    return records

def main():
    wait_for_services()

    # 1. Extract: baca file dataset asli
    df_raw = pd.read_csv(CSV_FILE)
    print(f"Dataset terbaca: {len(df_raw):,} baris, {len(df_raw.columns)} kolom.")

    # 2. Bronze: simpan file asli tanpa perubahan
    ensure_bucket("bronze")
    s3.upload_file(str(CSV_FILE), "bronze", "flights/flight_schedule_raw.csv")
    print("BRONZE: file CSV asli berhasil disimpan.")

    # 3. Silver: validasi, pembersihan, dan standardisasi
    df = df_raw.copy()
    df = df.drop_duplicates(subset=["Flight_ID"])
    datetime_cols = [
        "Scheduled_Departure", "Actual_Departure",
        "Scheduled_Arrival", "Actual_Arrival"
    ]
    for col in datetime_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df["Delay_Minutes"] = pd.to_numeric(df["Delay_Minutes"], errors="coerce").fillna(0).astype("int64")
    df["Passenger_Count"] = pd.to_numeric(df["Passenger_Count"], errors="coerce").fillna(0).astype("int64")

    # Baris tanpa waktu aktual tidak otomatis dihapus:
    # penerbangan Cancelled/Diverted dapat memang tidak memiliki waktu aktual.
    for col in ["Flight_ID", "Airline_Code", "Airline_Name", "Origin_Airport",
                "Destination_Airport", "Flight_Status"]:
        df[col] = df[col].astype("string").str.strip()

    silver_buffer = BytesIO()
    df.to_parquet(silver_buffer, index=False, engine="pyarrow", compression="snappy")
    silver_buffer.seek(0)
    ensure_bucket("silver")
    s3.upload_fileobj(silver_buffer, "silver", "flights/flight_schedule_clean.parquet")
    print(f"SILVER: {len(df):,} baris bersih disimpan dalam Parquet.")

    # 4. Gold: agregasi untuk descriptive analytics
    by_airline_status = (
        df.groupby(["Airline_Code", "Airline_Name", "Flight_Status"], dropna=False)
          .agg(
              total_flights=("Flight_ID", "count"),
              total_passengers=("Passenger_Count", "sum"),
              average_delay_minutes=("Delay_Minutes", "mean"),
          )
          .reset_index()
    )

    by_route = (
        df.groupby(["Origin_Airport", "Destination_Airport"], dropna=False)
          .agg(
              total_flights=("Flight_ID", "count"),
              total_passengers=("Passenger_Count", "sum"),
              average_delay_minutes=("Delay_Minutes", "mean"),
          )
          .reset_index()
    )

    ensure_bucket("gold")
    s3.put_object(
        Bucket="gold",
        Key="analytics/airline_status_summary.json",
        Body=by_airline_status.to_json(orient="records", indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    s3.put_object(
        Bucket="gold",
        Key="analytics/route_summary.json",
        Body=by_route.to_json(orient="records", indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print("GOLD: ringkasan maskapai/status dan rute berhasil disimpan.")

    # 5. Jalur ingestion yang sama ke MongoDB; upsert per batch untuk hemat memori.
    total_upserted = 0
    for start in range(0, len(df), CHUNK_SIZE):
        chunk = df.iloc[start:start + CHUNK_SIZE]
        records = make_json_safe(chunk)
        ops = []
        for record in records:
            flight_id = str(record["Flight_ID"])
            ops.append(ReplaceOne(
                {"_id": flight_id},
                {"_id": flight_id, **record},
                upsert=True
            ))
        if ops:
            result = collection.bulk_write(ops, ordered=False)
            total_upserted += result.upserted_count
        print(f"MONGODB: diproses {min(start + CHUNK_SIZE, len(df)):,}/{len(df):,} dokumen.")

    print(f"MongoDB total dokumen: {collection.count_documents({}):,}")
    print("INGESTION SELESAI.")

if __name__ == "__main__":
    main()
