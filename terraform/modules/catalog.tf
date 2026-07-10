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

# Grant GitHub Actions role DESCRIBE access via Lake Formation
resource "aws_lakeformation_permissions" "github_actions_db_access" {
  count = var.env != "prod" ? 0 : 1

  principal   = one(aws_iam_role.github_actions_role[*].arn)
  permissions = ["DESCRIBE"]

  database {
    name = aws_glue_catalog_database.jobscraper_db.name
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
      name = "company_name"
      type = "string"
    }
    columns {
      name = "location"
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
  }

  partition_keys {
    name = "ingestion_date"
    type = "string"
  }
}
