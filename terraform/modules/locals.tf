# =========================================================
#                     LOCAL VALUES
# =========================================================

# Environment suffix untuk naming resource.
# - dev: pakai suffix -dev / _dev
# - prod: tanpa suffix (existing resource tetap)
locals {
  env_suffix           = var.env != "prod" ? "-${var.env}" : ""
  env_suffix_underscore = var.env != "prod" ? "_${var.env}" : ""
}
