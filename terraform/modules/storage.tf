# =========================================================
#                     BUCKET RESOURCE
# =========================================================

# BRONZE

resource "aws_s3_bucket" "bronze" {
  bucket        = "jobscraper-bronze-data-8424560${local.env_suffix}"
  force_destroy = true

  tags = {
    Environment = var.env
    Layer       = "Bronze"
    Project     = "Job-Scraper"
    Owner       = "Sanju"
  }
}

resource "aws_s3_bucket_public_access_block" "bronze" {
  bucket = aws_s3_bucket.bronze.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SILVER

resource "aws_s3_bucket" "silver" {
  bucket        = "jobscraper-silver-data-8424560${local.env_suffix}"
  force_destroy = true

  tags = {
    Environment = var.env
    Layer       = "Silver"
    Project     = "Job-Scraper"
    Owner       = "Sanju"
  }
}

resource "aws_s3_bucket_public_access_block" "silver" {
  bucket = aws_s3_bucket.silver.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ATHENA QUERY RESULTS - Existing bucket (not managed by Terraform)
# Bucket: weather-data-lake-sanju / Path: athena-query-results/Unsaved/

data "aws_s3_bucket" "athena_query_results" {
  bucket = "weather-data-lake-sanju"
}
