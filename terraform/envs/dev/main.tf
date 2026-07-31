# ============================================
# Dev Environment — panggil module "base"
# ============================================
# Ini file utamanya! Cukup panggil module "base"
# dengan nilai variabel yang sesuai.
# Semua resource (VPC, EC2, S3, dll) dibuat
# otomatis oleh module.
# ============================================

module "base" {
  source = "../../modules"
  env          = var.env
  alert_email = "sanju329121@gmail.com"
  project_root = abspath("${path.root}/../../..")
}