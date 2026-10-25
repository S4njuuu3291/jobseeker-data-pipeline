# Deployment Lambda ZIP + Layers

Bronze dan Silver memakai runtime AWS Lambda Python 3.12, arsitektur x86_64,
source ZIP, dan dependency layers. Tidak ada Playwright, Chromium, webdriver,
Docker build, push ECR, atau image pull pada deployment/runtime pipeline ini.
Docker Compose Superset lokal tetap terpisah dari pipeline Lambda.

## Paket dan layer

| Fungsi | Source ZIP | Layer | Isi |
| --- | --- | --- | --- |
| `jobscraper-scraper-zip[-dev]` | `bronze.zip` | `jobscraper-data-deps[-dev]` + `jobscraper-bronze-deps[-dev]` | pandas, NumPy, PyArrow, Pandera, boto3, dotenv, httpx; BeautifulSoup |
| `jobscraper-silver-layer-zip[-dev]` | `silver.zip` | `jobscraper-data-deps[-dev]` + `jobscraper-silver-deps[-dev]` | Shared data dependencies; OpenAI SDK untuk DeepSeek dan json-repair |
| `jobscraper-slack-alert[-dev]` | `slack.zip` | `jobscraper-slack-alert-layer[-dev]` | requests dan boto3 |

`[-dev]` berarti suffix hanya untuk dev. Prod tanpa suffix.
`python/` di root ZIP layer menjadi `/opt/python` pada Lambda.
Source code memuat hanya Python yang dibutuhkan, tanpa `.env`, catatan API,
respons mentah, test, atau browser utilities. Playwright hanya tersisa sebagai
dependensi development untuk tes utilitas lama; bukan dependensi layer.

Builder memakai wheel manylinux CPython 3.12 x86_64 dengan versi transitive
dari `poetry.lock`, tidak menyalin library conda/OS lokal. Header kompilasi,
cache bytecode, dan test dependency dihapus. Model botocore dibatasi ke S3, SSM, STS, Athena, Glue, dan KMS. Arrow Flight
yang tidak digunakan dibuang; library yang dibutuhkan Parquet dipertahankan.
Simbol native yang tidak diperlukan dihapus dengan GNU strip. Metadata package,
resource runtime, dan timezone data dipertahankan. Source dan layer diarsip dengan timestamp
stabil. CI menghentikan deploy jika code + layers suatu fungsi mencapai 250 MiB.

ZIP diunggah Terraform ke bucket private dan versioned
`jobscraper-lambda-artifacts-<account-id>[-dev]`, key berdasarkan SHA-256.
Layer data dapat melebihi batas upload langsung 50 MB; upload lewat S3 tetap
mendukungnya, dengan batas total uncompressed 250 MiB per fungsi tetap berlaku.
Manifest ukuran build ada di `.lambda-build/manifest.json`.

## Alur runtime

1. EventBridge memicu pukul **11:00 dan 16:00 WIB**, sesuai cron UTC `04:00`
   dan `09:00` yang sudah ada. EventBridge bukan Lambda.
2. AWS Step Functions menjalankan state `ScrapersParallel` dengan lima cabang.
   Semuanya memanggil **fungsi Bronze yang sama** dengan payload berbeda:
   `{"platform":"kalibrr"}`, `glints`, `jobstreet`, `dealls`, `techinasia`.
   Jadi ada lima invocation paralel, bukan lima definisi fungsi scraper.
3. Bronze ZIP memakai **data layer + bronze layer**. Membaca manifest platform
   dari S3, memanggil listing API, menyaring native ID lama, lalu meminta detail
   untuk lowongan baru bila perlu. Glints memakai HTTP HTML detail tanpa browser;
   Dealls/Jobstreet memakai API detail. Kalibrr/Tech in Asia memakai listing.
