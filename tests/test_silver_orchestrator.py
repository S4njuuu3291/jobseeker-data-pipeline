"""Tests for Silver layer orchestrator module."""

from unittest.mock import patch
import pandas as pd
import pytest

from src.silver_layer.orchestrator import transform_silver, run_pipeline


class TestTransformSilver:
    """Tests for transform_silver pipeline orchestration."""

    @pytest.fixture
    def sample_bronze_dataframe(self):
        """Fixture for sample Bronze layer dataframe."""
        return pd.DataFrame(
            {
                "job_id": ["id1", "id2", "id3"],
                "job_title": ["Data Engineer", "Backend Dev", "Frontend Dev"],
                "company_name": ["Company A", "Company B", "Company C"],
                "location": [
                    "jakarta selatan",
                    "bandung",
                    "yogyakarta",
                ],  # Non-normalized
                "job_url": [
                    "http://example.com/1",
                    "http://example.com/2",
                    "http://example.com/3",
                ],
                "platform": ["kalibrr", "glints", "jobstreet"],
                "scraped_at": ["20260305_090000", "20260305_090100", "20260305_090200"],
            }
        )

    @patch("src.silver_layer.orchestrator.upload_to_silver")
    @patch("src.silver_layer.orchestrator.validate_silver_schema")
    @patch("src.silver_layer.orchestrator.apply_location_normalization")
    def test_transform_silver_success(
        self, mock_normalize, mock_validate, mock_upload, sample_bronze_dataframe
    ):
        """Test successful transformation pipeline."""
        # Setup mocks
        mock_normalize.side_effect = lambda df: df.copy()
        mock_validate.return_value = sample_bronze_dataframe.copy()
        mock_upload.return_value = (
            "ingestion_date=2026-03-05/job_data_2026-03-05.parquet"
        )

        # Test
        result = transform_silver(sample_bronze_dataframe)

        assert isinstance(result, str)
        assert "ingestion_date=" in result
        assert ".parquet" in result

        # Verify all steps were called
        mock_normalize.assert_called_once()
        mock_validate.assert_called_once()
        mock_upload.assert_called_once()

    @patch("src.silver_layer.orchestrator.validate_silver_schema")
    @patch("src.silver_layer.orchestrator.apply_location_normalization")
    def test_transform_silver_validation_error(
        self, mock_normalize, mock_validate, sample_bronze_dataframe
    ):
        """Test that validation errors are propagated."""
        mock_normalize.side_effect = lambda df: df.copy()
        mock_validate.side_effect = Exception("Schema validation failed")

        with pytest.raises(Exception, match="Schema validation failed"):
            transform_silver(sample_bronze_dataframe)


