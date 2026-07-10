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

# Cari image digest terbaru — graceful fallback jika repo masih kosong
data "external" "scraper_latest" {
  program = ["bash", "-c", format(<<EOT
    DIGEST=$(aws ecr describe-images \
      --repository-name %s \
      --image-ids imageTag=latest \
      --query 'imageDetails[0].imageDigest' \
      --output text 2>/dev/null || echo "")
    echo "{\"digest\": \"$DIGEST\"}"
  EOT
  , aws_ecr_repository.scraper_repo.name)]
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