4. Bronze membentuk **24 kolom inti**, menyimpan Parquet ke
   `s3://jobscraper-bronze-data-8424560[-dev]/platform=<platform>/ingestion_date=YYYY-MM-DD/<platform>_<HHMMSS>.parquet`.
   Sesudah upload berhasil, manifest native ID diperbarui di
   `manifests/<platform>/job_ids.parquet`. Jika tidak ada lowongan baru, upload
   platform tersebut dilewati. Perilaku penggantian file Bronze per tanggal
   mengikuti implementasi pipeline yang sudah ada.
5. Setelah seluruh cabang Bronze berhasil, Step Functions memanggil
   **Silver ZIP**, memakai **data layer + silver layer**. Silver membaca
   Bronze tanggal WIB hari ini, menjalankan parsing AI, menggabungkan hasil AI
   ke kolom Bronze yang kosong, menormalisasi lokasi/tipe, lalu memvalidasi data.
   Implementasi saat ini masih memanggil parser per baris; ini bukan optimasi
   skip AI untuk baris lengkap.
6. Silver menulis Parquet ke
   `s3://jobscraper-silver-data-8424560[-dev]/ingestion_date=YYYY-MM-DD/job_data_YYYY-MM-DD.parquet`.
   Rerun mengganti key tanggal yang sama. Nilai tidak diketahui tetap nullable.
7. **Glue Data Catalog** mendefinisikan tabel `jobscraper_silver_table[_dev]`
   di database `jobscraper_db[_dev]`. **Partition projection** menunjuk langsung
   ke folder tanggal di S3: tidak perlu Glue crawler, MSCK REPAIR, atau Lambda
   tambahan. Setelah upload Silver selesai, tabel siap diquery oleh Athena.
8. View Athena `v_jobscraper_clean` dan `v_job_*` menjadi lapisan analitik/Gold.
   Gold berupa view SQL, bukan file baru di bucket Gold. CI menginstal atau
   memperbarui view untuk environment yang dipilih sesudah Terraform apply.
9. Step Functions memanggil **Slack ZIP + slack layer**. Fungsi mengambil
   webhook dari SSM, query view melalui Athena, lalu mengirim notifikasi.
   Superset juga dapat membaca tabel/view Athena. Slack tidak memindahkan data
   lake ke bucket lain. Kegagalan Slack tetap tidak menggagalkan ingestion;
   kegagalan Silver kini dilempar sebagai error Lambda agar workflow berhenti.

Orkestrasi utamanya **AWS Step Functions**; penjadwalnya **EventBridge**.
Lambda failures dan state machine failures dimonitor CloudWatch/SNS. Retry
Step Functions tetap mengikuti policy di ASL. DLQ Lambda disiapkan, tetapi
invocation sinkron oleh Step Functions mengandalkan retry/error state machine;
DLQ bukan pengganti penanganan kegagalan invocation sinkron.

## CI/CD

- Pull request: offline tests → build ZIP/layers → smoke test tanpa site-packages
  lokal → batas ukuran → Terraform format/validate dev dan prod. Tidak deploy.
- Push `dev`: langkah yang sama → OIDC AWS → Terraform plan → apply saved plan
  untuk dev → install Athena views dev.
- Push `main`: alur yang sama untuk prod, memakai GitHub environment `main_env`.
- Workflow dispatch: input `dev` atau `prod` menentukan target secara eksplisit.
- Deploy tidak dibatalkan di tengah Terraform apply; concurrency diserialisasi
  per environment. Tidak ada apply bootstrap, build image, atau apply kedua.
- Unit tests berada di `tests/`; script percobaan live di `scripts/` tidak
  dijalankan sebagai unit test CI.

## Secrets dan migrasi

### Lake Formation untuk deployment view

Settings Lake Formation berlaku untuk satu akun/region dan hanya dikelola oleh
state prod. State dev melepaskan alamat settings lama tanpa menghapus settings
AWS (`removed` dengan `destroy = false`), sehingga deploy dev tidak menimpa
daftar admin prod. Role GitHub Actions menjadi data lake admin untuk mengelola
grant; identitas admin Slack dev/prod yang digunakan pipeline tetap dipertahankan.

