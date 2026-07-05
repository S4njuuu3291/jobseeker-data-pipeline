# Security & Governance Review — Job Data Pipeline

> **Tujuan dokumen:** Mencatat temuan security & governance dari proyek ini, prioritas perbaikan, dan konsep yang perlu dipelajari. Dibuat sebagai referensi belajar dan bahan evaluasi portofolio.

---

## 1. Ringkasan Temuan

| Level | Jumlah | Yang Harus Dilakukan |
|---|---|---|
| 🔴 KRITIS | 4 | Segera diperbaiki, risiko tinggi |
| 🟡 SEDANG | 7 | Perlu ditingkatkan untuk production readiness |
| 🟢 RENDAH | 3 | Catatan untuk improvement ke depan |

---

## 2. 🔴 Temuan KRITIS

### 2.1. AWS IAM Access Key & Secret Key di `.env` — Terekspos ke Git

**Lokasi:** `.env` baris 16-17
**Status:** FILE SUDAH MASUK GIT (`.env` tidak di-`.gitignore` — tapi anehnya file `.gitignore` sudah mencantumkan `.env`)

```
AWS_ACCESS_KEY=AKIA******** (redacted)
AWS_SECRET_KEY=******** (redacted)
```

**Risiko:** Siapa pun yang punya akses ke repo bisa menggunakan kredensial ini untuk mengakses AWS account.

**Perbaikan:**
1. Revoke kredensial ini via AWS Console (IAM → Users → `jobscraper_bot-crawler-bot` → Security credentials → Delete)
2. Buat access key baru, simpan di tempat aman (jangan di repo)
3. Hapus file `.env` dari git history (`git filter-branch` atau BFG Repo-Cleaner)
4. `.gitignore` sudah mencantumkan `.env` — kenapa file masih ter-track? Mungkin karena sudah di-commit sebelum `.gitignore` ditambahkan. Butuh `git rm --cached .env`

> **Catatan:** Kenapa kamu pakai IAM User + Access Key? Seharusnya **IAM Role** — karena Lambda yang jalan di AWS sudah punya IAM Role, gak perlu access key.

---

### 2.2. Slack Webhook URL di `.env` — Terekspos ke Git

**Lokasi:** `.env` baris 13

```
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/*** (redacted) ***"
```

**Risiko:** Siapa pun yang punya URL ini bisa spam Slack channel kamu.

**Perbaikan:**
1. Revoke webhook URL di Slack (Slack API → Apps → hapus webhook)
2. Buat webhook baru dan simpan via SSM Parameter Store (sudah ada resourcenya di Terraform: `aws_ssm_parameter.slack_webhook_url`)
3. Hapus dari git history (bersamaan dengan poin 2.1)

---

### 2.3. GitHub Actions Role = AdministratorAccess

**Lokasi:** `terraform/main.tf` baris 54-57

```terraform
resource "aws_iam_role_policy_attachment" "github_actions_admin" {
  role       = aws_iam_role.github_actions_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
```

**Risiko:** Jika ada supply chain attack (misal Actions compromised, dependency berbahaya), attacker dapat full admin akses ke seluruh AWS account.

**Perbaikan:** Ganti dengan policy spesifik yang cuma mencakup:
- `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`
- `s3:*` pada bucket terraform state
- `lambda:UpdateFunctionCode`
- `iam:PassRole` untuk role tertentu

Buat policy terpisah, jangan pake managed policy `AdministratorAccess`.

---

### 2.4. IAM User `jobscraper_bot` dengan Long-term Credentials

**Lokasi:** `terraform/main.tf` baris 113-120, 382-385

**Masalah:**
- Masih pake **IAM User** (long-term credentials) padahal sudah di era di mana AWS sendiri merekomendasikan **IAM Role** + STS
- Akses key tidak pernah di-rotate
- Key sudah bocor di git (poin 2.1)

**Perbaikan:**
- Hapus IAM user ini
- Ganti mekanisme akses dengan IAM Role (untuk Lambda yang jalan di AWS, role sudah otomatis tersedia)
- Backfill script bisa pake `boto3.Session()` tanpa credential — karena akan jalan di lingkungan yang sudah punya IAM Role

---

## 3. 🟡 Temuan SEDANG

