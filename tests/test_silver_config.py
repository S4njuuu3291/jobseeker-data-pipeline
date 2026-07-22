"""Tests for Silver layer configuration module."""

import os
import pytest

# Mock the dotenv load before importing config
os.environ["platform"] = "kalibrr,glints,jobstreet"
os.environ["AWS_S3_BUCKET_NAME"] = "test-bronze-bucket"
os.environ["AWS_S3_SILVER_BUCKET_NAME"] = "test-silver-bucket"

from src.silver_layer.config import (
    get_list_platforms,
    get_bronze_bucket_name,
    get_silver_bucket_name,
    JOB_SILVER_SCHEMA,
)


class TestGetListPlatforms:
    """Tests for get_list_platforms function."""

    def test_get_list_platforms_success(self):
        """Test successfully retrieving platform list from environment."""
        platforms = get_list_platforms()
        assert platforms == ["kalibrr", "glints", "jobstreet"]
        assert len(platforms) == 3

    def test_get_list_platforms_missing_env(self, monkeypatch):
        """Test error when platform environment variable is missing."""
        monkeypatch.delenv("platform", raising=False)
        with pytest.raises(ValueError, match="platform environment variable not set"):
            get_list_platforms()


class TestGetBronzeBucketName:
    """Tests for get_bronze_bucket_name function."""

    def test_get_bronze_bucket_success(self):
        """Test successfully retrieving Bronze bucket name."""
        bucket_name = get_bronze_bucket_name()
        assert bucket_name == "test-bronze-bucket"

    def test_get_bronze_bucket_missing_env(self, monkeypatch):
        """Test error when Bronze bucket environment variable is missing."""
        monkeypatch.delenv("AWS_S3_BUCKET_NAME", raising=False)
        with pytest.raises(
            ValueError, match="AWS_S3_BUCKET_NAME environment variable not set"
        ):
            get_bronze_bucket_name()


class TestGetSilverBucketName:
    """Tests for get_silver_bucket_name function."""

    def test_get_silver_bucket_success(self):
        """Test successfully retrieving Silver bucket name."""
        bucket_name = get_silver_bucket_name()
        assert bucket_name == "test-silver-bucket"

    def test_get_silver_bucket_missing_env(self, monkeypatch):
        """Test error when Silver bucket environment variable is missing."""
        monkeypatch.delenv("AWS_S3_SILVER_BUCKET_NAME", raising=False)
        with pytest.raises(
            ValueError, match="AWS_S3_SILVER_BUCKET_NAME environment variable not set"
        ):
            get_silver_bucket_name()


class TestJobSilverSchema:
    """Tests for JOB_SILVER_SCHEMA definition."""

    def test_schema_has_required_columns(self):
        """Test that schema has all required columns."""
        expected_columns = {
            "job_id",
            "job_title",
            "job_url",
            "platform",
            "scraped_at",
            "keyword",
            "job_description",
            "role",
            "company_name",
            "location",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "job_type",
            "seniority",
            "work_mode",
            "experience_min",
            "experience_max",
            "education",
            "company_industry",
            "skills",
            "benefits",
            "posting_date",
        }
        assert set(JOB_SILVER_SCHEMA.columns.keys()) == expected_columns

    def test_schema_job_id_is_unique(self):
        """Test that job_id column is marked as unique."""
        job_id_column = JOB_SILVER_SCHEMA.columns["job_id"]
        assert job_id_column.unique is True
