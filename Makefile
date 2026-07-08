.PHONY: sync-main update-main fmt lint mypy test ci help docker-build docker-up docker-down init-superset tf-prod-plan tf-prod-apply

# Git shortcuts
sync-main:
	@echo "🔄 Syncing with main branch..."
	git checkout main
	git pull origin main
	@echo "✅ Sync complete!"

update-main: sync-main

# CI shortcuts (matching ci.yml)
fmt:
	@echo "✨ Auto-formatting code..."
	poetry run ruff format src tests
	@echo "✅ Formatting complete!"

lint: fmt
	@echo "📝 Running ruff linter..."
	poetry run ruff format --check src tests
	poetry run ruff check src tests --fix --unsafe-fixes
	@echo "✅ Lint passed!"

mypy:
	@echo "🔍 Running type check with mypy..."
	poetry run mypy src tests
	@echo "✅ Type check passed!"

test:
	@echo "🧪 Running pytest..."
	poetry run pytest --tb=short
	@echo "✅ Tests passed!"

ci: fmt lint mypy test
	@echo "✅ All CI checks passed!"

help:
	@echo "Available commands:"
	@echo ""
	@echo "Git shortcuts:"
	@echo "  make sync-main     - Checkout main and pull latest changes"
	@echo "  make update-main   - Alias for sync-main"
	@echo ""
	@echo "CI shortcuts (from ci.yml):"
	@echo "  make fmt           - Auto-format code with ruff"
	@echo "  make lint          - Check formatting and linting"
	@echo "  make mypy          - Run type check with mypy"
	@echo "  make test          - Run pytest"
	@echo "  make ci            - Run all CI checks (fmt + lint + mypy + test)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  - Build docker images"
	@echo "  make docker-up     - Start containers in background"
	@echo "  make docker-down    - Stop and remove containers"
	@echo "  make init-superset - Init Superset (db upgrade, create admin, init)"
	@echo ""
	@echo "Terraform (envs/prod):"
	@echo "  make tf-prod-plan       - Run terraform plan for prod"
	@echo "  make tf-prod-apply      - Run terraform apply for prod"
	@echo ""
	@echo "Terraform (envs/dev):"
	@echo "  make tf-dev-plan        - Run terraform plan for dev"
	@echo "  make tf-dev-apply       - Run terraform apply for dev"

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

init-superset:
	docker compose exec superset_job_scraper /bin/bash /app/init-superset.sh

tf-prod-plan:
	@echo "📋 Running terraform plan (prod)..."
	cd terraform/envs/prod && terraform plan -var-file=terraform.tfvars
	@echo "✅ Terraform plan complete!"

tf-prod-apply:
	@echo "🚀 Running terraform apply (prod)..."
	cd terraform/envs/prod && terraform apply -var-file=terraform.tfvars
	@echo "✅ Terraform apply complete!"

tf-dev-plan:
	@echo "📋 Running terraform plan (dev)..."
	cd terraform/envs/dev && terraform plan -var-file=terraform.tfvars
	@echo "✅ Terraform plan complete!"

tf-dev-apply:
	@echo "🚀 Running terraform apply (dev)..."
	cd terraform/envs/dev && terraform apply -var-file=terraform.tfvars
	@echo "✅ Terraform apply complete!"
