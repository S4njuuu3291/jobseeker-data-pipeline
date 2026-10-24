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

# Versioned, private deployment artifacts. Separate from the queryable data lake.
resource "aws_s3_bucket" "lambda_artifacts" {
  bucket = "jobscraper-lambda-artifacts-${data.aws_caller_identity.current.account_id}${local.env_suffix}"
  tags   = { Environment = var.env, Project = "Job-Scraper", Purpose = "LambdaPackages" }
}

resource "aws_s3_bucket_public_access_block" "lambda_artifacts" {
  bucket                  = aws_s3_bucket.lambda_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
