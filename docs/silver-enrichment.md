# Silver: AI mengisi informasi yang belum tersedia

Silver mempertahankan 24 kolom inti dari Bronze dan menambahkan 12 kolom operasional proses AI. Nilai sumber yang sudah terisi tidak ditimpa oleh hasil AI. Normalisasi lokasi existing tetap diterapkan, tetapi null dipertahankan sebagai null.

## Pemilihan kolom

Untuk setiap baris, Silver memeriksa 16 atribut bisnis: role, lokasi, empat kolom gaji, tipe pekerjaan, seniority, mode kerja, dua kolom pengalaman, pendidikan, industri perusahaan, skill, benefit, dan tanggal posting.

Hanya kolom kosong yang dikirim sebagai `requested_fields`. `None`, NaN, `pd.NA`, string kosong, placeholder unknown/null/n/a, serta array kosong diperlakukan sebagai informasi yang belum tersedia. Angka 0 yang memang sudah ada tidak otomatis dianggap kosong. Kategori role yang sudah terisi tetap dipertahankan; perubahan kategori menjadi role kanonik merupakan pekerjaan normalisasi tersendiri.

Baris lengkap tidak memanggil AI: token/biaya/attempt 0, `api_model=null`, dan `api_finish_reason=not_needed`. URL dan keyword pencarian tidak dijadikan bukti untuk mengisi data.

## Persyaratan bukti

AI mengembalikan setiap field sebagai null atau objek berikut:

```json
{
  "seniority": {
    "value": "senior",
    "evidence": "Senior Data Engineer"
  },
  "salary_min": null
}
```

Kode memeriksa kutipan terhadap judul/deskripsi sumber dan memvalidasi dukungan nilai, bukan hanya bentuk JSON:

- Kutipan yang tidak ditemukan di sumber ditolak. Pemotongan kutipan untuk menyembunyikan negasi diperiksa terhadap kalimat sumber.
- Angka pengalaman memerlukan tahun/batas eksplisit. Minimum tidak dipakai sebagai maksimum; kode kategori 200 bukan tahun pengalaman.
- Nominal gaji memerlukan rentang eksplisit; mata uang/periode memerlukan penyebutan eksplisit. Negara Indonesia tidak menjadi bukti currency IDR.
- Seniority memerlukan level eksplisit pada judul atau label level posisi; pengalaman atau level rekan kerja tidak menjadi bukti.
- Seluruh item skill/benefit harus didukung kutipan. Item tambahan tanpa bukti membuat usulan field tersebut ditolak.
- Tanggal posting memerlukan tanggal ISO dan konteks posting, bukan deadline/tanggal relatif/hari pemrosesan.
- Bagian `ABOUT COMPANY` dipisahkan dari sumber atribut pekerjaan. Bagian ini dapat dipakai untuk industri perusahaan yang dinyatakan eksplisit, bukan gaji, lokasi kerja, atau persyaratan kandidat. Pengalaman pada industri klien tidak otomatis menjadi industri perusahaan.
- Ketidakjelasan, negasi, konflik, atau pola yang tidak didukung menghasilkan null. Pemeriksaan bersifat konservatif; informasi yang sebenarnya ada tetapi bentuknya belum didukung dapat tetap null.

`src/ai/extraction.py` menjalankan pemeriksaan bukti. `parse_job` hanya mengembalikan field yang diminta dan metadata. Bukti yang diterima tersedia pada `_evidence` hasil parser untuk pemeriksaan internal, dan tidak ditambahkan sebagai kolom output Silver.

## Penggabungan dan kegagalan

Hasil digabung per baris hanya pada kolom yang kosong. Kolom identitas, judul, nama perusahaan, dan nilai Bronze yang sudah ada tidak dapat ditimpa AI. Kolom tambahan yang tidak diminta pada respons AI diabaikan.

Retry AI maksimum empat attempt pada parser; orchestrator tidak mengulang retry budget tersebut. Token dan biaya seluruh respons yang diterima dijumlahkan. Respons terpotong/tidak valid tidak digunakan. Setelah gagal, tidak ada fallback yang menebak nilai: kolom kosong tetap null.

Default `mid`, `full_time`, `IDR`, `monthly`, 0 tahun/gaji, dan tanggal hari ini sudah dihapus. Integer memakai dtype nullable `Int64`, sehingga validator menerima angka yang belum tersedia tanpa `fillna(0)`.

Pengujian memakai respons AI mock dan upload mock; tidak menjalankan permintaan AI berbayar atau menulis hasil pengujian ke S3.
