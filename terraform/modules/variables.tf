variable "aws_region" {
  type        = string
  default     = "ap-southeast-1"
  description = "AWS region untuk deploy resources. Default: ap-southeast-1 (Singapore)"
}

variable "slack_webhook_url" {
  type        = string
  default     = ""
  description = "Slack webhook URL for sending alerts. Leave empty and set manually in AWS Console SSM Parameter Store"
  sensitive   = true
}

variable "project_root" {
  type        = string
  description = "Absolute path to project root (used for archive_file source paths)"
}

variable "env" {
  type        = string
  description = "Environment name (dev, prod)"
  # validasi hanya menerima nilai tertentu
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "Environment name harus salah satu dari: dev, prod"
  }
}

