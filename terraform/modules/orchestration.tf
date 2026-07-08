# =========================================================
#           EVENTBRIDGE SCHEDULER (CRON) → STATE MACHINE
# =========================================================

# Event Rule untuk jam 11 pagi WIB (04:00 UTC)
# Strategi: Capture postingan tadi malam + pagi, apply saat HR aktif
resource "aws_cloudwatch_event_rule" "scrape_morning" {
  name                = "jobscraper-schedule-morning${local.env_suffix}"
  schedule_expression = "cron(0 4 * * ? *)"
  description         = "Trigger State Machine jam 09:00 WIB - Prime time HR activity (pagi)"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Schedule    = "Morning"
    ManagedBy   = "Terraform"
  }
}

resource "aws_cloudwatch_event_target" "scrape_morning_target" {
  rule      = aws_cloudwatch_event_rule.scrape_morning.name
  target_id = "TriggerStateMachineMorning"
  arn       = aws_sfn_state_machine.joscraper_orchestrator.arn
  role_arn  = aws_iam_role.eventbridge_role.arn
}

# Event Rule untuk jam 4 sore WIB (09:00 UTC)
# Strategi: Capture postingan setelah makan siang, apply sebelum HR tutup laptop
resource "aws_cloudwatch_event_rule" "scrape_evening" {
  name                = "jobscraper-schedule-evening${local.env_suffix}"
  schedule_expression = "cron(0 9 * * ? *)"
  description         = "Trigger State Machine jam 16:00 WIB - Sebelum HR tutup (sore)"

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Schedule    = "Evening"
    ManagedBy   = "Terraform"
  }
}

resource "aws_cloudwatch_event_target" "scrape_evening_target" {
  rule      = aws_cloudwatch_event_rule.scrape_evening.name
  target_id = "TriggerStateMachineEvening"
  arn       = aws_sfn_state_machine.joscraper_orchestrator.arn
  role_arn  = aws_iam_role.eventbridge_role.arn
}

# =========================================================
#           STEP FUNCTIONS STATE MACHINE
# =========================================================

resource "aws_sfn_state_machine" "joscraper_orchestrator" {
  name     = "jobscraper_orchestrator${local.env_suffix_underscore}"
  role_arn = aws_iam_role.step_functions_role.arn

  definition = templatefile("${path.module}/step_functions/JobScraperMachine.asl.json", {
    kalibrr_lambda_arn      = aws_lambda_function.kalibrr.arn
    glints_lambda_arn       = aws_lambda_function.glints.arn
    jobstreet_lambda_arn    = aws_lambda_function.jobstreet.arn
    silver_layer_lambda_arn = aws_lambda_function.silver_layer.arn
    slack_alert_lambda_arn  = aws_lambda_function.slack_alert.arn
  })

  logging_configuration {
    level                  = "ERROR"
    include_execution_data = true
    log_destination        = "${aws_cloudwatch_log_group.step_functions_logs.arn}:*"
  }

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    Owner       = "Sanju"
    ManagedBy   = "Terraform"
  }
}
