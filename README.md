# Airport Big Data Pipeline (Local Lab)

Starter project untuk demonstrasi:
- SeaweedFS Data Lake: 1 master + 3 volume-server nodes
- Replikasi SeaweedFS `002` (2 salinan tambahan; target 3 salinan pada 3 volume servers)
- Bucket Bronze, Silver, Gold
- MongoDB single node
- Python batch ingestion ke Data Lake dan MongoDB

## Prasyarat
1. Docker Desktop sudah terpasang dan sedang berjalan.
2. VS Code.
3. Python 3.10+.

> Ketiga volume-server di project ini adalah tiga node logis berupa container Docker pada satu komputer. Untuk tiga mesin fisik/VM, jalankan tiap volume server pada host terpisah dan sesuaikan alamat jaringan.

## Jalankan di Windows PowerShell
Buka folder project di VS Code, lalu Terminal > New Terminal.

```powershell
docker --version
docker compose version
docker compose up -d
docker compose ps
```

Tunggu semua container berstatus Up. Dashboard SeaweedFS Master: http://localhost:9333
SeaweedFS Filer: http://localhost:8888
MongoDB: localhost:27017

Buat virtual environment dan install library:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jika PowerShell menolak aktivasi:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Jalankan ingestion:

```powershell
python scripts/ingest.py
```

Jalankan verifikasi:

```powershell
python scripts/verify.py
```

## Bukti 3 node
Periksa log registrasi volume server:
```powershell
docker compose logs --tail=80 volume1 volume2 volume3
```

Periksa file fisik pada masing-masing volume server:
```powershell
docker exec airport-volume1 sh -c "find /data -type f"
docker exec airport-volume2 sh -c "find /data -type f"
docker exec airport-volume3 sh -c "find /data -type f"
```

Dengan `-defaultReplication=002`, SeaweedFS dikonfigurasi membuat dua salinan tambahan pada volume server lain. Pastikan ketiga volume server sudah terdaftar sebelum ingestion dilakukan. Simpan screenshot dari ketiga perintah di atas sebagai bukti; jangan hanya mengandalkan status container `Up`.

## Bukti MongoDB
```powershell
docker exec -it airport-mongodb mongosh
```

Di prompt mongosh:
```javascript
use airport_database
db.flight_records.countDocuments()
db.flight_records.find().pretty()
```
Keluar:
```javascript
exit
```

## Stop dan reset
Stop tanpa menghapus data:
```powershell
docker compose down
```

Reset total (menghapus seluruh data volume; gunakan hanya jika ingin mulai dari nol):
```powershell
docker compose down -v
```

## Catatan
- Ini adalah batch ingestion demonstrasi. Data CSV contoh dapat diganti dengan data penerbangan yang Anda miliki.
- Bronze menyimpan data asli; Silver menyimpan data bersih dalam Parquet; Gold menyimpan agregasi untuk analisis.
- MongoDB menyimpan dokumen penerbangan untuk query operasional/serving.
- Untuk streaming real-time, tambahkan Kafka/Connect/NiFi setelah pipeline batch ini berhasil.
