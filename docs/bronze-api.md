# Bronze API — 24 kolom inti

Implementasi LANJUTAN 2 memakai lima `src/scraper/jobscraper_<platform>.py` berbasis API.
`src/main/main.py` sekarang menjalankan adapter API tersebut, termasuk melalui handler Lambda yang sudah ada. Tidak ada deployment atau upload S3 live yang dilakukan saat implementasi.

## Skema

`src/scraper/bronze_schema.py` mendefinisikan tepat **24 kolom**, sama dengan kolom wajib `JOB_SILVER_SCHEMA`:

| Kelompok | Kolom |
| --- | --- |
| Identitas dan ingestion | `job_id`, `job_title`, `job_url`, `platform`, `scraped_at`, `keyword` |
| Deskripsi dan perusahaan | `job_description`, `company_name`, `company_industry` |
| Kategori dan lokasi | `role`, `location`, `job_type`, `seniority`, `work_mode` |
| Gaji | `salary_min`, `salary_max`, `salary_currency`, `salary_period` |
| Persyaratan dan benefit | `experience_min`, `experience_max`, `education`, `skills`, `benefits` |
| Tanggal | `posting_date` |

Silver normal juga menambahkan **12 kolom operasional AI**, sehingga output normal Silver berjumlah **36 kolom**. Dua puluh empat adalah jumlah kolom inti, bukan seluruh output operasional. `ingestion_date` merupakan partisi.

- `job_id` adalah **native ID lowongan dalam bentuk string**, bukan hash URL. ID bersifat spesifik per platform; manifest dipisah per platform.
- `salary_min/max` dan `experience_min/max` memakai integer nullable; semua kolom lainnya string nullable kecuali konteks ingestion wajib.
- `skills`/`benefits` berupa string JSON array. Array kosong yang tidak mengumumkan informasi disimpan `null` untuk enrichment berikutnya.
- Nilai yang tidak diketahui tetap `null`. Kode pendidikan/pengalaman tidak diperlakukan sebagai tahun/jenjang tanpa lookup terverifikasi. Seniority tidak ditebak dari rentang pengalaman.
- HTML dibersihkan; narasi tugas, kualifikasi, dan about company digabung dengan label bagian. About company hanya ditambahkan jika tersedia dari sumber.
- Kategori role/industri sumber dipertahankan untuk normalisasi lanjutan; kategori luas belum tentu role kanonik final.
- Gaji tersembunyi tidak diambil dari Glints/Kalibrr. Tech in Asia `0/0` diperlakukan sebagai nominal yang belum diumumkan, bukan gaji nyata nol.

## Request per platform

| Platform | Listing | Detail/konteks tambahan |
| --- | --- | --- |
| Dealls | GET `https://api.sejutacita.id/v1/explore-job/job` | GET `https://api.sejutacita.id/v1/job-portal/job/public/slug/{slug}`; responsibilities, requirements, jobRole, company.description |
| Glints | POST `https://glints.com/api/v2-alc/graphql?op=searchJobsV3` | GET halaman lowongan; BeautifulSoup membaca `__NEXT_DATA__` dan JSON-LD, tanpa browser driver. Termasuk deskripsi, benefits, about company. |
| Jobstreet | GET `https://id.jobstreet.com/api/jobsearch/v5/search` | POST `https://id.jobstreet.com/graphql`, operation `jobDetails`; content/content2, profil perusahaan, benefit, label gaji |
| Kalibrr | GET `https://kalibrr.id/kjs/job_board/search` | Listing sudah berisi description, qualifications, company description, dan metadata; tanpa request detail tambahan. |
| Tech in Asia | POST `https://219wx3mpv4-dsn.algolia.net/1/indexes/*/queries` | Deskripsi sudah di Algolia. GET halaman job untuk canonical URL dan halaman perusahaan untuk deskripsi perusahaan, jika dapat diakses; cache perusahaan selama satu batch detail. |

Filter judul, keyword, pagination, batas halaman default (Kalibrr 3, lainnya 1), serta timestamp WIB dipertahankan. HTTP sementara dicoba maksimal tiga kali. Glints listing membutuhkan `GLINTS_COOKIE`; Algolia membutuhkan `TECHINASIA_API_KEY`. Tidak ada kredensial yang ditanam di kode atau dibaca otomatis dari catatan request. Query detail Jobstreet publik tidak membutuhkan Bearer token pada sampel yang diuji.

Deskripsi pendidikan/pengalaman hanya diparsing untuk pola eksplisit. Skill naratif dan benefit yang belum memiliki field langsung tetap dapat diisi AI nanti dari `job_description`.

## Manifest dan penyimpanan

