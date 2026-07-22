"""Tests for Silver layer storage module."""

import io
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
from botocore.exceptions import ClientError

from src.silver_layer.storage import get_bronze_object, upload_to_silver


class TestGetBronzeObject:
    """Tests for get_bronze_object function."""

    @pytest.fixture
    def sample_dataframe(self):
        """Fixture for sample dataframe."""
        return pd.DataFrame(
            {
                "job_id": ["id1", "id2"],
                "job_title": ["Engineer", "Developer"],
                "company_name": ["Company A", "Company B"],
                "location": ["Jakarta", "Bandung"],
                "job_url": ["http://example.com/1", "http://example.com/2"],
                "platform": ["kalibrr", "glints"],
                "scraped_at": ["20260305_090000", "20260305_090100"],
            }
        )

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.get_bronze_bucket_name")
    def test_get_bronze_object_success(
        self, mock_bucket, mock_s3_client, sample_dataframe
    ):
        """Test successfully reading from Bronze S3 bucket."""
        mock_bucket.return_value = "test-bronze-bucket"

        # Mock S3 client
        mock_s3 = MagicMock()
        mock_s3_client.return_value = mock_s3

        # Mock list_objects_v2 response
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "platform=kalibrr/ingestion_date=2026-03-05/kalibrr_090000.parquet"
                },
            ]
        }

        # Mock get_object response
        buffer = io.BytesIO()
        sample_dataframe.to_parquet(buffer)
        buffer.seek(0)

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: buffer.getvalue())
        }

        # Test
        result = get_bronze_object(["kalibrr"])

        assert len(result) > 0
        assert "job_id" in result.columns

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.get_bronze_bucket_name")
    def test_get_bronze_object_no_objects(self, mock_bucket, mock_s3_client):
        """Test when no objects found in Bronze bucket."""
        mock_bucket.return_value = "test-bronze-bucket"

        mock_s3 = MagicMock()
        mock_s3_client.return_value = mock_s3

        # Mock empty response
        mock_s3.list_objects_v2.return_value = {}

        result = get_bronze_object(["kalibrr"])

        assert len(result) == 0
        assert isinstance(result, pd.DataFrame)

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.get_bronze_bucket_name")
    def test_get_bronze_object_multiple_platforms(
        self, mock_bucket, mock_s3_client, sample_dataframe
    ):
        """Test reading from multiple platforms."""
        mock_bucket.return_value = "test-bronze-bucket"

        mock_s3 = MagicMock()
        mock_s3_client.return_value = mock_s3

        # Mock responses for each platform
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "platform=kalibrr/ingestion_date=2026-03-05/kalibrr_090000.parquet"
                },
                {
                    "Key": "platform=glints/ingestion_date=2026-03-05/glints_090100.parquet"
                },
            ]
        }

        # Mock get_object
        buffer = io.BytesIO()
        sample_dataframe.to_parquet(buffer)
        buffer.seek(0)

        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: buffer.getvalue())
        }

        result = get_bronze_object(["kalibrr", "glints"])

        assert len(result) > 0

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.get_bronze_bucket_name")
    def test_get_bronze_object_s3_error(self, mock_bucket, mock_s3_client):
        """Test error handling when S3 operation fails."""
        mock_bucket.return_value = "test-bronze-bucket"

        mock_s3 = MagicMock()
        mock_s3_client.return_value = mock_s3

        # Mock S3 error
        mock_s3.list_objects_v2.side_effect = ClientError(
            {
                "Error": {
                    "Code": "NoSuchBucket",
                    "Message": "The specified bucket does not exist",
                }
            },
            "ListObjects",
        )

        with pytest.raises(ClientError):
            get_bronze_object(["kalibrr"])


class TestUploadToSilver:
    """Tests for upload_to_silver function."""

    @pytest.fixture
    def sample_dataframe(self):
        """Fixture for sample dataframe."""
        return pd.DataFrame(
            {
                "job_id": ["id1", "id2"],
                "job_title": ["Engineer", "Developer"],
                "company_name": ["Company A", "Company B"],
                "location": ["Jakarta", "Bandung"],
                "job_url": ["http://example.com/1", "http://example.com/2"],
                "platform": ["kalibrr", "glints"],
                "scraped_at": ["20260305_090000", "20260305_090100"],
                "keyword": ["data-engineer", "data-scientist"],
            }
        )

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.os.getenv")
    def test_upload_to_silver_success(
        self, mock_getenv, mock_s3_client, sample_dataframe
    ):
        """Test successfully uploading to Silver S3 bucket."""
        # Mock os.getenv for bucket and glue config
        mock_getenv.side_effect = lambda key, default=None: {
            "AWS_S3_SILVER_BUCKET_NAME": "test-silver-bucket",
            "AWS_GLUE_DATABASE_NAME": "test_db",
            "AWS_GLUE_SILVER_TABLE_NAME": "test_table",
        }.get(key, default)

        mock_s3 = MagicMock()
        mock_s3_client.return_value = mock_s3

        mock_s3.put_object.return_value = {"ETag":"abc123"}

        result = upload_to_silver(sample_dataframe)

        assert isinstance(result, str)
        assert "ingestion_date=" in result
        assert "job_data_" in result
        assert ".parquet" in result
        mock_s3.put_object.assert_called_once()

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.os.getenv")
    def test_upload_to_silver_s3_error(
        self, mock_getenv, mock_s3_client, sample_dataframe
    ):
        """Test error handling when S3 upload fails."""
        # Mock os.getenv for bucket and glue config
        mock_getenv.side_effect = lambda key, default=None: {
            "AWS_S3_SILVER_BUCKET_NAME": "test-silver-bucket",
            "AWS_GLUE_DATABASE_NAME": "test_db",
            "AWS_GLUE_SILVER_TABLE_NAME": "test_table",
        }.get(key, default)

        mock_s3 = MagicMock()
        mock_s3_client.return_value = mock_s3

        # Mock S3 error
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "PutObject"
        )

        with pytest.raises(ClientError):
            upload_to_silver(sample_dataframe)

    @patch("src.silver_layer.storage.boto3.client")
    @patch("src.silver_layer.storage.os.getenv")
    def test_upload_to_silver_object_key_format(
        self, mock_getenv, mock_s3_client, sample_dataframe
    ):
        """Test that object key has correct format."""
        # Mock os.getenv for bucket and glue config
        mock_getenv.side_effect = lambda key, default=None: {
            "AWS_S3_SILVER_BUCKET_NAME": "test-silver-bucket",
            "AWS_GLUE_DATABASE_NAME": "test_db",
            "AWS_GLUE_SILVER_TABLE_NAME": "test_table",
        }.get(key, default)

        mock_s3 = MagicMock()
        mock_glue = MagicMock()
        mock_s3_client.side_effect = [mock_s3, mock_glue]

        mock_glue.create_partition.return_value = {}

        upload_to_silver(sample_dataframe)

        # Get the call arguments
        call_args = mock_s3.put_object.call_args
        object_key = call_args[1]["Key"]

        # Validate format
        assert object_key.startswith("ingestion_date=")
        assert "job_data_" in object_key
        assert object_key.endswith(".parquet")
