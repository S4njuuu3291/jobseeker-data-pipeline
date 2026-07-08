# =========================================================
#                     ECR REPOSITORY
# =========================================================

resource "aws_ecr_repository" "scraper_repo" {
  name                 = "job-scraper-lambda${local.env_suffix}"
  force_delete         = true
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Environment = var.env
    Project     = "Job-Scraper"
    ManagedBy   = "Terraform"
  }
}

data "aws_ecr_image" "scraper_latest" {
  repository_name = aws_ecr_repository.scraper_repo.name
  image_tag       = "latest"
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  repository = aws_ecr_repository.scraper_repo.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Hanya simpan 1 image terbaru, hapus sisanya"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 1
      }
      action = { type = "expire" }
    }]
  })
}
