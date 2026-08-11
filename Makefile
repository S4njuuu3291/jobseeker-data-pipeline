.PHONY: sync-main update-main fmt lint mypy test ci help docker-build docker-up docker-down init-superset tf-prod-plan tf-prod-apply docker-ecr-login-dev docker-ecr-push-dev tf-dev-plan tf-dev-apply reset-manifest

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

docker-build:
	docker compose build

docker-up:
	docker compose up -d

# Reset manifest untuk platform tertentu (biar scrape ulang fresh)
# Usage: make reset-manifest PLATFORM=dealls
reset-manifest:
	@echo "Resetting manifest for platform: $(PLATFORM)"
	poetry run python -c "import sys; sys.path.insert(0, '.'); from src.utils.manifest import read_manifest, update_manifest; print('before:', len(read_manifest('$(PLATFORM)'))); update_manifest('$(PLATFORM)', set()); print('after:', len(read_manifest('$(PLATFORM)')))"
	@echo "Manifest $(PLATFORM) reset!"

tf-dev-init:
	@echo "🔧 Initializing Terraform for dev environment..."
	cd terraform/envs/dev && terraform init
	@echo "✅ Terraform initialization complete!"

tf-dev-unlock:
	@echo "🔓 Unlocking Terraform state for dev environment..."
	cd terraform/envs/dev && terraform force-unlock $(LOCK_ID)
	@echo "✅ Terraform state unlocked!"

tf-dev-plan:
	@echo "🔍 Terraform plan for dev environment..."
	cd terraform/envs/dev && terraform plan
	@echo "✅ Terraform plan complete!"

tf-dev-apply:
	@echo "🚀 Applying Terraform for dev environment..."
	cd terraform/envs/dev && terraform apply -auto-approve
	@echo "✅ Terraform apply complete!"
