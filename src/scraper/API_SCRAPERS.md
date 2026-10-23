# Bronze API adapters — versi listing sementara

Lima modul `jobscraper_<platform>_api.py` memakai HTTP JSON (`httpx`), tanpa Playwright atau pengambilan HTML halaman lowongan. BeautifulSoup hanya mengubah string HTML yang sudah ada di respons API menjadi teks.

Antarmuka tiap modul mengikuti modul existing:

```python
await collect_job_cards(url, headless=True, max_pages=1)
await scrape_job_details(results, headless=True)
await jobscraper_dealls(url, headless=True, seen_ids=set(), max_pages=1)
```

Nama fungsi utama mengikuti platform: `jobscraper_glints`, `jobscraper_jobstreet`, `jobscraper_kalibrr`, `jobscraper_dealls`, dan `jobscraper_techinasia`. `headless` diterima untuk kompatibilitas. `scrape_job_details` mempertahankan antarmuka tahap detail dan logging, tetapi memakai teks listing yang sudah dipetakan; tidak memanggil endpoint detail.

## Output dan alur

Fungsi utama mengembalikan `list[dict]` dengan tujuh field: `job_id`, `job_title`, `company_name`, `job_url`, `platform`, `scraped_at`, `job_description`. `keyword` tetap ditambahkan orchestrator, seperti existing. Preview CLI juga menambahkan `keyword` agar bentuk JSON sesuai record yang akan diunggah.

- `job_id`: MD5 URL setelah query, params, dan fragment dihapus, sama dengan algoritma existing.
- `scraped_at`: `%Y%m%d_%H%M%S` dalam WIB.
- Filter judul memakai `is_relevant_title` existing. Nama perusahaan kosong menjadi `Unknown`.
- `seen_ids` dan duplikat dalam batch disaring; set milik pemanggil tidak diubah.
- Error HTTP/GraphQL atau kontrak yang tidak sesuai diteruskan sebagai error, bukan dianggap pencarian kosong. Error sementara dicoba maksimal tiga kali. Log aplikasi tidak menampilkan cookie atau API key.
- Pagination dibatasi `max_pages` dan berhenti jika hasil habis atau server mengulang halaman. Default satu halaman; Kalibrr tiga halaman, mengikuti listing awal dan dua klik Load More existing. Ukuran halaman mengikuti contract: Dealls 40, Glints 30, Jobstreet default server, Kalibrr 20, Tech in Asia 9.

Modul baru disediakan untuk pengujian terpisah. `src/main/main.py` masih mengimpor scraper existing. Modul API tidak mengunggah S3 atau memperbarui manifest sendiri. Jika nanti dipilih oleh orchestrator yang sama, tujuan Parquet tetap ditentukan `upload_to_s3`: `platform={platform}/ingestion_date={YYYY-MM-DD}/{platform}_{HHMMSS}.parquet`; manifest tetap `manifests/{platform}/job_ids.parquet`.

## Kekurangan data yang disetujui untuk versi sementara

| Platform | Isi `job_description` dari listing | Batasan |
|---|---|---|
| Dealls | Judul, perusahaan, kota, tipe kerja, rentang gaji bila ada, skill, preferensi kandidat, sektor, insight perusahaan | Deskripsi pekerjaan, kualifikasi naratif, dan detail perusahaan lengkap tidak tersedia. |
| Glints | Judul, perusahaan, lokasi, tipe/aturan kerja, pendidikan, pengalaman, skill, gaji yang boleh ditampilkan, industri, kategori | Deskripsi pekerjaan lengkap tidak tersedia. Memerlukan sesi browser yang valid. |
| Jobstreet | Judul, perusahaan, lokasi, tipe kerja, gaji, teaser, bullet points, klasifikasi | Teaser bukan deskripsi pekerjaan lengkap. |
| Kalibrr | Deskripsi, kualifikasi, lokasi, tipe kerja, pengalaman, perks, deskripsi/industri perusahaan, gaji yang boleh ditampilkan | Endpoint HTTP 200 belum membuktikan filter `text` diterapkan. Respons tersimpan memuat 20 lowongan tidak relevan; filter judul existing dapat menghasilkan nol record bronze. |
| Tech in Asia | Deskripsi HTML dari Algolia diubah menjadi teks, ditambah tipe kerja, pengalaman, lokasi, skill, gaji yang boleh ditampilkan, ukuran/industri perusahaan | Tidak memuat seluruh teks/UI halaman detail atau URL canonical. |

