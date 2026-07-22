import pytest
import pandera.pandas as pa
from src.utils.data_validator import validate_job_data
from src.utils.data_validator import job_schema
from src.utils.scraper_utils import (
    DEVICE_PROFILES,
    human_delay,
)
from src.utils.upload_to_s3 import upload_to_s3
from unittest.mock import patch, MagicMock
import pandas as pd

# ===============================================================================
#                              DATA VALIDATOR TESTS
# ===============================================================================


class TestDataValidator:
    def test_valid_data(self):
        data = {
            "job_id": ["1", "2"],
            "job_title": ["Software Engineer", "Data Scientist"],
            "company_name": ["Company A", "Company B"],
            "location": ["Jakarta", "Bandung"],
            "job_url": ["http://example.com/job1", "http://example.com/job2"],
            "platform": ["kalibrr", "jobstreet"],
            "job_description": "test description",
            "scraped_at": ["2024-06-01T12:00:00Z", "2024-06-01T12:05:00Z"],            "job_description": ["Job desc 1","Job desc 2"],        }

        df = pd.DataFrame(data)
        validated_df = validate_job_data(df)

        assert validated_df.equals(df)

    def test_invalid_platform(self):
        data = {
            "job_id": ["1"],
            "job_title": ["Software Engineer"],
            "company_name": ["Company A"],
            "location": ["Jakarta"],
            "job_url": ["http://example.com/job1"],
            "platform": ["invalid_platform"],
            "job_description": "test description",
            "scraped_at": ["2024-06-01T12:00:00Z"],
        }

        df = pd.DataFrame(data)
        with pytest.raises(pa.errors.SchemaError):
            validate_job_data(df)

    def test_missing_column(self):
        data = {
            "job_id": ["1"],
            "job_title": ["Software Engineer"],
            "company_name": ["Company A"],
            "location": ["Jakarta"],
            "job_url": ["http://example.com/job1"],
            # "platform" column is missing
            "job_description": "test description",
            "scraped_at": ["2024-06-01T12:00:00Z"],
        }

        df = pd.DataFrame(data)
        with pytest.raises(pa.errors.SchemaError):
            validate_job_data(df)

    def test_duplicate_job_id(self):
        data = {
            "job_id": ["1", "1"],  # Duplicate job_id
            "job_title": ["Software Engineer", "Data Scientist"],
            "company_name": ["Company A", "Company B"],
            "location": ["Jakarta", "Bandung"],
            "job_url": ["http://example.com/job1", "http://example.com/job2"],
            "platform": ["kalibrr", "jobstreet"],
            "job_description": "test description",
            "scraped_at": ["2024-06-01T12:00:00Z", "2024-06-01T12:05:00Z"],
        }

        df = pd.DataFrame(data)
        with pytest.raises(pa.errors.SchemaError):
            validate_job_data(df)

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=job_schema.columns)
        validated_df = validate_job_data(df)

        assert len(validated_df) == 0


# ===============================================================================
#                              SCRAPER UTILS TESTS
# ===============================================================================


class TestScraperUtils:
    @pytest.mark.asyncio
    async def test_human_delay_within_range(self):
        min_ms = 50
        max_ms = 150
        start_time = pd.Timestamp.now()
        await human_delay(min_ms, max_ms)
        end_time = pd.Timestamp.now()
        elapsed_ms = (end_time - start_time).total_seconds() * 1000

        assert (
            min_ms <= elapsed_ms <= max_ms + 50
        )  # Allow some buffer for execution time

    def test_device_profiles(self):
        for profile_name, profile in DEVICE_PROFILES.items():
            assert "user_agent" in profile
            assert "viewport" in profile
            assert "device_scale_factor" in profile
            assert "is_mobile" in profile
            assert "has_touch" in profile

    def test_device_profiles_viewport(self):
        for profile_name, profile in DEVICE_PROFILES.items():
            viewport = profile["viewport"]
            assert viewport["width"] > 0
            assert viewport["height"] > 0
            assert isinstance(viewport["width"], int)
            assert isinstance(viewport["height"], int)


# ===============================================================================
#                              UPLOAD TO S3 TESTS
# ===============================================================================


class TestUploadToS3:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame(
            {
                "job_id": ["1", "2"],
                "job_title": ["Software Engineer", "Data Scientist"],
                "company_name": ["Company A", "Company B"],
                "location": ["Jakarta", "Bandung"],
                "job_url": ["http://example.com/job1", "http://example.com/job2"],
            }
        )

    @patch.dict("os.environ", {"AWS_S3_BUCKET_NAME": "test-bucket"})
    @patch("src.utils.upload_to_s3.boto3.client")
    def test_upload_to_s3_success(self, mock_boto3_client, sample_df):
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = (
            mock_s3_client  # Mock list_objects_v2 to return no existing objects
        )
        mock_s3_client.list_objects_v2.return_value = {"KeyCount": 0}
        result = upload_to_s3(sample_df, "kalibrr")

        assert result
        assert mock_s3_client.put_object.called

        args, kwargs = mock_s3_client.put_object.call_args
        assert kwargs["Bucket"] == "test-bucket"
        assert "kalibrr" in kwargs["Key"]
        assert "platform=kalibrr" in kwargs["Key"]

    @patch.dict("os.environ", {}, clear=True)  # Clear environment variables
    def test_missing_bucket_name(self, sample_df):
        with pytest.raises(ValueError):
            upload_to_s3(sample_df, "kalibrr")

    @patch.dict("os.environ", {"AWS_S3_BUCKET_NAME": "test-bucket"})
    @patch("src.utils.upload_to_s3.boto3.client")
    def test_upload_to_s3_failure(self, mock_boto3_client, sample_df):
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client
        # Mock list_objects_v2 to return no existing objects
        mock_s3_client.list_objects_v2.return_value = {"KeyCount": 0}
        mock_s3_client.put_object.side_effect = Exception("S3 upload failed")

        result = upload_to_s3(sample_df, "kalibrr")
        assert not result

    @patch.dict("os.environ", {"AWS_S3_BUCKET_NAME": "test-bucket"})
    @patch("src.utils.upload_to_s3.boto3.client")
    def test_file_path_format(self, mock_boto3_client, sample_df):
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client
        # Mock list_objects_v2 to return no existing objects
        mock_s3_client.list_objects_v2.return_value = {"KeyCount": 0}

        upload_to_s3(sample_df, "kalibrr")

        call_args = mock_s3_client.put_object.call_args
        file_key = call_args[1]["Key"]

        assert file_key.startswith("platform=kalibrr/ingestion_date=")
        assert file_key.endswith(".parquet")
        assert "kalibrr_" in file_key