### 3.1. S3 Bucket — Tidak Ada Enkripsi Eksplisit

**Lokasi:** `terraform/main.tf` — resource `aws_s3_bucket.bronze` dan `aws_s3_bucket.silver`

**Masalah:** AWS default-nya pake SSE-S3, tapi lebih baik explicit daripada rely on default.

**Perbaikan:** Tambahkan resource berikut untuk tiap bucket:

```terraform
resource "aws_s3_bucket_server_side_encryption_configuration" "bronze_encrypt" {
  bucket = aws_s3_bucket.bronze.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
```

### 3.2. S3 Bucket — Tidak Ada Versioning

**Masalah:** Kalau data terhapus atau ter-overwrite, hilang permanen.

**Perbaikan:** Tambahkan `aws_s3_bucket_versioning` untuk bronze dan silver bucket:

```terraform
resource "aws_s3_bucket_versioning" "bronze_versioning" {
  bucket = aws_s3_bucket.bronze.id
  versioning_configuration {
    status = "Enabled"
  }
}
```

### 3.3. ECR — Tag Mutability = MUTABLE

**Lokasi:** `terraform/main.tf` baris 449

```terraform
image_tag_mutability = "MUTABLE"
```

**Masalah:** Tag `latest` bisa di-overwrite. Risk: deploy image yang salah tanpa terdeteksi.

**Perbaikan:** Ganti ke `IMMUTABLE` dan gunakan version tag (misal `v1.2.3`) bukan `latest`.

### 3.4. ECR Lifecycle — Cuma Simpan 1 Image

**Lokasi:** `terraform/main.tf` baris 472

```terraform
countNumber = 1
```

**Masalah:** Tidak bisa rollback ke image sebelumnya.

**Perbaikan:** Simpan 3-5 image terakhir:

```terraform
countNumber = 5
```

### 3.5. IAM Policy — Masih Banyak `Resource = "*"`

Beberapa policy masih menggunakan wildcard yang terlalu luas:

| Policy | Resource | Seharusnya |
|---|---|---|
| `lambda_glue_policy` | `*` | Di-scope ke database/table tertentu |
| `slack_athena_policy` (Athena actions) | `*` | Di-scope ke workgroup tertentu |
| `slack_athena_policy` (Glue actions) | `*` | Di-scope ke database `jobscraper_db` |

**Perbaikan:** Scope `Resource` ke ARN spesifik (workgroup, database, table).

### 3.6. Step Functions — Logging dengan `include_execution_data = true`

**Lokasi:** `terraform/main.tf` baris 984

```terraform
logging_configuration {
  include_execution_data = true
}
```

**Masalah:** Data eksekusi Lambda ikut tercatat di CloudWatch. Kalau payload mengandung data sensitif (misal URL jobs), itu tersimpan di log.

**Perbaikan:** Set `include_execution_data = false` atau pastikan tidak ada data sensitif di payload.

### 3.7. S3 Bucket — Tidak Ada Policy HTTPS-only

**Masalah:** Koneksi ke S3 bisa dilakukan via HTTP (plaintext). Risiko: data bisa di-intercept dalam transit.

**Perbaikan:** Tambahkan bucket policy yang deny akses kalau bukan HTTPS:

```terraform
data "aws_iam_policy_document" "bucket_policy" {
  statement {
    effect = "Deny"
    principals {
      identifiers = ["*"]
      type        = "*"
    }
    actions   = ["s3:*"]
    resources = ["${aws_s3_bucket.bronze.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
```

---

## 4. 🟢 Temuan RENDAH (Catatan)

| Temuan | Saran |
|---|---|
| CloudWatch log retention 7 hari | Untuk audit/forensic, set minimal 1 tahun |
| `force_destroy = true` di S3 bucket | Hati-hati — bisa kehapus semua data + terraform state |
| Tidak ada data classification tags | Tambah tag `DataClassification: Public/Internal/Confidential` |
| Superset secret key hardcoded di docker-compose | Pindahkan ke environment variable |
| AWS credentials di-mount dari `~/.aws` ke Superset container | Risk: container bisa akses semua kredensial lokal |

---

## 5. 📚 Konsep yang Perlu Dipelajari

### 5.1. Fundamental

