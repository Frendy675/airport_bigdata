import boto3
from botocore.client import Config
from pymongo import MongoClient

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:8333",
    aws_access_key_id="admin",
    aws_secret_access_key="secret",
    region_name="us-east-1",
    config=Config(s3={"addressing_style": "path"}),
)

print("=== DATA LAKE: BUCKET DAN OBJEK ===")
for bucket in ["bronze", "silver", "gold"]:
    print(f"\nBucket: {bucket}")
    try:
        response = s3.list_objects_v2(Bucket=bucket)
        for item in response.get("Contents", []):
            print(f" - {item['Key']} ({item['Size']:,} bytes)")
    except Exception as exc:
        print(f"Belum dapat dibaca: {exc}")

print("\n=== MONGODB ===")
client = MongoClient("mongodb://127.0.0.1:27018")
coll = client["airport_database"]["flight_records"]
print("Database: airport_database")
print("Collection: flight_records")
print("Jumlah dokumen:", f"{coll.count_documents({}):,}")
print("\nContoh 3 dokumen:")
for doc in coll.find().limit(3):
    print(doc)
