#!/bin/bash
set -e

echo "Upgrading Superset DB..."
superset db upgrade

echo "Creating Admin user..."
superset fab create-admin \
              --username admin \
              --firstname Superset \
              --lastname Admin \
              --email admin@superset.com \
              --password admin

echo "Initializing Superset..."
superset init

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  Superset siap!                                     ║"
echo "║                                                          ║"
echo "║  Koneksi Athena via UI:                                  ║"
echo "║  1. Buka http://localhost:8088                           ║"
echo "║  2. Login admin:admin                                    ║"
echo "║  3. Settings → Database Connections → + Database         ║"
echo "║  4. Pilih Amazon Athena                                  ║"
echo "║  5. Isi:                                                  ║"
echo "║     - Database name: Job Scraper (Athena)                ║"
echo "║     - S3 staging dir:                                    ║"
echo "║       s3://weather-data-lake-sanju/                      ║"
echo "║         athena-query-results/jobscraper/                 ║"
echo "║     - Database: jobscraper_db                            ║"
echo "║     - Workgroup: jobscraper-slack-alert-workgroup        ║"
echo "║     - Region: ap-southeast-1                             ║"
echo "║  6. Test Connection → Save                                ║"
echo "╚══════════════════════════════════════════════════════════╝"