1. Baca `manifests/{platform}/job_ids.parquet`.
2. Request listing dan filter judul.
3. Lewati native ID yang sudah tersimpan; duplikat dalam batch juga dilewati.
4. Request detail hanya untuk lowongan baru. Detail wajib Dealls/Glints/Jobstreet yang gagal dikeluarkan dari batch, sehingga tidak masuk manifest dan dapat dicoba pada run berikutnya.
5. Validasi tepat 24 kolom dan tipe data, lalu upload Parquet ke `platform={platform}/ingestion_date={YYYY-MM-DD}/`.
6. Setelah upload sukses, simpan gabungan ID lama + ID baru ke manifest yang sama. Set `seen_ids` milik pemanggil tidak dimutasi adapter.

Nama file memakai timestamp + UUID untuk mencegah overwrite. Batch baru **tidak menghapus file hari yang sama**: menghapus batch lama sambil mempertahankan manifest akan menghilangkan data yang tidak lagi diambil ulang. Schema Arrow ditetapkan eksplisit agar kolom seluruhnya null tetap bertipe string/int64, bukan tipe null.

Manifest yang belum ada berarti first run. Error akses, error jaringan, atau manifest rusak menghentikan run; tidak dianggap riwayat kosong.

### Transisi manifest hash lama

Adapter juga memeriksa MD5 URL listing yang dinormalisasi seperti scraper lama. Hash lama yang cocok tetap dilewati. Hash lama dipertahankan ketika manifest diperbarui; native ID baru ditambahkan untuk data baru.

**Batas kompatibilitas:** hash tidak dapat dibalik menjadi native ID. Jika URL lama berbeda host/slug/path dari URL listing yang direkonstruksi sekarang, hash lama tidak dapat dicocokkan otomatis. Jaminan deduplikasi dengan native ID berlaku setelah ID tersebut masuk manifest. Migrasi penuh histori hash dengan URL berbeda memerlukan pemetaan dari histori Bronze; implementasi ini tidak menghapus/reset manifest lama.

## Batas sumber yang sudah diketahui

- Sampel Kalibrr tersimpan memuat 20 judul tidak relevan terhadap `data engineer`; filter judul existing menghasilkan nol record. Kontrak filter pencarian perlu diverifikasi sebelum menganggap hasilnya lengkap.
- URL canonical Tech in Asia tidak ada pada Algolia. Adapter mencoba HTTP pada URL ID lalu memakai `<link rel="canonical">` jika tersedia. Pengecekan live mendapat HTTP 403; jika gagal, URL berbasis ID tetap merupakan fallback **yang belum terverifikasi**, dengan warning. `TECHINASIA_JOB_URL_TEMPLATE` dapat diisi rute terverifikasi dengan placeholder `{id}`. About company yang tidak dapat diakses tidak dikarang. `external_link` dapat menunjuk daftar karier umum, sehingga tidak otomatis dipakai sebagai URL lowongan.
- Tanggal aktivasi Kalibrr dan zona waktu `published_at` Tech in Asia masih memerlukan aturan sumber; nilainya dipertahankan tanpa mengarang zona waktu.
- Field pengalaman Tech in Asia dapat bertentangan dengan teks. Mapping memakai angka field; teks asli dipertahankan untuk pemeriksaan/normalisasi berikutnya.

## Pengujian lokal

Preview tidak menyentuh S3 atau manifest:

```bash
conda activate basic_dev
python -m src.scraper.jobscraper_dealls --keyword "data engineer" --output /tmp/dealls_bronze.json
python -m src.scraper.jobscraper_glints --keyword "data engineer" --output /tmp/glints_bronze.json
python -m src.scraper.jobscraper_jobstreet --keyword "data engineer" --output /tmp/jobstreet_bronze.json
python -m src.scraper.jobscraper_kalibrr --keyword "data engineer" --output /tmp/kalibrr_bronze.json
python -m src.scraper.jobscraper_techinasia --keyword "data engineer" --output /tmp/techinasia_bronze.json
```

Pipeline upload tetap melalui entrypoint yang sama:

```bash
python -m src.main.main --platform dealls --keywords "data engineer"
```

**Silver sudah disesuaikan:** AI hanya diminta mengisi kolom kosong per baris. Nilai hasil AI harus didukung kutipan sumber yang lolos pemeriksaan kode. Nilai Bronze yang sudah terisi dipertahankan; tidak ada concat kolom duplikat atau default tebakan. Rincian di `docs/silver-enrichment.md`.

## Pemeriksaan hasil dan kegagalan keyword

Reader membaca seluruh Parquet pada prefix, menjumlahkan baris fisik, dan memperingatkan ID duplikat lintas batch. Untuk memeriksa Bronze tanpa bergantung pada Silver:

```bash
python src/utils/data_reader.py --date 2026-10-23 --platform kalibrr --layer bronze
```

Jika request sebuah keyword gagal setelah retry, pipeline melanjutkan keyword lain dan menyimpan hasil yang berhasil sebelum memperbarui manifest. Run kemudian melaporkan `PARTIAL` dengan jumlah yang berhasil diunggah dan daftar keyword gagal; CLI keluar dengan status 1. Pada retry, native ID yang sudah tersimpan dilewati. Jika seluruh keyword gagal, tidak ada upload atau update manifest.
