# =========================================================
#        LAMBDA LAYER - SLACK ALERT DEPENDENCIES
# =========================================================

# Zip file untuk Lambda Layer (requests library)
data "archive_file" "slack_alert_layer" {
  type        = "zip"
  source_dir  = "${var.project_root}/lambda-layers/slack-alert-layer"
  output_path = "${path.root}/.terraform-artifacts/slack-alert-layer.zip"
}

resource "aws_lambda_layer_version" "slack_alert_layer" {
  filename            = data.archive_file.slack_alert_layer.output_path
  layer_name          = "jobscraper-slack-alert-layer${local.env_suffix}"
  compatible_runtimes = ["python3.12"]
  source_code_hash    = data.archive_file.slack_alert_layer.output_base64sha256

  depends_on = [aws_iam_role.slack_lambda_role]
}

# =========================================================
#                     LAMBDA RESOURCE
# =========================================================

# Resource untuk Scraper (generik — semua platform, dispatch via event["platform"])
resource "aws_lambda_function" "scraper" {
  function_name = "jobscraper-scraper${local.env_suffix}"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  architectures = ["x86_64"]
  image_uri     = local.ecr_image_uri

  publish = false

  lifecycle {
    ignore_changes = [publish]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.scraper_dlq.arn
  }

  image_config {
    command = ["src.entrypoint.handlers.scraper_handler"]
  }

  environment {
    variables = {
      PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers"
      AWS_S3_BUCKET_NAME       = aws_s3_bucket.bronze.id
    }
  }

  memory_size = 3008
  timeout     = 900

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    Platform    = "all"
    ManagedBy   = "Terraform"
  }
}

# Resource untuk Silver Layer Transformation
resource "aws_lambda_function" "silver_layer" {
  function_name = "jobscraper-silver-layer${local.env_suffix}"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  architectures = ["x86_64"]
  image_uri     = local.ecr_image_uri

  publish = false

  lifecycle {
    ignore_changes = [publish]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.scraper_dlq.arn
  }

  image_config {
    command = ["src.entrypoint.handlers.silver_layer_handler"]
  }

  environment {
    variables = {
      platform                   = "kalibrr,glints,jobstreet,dealls,techinasia"
      AWS_S3_BUCKET_NAME         = aws_s3_bucket.bronze.id
      AWS_S3_SILVER_BUCKET_NAME  = aws_s3_bucket.silver.id
      AWS_GLUE_DATABASE_NAME     = "jobscraper_db${local.env_suffix_underscore}"
      AWS_GLUE_SILVER_TABLE_NAME = "jobscraper_silver_table${local.env_suffix_underscore}"
      DEEPSEEK_API_KEY           = data.aws_ssm_parameter.deepseek_api_key.value
    }
  }

  memory_size = 1024
  timeout     = 300

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    Layer       = "Silver"
    ManagedBy   = "Terraform"
  }
}

# Resource untuk Slack Alert
data "archive_file" "slack_alert_code" {
  type        = "zip"
  source_dir  = "${var.project_root}/src/slack-alert"
  output_path = "${path.root}/.terraform-artifacts/slack-alert.zip"
}

resource "aws_lambda_function" "slack_alert" {
  function_name    = "jobscraper-slack-alert${local.env_suffix}"
  role             = aws_iam_role.slack_lambda_role.arn
  filename         = data.archive_file.slack_alert_code.output_path
  source_code_hash = data.archive_file.slack_alert_code.output_base64sha256
  handler          = "slack_handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]

  layers = [
    aws_lambda_layer_version.slack_alert_layer.arn
  ]

  environment {
    variables = {
      AWS_GLUE_DATABASE_NAME     = "jobscraper_db${local.env_suffix_underscore}"
      ATHENA_WORKGROUP           = "jobscraper-slack-alert-workgroup${local.env_suffix}"
      ATHENA_VIEW_NAME           = "v_jobscraper_clean"
      ENVIRONMENT                = var.env
      SSM_WEBHOOK_PARAM_NAME     = "/jobscraper/slack/webhook_url${local.env_suffix}"
    }
  }

  memory_size = 512
  timeout     = 60

  depends_on = [
    aws_iam_role_policy_attachment.slack_athena_attachment,
    aws_iam_role_policy_attachment.slack_ssm_attachment,
    aws_iam_role_policy_attachment.slack_s3_attachment,
    aws_iam_role_policy_attachment.slack_basic_execution,
    aws_lambda_layer_version.slack_alert_layer
  ]

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Purpose     = "SlackAlerts"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}