Masing-masing environment mengelola grant database-nya sendiri. Role deployment
mendapat `CREATE_TABLE`/`DESCRIBE` pada database dan
`ALTER`/`DESCRIBE`/`DROP`/`SELECT` pada seluruh tabel/view database tersebut,
termasuk view yang sebelumnya dibuat manual. `SELECT` dapat diteruskan agar
deployment dapat mengelola akses view. Slack mendapat `DESCRIBE` database serta
`DESCRIBE`/`SELECT` tabel/view. IAM `AdministratorAccess` saja tidak menggantikan
grant Lake Formation. Terraform memasang grant sebelum CI menjalankan SQL view.

Untuk migrasi pertama, deploy prod terlebih dahulu agar role deployment terdaftar
sebagai data lake admin, lalu deploy dev. Setelah itu urutan deploy bebas.

SSM SecureStrings dibaca saat invocation dengan `WithDecryption=True`:

| Pemakai | Parameter prod | Parameter dev |
| --- | --- | --- |
| Glints | `/jobscraper/glints/cookie` | `/jobscraper/glints/cookie-dev` |
| Tech in Asia | `/jobscraper/techinasia/api_key` | `/jobscraper/techinasia/api_key-dev` |
| Silver AI | `/jobscraper/deepseek/api_key` | `/jobscraper/deepseek/api_key-dev` |
| Slack | `/jobscraper/slack/webhook_url` | `/jobscraper/slack/webhook_url-dev` |

Terraform membuat placeholder untuk parameter baru; isi nilai sebenarnya di SSM
sebelum menjalankan pipeline. Cookie Glints perlu diperbarui jika kedaluwarsa.
Tidak ada nilai secret pada ZIP, log build, atau GitHub artifact. Parameter
DeepSeek lama tetap dipakai; value-nya tidak lagi dibaca Terraform ke environment
Lambda. IAM runtime hanya memberi `GetParameter` pada parameter yang dibutuhkan.

AWS tidak bisa mengubah package type Image menjadi ZIP langsung. Terraform
membuat fungsi fisik baru dengan nama `*-zip`, memperbarui ARN di Step Functions,
lalu menghapus fungsi container lama. `create_before_destroy` mengurangi jeda;
jalankan deploy ketika tidak ada execution lama yang sedang berlangsung.
Nama state machine, bucket Bronze/Silver, tabel Glue, partisi, dan manifest
konsisten dengan deployment sebelumnya. Repo ECR lama tetap disimpan untuk
rollback dengan `removed { lifecycle { destroy = false } }`: Terraform melepas
pengelolaannya tanpa menghapus image. Deployment baru tidak membuat repo ECR.
Runtime dan CI tidak menggunakannya lagi. Memakai Terraform minimal 1.7.

## Build dan pemeriksaan lokal

```bash
conda activate basic_dev
python scripts/build_lambda_packages.py
cat .lambda-build/manifest.json
terraform -chdir=terraform/envs/dev init
terraform -chdir=terraform/envs/dev validate
terraform -chdir=terraform/envs/dev plan -var='env=dev'
python scripts/deploy_athena_views.py --environment dev --dry-run
```

Build menjalankan smoke test Python `-S` dengan hanya code/layer directories:
import semua scraper/Silver/Slack dan Parquet round trip. Artefak CI inilah yang
dipakai pada Terraform deployment; source changes memicu hash/update kode dan
perubahan dependency memicu versi layer baru. Build dan validasi lokal tidak
menjalankan Terraform apply atau mengirim notifikasi Slack.

Ukuran setelah optimasi (MiB, code + semua layer uncompressed): Bronze 171.96, Silver 176.32, Slack 7.24. Smoke test mencakup impor, Parquet round trip, dan inisialisasi client enam layanan AWS secara offline.
