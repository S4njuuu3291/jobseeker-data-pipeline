# The pipeline no longer creates or uses ECR. On migration, forget legacy
# image resources without deleting repositories/images needed for rollback.
# Terraform >= 1.7 supports non-destructive removed blocks.
removed {
  from = aws_ecr_repository.scraper_repo
  lifecycle { destroy = false }
}

removed {
  from = aws_ecr_lifecycle_policy.cleanup
  lifecycle { destroy = false }
}
