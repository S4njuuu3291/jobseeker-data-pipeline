# ADR-001: Migrasi ke Arsitektur Multi-Lingkungan (Dev & Prod)

* **Status:** Approved
* **Date:** 2026-07-08

## Context
Saat ini, infrastruktur proyek hanya memiliki satu lingkungan (prod) yang juga dipakai untuk pengembangan. Semua perubahan langsung diterapkan ke resource yang sama — riskan, tidak ada isolasi antara eksperimen vs produksi. CI/CD sudah berjalan (push ke main → deploy), tapi tanpa environment staging untuk validasi.

## Options Considered
1. **Multi-account AWS** — Isolasi maksimum, tapi kompleks & biaya tinggi untuk proyek personal
2. **Terraform Workspaces** — Lebih ringan, tapi rawan human error (salah apply workspace), kurang cocok GitOps
3. **Terraform directory separation + modules** — Infra terisolasi per folder, state terpisah, workflow jelas

## Decision
Pilih **opsi 3: Directory separation + shared modules**.

- `terraform/` → refactor jadi struktur:
  ```
  terraform/
  ├── modules/       # Shared modules (s3, lambda, iam, dll)
  ├── envs/prod/     # Existing infra — di-import state, TIDAK di-rename
  └── envs/dev/      # Copy dari prod, pakai suffix -dev
  ```
- **Prod (existing):** Nama bucket & resource tetap. Dipindahkan ke `envs/prod/` dengan state import.
- **Dev (baru):** Nama bucket & resource pakai suffix `-dev`. Bikin dari nol via module.
- Kode Lambda membaca bucket name dari environment variable (bukan hardcode).

## Consequences
* **Positif:** 
  * Isolasi environment tanpa biaya multi-account
  * Prod tidak terganggu — data existing aman
  * Module reusable — DRY, perubahan cukup di 1 tempat
  * CI/CD bisa `plan` di dev dulu, `apply` ke prod setelah review
  * Cocok GitOps — mapping folder ke branch
* **Negatif:** 
  * Membutuhkan refactor & state migration (risiko kecil)
  * Biaya AWS ~2x lipat (resource di-duplicate)
  * Perlu disiplin maintain module agar backward compatible