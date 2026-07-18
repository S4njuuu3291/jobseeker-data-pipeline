# =========================================================
#           LAKE FORMATION SETTINGS
# =========================================================

# Lake Formation Data Lake Settings - Add Lambda role as Data Lake Admin
# Also disable cross-account filtering to simplify permissions
resource "aws_lakeformation_data_lake_settings" "slack_lambda_admin" {
  depends_on = [aws_iam_role.slack_lambda_role]

  admins = [
    aws_iam_role.slack_lambda_role.arn
  ]

  # Disable fine-grained access control which is causing column-level permission issues
  allow_external_data_filtering = false
}

# =========================================================
#           ATHENA WORKGROUP
# =========================================================

# Athena Workgroup untuk Slack Lambda query
resource "aws_athena_workgroup" "slack_alert_workgroup" {
  name          = "jobscraper-slack-alert-workgroup${local.env_suffix}"
  force_destroy = true
  state         = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false

    result_configuration {
      output_location = "s3://${data.aws_s3_bucket.athena_query_results.id}/athena-query-results/jobscraper/"
    }

    engine_version {
      selected_engine_version = "AUTO"
    }
  }

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Purpose     = "SlackAlerts"
  }
}

# =========================================================
#                    GLUE DATA CATALOG
# =========================================================

resource "aws_glue_catalog_database" "jobscraper_db" {
  name        = "jobscraper_db${local.env_suffix_underscore}"
  description = "Glue Catalog Database untuk Job Scraper Pipeline"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}

# SILVER TABLE
resource "aws_glue_catalog_table" "silver_table" {
  name          = "jobscraper_silver_table${local.env_suffix_underscore}"
  database_name = aws_glue_catalog_database.jobscraper_db.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "typeOfData"     = "file"

    # Partition Projection — auto-discover partitions without MSCK or Crawler
    "projection.enabled"                      = "true"
    "projection.ingestion_date.type"          = "date"
    "projection.ingestion_date.range"         = "2025-01-01,NOW+1DAY"
    "projection.ingestion_date.format"        = "yyyy-MM-dd"
    "projection.ingestion_date.interval"      = "1"
    "projection.ingestion_date.interval.unit" = "DAYS"
    "storage.location.template"               = "s3://${aws_s3_bucket.silver.id}/ingestion_date=$${ingestion_date}/"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.silver.id}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "job_id"
      type = "string"
    }
    columns {
      name = "job_title"
      type = "string"
    }
    columns {
      name = "job_url"
      type = "string"
    }
    columns {
      name = "platform"
      type = "string"
    }
    columns {
      name = "scraped_at"
      type = "string"
    }
    columns {
      name = "keyword"
      type = "string"
    }
    columns {
      name = "job_description"
      type = "string"
    }
    # AI-parsed fields
    columns {
      name = "role"
      type = "string"
    }

    columns {
      name = "company_name"
      type = "string"
    }
    columns {
      name = "location"
      type = "string"
    }
    columns {
      name = "salary_min"
      type = "int"
    }
    columns {
      name = "salary_max"
      type = "int"
    }
    columns {
      name = "salary_currency"
      type = "string"
    }
    columns {
      name = "salary_period"
      type = "string"
    }
    columns {
      name = "job_type"
      type = "string"
    }
    columns {
      name = "seniority"
      type = "string"
    }
    columns {
      name = "work_mode"
      type = "string"
    }
    columns {
      name = "experience_min"
      type = "int"
    }
    columns {
      name = "experience_max"
      type = "int"
    }
    columns {
      name = "education"
      type = "string"
    }
    columns {
      name = "company_industry"
      type = "string"
    }
    columns {
      name = "skills"
      type = "string"
    }
    columns {
      name = "benefits"
      type = "string"
    }
    columns {
      name = "posting_date"
      type = "string"
    }
  }

  partition_keys {
    name = "ingestion_date"
    type = "string"
  }
}
