"""Tests for Excel exporter functionality."""

import pytest
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field

# Test helper models
from myelin.helpers.excel_exporter import (
    _flatten_model,
    _format_value,
    _humanize_key,
    _extract_list_items,
)


class SampleNestedModel(BaseModel):
    """Test nested model."""
    value: str = "test"
    count: int = 42


class SampleListItemModel(BaseModel):
    """Test list item model."""
    name: str = ""
    amount: float = 0.0


class SampleModel(BaseModel):
    """Test model with various field types."""
    simple_field: str = "hello"
    number_field: int = 100
    float_field: float = 99.99
    bool_field: bool = True
    none_field: str | None = None
    nested: SampleNestedModel = Field(default_factory=SampleNestedModel)
    items: list[SampleListItemModel] = Field(default_factory=list)


class TestFormatValue:
    """Tests for _format_value function."""

    def test_none_value(self):
        assert _format_value(None) == ""

    def test_bool_true(self):
        assert _format_value(True) == "Yes"

    def test_bool_false(self):
        assert _format_value(False) == "No"

    def test_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30)
        assert _format_value(dt) == dt

    def test_string(self):
        assert _format_value("test") == "test"

    def test_number(self):
        assert _format_value(42) == 42
        assert _format_value(3.14) == 3.14


class TestHumanizeKey:
    """Tests for _humanize_key function."""

    def test_simple_key(self):
        assert _humanize_key("simple") == "Simple"

    def test_snake_case(self):
        assert _humanize_key("my_field_name") == "My Field Name"

    def test_already_readable(self):
        assert _humanize_key("Test") == "Test"


class TestFlattenModel:
    """Tests for _flatten_model function."""

    def test_simple_fields(self):
        model = SampleModel()
        flat = _flatten_model(model)
        
        assert flat["simple_field"] == "hello"
        assert flat["number_field"] == 100
        assert flat["float_field"] == 99.99
        assert flat["bool_field"] == "Yes"
        assert flat["none_field"] == ""

    def test_nested_model(self):
        model = SampleModel()
        flat = _flatten_model(model)
        
        assert flat["nested_value"] == "test"
        assert flat["nested_count"] == 42

    def test_list_field_count(self):
        model = SampleModel(items=[
            SampleListItemModel(name="item1", amount=10.0),
            SampleListItemModel(name="item2", amount=20.0),
        ])
        flat = _flatten_model(model)
        
        assert flat["items_count"] == 2


class TestExtractListItems:
    """Tests for _extract_list_items function."""

    def test_empty_list(self):
        model = SampleModel()
        lists = _extract_list_items(model)
        
        # Empty list should not be extracted
        assert "items" not in lists

    def test_populated_list(self):
        model = SampleModel(items=[
            SampleListItemModel(name="item1", amount=10.0),
        ])
        lists = _extract_list_items(model)
        
        assert "items" in lists
        assert len(lists["items"]) == 1


class TestExcelExporter:
    """Integration tests for ExcelExporter."""

    @pytest.fixture
    def sample_output(self):
        """Create a sample MyelinOutput for testing."""
        from myelin.core import MyelinOutput
        from myelin.msdrg.msdrg_output import MsdrgOutput
        
        return MyelinOutput(
            msdrg=MsdrgOutput(
                claim_id="test-claim-001",
                drg_version="42.0",
                final_drg_value="470",
                final_drg_description="Major Hip and Knee Joint Replacement",
                final_mdc_value="08",
                final_mdc_description="Diseases and Disorders of the Musculoskeletal System",
            )
        )

    @pytest.mark.skipif(
        not pytest.importorskip("openpyxl", reason="openpyxl not installed"),
        reason="openpyxl required for this test"
    )
    def test_export_to_bytes(self, sample_output):
        """Test exporting to bytes."""
        try:
            from myelin.helpers.excel_exporter import ExcelExporter
            
            exporter = ExcelExporter(sample_output)
            excel_bytes = exporter.export_to_bytes()
            
            assert isinstance(excel_bytes, bytes)
            assert len(excel_bytes) > 0
            # Check for Excel file signature (ZIP format)
            assert excel_bytes[:4] == b'PK\x03\x04'
        except ImportError:
            pytest.skip("openpyxl not installed")

    @pytest.mark.skipif(
        not pytest.importorskip("openpyxl", reason="openpyxl not installed"),
        reason="openpyxl required for this test"
    )
    def test_export_to_file(self, sample_output, tmp_path):
        """Test exporting to a file."""
        try:
            from myelin.helpers.excel_exporter import export_to_excel
            
            filepath = tmp_path / "test_output.xlsx"
            export_to_excel(sample_output, filepath)
            
            assert filepath.exists()
            assert filepath.stat().st_size > 0
        except ImportError:
            pytest.skip("openpyxl not installed")

    @pytest.mark.skipif(
        not pytest.importorskip("openpyxl", reason="openpyxl not installed"),
        reason="openpyxl required for this test"
    )
    def test_myelin_output_to_excel_method(self, sample_output, tmp_path):
        """Test the to_excel method on MyelinOutput."""
        try:
            filepath = tmp_path / "test_method.xlsx"
            sample_output.to_excel(str(filepath))
            
            assert filepath.exists()
        except ImportError:
            pytest.skip("openpyxl not installed")

    def test_import_error_without_openpyxl(self):
        """Test that proper error is raised when openpyxl is not available."""
        from myelin.helpers import excel_exporter
        
        # Save original state
        original_available = excel_exporter.OPENPYXL_AVAILABLE
        
        try:
            # Simulate openpyxl not being available
            excel_exporter.OPENPYXL_AVAILABLE = False
            
            with pytest.raises(ImportError) as exc_info:
                excel_exporter._ensure_openpyxl()
            
            assert "openpyxl" in str(exc_info.value)
            assert "pip install" in str(exc_info.value)
        finally:
            # Restore original state
            excel_exporter.OPENPYXL_AVAILABLE = original_available