Teks listing digabung dengan label bagian dan disimpan sebagai satu string. Ini mempertahankan bentuk kolom bronze, tetapi belum menjamin cakupan informasi yang sama dengan hasil browser. Atribut yang tidak tersedia tidak dikarang; nilai metadata yang kosong dapat dilewati.

## URL dan kompatibilitas manifest

Listing tidak selalu memuat URL lengkap. Adapter merekonstruksi URL Dealls dari slug lowongan/perusahaan, Glints dari slug judul/ID, Jobstreet dari ID, dan Kalibrr dari company code/ID/slug. Rute ini perlu dibandingkan dengan `job_url` browser existing saat pengujian. Perbedaan host, bahasa, slug, atau trailing slash mengubah hash karena normalizer existing hanya menghapus parameter URL. Jangan mengasumsikan deduplikasi terhadap manifest lama sudah terbukti hanya karena algoritma hash sama.

Tech in Asia tidak memuat slug URL dalam respons Algolia. Default sementara `https://www.techinasia.com/jobs/{id}` adalah URL berbasis ID yang **belum diverifikasi sebagai URL detail yang valid/canonical**, sehingga hash berpotensi berbeda dari manifest lama. `TECHINASIA_JOB_URL_TEMPLATE` dapat diisi template URL yang telah diverifikasi dengan placeholder `{id}`. Kontrak URL/detail tambahan tetap diperlukan jika website memakai slug yang tidak tersedia di listing.

## Pengujian lokal per modul

Aktifkan `basic_dev` dan jalankan dari root proyek:

```bash
conda activate basic_dev
python -m src.scraper.jobscraper_dealls_api --keyword "data engineer" --output /tmp/dealls_bronze.json
python -m src.scraper.jobscraper_jobstreet_api --keyword "data engineer" --output /tmp/jobstreet_bronze.json
python -m src.scraper.jobscraper_kalibrr_api --keyword "data engineer" --max-pages 3 --output /tmp/kalibrr_bronze.json
python -m src.scraper.jobscraper_glints_api --keyword "data engineer" --output /tmp/glints_bronze.json
python -m src.scraper.jobscraper_techinasia_api --keyword "data engineer" --output /tmp/techinasia_bronze.json
```

Glints memerlukan `GLINTS_COOKIE` berupa cookie sesi yang Anda izinkan. Tech in Asia memerlukan `TECHINASIA_API_KEY` berupa Algolia search key. Isi melalui environment atau `.env` lokal; CLI memuat `.env`. Kredensial tidak ditanam di kode dan file catatan tidak dibaca otomatis. Jika sesi Glints kedaluwarsa, adapter menolak respons `isAuthenticated=false` agar empat hasil yang berbeda dari sesi browser tidak dianggap hasil pencarian yang benar.

`--url` menerima URL pencarian existing untuk menggantikan keyword/default filter. Contoh Kalibrr:

```bash
python -m src.scraper.jobscraper_kalibrr_api \
  --url 'https://kalibrr.id/kjs/job_board/search?text=data%20engineer&sort=Freshness&limit=20&offset=0' \
  --max-pages 1 --output /tmp/kalibrr_bronze.json
```

Request tetap dimulai dari halaman/offset pertama dan menggunakan ukuran halaman di atas; `--max-pages` mengatur jumlah halaman. Pengujian CLI tidak membaca atau menulis S3. Pengujian kode memakai fixture sanitasi di `tests/fixtures/scraper_api/` dan HTTP mock, bukan eksekusi live pipeline. Fixture mempertahankan bentuk data, memakai identitas dan teks contoh, serta tidak bergantung pada respons mentah lokal.
