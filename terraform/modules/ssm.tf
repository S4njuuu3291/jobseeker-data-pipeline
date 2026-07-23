# SSM PARAMETER STORE

resource "aws_ssm_parameter" "slack_webhook_url" {
  name  = "/jobscraper/slack/webhook_url${local.env_suffix}"
  type  = "SecureString"
  value = var.slack_webhook_url != "" ? var.slack_webhook_url : "default"

  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
    Purpose     = "SlackWebhookURL"
  }
}

resource "aws_ssm_parameter" "deepseek_api_key" {
  name     = "/jobscraper/deepseek/api_key${local.env_suffix}"
  type     = "SecureString"
  value    = "placeholder"
  overwrite = true
  lifecycle { ignore_changes = [value] }
  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
    Purpose     = "DeepSeekAPIKey"
  }
}

data "aws_ssm_parameter" "deepseek_api_key" {
  name = aws_ssm_parameter.deepseek_api_key.name
  depends_on = [aws_ssm_parameter.deepseek_api_key]
}
