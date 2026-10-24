# Linux CPython 3.12 x86_64 packages are built and smoke-tested in CI first.
# S3 upload avoids the 50 MB direct-upload limit; combined unzipped code/layers
# must still fit 250 MB (enforced by scripts/build_lambda_packages.py).
locals {
  lambda_artifacts = toset([
    "bronze", "silver", "slack", "data-layer", "bronze-layer", "silver-layer", "slack-layer"
  ])
  dependency_layers = toset(["data", "bronze", "silver"])
}

resource "aws_s3_object" "lambda_artifact" {
  for_each = local.lambda_artifacts
  bucket   = aws_s3_bucket.lambda_artifacts.id
  key      = "lambda/${each.key}/${filesha256("${var.project_root}/.lambda-build/${each.key}.zip")}.zip"
  source   = "${var.project_root}/.lambda-build/${each.key}.zip"
  etag     = filemd5("${var.project_root}/.lambda-build/${each.key}.zip")
}

resource "aws_lambda_layer_version" "dependencies" {
  for_each                 = local.dependency_layers
  layer_name               = "jobscraper-${each.key}-deps${local.env_suffix}"
  s3_bucket                = aws_s3_bucket.lambda_artifacts.id
  s3_key                   = aws_s3_object.lambda_artifact["${each.key}-layer"].key
  source_code_hash         = filebase64sha256("${var.project_root}/.lambda-build/${each.key}-layer.zip")
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
  lifecycle { create_before_destroy = true }
}

resource "aws_lambda_layer_version" "slack_alert_layer" {
  layer_name               = "jobscraper-slack-alert-layer${local.env_suffix}"
  s3_bucket                = aws_s3_bucket.lambda_artifacts.id
  s3_key                   = aws_s3_object.lambda_artifact["slack-layer"].key
  source_code_hash         = filebase64sha256("${var.project_root}/.lambda-build/slack-layer.zip")
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
  lifecycle { create_before_destroy = true }
}

resource "aws_lambda_function" "scraper_zip" {
  function_name    = "jobscraper-scraper-zip${local.env_suffix}"
  role             = aws_iam_role.lambda_exec_role.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "src.entrypoint.handlers.scraper_handler"
  s3_bucket        = aws_s3_bucket.lambda_artifacts.id
  s3_key           = aws_s3_object.lambda_artifact["bronze"].key
  source_code_hash = filebase64sha256("${var.project_root}/.lambda-build/bronze.zip")
  layers = [
    aws_lambda_layer_version.dependencies["data"].arn,
    aws_lambda_layer_version.dependencies["bronze"].arn,
  ]
  lifecycle { create_before_destroy = true }
  dead_letter_config { target_arn = aws_sqs_queue.scraper_dlq.arn }
  environment {
    variables = {
      AWS_S3_BUCKET_NAME           = aws_s3_bucket.bronze.id
      GLINTS_COOKIE_PARAMETER      = aws_ssm_parameter.scraper_credentials["glints"].name
      TECHINASIA_API_KEY_PARAMETER = aws_ssm_parameter.scraper_credentials["techinasia"].name
    }
  }
  memory_size = 1024
  timeout     = 900
  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_iam_role_policy_attachment.lambda_s3,
    aws_iam_role_policy_attachment.lambda_dlq,
    aws_iam_role_policy_attachment.lambda_runtime_secrets,
  ]
  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    Platform    = "all"
    ManagedBy   = "Terraform"
  }
}

# Resource untuk Silver Layer Transformation
resource "aws_lambda_function" "silver_layer_zip" {
  function_name    = "jobscraper-silver-layer-zip${local.env_suffix}"
  role             = aws_iam_role.lambda_exec_role.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "src.entrypoint.handlers.silver_layer_handler"
  s3_bucket        = aws_s3_bucket.lambda_artifacts.id
  s3_key           = aws_s3_object.lambda_artifact["silver"].key
  source_code_hash = filebase64sha256("${var.project_root}/.lambda-build/silver.zip")
  layers = [
    aws_lambda_layer_version.dependencies["data"].arn,
    aws_lambda_layer_version.dependencies["silver"].arn,
  ]
  lifecycle { create_before_destroy = true }
  dead_letter_config { target_arn = aws_sqs_queue.scraper_dlq.arn }
  environment {
    variables = {
      platform                   = "kalibrr,glints,jobstreet,dealls,techinasia"
      AWS_S3_BUCKET_NAME         = aws_s3_bucket.bronze.id
      AWS_S3_SILVER_BUCKET_NAME  = aws_s3_bucket.silver.id
      AWS_GLUE_DATABASE_NAME     = aws_glue_catalog_database.jobscraper_db.name
      AWS_GLUE_SILVER_TABLE_NAME = aws_glue_catalog_table.silver_table.name
      DEEPSEEK_API_KEY_PARAMETER = aws_ssm_parameter.deepseek_api_key.name
    }
  }
  memory_size = 1024
  timeout     = 300
  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_iam_role_policy_attachment.lambda_s3,
    aws_iam_role_policy_attachment.lambda_dlq,
    aws_iam_role_policy_attachment.lambda_runtime_secrets,
  ]
  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Layer       = "Silver"
    ManagedBy   = "Terraform"
  }
}

resource "aws_lambda_function" "slack_alert" {
  function_name    = "jobscraper-slack-alert${local.env_suffix}"
  role             = aws_iam_role.slack_lambda_role.arn
  s3_bucket        = aws_s3_bucket.lambda_artifacts.id
  s3_key           = aws_s3_object.lambda_artifact["slack"].key
  source_code_hash = filebase64sha256("${var.project_root}/.lambda-build/slack.zip")
  handler          = "slack_handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  layers           = [aws_lambda_layer_version.slack_alert_layer.arn]
  environment {
    variables = {
      AWS_GLUE_DATABASE_NAME = aws_glue_catalog_database.jobscraper_db.name
      ATHENA_WORKGROUP       = aws_athena_workgroup.slack_alert_workgroup.name
      ATHENA_VIEW_NAME       = "v_jobscraper_clean"
      ENVIRONMENT            = var.env
      SSM_WEBHOOK_PARAM_NAME = aws_ssm_parameter.slack_webhook_url.name
    }
  }
  memory_size = 512
  timeout     = 60
  depends_on = [
    aws_iam_role_policy_attachment.slack_athena_attachment,
    aws_iam_role_policy_attachment.slack_ssm_attachment,
    aws_iam_role_policy_attachment.slack_s3_attachment,
    aws_iam_role_policy_attachment.slack_basic_execution,
  ]
  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Purpose     = "SlackAlerts"
    ManagedBy   = "Terraform"
  }
}
