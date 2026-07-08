# EPIC: Migrasi ke Arsitektur Multi-Environment (Dev & Prod)

> **ADR Terkait:** `ADR-001-migration-to-multi-environment.md`
> **Status:** In Progress

## Ringkasan

Refactor infrastruktur Terraform dari single environment menjadi multi-environment (dev/prod) dengan directory separation + shared modules. Existing infra menjadi **prod**, dev dibuat baru dengan suffix `-dev`. Data existing aman — tidak ada rename bucket atau data loss.

---

## Tasks — Jira Backlog

### Phase 1: Refactor Terraform ke Module + Env Structure

#### [TASK-1] Extract shared Terraform modules
- Pindah resource definitions keslas `terraform/modules/{s3-bucket,lambda-function,iam-role,glue-crawler,ecr,ssm,eventbridge,step-functions}`
- Module harus parameterized: `env_name`, `bucket_name`, `tags`, dll
- **Story Points:** 5

#### [TASK-2] Migrate existing infra ke `envs/prod/`
- Pindahkan current `.tf` files ke `terraform/envs/prod/` — **tanpa rename resource**
- State migration via `terraform state mv` (55 resource ke `module.base.`)
- Sisa: `Plan: 33 to change` (tag updates, aman diapply nanti)
- **Story Points:** 8

#### [TASK-3] Setup `envs/dev/` dari scratch
- Copy struktur prod, ubah variable: `env = "dev"` → suffix `-dev` otomatis
- State file terpisah (`dev/terraform.tfstate`)
- ✅ Infra non-container berhasil di-apply
- ⏳ Container Lambdas (kalibrr, glints, jobstreet, silver_layer) butuh image di ECR dev
- **Story Points:** 5

### Phase 2: Update Kode Lambda

#### [TASK-4] Inject environment variable untuk bucket & resource path
- Update semua Lambda code baca konfigurasi dari env var, bukan hardcode
  - `BRONZE_BUCKET`, `SILVER_BUCKET`, `GLUE_DATABASE`, dll
  - Default fallback ke nilai prod (backward compatible)
- **Story Points:** 5

#### [TASK-5] Update Terraform resource definition untuk inject env var ke Lambda
- Pastikan tiap Lambda function di `envs/dev/` dan `envs/prod/` punya env var sesuai environment-nya
- **Story Points:** 3

### Phase 3: CI/CD Pipeline

#### [TASK-6] Modify GitHub Actions workflow untuk multi-environment
- **Dev:** Trigger tiap push ke branch `dev` → `terraform plan & apply` di `envs/dev/`
- **Prod:** Trigger tiap push ke branch `main` → `terraform plan & apply` di `envs/prod/`
- Plan output di-attach ke PR sebagai comment
- **Story Points:** 5

### Phase 4: Testing & Deployment

#### [TASK-7] Deploy & smoke test dev environment
- Jalankan pipeline scraping di dev
- Validasi data masuk ke S3 dev bucket
- Validasi Slack alert tetap jalan
- **Story Points:** 3

#### [TASK-8] Smoke test prod environment
- Pastikan prod masih berfungsi normal setelah refactor
- Tidak ada data loss atau duplicate
- **Story Points:** 2

---

## Ringkasan Story Points

| Task | Description | Points |
|------|-------------|--------|
| TASK-1 | Extract shared modules | 5 |
| TASK-2 | Migrate existing infra ke prod/ | 8 |
| TASK-3 | Setup envs/dev/ | 5 |
| TASK-4 | Env var di kode Lambda | 5 |
| TASK-5 | Env var di Terraform | 3 |
| TASK-6 | CI/CD workflow | 5 |
| TASK-7 | Smoke test dev | 3 |
| TASK-8 | Smoke test prod | 2 |
| **Total** | | **36** |
