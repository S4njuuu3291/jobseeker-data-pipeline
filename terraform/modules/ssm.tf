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
