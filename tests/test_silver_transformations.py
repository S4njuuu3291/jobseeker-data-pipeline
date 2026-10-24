"""Tests for Silver layer transformations module."""

import pandas as pd

from src.silver_layer.transformations import (
    normalize_location,
    apply_location_normalization,
)


class TestNormalizeLocation:
    """Tests for normalize_location function."""

    def test_jakarta_selatan_variations(self):
        """Test Jakarta Selatan normalization with different spellings."""
        assert normalize_location("jakarta selatan") == "Jakarta Selatan"
        assert normalize_location("JAKARTA SELATAN") == "Jakarta Selatan"
        assert normalize_location("south jakarta") == "Jakarta Selatan"
        assert normalize_location("South Jakarta") == "Jakarta Selatan"

    def test_jakarta_barat_variations(self):
        """Test Jakarta Barat normalization."""
        assert normalize_location("jakarta barat") == "Jakarta Barat"
        assert normalize_location("west jakarta") == "Jakarta Barat"

    def test_jakarta_pusat_variations(self):
        """Test Jakarta Pusat normalization."""
        assert normalize_location("jakarta pusat") == "Jakarta Pusat"
        assert normalize_location("central jakarta") == "Jakarta Pusat"

    def test_jakarta_timur_variations(self):
        """Test Jakarta Timur normalization."""
        assert normalize_location("jakarta timur") == "Jakarta Timur"
        assert normalize_location("east jakarta") == "Jakarta Timur"

    def test_jakarta_utara_variations(self):
        """Test Jakarta Utara normalization."""
        assert normalize_location("jakarta utara") == "Jakarta Utara"
        assert normalize_location("north jakarta") == "Jakarta Utara"

    def test_generic_jakarta(self):
        """Test generic Jakarta location."""
        assert normalize_location("jakarta") == "Jakarta"
        assert normalize_location("Jakarta") == "Jakarta"

    def test_yogyakarta_variations(self):
        """Test Yogyakarta normalization."""
        assert normalize_location("yogyakarta") == "Yogyakarta"
        assert normalize_location("jogja") == "Yogyakarta"

    def test_bandung(self):
        """Test Bandung normalization."""
        assert normalize_location("bandung") == "Bandung"

    def test_surabaya(self):
        """Test Surabaya normalization."""
        assert normalize_location("surabaya") == "Surabaya"

    def test_tangerang(self):
        """Test Tangerang normalization."""
        assert normalize_location("tangerang") == "Tangerang"

    def test_bekasi_variations(self):
        """Test Bekasi normalization."""
        assert normalize_location("bekasi") == "Bekasi"
        assert normalize_location("cikarang") == "Bekasi"

    def test_depok(self):
        """Test Depok normalization."""
        assert normalize_location("depok") == "Depok"

    def test_bogor_variations(self):
        """Test Bogor normalization."""
        assert normalize_location("bogor") == "Bogor"
        assert normalize_location("cileungsi") == "Bogor"

    def test_semarang(self):
        """Test Semarang normalization."""
        assert normalize_location("semarang") == "Semarang"

    def test_unknown_location(self):
        """Test unknown location is title-cased."""
        assert normalize_location("unknown city") == "Unknown City"
        assert normalize_location("some place") == "Some Place"

    def test_case_insensitivity(self):
        """Test that function is case-insensitive."""
        assert normalize_location("JaKaRtA sElAtAn") == "Jakarta Selatan"


class TestApplyLocationNormalization:
    """Tests for apply_location_normalization function."""

    def test_apply_normalization_to_dataframe(self):
        """Test applying normalization to a dataframe."""
        df = pd.DataFrame(
            {
                "location": ["jakarta selatan", "bandung", "yogyakarta"],
                "job_title": ["Engineer", "Developer", "Analyst"],
            }
        )

        result = apply_location_normalization(df)

        assert result["location"].tolist() == [
            "Jakarta Selatan",
            "Bandung",
            "Yogyakarta",
        ]
        assert result["job_title"].tolist() == ["Engineer", "Developer", "Analyst"]

    def test_normalization_preserves_dataframe_structure(self):
        """Test that normalization preserves dataframe structure."""
        df = pd.DataFrame(
            {
                "location": ["jakarta barat", "bekasi"],
                "job_id": ["id1", "id2"],
                "job_title": ["Dev", "Manager"],
            }
        )

        result = apply_location_normalization(df)

        assert len(result) == 2
        assert set(result.columns) == {"location", "job_id", "job_title"}

    def test_empty_dataframe(self):
        """Test normalization with empty dataframe."""
        df = pd.DataFrame({"location": []})
        result = apply_location_normalization(df)

        assert len(result) == 0
        assert "location" in result.columns


def test_null_locations_remain_missing():
    df = pd.DataFrame({'location': [None, float('nan'), pd.NA, '', 'bandung']})
    result = apply_location_normalization(df)
    assert result.location.iloc[:4].isna().all()
    assert result.location.iloc[4] == 'Bandung'
