# =========================================================
#                      DATA SOURCES
# =========================================================

data "aws_caller_identity" "current" {}

# =========================================================
#              GITHUB OIDC PROVIDER FOR CI/CD
# =========================================================

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.env != "prod" ? 0 : 1
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
    Purpose     = "GitHubOIDC"
  }
}

resource "aws_iam_role" "github_actions_role" {
  count = var.env != "prod" ? 0 : 1
  name = "jobscraper-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = one(aws_iam_openid_connect_provider.github[*].arn) }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:S4njuuu3291/job-data-pipeline:*"
        }
      }
    }]
  })

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
    Purpose     = "GitHubActionsRole"
  }
}

resource "aws_iam_role_policy_attachment" "github_actions_admin" {
  count      = var.env != "prod" ? 0 : 1
  role       = one(aws_iam_role.github_actions_role[*].name)
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# =========================================================
#           TERRAFORM STATE LOCKING (DYNAMODB)
# =========================================================

resource "aws_dynamodb_table" "terraform_lock" {
  name         = "jobscraper-terraform-lock${local.env_suffix}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
    Purpose     = "StateLocking"
  }
}

# =========================================================
#        CUSTOM IAM POLICIES (Scraper S3, DLQ, Glue)
# =========================================================

resource "aws_iam_policy" "scraper_s3_write_policy" {
  name        = "jobscraper_s3_write_policy${local.env_suffix_underscore}"
  description = "Write access for scraper to Bronze and Silver S3 buckets"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:ListBucketVersions"]
        Resource = [aws_s3_bucket.bronze.arn, aws_s3_bucket.silver.arn]
      },
      {
        Sid      = "AllowBronzeObjectReadWrite"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.bronze.arn}/*"]
      },
      {
        Sid      = "AllowSilverObjectWrite"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = ["${aws_s3_bucket.silver.arn}/*"]
      }
    ]
  })
}

# Policy untuk mengizinkan Lambda mengirim pesan ke SQS DLQ
resource "aws_iam_policy" "lambda_dlq_policy" {
  name = "jobscraper_lambda_dlq_policy${local.env_suffix_underscore}"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = aws_sqs_queue.scraper_dlq.arn
    }]
  })
}

resource "aws_iam_policy" "lambda_glue_policy" {
  name        = "jobscraper_lambda_glue_policy${local.env_suffix_underscore}"
  description = "Allow Lambda to create partitions in Glue Catalog (silver layer)"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "glue:BatchCreatePartition",
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
          "glue:CreatePartition",
          "glue:DeletePartition"
        ]
        Resource = "*"
      }
    ]
  })
}

# =========================================================
#           SLACK ALERT LAMBDA ROLE & POLICIES
# =========================================================

resource "aws_iam_role" "slack_lambda_role" {
  name = "jobscraper_slack_lambda_role${local.env_suffix}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Purpose     = "SlackAlertLambda"
    ManagedBy   = "Terraform"
  }
}

# Policy untuk Athena (query job postings dari Silver layer)
resource "aws_iam_policy" "slack_athena_policy" {
  name        = "jobscraper_slack_athena_policy${local.env_suffix_underscore}"
  description = "Allow Slack Lambda to query Athena for new job postings"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAthenaQueryExecution"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetWorkGroup"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowGlueAccess"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowLakeFormationAccess"
        Effect = "Allow"
        Action = [
          "lakeformation:GetDataAccess",
          "lakeformation:GetDataLakePrincipal"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy untuk SSM (get Slack webhook URL dari Parameter Store)
resource "aws_iam_policy" "slack_ssm_policy" {
  name        = "jobscraper_slack_ssm_policy${local.env_suffix_underscore}"
  description = "Allow Slack Lambda to retrieve webhook URL from SSM Parameter Store"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowGetParameter"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:*:*:parameter/jobscraper/slack/*"
      }
    ]
  })
}

# Policy untuk S3 (read Athena query results)
resource "aws_iam_policy" "slack_s3_policy" {
  name        = "jobscraper_slack_s3_policy${local.env_suffix_underscore}"
  description = "Allow Slack Lambda to read S3 query results from Athena"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAthenaQueryResultsAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:GetBucketLocation",
          "s3:DeleteObject"
        ]
        Resource = [
          data.aws_s3_bucket.athena_query_results.arn,
          "${data.aws_s3_bucket.athena_query_results.arn}/*"
        ]
      }
    ]
  })
}

# Attach policies ke slack_lambda_role
resource "aws_iam_role_policy_attachment" "slack_athena_attachment" {
  role       = aws_iam_role.slack_lambda_role.name
  policy_arn = aws_iam_policy.slack_athena_policy.arn
}

resource "aws_iam_role_policy_attachment" "slack_ssm_attachment" {
  role       = aws_iam_role.slack_lambda_role.name
  policy_arn = aws_iam_policy.slack_ssm_policy.arn
}

resource "aws_iam_role_policy_attachment" "slack_s3_attachment" {
  role       = aws_iam_role.slack_lambda_role.name
  policy_arn = aws_iam_policy.slack_s3_policy.arn
}

# Also attach basic Lambda execution policy untuk logs ke CloudWatch
resource "aws_iam_role_policy_attachment" "slack_basic_execution" {
  role       = aws_iam_role.slack_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# =========================================================
#           LAMBDA EXEC ROLE (Scrapers & Silver)
# =========================================================

resource "aws_iam_role" "lambda_exec_role" {
  name = "jobscraper_lambda_role${local.env_suffix}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.scraper_s3_write_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_ecr" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Attach DLQ policy ke role Lambda
resource "aws_iam_role_policy_attachment" "lambda_dlq" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_dlq_policy.arn
}

# Attach Glue policy ke role Lambda (untuk silver layer transformation)
resource "aws_iam_role_policy_attachment" "lambda_glue" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_glue_policy.arn
}

# =========================================================
#           EVENTBRIDGE SCHEDULER ROLE
# =========================================================

# IAM Role untuk EventBridge
resource "aws_iam_role" "eventbridge_role" {
  name = "jobscraper_eventbridge_role${local.env_suffix}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
    }]
  })

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_policy" "eventbridge_state_machine_policy" {
  name        = "jobscraper_eventbridge_state_machine_policy${local.env_suffix_underscore}"
  description = "Policy untuk EventBridge invoke State Machine"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "states:StartExecution"
      ]
      Resource = aws_sfn_state_machine.jobscraper_orchestrator.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eventbridge_state_machine_attach" {
  role       = aws_iam_role.eventbridge_role.id
  policy_arn = aws_iam_policy.eventbridge_state_machine_policy.arn
}

# =========================================================
#           GLUE CRAWLER ROLE & POLICY
# =========================================================

resource "aws_iam_role" "glue_role" {
  name = "jobscraper_glue_crawler_role${local.env_suffix}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_role_policy_attachment" "glue_service_role" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_policy" "glue_s3_read" {
  name        = "jobscraper_glue_s3_read_policy${local.env_suffix_underscore}"
  description = "Read access untuk Glue Crawler ke S3 bucket"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:ListBucket",
        "s3:GetObject",
      ]
      Resource = [
        aws_s3_bucket.bronze.arn,
        "${aws_s3_bucket.bronze.arn}/*"
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_s3_read_attach" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_s3_read.arn
}

# =========================================================
#           STATE MACHINE (STEP FUNCTIONS)
# =========================================================

resource "aws_iam_role" "step_functions_role" {
  name = "jobscraper_step_functions_role${local.env_suffix}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
    }]
  })

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_policy" "step_functions_policy" {
  name        = "jobscraper_step_functions_policy${local.env_suffix_underscore}"
  description = "Policy untuk Step Functions invoke Lambda dan logging"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaInvoke"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          "${aws_lambda_function.scraper.arn}:*",
          "${aws_lambda_function.silver_layer.arn}:*",
          "${aws_lambda_function.slack_alert.arn}:*"
        ]
      },
      {
        Sid    = "AllowCloudWatchLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "step_functions_policy" {
  role       = aws_iam_role.step_functions_role.id
  policy_arn = aws_iam_policy.step_functions_policy.arn
}