| Konsep | Kenapa Penting | Cara Belajar |
|---|---|---|
| **IAM Least Privilege** | Setiap role cuma boleh punya permission yang cukup | AWS IAM docs + practice: bikin policy dari nol, bukan copy-paste |
| **IAM Role vs IAM User** | Role = temporary credentials (best practice). User = long-term keys (avoid). | Cari perbedaan di AWS IAM User Guide |
| **git-secrets / secret scanning** | Mencegah credentials ke-commit ke git | `git secrets --scan`, `trufflehog`, GitHub secret scanning |
| **S3 security (versioning, encryption, bucket policy)** | Melindungi data di rest dan in transit | AWS S3 Security docs |

### 5.2. Intermediate

| Konsep | Kenapa Penting | Cara Belajar |
|---|---|---|
| **Supply chain security** | CI/CD pipeline bisa jadi attack vector | OWASP Software Supply Chain Security, SLSA framework |
| **ECR immutability + image signing** | Mencegah image manipulation | AWS ECR docs, `docker trust`, Notary |
| **CloudTrail + audit logging** | Merekam semua API activity di AWS | AWS CloudTrail docs — setup trail ke S3 |
| **Terraform state security** | State file contains sensitive info | Pastikan state di S3 + DynamoDB locking (already done ✅) |
| **Data governance (tagging, classification, lineage)** | Melacak asal-usul dan sensitivitas data | AWS Lake Formation, OpenMetadata, DataHub |

### 5.3. Advanced (untuk jangka panjang)

| Konsep | Kenapa Penting |
|---|---|
| **AWS WAF + Shield** | Proteksi web scraper dari serangan (kalau scraper punya endpoint publik) |
| **VPC + Security Groups + PrivateLink** | Isolasi jaringan Lambda tanpa akses internet |
| **Data retention policy compliance** | Aturan hukum berapa lama data boleh disimpan (UU PDP Indonesia) |
| **Penetration testing** | Simulasi serangan untuk cari celah keamanan |
| **KMS (Key Management Service)** | Enkripsi customer-managed key, bukan AWS-managed |

---

## 6. Prioritas Perbaikan

| # | Item | Level | Effort | Waktu |
|---|---|---|---|---|
| 1 | Revoke AWS Access Key + Slack webhook di AWS Console | 🔴 KRITIS | 5 menit | **Hari ini** |
| 2 | `git rm --cached .env` + hapus dari git history | 🔴 KRITIS | 15 menit | **Hari ini** |
| 3 | Ganti AdministratorAccess dengan scoped policy | 🔴 KRITIS | 1 jam | **Minggu ini** |
| 4 | Hapus IAM user + ganti pake IAM Role | 🔴 KRITIS | 30 menit | **Minggu ini** |
| 5 | Tambah S3 encryption + versioning | 🟡 SEDANG | 20 menit | **Minggu ini** |
| 6 | ECR immutable + simpan 5 image | 🟡 SEDANG | 10 menit | **Minggu ini** |
| 7 | Scope IAM wildcard ke resource spesifik | 🟡 SEDANG | 30 menit | **Bulan ini** |
| 8 | S3 bucket policy HTTPS-only | 🟡 SEDANG | 15 menit | **Bulan ini** |

---

## 7. Yang SUDAH BAIK (tetap dipertahankan)

Biar tidak lupa, ini praktik yang sudah benar:

- ✅ **OIDC untuk CI/CD** — No static AWS keys di GitHub Actions
- ✅ **S3 Public Access Block** — Semua bucket diblok akses publiknya
- ✅ **SSM Parameter Store SecureString** — Slack webhook dienkripsi
- ✅ **DLQ + CloudWatch Alarm** — Deteksi kegagalan scraper
- ✅ **SQL injection prevention via regex** — Input tanggal divalidasi
- ✅ **Separate IAM roles** — 6 role berbeda untuk concern berbeda
- ✅ **State locking (DynamoDB)** — Mencegah race condition terraform
- ✅ **ECR image scanning on push** — Deteksi vulnerability di image
- ✅ **Terraform backend encryption** — State file dienkripsi

---

> **Catatan:** Dokumen ini dibuat berdasarkan review keamanan pada 2026-07-05. Beberapa temuan mungkin sudah berubah setelah perbaikan dilakukan.
