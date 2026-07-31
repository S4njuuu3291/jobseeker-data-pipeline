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
  # Mencakup 3 scraper (kalibrr, glints, jobstreet) + silver_layer + slack_alert
  lambda_scraper_functions = [
    "jobscraper-kalibrr${local.env_suffix}",
    "jobscraper-glints${local.env_suffix}",
    "jobscraper-jobstreet${local.env_suffix}",
    "jobscraper-silver-layer${local.env_suffix}",
    "jobscraper-slack-alert${local.env_suffix}",
  ]

  # image_uri: @digest jika ada, :latest jika repo kosong atau data source error
  ecr_image_uri = try(
    data.external.scraper_latest.result["digest"] != ""
      ? "${aws_ecr_repository.scraper_repo.repository_url}@${data.external.scraper_latest.result["digest"]}"
      : "${aws_ecr_repository.scraper_repo.repository_url}:latest",
    "${aws_ecr_repository.scraper_repo.repository_url}:latest"
  )
}
