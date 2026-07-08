terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# AWS Provider Configuration
provider "aws" {
  region = var.aws_region

  skip_metadata_api_check = true
  skip_region_validation  = false

  default_tags {
    tags = {
      Environment = "Learning"
      Project     = "Terraform-Fundamentals"
      ManagedBy   = "Terraform"
      Chapter     = "00-setup-provider"
    }
  }
}
