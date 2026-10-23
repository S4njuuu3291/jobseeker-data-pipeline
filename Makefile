.PHONY: sync-main update-main fmt lint mypy test ci help docker-build docker-up docker-down init-superset tf-prod-plan tf-prod-apply docker-ecr-login-dev docker-ecr-push-dev tf-dev-plan tf-dev-apply reset-manifest

# Contoh command manual (dokumentasi saja, bukan target/shortcut Make).
# Jalankan dari root project kecuali bagian SAM; aktifkan environment Python:
# conda activate basic_dev
# Konfigurasi bucket/kredensial AWS mengikuti .env atau environment lokal.
# Pipeline main menulis ke S3; data_reader hanya membaca.
#
# Data reader: head 5 baris, jumlah baris, dan rekonsiliasi Bronze/Silver.
# python src/utils/data_reader.py --date 2026-10-13
# python src/utils/data_reader.py --date 2026-10-23 --platform kalibrr --layer bronze
# python src/utils/data_reader.py --help
#
# Main: pilih platform; tanpa --keywords memakai default/SCRAPE_KEYWORDS.
# python -m src.main.main --platform glints
# python -m src.main.main --platform kalibrr
# python -m src.main.main --platform jobstreet
# python -m src.main.main --platform dealls
# python -m src.main.main --platform techinasia
# python -m src.main.main --platform glints --keywords "data engineer" "etl"
# python -m src.main.main --platform all
# python -m src.main.main --platform all --keywords "data engineer" "etl"
# python -m src.main.main --help
# --platform all menjalankan kelima platform secara berurutan.
# --keywords menerima keyword dengan spasi; main menyesuaikan format per platform.
#
# Manifest CLI (platform dapat diganti dengan salah satu dari kelima platform).
# python -m src.utils.manifest glints read
# python -m src.utils.manifest glints filter JOB_ID_1 JOB_ID_2
# update mengganti seluruh manifest dengan ID yang diberikan; tanpa ID = reset kosong.
# python -m src.utils.manifest glints update JOB_ID_1 JOB_ID_2
# python -m src.utils.manifest glints update
# delete menghapus manifest dan meminta konfirmasi interaktif.
# python -m src.utils.manifest glints delete
#
# SAM + Terraform dev: jalankan dari terraform/envs/dev.
# Memerlukan SAM CLI, Docker, kredensial AWS, dan akses image ECR.
# terraform.tfvars dibaca otomatis; TF_VAR_env tidak diperlukan.
# cd terraform/envs/dev
# Buat event.json di folder tersebut dengan isi: {"platform": "glints"}
# sam local invoke --hook-name terraform module.base.aws_lambda_function.scraper -e event.json
# Platform dipilih melalui event.json; kode berasal dari image rujukan Terraform.
# Untuk kembali ke root project: cd ../../..
#
# Docker lokal: build kode lokal tanpa push ECR, jalankan dari root project.
# docker build -t jobscraper-local .
# AWS_PROFILE dapat diganti dengan profil lokal yang digunakan.
# docker run --rm -p 9000:8080 -v "$HOME/.aws:/root/.aws:ro" -e AWS_PROFILE=default -e AWS_DEFAULT_REGION=ap-southeast-1 -e AWS_S3_BUCKET_NAME=jobscraper-bronze-data-8424560-dev jobscraper-local src.entrypoint.handlers.scraper_handler
# Dari terminal lain, panggil handler (platform dapat diganti):
# curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations -H 'Content-Type: application/json' -d '{"platform":"glints"}'
# Default CMD Dockerfile juga menggunakan generic scraper_handler.
#
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
