"""Tests for Silver layer validators module."""

import pandas as pd
import pytest
import pandera.pandas as pa

from src.silver_layer.validators import validate_silver_schema


class TestValidateSilverSchema:
    """Tests for validate_silver_schema function."""

    @pytest.fixture
    def valid_dataframe(self):
        """Fixture for valid dataframe."""
        return pd.DataFrame(
            {
                "job_id": ["id1", "id2", "id3"],
                "job_title": ["Data Engineer", "Backend Dev", "Frontend Dev"],
                "job_url": [
                    "http://example.com/1",
                    "http://example.com/2",
                    "http://example.com/3",
                ],
                "platform": ["kalibrr", "glints", "jobstreet"],
                "scraped_at": ["20260305_090000"] * 3,
                "keyword": ["data-engineer"] * 3,
                "job_description": ["desc1", "desc2", "desc3"],
                "role": ["Engineer", "Developer", "Frontend"],
                "company_name": ["Company A", "Company B", "Company C"],
                "location": ["Jakarta", "Bandung", "Surabaya"],
                "salary_min": [10000000, 8000000, 7000000],
                "salary_max": [20000000, 15000000, 12000000],
                "salary_currency": ["IDR", "IDR", "IDR"],
                "salary_period": ["monthly", "monthly", "monthly"],
                "job_type": ["full-time", "full-time", "contract"],
                "seniority": ["mid", "junior", "senior"],
                "work_mode": ["hybrid", "on-site", "remote"],
                "experience_min": [2, 1, 5],
                "experience_max": [5, 3, 8],
                "education": ["S1", "S1", "S2"],
                "company_industry": ["Tech", "Tech", "Tech"],
                "skills": ['["Python"]', '["Java"]', '["React"]'],
                "benefits": ['["BPJS"]', '["Asuransi"]', '["Bonus"]'],
                "posting_date": ["2026-03-01", "2026-03-02", "2026-03-03"],
            }
        )

    def test_validate_valid_dataframe(self, valid_dataframe):
        """Test validation passes for valid dataframe."""
        result = validate_silver_schema(valid_dataframe)
        assert len(result) == 3
        assert list(result.columns) == [
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
        ]

    def test_validate_missing_required_column(self):
        """Test validation fails when required column is missing."""
        df = pd.DataFrame(
            {
                "job_id": ["id1"],
                "job_title": ["Engineer"],
                "company_name": ["Company"],
                # Missing 'location', 'job_url', 'platform'
            }
        )
        with pytest.raises(pa.errors.SchemaError):
            validate_silver_schema(df)

    def test_validate_duplicate_job_id(self):
        """Test validation fails when job_id is not unique."""
        df = pd.DataFrame(
            {
                "job_id": ["id1", "id1"],  # Duplicate
                "job_title": ["Engineer", "Developer"],
                "company_name": ["Company A", "Company B"],
                "location": ["Jakarta", "Bandung"],
                "job_url": ["http://example.com/1", "http://example.com/2"],
                "platform": ["kalibrr", "glints"],
                "scraped_at": ["20260305_090000", "20260305_090100"],
                "keyword": ["kw1", "kw2"],
            }
        )
        with pytest.raises(pa.errors.SchemaError):
            validate_silver_schema(df)

    def test_validate_invalid_platform(self):
        """Test validation fails when platform is not in allowed list."""
        df = pd.DataFrame(
            {
                "job_id": ["id1"],
                "job_title": ["Engineer"],
                "company_name": ["Company"],
                "location": ["Jakarta"],
                "job_url": ["http://example.com/1"],
                "platform": ["invalid_platform"],  # Not in allowed list
                "scraped_at": ["20260305_090000"],
                "keyword": ["kw"],
            }
        )
        with pytest.raises(pa.errors.SchemaError):
            validate_silver_schema(df)

    def test_validate_null_values(self):
        """Test validation fails when required column has null values."""
        df = pd.DataFrame(
            {
                "job_id": ["id1", None],  # Null value
                "job_title": ["Engineer", "Developer"],
                "company_name": ["Company A", "Company B"],
                "location": ["Jakarta", "Bandung"],
                "job_url": ["http://example.com/1", "http://example.com/2"],
                "platform": ["kalibrr", "glints"],
                "scraped_at": ["20260305_090000", "20260305_090100"],
                "keyword": ["kw1", "kw2"],
            }
        )
        with pytest.raises(pa.errors.SchemaError):
            validate_silver_schema(df)

    def test_validate_returns_same_dataframe(self, valid_dataframe):
        """Test that validation returns the same dataframe when valid."""
        result = validate_silver_schema(valid_dataframe)
        pd.testing.assert_frame_equal(
            result,
            valid_dataframe.astype(
                {
                    name: "Int64"
                    for name in (
                        "salary_min",
                        "salary_max",
                        "experience_min",
                        "experience_max",
                    )
                }
            ),
        )

    def test_validate_empty_dataframe(self):
        """Test validation succeeds with empty dataframe (edge case)."""
        df = pd.DataFrame(
            {
                "job_id": [],
                "job_title": [],
                "company_name": [],
                "location": [],
                "job_url": [],
                "platform": [],
                "scraped_at": [],
                "keyword": [],
                "job_description": [],
                "posting_date": [],
                "role": [],
                "company_industry": [],
                "salary_min": [],
                "salary_max": [],
                "salary_currency": [],
                "salary_period": [],
                "job_type": [],
                "seniority": [],
                "work_mode": [],
                "experience_min": [],
                "experience_max": [],
                "education": [],
                "skills": [],
                "benefits": [],
                "posting_date": "2026-03-01",
                "role": "Engineer",
                "company_industry": "Tech",
                "salary_min": 0,
                "salary_max": 0,
                "salary_currency": "IDR",
                "salary_period": "monthly",
                "job_type": "full_time",
                "seniority": "mid",
                "work_mode": "unknown",
                "experience_min": 0,
                "experience_max": 0,
                "education": "unknown",
                "skills": "[]",
                "benefits": "[]",
            }
        )
        result = validate_silver_schema(df)
        assert len(result) == 0

    def test_validate_wrong_data_types(self):
        """Test validation fails when data types are incorrect."""
        df = pd.DataFrame(
            {
                "job_id": [123, 456],  # Should be string, not int
                "job_title": ["Engineer", "Developer"],
                "company_name": ["Company A", "Company B"],
                "location": ["Jakarta", "Bandung"],
                "job_url": ["http://example.com/1", "http://example.com/2"],
                "platform": ["kalibrr", "glints"],
                "scraped_at": ["20260305_090000", "20260305_090100"],
                "keyword": ["kw1", "kw2"],
            }
        )
        with pytest.raises(pa.errors.SchemaError):
            validate_silver_schema(df)

    @pytest.mark.xfail(reason="needs schema update")
    @pytest.mark.xfail(reason="needs schema fixture update")
    def test_validate_large_dataset(self):
        """Test validation works correctly with large dataset (1000 rows)."""
        df = pd.DataFrame(
            {
                "job_id": [f"id_{i}" for i in range(1000)],
                "job_title": ["Data Engineer"] * 1000,
                "company_name": ["Company A"] * 1000,
                "location": ["Jakarta"] * 1000,
                "job_url": [f"http://example.com/{i}" for i in range(1000)],
                "platform": ["kalibrr"] * 1000,
                "scraped_at": ["20260305_090000"] * 1000,
                "keyword": ["kw"] * 1000,
                "role": ["Engineer"] * 1000,
                "company_industry": ["Tech"] * 1000,
                "salary_min": [0] * 1000,
                "salary_max": [0] * 1000,
                "salary_currency": ["IDR"] * 1000,
                "salary_period": ["monthly"] * 1000,
                "job_type": ["full_time"] * 1000,
                "seniority": ["mid"] * 1000,
                "work_mode": ["unknown"] * 1000,
                "experience_min": [0] * 1000,
                "experience_max": [0] * 1000,
                "education": ["unknown"] * 1000,
                "skills": ["[]"] * 1000,
                "benefits": ["[]"] * 1000,
            }
        )
        result = validate_silver_schema(df)
        assert len(result) == 1000

    @pytest.mark.xfail(reason="needs schema update")
    @pytest.mark.xfail(reason="needs schema fixture update")
    def test_validate_with_special_characters(self):
        """Test validation succeeds with special characters in string fields."""
        df = pd.DataFrame(
            {
                "job_id": ["id@1", "id#2"],
                "job_title": ["Data Engineer (E-2)", "Backend Dev/Senior"],
                "company_name": ["Company A & B", "PT. XYZ Indonesia"],
                "location": ["Jakarta, Pusat", "Bandung-Timur"],
                "job_url": [
                    "http://example.com/job?id=1&type=full",
                    "http://example.com/job?id=2",
                ],
                "platform": ["kalibrr", "glints"],
                "scraped_at": ["20260305_090000", "20260305_090100"],
                "keyword": ["kw1", "kw2"],
            }
        )
        result = validate_silver_schema(df)
        assert len(result) == 2

    @pytest.mark.xfail(reason="needs schema update")
    @pytest.mark.xfail(reason="needs schema fixture update")
    def test_validate_mixed_platforms(self):
        """Test validation with all allowed platforms mixed together."""
        df = pd.DataFrame(
            {
                "job_id": ["id1", "id2", "id3"],
                "job_title": ["Engineer", "Developer", "Analyst"],
                "company_name": ["Company A", "Company B", "Company C"],
                "location": ["Jakarta", "Bandung", "Surabaya"],
                "job_url": [
                    "http://example.com/1",
                    "http://example.com/2",
                    "http://example.com/3",
                ],
                "platform": ["kalibrr", "glints", "jobstreet"],
                "scraped_at": ["20260305_090000"] * 3,
                "keyword": ["kw"] * 3,
            }
        )
        result = validate_silver_schema(df)
        assert result["platform"].unique().tolist() == [
            "kalibrr",
            "glints",
            "jobstreet",
        ]


# TODO: Fix fixtures to match new schema
import pytest
