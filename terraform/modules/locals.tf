# =========================================================
#                     LOCAL VALUES
# =========================================================

# Environment suffix untuk naming resource.
# - dev: pakai suffix -dev / _dev
# - prod: tanpa suffix (existing resource tetap)
locals {
  env_suffix            = var.env != "prod" ? "-${var.env}" : ""
  env_suffix_underscore = var.env != "prod" ? "_${var.env}" : ""

  # Fallback ke tag :latest jika ECR repo masih kosong (first deploy)
  ecr_image_digest = try(data.external.scraper_latest.result["digest"], "latest")
}
