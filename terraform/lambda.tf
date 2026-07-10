# =========================================================
#        LAMBDA LAYER - SLACK ALERT DEPENDENCIES
# =========================================================

# Zip file untuk Lambda Layer (requests library)
data "archive_file" "slack_alert_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda-layers/slack-alert-layer"
  output_path = "${path.module}/../.terraform-artifacts/slack-alert-layer.zip"
}

resource "aws_lambda_layer_version" "slack_alert_layer" {
  filename            = data.archive_file.slack_alert_layer.output_path
  layer_name          = "jobscraper-slack-alert-layer"
  compatible_runtimes = ["python3.12"]
  source_code_hash    = data.archive_file.slack_alert_layer.output_base64sha256

  depends_on = [aws_iam_role.slack_lambda_role]
}

# =========================================================
#                     LAMBDA RESOURCE
# =========================================================

# Resource untuk Kalibrr
resource "aws_lambda_function" "kalibrr" {
  function_name = "jobscraper-kalibrr"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  architectures = ["x86_64"]
  image_uri     = "${aws_ecr_repository.scraper_repo.repository_url}@${data.aws_ecr_image.scraper_latest.image_digest}"

  publish = false

  lifecycle {
    ignore_changes = [publish]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.scraper_dlq.arn
  }

  image_config {
    command = ["src.entrypoint.handlers.kalibrr_handler"]
  }

  environment {
    variables = {
      PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers"
      AWS_S3_BUCKET_NAME       = aws_s3_bucket.bronze.id
      SCRAPE_KEYWORDS          = "data-engineer-intern,etl-developer-intern,big-data-intern,bi-engineer-intern"
    }
  }

  memory_size = 3008
  timeout     = 900
}

# Resource untuk Glints
resource "aws_lambda_function" "glints" {
  function_name = "jobscraper-glints"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  architectures = ["x86_64"]
  image_uri     = "${aws_ecr_repository.scraper_repo.repository_url}@${data.aws_ecr_image.scraper_latest.image_digest}"

  publish = false

  lifecycle {
    ignore_changes = [publish]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.scraper_dlq.arn
  }

  image_config {
    command = ["src.entrypoint.handlers.glints_handler"]
  }

  environment {
    variables = {
      PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers"
      AWS_S3_BUCKET_NAME       = aws_s3_bucket.bronze.id
      SCRAPE_KEYWORDS          = "data+engineer+intern,etl+developer+intern,big+data+intern,bi+engineer+intern"
    }
  }

  memory_size = 3008
  timeout     = 900
}

# Resource untuk Jobstreet
resource "aws_lambda_function" "jobstreet" {
  function_name = "jobscraper-jobstreet"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  architectures = ["x86_64"]
  image_uri     = "${aws_ecr_repository.scraper_repo.repository_url}@${data.aws_ecr_image.scraper_latest.image_digest}"

  publish = false

  lifecycle {
    ignore_changes = [publish]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.scraper_dlq.arn
  }

  image_config {
    command = ["src.entrypoint.handlers.jobstreet_handler"]
  }

  environment {
    variables = {
      PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers"
      AWS_S3_BUCKET_NAME       = aws_s3_bucket.bronze.id
      SCRAPE_KEYWORDS          = "data-engineer-intern,etl-developer-intern,big-data-intern,bi-engineer-intern"
    }
  }

  memory_size = 3008
  timeout     = 900
}

# Resource untuk Silver Layer Transformation
resource "aws_lambda_function" "silver_layer" {
  function_name = "jobscraper-silver-layer"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  architectures = ["x86_64"]
  image_uri     = "${aws_ecr_repository.scraper_repo.repository_url}@${data.aws_ecr_image.scraper_latest.image_digest}"

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
      platform                   = "kalibrr,glints,jobstreet"
      AWS_S3_BUCKET_NAME         = aws_s3_bucket.bronze.id
      AWS_S3_SILVER_BUCKET_NAME  = aws_s3_bucket.silver.id
      AWS_GLUE_DATABASE_NAME     = "jobscraper_db"
      AWS_GLUE_SILVER_TABLE_NAME = "jobscraper_silver_table"
    }
  }

  memory_size = 1024
  timeout     = 300
}

# Resource untuk Slack Alert
data "archive_file" "slack_alert_code" {
  type        = "zip"
  source_dir  = "${path.module}/../src/slack-alert"
  output_path = "${path.module}/../.terraform-artifacts/slack-alert.zip"
}

resource "aws_lambda_function" "slack_alert" {
  function_name    = "jobscraper-slack-alert"
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
      AWS_GLUE_DATABASE_NAME = "jobscraper_db"
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
    Project   = "Job-Scraper"
    Purpose   = "SlackAlerts"
    ManagedBy = "Terraform"
  }
}