class TestRunPipeline:
    """Tests for run_pipeline orchestration function."""

    @pytest.fixture
    def sample_bronze_dataframe(self):
        """Fixture for sample Bronze layer dataframe."""
        return pd.DataFrame(
            {
                "job_id": ["id1", "id2"],
                "job_title": ["Engineer", "Developer"],
                "company_name": ["Company A", "Company B"],
                "location": ["jakarta", "bandung"],
                "job_url": ["http://example.com/1", "http://example.com/2"],
                "platform": ["kalibrr", "glints"],
            }
        )

    @patch("src.silver_layer.orchestrator.upload_to_silver")
    @patch("src.silver_layer.orchestrator.validate_silver_schema")
    @patch("src.silver_layer.orchestrator.apply_location_normalization")
    @patch("src.silver_layer.orchestrator.get_bronze_object")
    @patch("src.silver_layer.orchestrator.get_list_platforms")
    def test_run_pipeline_success(
        self,
        mock_platforms,
        mock_get_bronze,
        mock_normalize,
        mock_validate,
        mock_upload,
        sample_bronze_dataframe,
    ):
        """Test successful complete pipeline execution."""
        # Setup mocks
        mock_platforms.return_value = ["kalibrr", "glints"]
        mock_get_bronze.return_value = sample_bronze_dataframe
        mock_normalize.side_effect = lambda df: df.copy()
        mock_validate.return_value = sample_bronze_dataframe.copy()
        mock_upload.return_value = (
            "ingestion_date=2026-03-05/job_data_2026-03-05.parquet"
        )

        # Test
        result = run_pipeline()

        assert result["statusCode"] == 200
        assert result["message"] == "Data transformation to Silver successful"
        assert "object_key" in result
        assert (
            result["object_key"]
            == "ingestion_date=2026-03-05/job_data_2026-03-05.parquet"
        )

        # Verify all steps were called
        mock_platforms.assert_called_once()
        mock_get_bronze.assert_called_once()

    @patch("src.silver_layer.orchestrator.get_list_platforms")
    def test_run_pipeline_platform_config_error(self, mock_platforms):
        """Test error handling when platform config fails."""
        mock_platforms.side_effect = ValueError("platform environment variable not set")

        result = run_pipeline()

        assert result["statusCode"] == 500
        assert "failed" in result["message"].lower()
        assert "error" in result
        assert "platform environment variable not set" in result["error"]

    @patch("src.silver_layer.orchestrator.upload_to_silver")
    @patch("src.silver_layer.orchestrator.validate_silver_schema")
    @patch("src.silver_layer.orchestrator.apply_location_normalization")
    @patch("src.silver_layer.orchestrator.get_bronze_object")
    @patch("src.silver_layer.orchestrator.get_list_platforms")
    def test_run_pipeline_bronze_read_error(
        self,
        mock_platforms,
        mock_get_bronze,
        mock_normalize,
        mock_validate,
        mock_upload,
    ):
        """Test error handling when Bronze read fails."""
        mock_platforms.return_value = ["kalibrr"]
        mock_get_bronze.side_effect = Exception("S3 connection failed")

        result = run_pipeline()

        assert result["statusCode"] == 500
        assert "failed" in result["message"].lower()
        assert "error" in result

    @patch("src.silver_layer.orchestrator.upload_to_silver")
    @patch("src.silver_layer.orchestrator.validate_silver_schema")
    @patch("src.silver_layer.orchestrator.apply_location_normalization")
    @patch("src.silver_layer.orchestrator.get_bronze_object")
    @patch("src.silver_layer.orchestrator.get_list_platforms")
    def test_run_pipeline_transform_error(
        self,
        mock_platforms,
        mock_get_bronze,
        mock_normalize,
        mock_validate,
        mock_upload,
    ):
        """Test error handling when transformation fails."""
        df = pd.DataFrame({"test": [1, 2, 3]})
        mock_platforms.return_value = ["kalibrr"]
        mock_get_bronze.return_value = df
        mock_normalize.side_effect = Exception("Transformation failed")

        result = run_pipeline()

        assert result["statusCode"] == 500
        assert "failed" in result["message"].lower()
        assert "error" in result

    @patch("src.silver_layer.orchestrator.upload_to_silver")
    @patch("src.silver_layer.orchestrator.validate_silver_schema")
    @patch("src.silver_layer.orchestrator.apply_location_normalization")
    @patch("src.silver_layer.orchestrator.get_bronze_object")
    @patch("src.silver_layer.orchestrator.get_list_platforms")
    def test_run_pipeline_upload_error(
        self,
        mock_platforms,
        mock_get_bronze,
        mock_normalize,
        mock_validate,
        mock_upload,
    ):
        """Test error handling when upload fails."""
        df = pd.DataFrame({"test": [1, 2, 3]})
        mock_platforms.return_value = ["kalibrr"]
        mock_get_bronze.return_value = df
        mock_normalize.side_effect = lambda df: df.copy()
        mock_validate.return_value = df
        mock_upload.side_effect = Exception("S3 write failed")

        result = run_pipeline()

        assert result["statusCode"] == 500
        assert "failed" in result["message"].lower()
        assert "error" in result


@pytest.fixture(autouse=True)
def prevent_live_ai_requests(monkeypatch):
    from src.ai.nlp import empty_result

    monkeypatch.setattr(
        "src.silver_layer.orchestrator.parse_job",
        lambda *args, **kwargs: empty_result(kwargs.get("fields", [])),
    )
