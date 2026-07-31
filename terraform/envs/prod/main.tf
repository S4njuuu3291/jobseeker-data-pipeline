# ============================================
# Prod Environment — panggil module "base"
# ============================================
# Ini file utamanya! Cukup panggil module "base"
# dengan nilai variabel yang sesuai.
# Semua resource (VPC, EC2, S3, dll) dibuat
# otomatis oleh module.
# ============================================

module "base" {
  source = "../../modules"
  alert_email = "sanju329121@gmail.com"
  env          = var.env
  project_root = abspath("${path.root}/../../..")
}