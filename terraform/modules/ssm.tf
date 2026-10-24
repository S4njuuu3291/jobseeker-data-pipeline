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
  name      = "/jobscraper/deepseek/api_key${local.env_suffix}"
  type      = "SecureString"
  value     = "placeholder"
  overwrite = true
  lifecycle { ignore_changes = [value] }
  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
    Purpose     = "DeepSeekAPIKey"
  }
}



# Populate SecureStrings outside Terraform. Glints sessions need refreshing
# when they expire; placeholders fail explicitly rather than returning no jobs.
resource "aws_ssm_parameter" "scraper_credentials" {
  for_each = {
    glints     = "/jobscraper/glints/cookie${local.env_suffix}"
    techinasia = "/jobscraper/techinasia/api_key${local.env_suffix}"
  }
  name  = each.value
  type  = "SecureString"
  value = "placeholder"
  lifecycle { ignore_changes = [value] }
  tags = { Environment = var.env, Project = "Job-Scraper", ManagedBy = "Terraform" }
}

data "aws_ssm_parameter" "deepseek_api_key" {
  name = aws_ssm_parameter.deepseek_api_key.name
  depends_on = [aws_ssm_parameter.deepseek_api_key]
}
