# =========================================================
#                     LOCAL VALUES
# =========================================================

# Environment suffix untuk naming resource.
# - dev: pakai suffix -dev / _dev
# - prod: tanpa suffix (existing resource tetap)
locals {
  env_suffix            = var.env != "prod" ? "-${var.env}" : ""
  env_suffix_underscore = var.env != "prod" ? "_${var.env}" : ""

  # image_uri: @digest jika ada, :latest jika repo kosong atau data source error
  ecr_image_uri = try(
    data.external.scraper_latest.result["digest"] != ""
      ? "${aws_ecr_repository.scraper_repo.repository_url}@${data.external.scraper_latest.result["digest"]}"
      : "${aws_ecr_repository.scraper_repo.repository_url}:latest",
    "${aws_ecr_repository.scraper_repo.repository_url}:latest"
  )
}
