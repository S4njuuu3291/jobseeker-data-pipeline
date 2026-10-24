# 1. AWS SNS Topic untuk Penampung Alert
resource "aws_sns_topic" "pipeline_alert" {
  name = "scraper-dlq-sns${local.env_suffix}"
}

# 2. Email Subscription ke SNS Topic
resource "aws_sns_topic_subscription" "pipeline_alert_email" {
  topic_arn = aws_sns_topic.pipeline_alert.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# 3. CloudWatch Alarm: Step Functions Failure
resource "aws_cloudwatch_metric_alarm" "sfn_execution_failure" {
  alarm_name          = "StepFunctionsFailureAlarm${local.env_suffix}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300 # Window evaluasi 5 menit (300 detik)
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "ALERT: Step Functions JobScraperMachine mengalami failure/crash!"
  treat_missing_data  = "notBreaching" # Jika pipeline tidak jalan, jangan anggap error (karena ini khusus monitor error)

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.jobscraper_orchestrator.arn
  }

  alarm_actions = [aws_sns_topic.pipeline_alert.arn]
  ok_actions    = [aws_sns_topic.pipeline_alert.arn]
}

# 4. CloudWatch Alarm: Lambda Unhandled Errors / Timeout (per scraper)
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(local.lambda_scraper_functions)

  alarm_name          = "${each.key}-Errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "ALERT: Lambda ${each.key} melempar unhandled exception atau timeout!"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.key
  }

  alarm_actions = [aws_sns_topic.pipeline_alert.arn]
  ok_actions    = [aws_sns_topic.pipeline_alert.arn]
}

# 5. SLA Monitoring: CloudWatch Alarm untuk State Machine
# CloudWatch Alarm: Data Freshness SLA Breach
resource "aws_cloudwatch_metric_alarm" "pipeline_freshness_sla" {
  alarm_name          = "job-pipeline-freshness-sla-breach${local.env_suffix}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsStarted"
  namespace           = "AWS/States"

  # Window Evaluasi: 24 Jam (86400 detik)
  period    = 86400
  statistic = "Sum"
  threshold = 1 # Ekspektasi: Minimal ada 1 eksekusi per hari

  alarm_description = "CRITICAL: Pipeline tidak berjalan sama sekali dalam 24 jam terakhir! Potensi EventBridge mati atau terhapus."

  treat_missing_data = "breaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.jobscraper_orchestrator.arn
  }

  alarm_actions = [aws_sns_topic.pipeline_alert.arn]
  ok_actions    = [aws_sns_topic.pipeline_alert.arn]
}
