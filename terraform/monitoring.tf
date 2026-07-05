# =========================================================
#                   SQS DEAD LETTER QUEUE
# =========================================================

resource "aws_sqs_queue" "scraper_dlq" {
  name                      = "jobscraper-dlq"
  message_retention_seconds = 1209600 # 14 hari
  tags = {
    Project = "Job-Scraper"
    Purpose = "DeadLetterQueue"
  }
}

# CloudWatch Alarm: Berbunyi jika ada pesan masuk ke DLQ (indikasi ada scraper gagal)
resource "aws_cloudwatch_metric_alarm" "dlq_alarm" {
  alarm_name          = "jobscraper-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # Cek tiap 5 menit
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Ada Lambda scraper yang gagal dan masuk ke Dead Letter Queue"
  dimensions = {
    QueueName = aws_sqs_queue.scraper_dlq.name
  }
}

# =========================================================
#           CLOUDWATCH LOG GROUP STEP FUNCTIONS
# =========================================================

resource "aws_cloudwatch_log_group" "step_functions_logs" {
  name              = "/aws/stepfunctions/jobscraper-orchestrator"
  retention_in_days = 7

  tags = {
    Project   = "Job-Scraper"
    ManagedBy = "Terraform"
    Purpose   = "StepFunctionsLogging"
  }
}
