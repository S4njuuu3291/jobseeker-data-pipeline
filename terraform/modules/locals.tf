# =========================================================
#                     LOCAL VALUES
# =========================================================

# Environment suffix untuk naming resource.
# - dev: pakai suffix -dev / _dev
# - prod: tanpa suffix (existing resource tetap)
locals {
  env_suffix            = var.env != "prod" ? "-${var.env}" : ""
  env_suffix_underscore = var.env != "prod" ? "_${var.env}" : ""

  # Nama-nama Lambda function untuk CloudWatch alarm for_each
  # Generic Bronze ZIP function + Silver ZIP function + Slack.
  lambda_scraper_functions = [
    "jobscraper-scraper-zip${local.env_suffix}",
    "jobscraper-silver-layer-zip${local.env_suffix}",
    "jobscraper-slack-alert${local.env_suffix}",
  ]

}
