"""Tests for psd2svg.core.font_utils module."""

import logging
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from psd2svg.core.font_utils import HAS_FONTCONFIG, FontInfo, create_file_url


class TestFontInfo:
    """Tests for FontInfo dataclass."""

    def test_init(self) -> None:
        """Test FontInfo initialization."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.postscript_name == "ArialMT"
        assert font.file == "/path/to/arial.ttf"
        assert font.family == "Arial"
        assert font.style == "Regular"
        assert font.weight == 80.0

    def test_family_name_property(self) -> None:
        """Test family_name property returns family name."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.family_name == "Arial"

    def test_family_name_property_empty(self) -> None:
        """Test family_name property with empty family string."""
        font = FontInfo(
            postscript_name="UnknownFont",
            file="/path/to/unknown.ttf",
            family="",
            style="Regular",
            weight=80.0,
        )
        assert font.family_name == ""

    def test_bold_property_regular_weight(self) -> None:
        """Test bold property returns False for regular weight."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.bold is False

    def test_bold_property_bold_weight(self) -> None:
        """Test bold property returns True for bold weight (>= 200)."""
        font = FontInfo(
            postscript_name="Arial-BoldMT",
            file="/path/to/arial-bold.ttf",
            family="Arial",
            style="Bold",
            weight=200.0,
        )
        assert font.bold is True

    def test_bold_property_edge_case(self) -> None:
        """Test bold property at weight boundary."""
        # Weight exactly 200 should be bold
        font = FontInfo(
            postscript_name="Arial-BoldMT",
            file="/path/to/arial-bold.ttf",
            family="Arial",
            style="Bold",
            weight=200.0,
        )
        assert font.bold is True

        # Weight just under 200 should not be bold
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="SemiBold",
            weight=199.9,
        )
        assert font.bold is False

    def test_italic_property_regular_style(self) -> None:
        """Test italic property returns False for regular style."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.italic is False

    def test_italic_property_italic_style(self) -> None:
        """Test italic property returns True for italic style."""
        font = FontInfo(
            postscript_name="Arial-ItalicMT",
            file="/path/to/arial-italic.ttf",
            family="Arial",
            style="Italic",
            weight=80.0,
        )
        assert font.italic is True

    def test_italic_property_case_insensitive(self) -> None:
        """Test italic property is case-insensitive."""
        for style in ["italic", "ITALIC", "Italic"]:
            font = FontInfo(
                postscript_name="Arial-ItalicMT",
                file="/path/to/arial-italic.ttf",
                family="Arial",
                style=style,
                weight=80.0,
            )
            assert font.italic is True

    def test_italic_property_oblique(self) -> None:
        """Test italic property returns True for oblique style."""
        font = FontInfo(
            postscript_name="Arial-Oblique",
            file="/path/to/arial-oblique.ttf",
            family="Arial",
            style="Oblique italic",
            weight=80.0,
        )
        assert font.italic is True


class TestFontInfoCSSWeight:
    """Tests for FontInfo CSS weight conversion methods."""

    def test_css_weight_property_regular(self) -> None:
        """Test css_weight property for regular weight."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.css_weight == 400

    def test_css_weight_property_bold(self) -> None:
        """Test css_weight property for bold weight."""
        font = FontInfo(
            postscript_name="Arial-BoldMT",
            file="/path/to/arial-bold.ttf",
            family="Arial",
            style="Bold",
            weight=200.0,
        )
        assert font.css_weight == 700

    def test_get_css_weight_numeric(self) -> None:
        """Test get_css_weight() returns numeric values by default."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.get_css_weight() == 400
        assert font.get_css_weight(semantic=False) == 400

    def test_get_css_weight_semantic_normal(self) -> None:
        """Test get_css_weight(semantic=True) returns 'normal' for 400."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        assert font.get_css_weight(semantic=True) == "normal"

    def test_get_css_weight_semantic_bold(self) -> None:
        """Test get_css_weight(semantic=True) returns 'bold' for 700."""
        font = FontInfo(
            postscript_name="Arial-BoldMT",
            file="/path/to/arial-bold.ttf",
            family="Arial",
            style="Bold",
            weight=200.0,
        )
        assert font.get_css_weight(semantic=True) == "bold"

    def test_get_css_weight_semantic_light(self) -> None:
        """Test get_css_weight(semantic=True) returns numeric for non-normal/bold."""
        font = FontInfo(
            postscript_name="Arial-Light",
            file="/path/to/arial-light.ttf",
            family="Arial",
            style="Light",
            weight=50.0,
        )
        # Light (300) has no semantic keyword in CSS
        assert font.get_css_weight(semantic=True) == 300

    def test_css_weight_all_ranges(self) -> None:
        """Test CSS weight mapping for all weight ranges."""
        test_cases = [
            (0, 100),  # thin
            (40, 200),  # extralight
            (45, 250),  # between extralight and light (Hiragino W2)
            (50, 300),  # light
            (55, 350),  # demilight
            (75, 380),  # book
            (80, 400),  # regular
            (100, 500),  # medium
            (180, 600),  # semibold
            (200, 700),  # bold
            (205, 800),  # extrabold
            (210, 900),  # black
        ]

        for fc_weight, expected_css in test_cases:
            font = FontInfo(
                postscript_name="TestFont",
                file="/path/to/test.ttf",
                family="Test",
                style="Test",
                weight=float(fc_weight),
            )
            assert font.css_weight == expected_css, (
                f"FC weight {fc_weight} should map to CSS {expected_css}"
            )


class TestFontInfoLookupStatic:
    """Tests for FontInfo.lookup_static() method (static mapping only)."""

    def test_lookup_static_from_default_mapping(self) -> None:
        """Test lookup_static with font in default static mapping."""
        font = FontInfo.lookup_static("ArialMT")

        assert font is not None
        assert font.postscript_name == "ArialMT"
        assert font.family == "Arial"
        assert font.style == "Regular"
        assert font.weight == 80.0
        assert font.file == ""  # No file path from static mapping

    def test_lookup_static_with_custom_mapping(self) -> None:
        """Test lookup_static with custom font mapping."""
        custom_mapping: dict[str, dict[str, str | float]] = {
            "CustomFont-Test": {
                "family": "My Custom Font",
                "style": "Test",
                "weight": 150.0,
            }
        }

        font = FontInfo.lookup_static("CustomFont-Test", font_mapping=custom_mapping)

        assert font is not None
        assert font.postscript_name == "CustomFont-Test"
        assert font.family == "My Custom Font"
        assert font.style == "Test"
        assert font.weight == 150.0
        assert font.file == ""  # No file path from static mapping

    def test_lookup_static_custom_overrides_default(self) -> None:
        """Test that custom mapping overrides default for same PostScript name."""
        custom_mapping: dict[str, dict[str, str | float]] = {
            "ArialMT": {"family": "My Custom Arial", "style": "Custom", "weight": 999.0}
        }

        font = FontInfo.lookup_static("ArialMT", font_mapping=custom_mapping)

        assert font is not None
        assert font.family == "My Custom Arial"  # Custom, not "Arial"
        assert font.style == "Custom"
        assert font.weight == 999.0

    def test_lookup_static_with_suffix_parsing(self) -> None:
        """Test lookup_static uses suffix parsing as fallback when not in mapping."""
        # NonExistentFont-Regular is not in mapping, but the method
        # falls back to parsing the PostScript name structure
        font = FontInfo.lookup_static("NonExistentFont-Regular")

        assert font is not None
        assert font.postscript_name == "NonExistentFont-Regular"
        assert font.family == "Non Existent Font"  # CamelCase parsed
        assert font.style == "Regular"  # Suffix parsed
        assert font.weight == 80.0
        assert font.file == ""  # No file path from static mapping

    def test_lookup_static_with_none_mapping(self) -> None:
        """Test that None custom mapping works (uses default only)."""
        font = FontInfo.lookup_static("ArialMT", font_mapping=None)

        assert font is not None
        assert font.family == "Arial"  # From default mapping

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_lookup_static_does_not_call_fontconfig(
        self, mock_match: MagicMock
    ) -> None:
        """Test that lookup_static never calls fontconfig (static mapping only)."""
        # ArialMT is in the static mapping
        font = FontInfo.lookup_static("ArialMT")

        assert font is not None
        assert font.family == "Arial"

        # Fontconfig should NEVER be called for static lookup
        mock_match.assert_not_called()


class TestFontInfoResolve:
    """Tests for FontInfo.resolve() method (platform font resolution)."""

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_success(self, mock_match: MagicMock) -> None:
        """Test resolve method with successful fontconfig resolution."""
        mock_match.return_value = {
            "file": "/path/to/custom.ttf",
            "family": "CustomFont",
            "style": "Regular",
            "weight": 80.0,
        }

        font = FontInfo.resolve("CustomFont-Regular")

        assert font is not None
        assert font.postscript_name == "CustomFont-Regular"
        assert font.file == "/path/to/custom.ttf"
        assert font.family == "CustomFont"
        assert font.style == "Regular"
        assert font.weight == 80.0

        mock_match.assert_called_once_with(
            pattern=":postscriptname=CustomFont-Regular",
            select=("file", "family", "style", "weight"),
        )

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_not_found(
        self, mock_match: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test resolve method when font is not found."""
        mock_match.return_value = None

        with caplog.at_level(logging.WARNING):
            font = FontInfo.resolve("NonExistentFont")

        assert font is None
        assert "Font 'NonExistentFont' not found" in caplog.text
        assert "Make sure the font is installed on your system" in caplog.text

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_empty_result(
        self, mock_match: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test resolve method with empty match result."""
        mock_match.return_value = {}

        with caplog.at_level(logging.WARNING):
            font = FontInfo.resolve("EmptyFont")

        assert font is None
        assert "Font 'EmptyFont' not found" in caplog.text

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_bold_font(self, mock_match: MagicMock) -> None:
        """Test resolve method correctly identifies bold fonts."""
        mock_match.return_value = {
            "file": "/path/to/custom-bold.ttf",
            "family": "CustomFont",
            "style": "Bold",
            "weight": 200.0,
        }

        font = FontInfo.resolve("CustomFont-Bold")

        assert font is not None
        assert font.bold is True
        assert font.italic is False

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_italic_font(self, mock_match: MagicMock) -> None:
        """Test resolve method correctly identifies italic fonts."""
        mock_match.return_value = {
            "file": "/path/to/custom-italic.ttf",
            "family": "CustomFont",
            "style": "Italic",
            "weight": 80.0,
        }

        font = FontInfo.resolve("CustomFont-Italic")

        assert font is not None
        assert font.bold is False
        assert font.italic is True

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_bold_italic_font(self, mock_match: MagicMock) -> None:
        """Test resolve method correctly identifies bold italic fonts."""
        mock_match.return_value = {
            "file": "/path/to/custom-bolditalic.ttf",
            "family": "CustomFont",
            "style": "Bold Italic",
            "weight": 200.0,
        }

        font = FontInfo.resolve("CustomFont-BoldItalic")

        assert font is not None
        assert font.bold is True
        assert font.italic is True

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_with_special_characters(self, mock_match: MagicMock) -> None:
        """Test resolve method handles postscript names with special characters."""
        mock_match.return_value = {
            "file": "/path/to/font.ttf",
            "family": "Special Font",
            "style": "Regular",
            "weight": 80.0,
        }

        font = FontInfo.resolve("SpecialFont-Regular_1.0")

        assert font is not None
        assert font.postscript_name == "SpecialFont-Regular_1.0"
        mock_match.assert_called_once_with(
            pattern=":postscriptname=SpecialFont-Regular_1.0",
            select=("file", "family", "style", "weight"),
        )

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    @patch("psd2svg.core.font_utils.fontconfig.CharSet")
    def test_resolve_with_charset(
        self, mock_charset_class: MagicMock, mock_match: MagicMock
    ) -> None:
        """Test resolve with charset codepoints for better font matching."""
        # Mock CharSet creation
        mock_charset_instance = MagicMock()
        mock_charset_class.from_codepoints.return_value = mock_charset_instance

        # Mock fontconfig match result
        mock_match.return_value = {
            "file": "/path/to/noto-sans-cjk.ttf",
            "family": "Noto Sans CJK JP",
            "style": "Regular",
            "weight": 80.0,
        }

        # Test with charset codepoints (Japanese hiragana)
        codepoints = {0x3042, 0x3044, 0x3046}
        font = FontInfo.resolve(
            "MyCustomCJKFont-Regular", charset_codepoints=codepoints
        )

        assert font is not None
        assert font.postscript_name == "MyCustomCJKFont-Regular"
        assert font.file == "/path/to/noto-sans-cjk.ttf"
        assert font.family == "Noto Sans CJK JP"

        # Verify CharSet was created with sorted codepoints
        mock_charset_class.from_codepoints.assert_called_once_with(sorted(codepoints))

        # Verify fontconfig.match was called with properties dict including charset
        mock_match.assert_called_once()
        call_kwargs = mock_match.call_args.kwargs
        assert "properties" in call_kwargs
        assert call_kwargs["properties"]["postscriptname"] == "MyCustomCJKFont-Regular"
        assert call_kwargs["properties"]["charset"] == mock_charset_instance

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    @patch("psd2svg.core.font_utils.fontconfig.CharSet")
    def test_resolve_charset_fallback_on_error(
        self,
        mock_charset_class: MagicMock,
        mock_match: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test resolve gracefully falls back when charset matching fails."""
        # Mock CharSet to raise exception
        mock_charset_class.from_codepoints.side_effect = Exception(
            "CharSet creation failed"
        )

        # Fallback call succeeds
        mock_match.return_value = {
            "file": "/path/to/font.ttf",
            "family": "SomeFont",
            "style": "Regular",
            "weight": 80.0,
        }

        codepoints = {0x3042, 0x3044}

        with caplog.at_level(logging.WARNING):
            font = FontInfo.resolve("CustomFont", charset_codepoints=codepoints)

        # Should still succeed via fallback
        assert font is not None
        assert font.family == "SomeFont"

        # Check warning was logged
        assert any(
            "Charset-based matching failed" in record.message
            and "Falling back to name-only matching" in record.message
            for record in caplog.records
        )

        # Verify fallback to name-only matching was attempted
        assert mock_match.call_count == 1
        call_kwargs = mock_match.call_args.kwargs
        assert "pattern" in call_kwargs
        assert call_kwargs["pattern"] == ":postscriptname=CustomFont"

    @pytest.mark.skipif(not HAS_FONTCONFIG, reason="Requires fontconfig (Linux/macOS)")
    @patch("psd2svg.core.font_utils.fontconfig.match")
    def test_resolve_without_charset_uses_name_only(
        self, mock_match: MagicMock
    ) -> None:
        """Test resolve uses name-only matching when charset is not provided."""
        mock_match.return_value = {
            "file": "/path/to/font.ttf",
            "family": "TestFont",
            "style": "Regular",
            "weight": 80.0,
        }

        font = FontInfo.resolve("TestFont-Regular")

        assert font is not None
        mock_match.assert_called_once_with(
            pattern=":postscriptname=TestFont-Regular",
            select=("file", "family", "style", "weight"),
        )


class TestResolveFromCustomMappingWithFile:
    """Tests for FontInfo._resolve_from_custom_mapping_with_file helper method."""

    def test_successful_resolution(self, tmp_path: Path) -> None:
        """Test successful resolution with valid custom mapping and existing file."""
        # Create a temporary font file
        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT_DATA")

        font_mapping: dict[str, dict[str, float | str]] = {
            "ArialMT": {
                "family": "Arial",
                "style": "Regular",
                "weight": 80.0,
                "file": str(font_file),
            }
        }

        result = FontInfo._resolve_from_custom_mapping_with_file(
            "ArialMT", font_mapping
        )

        assert result is not None
        assert result.postscript_name == "ArialMT"
        assert result.family == "Arial"
        assert result.style == "Regular"
        assert result.weight == 80.0
        assert result.file == str(font_file)

    def test_fallback_when_file_missing(self) -> None:
        """Test fallback to None when file field is missing."""
        font_mapping: dict[str, dict[str, float | str]] = {
            "ArialMT": {
                "family": "Arial",
                "style": "Regular",
                "weight": 80.0,
                # Missing "file" field
            }
        }

        result = FontInfo._resolve_from_custom_mapping_with_file(
            "ArialMT", font_mapping
        )

        assert result is None

    def test_fallback_when_file_doesnt_exist(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test fallback to None when file doesn't exist."""
        font_mapping: dict[str, dict[str, float | str]] = {
            "ArialMT": {
                "family": "Arial",
                "style": "Regular",
                "weight": 80.0,
                "file": "/nonexistent/path/arial.ttf",
            }
        }

        with caplog.at_level(logging.WARNING):
            result = FontInfo._resolve_from_custom_mapping_with_file(
                "ArialMT", font_mapping
            )

        assert result is None
        assert "does not exist" in caplog.text
        assert "Falling back to platform resolution" in caplog.text

    def test_fallback_when_required_fields_missing(self) -> None:
        """Test fallback when other required fields are missing."""
        font_mapping: dict[str, dict[str, float | str]] = {
            "ArialMT": {
                "family": "Arial",
                # Missing "style" and "weight"
                "file": "/path/to/arial.ttf",
            }
        }

        result = FontInfo._resolve_from_custom_mapping_with_file(
            "ArialMT", font_mapping
        )

        assert result is None

    def test_font_not_in_mapping(self) -> None:
        """Test returns None when font not found in mapping."""
        font_mapping: dict[str, dict[str, float | str]] = {
            "HelveticaMT": {
                "family": "Helvetica",
                "style": "Regular",
                "weight": 80.0,
                "file": "/path/to/helvetica.ttf",
            }
        }

        result = FontInfo._resolve_from_custom_mapping_with_file(
            "ArialMT", font_mapping
        )

        assert result is None


class TestFontInfoSerialization:
    """Tests for FontInfo serialization methods."""

    def test_to_dict(self) -> None:
        """Test to_dict method converts FontInfo to dictionary."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )

        result = font.to_dict()

        assert isinstance(result, dict)
        assert result["postscript_name"] == "ArialMT"
        assert result["file"] == "/path/to/arial.ttf"
        assert result["family"] == "Arial"
        assert result["style"] == "Regular"
        assert result["weight"] == 80.0

    def test_from_dict(self) -> None:
        """Test from_dict classmethod creates FontInfo from dictionary."""
        data: dict[str, Any] = {
            "postscript_name": "ArialMT",
            "file": "/path/to/arial.ttf",
            "family": "Arial",
            "style": "Regular",
            "weight": 80.0,
        }

        font = FontInfo.from_dict(cast(dict[str, str | float], data))

        assert isinstance(font, FontInfo)
        assert font.postscript_name == "ArialMT"
        assert font.file == "/path/to/arial.ttf"
        assert font.family == "Arial"
        assert font.style == "Regular"
        assert font.weight == 80.0

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test that to_dict and from_dict are symmetric."""
        original = FontInfo(
            postscript_name="Arial-BoldMT",
            file="/path/to/arial-bold.ttf",
            family="Arial",
            style="Bold",
            weight=200.0,
        )

        # Convert to dict and back
        data = original.to_dict()
        restored = FontInfo.from_dict(data)

        # Verify all fields match
        assert restored.postscript_name == original.postscript_name
        assert restored.file == original.file
        assert restored.family == original.family
        assert restored.style == original.style
        assert restored.weight == original.weight

    def test_from_dict_with_string_weight(self) -> None:
        """Test from_dict handles string weight by converting to float."""
        data: dict[str, Any] = {
            "postscript_name": "ArialMT",
            "file": "/path/to/arial.ttf",
            "family": "Arial",
            "style": "Regular",
            "weight": "80.0",  # String instead of float
        }

        font = FontInfo.from_dict(cast(dict[str, str | float], data))

        assert font.weight == 80.0
        assert isinstance(font.weight, float)


class TestFontInfoIsResolved:
    """Test FontInfo.is_resolved() method."""

    @patch("os.path.exists")
    def test_is_resolved_with_valid_file(self, mock_exists: MagicMock) -> None:
        """Test is_resolved() returns True when font has valid file path."""
        mock_exists.return_value = True

        font_info = FontInfo(
            postscript_name="ArialMT",
            file="/usr/share/fonts/truetype/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )

        assert font_info.is_resolved() is True
        mock_exists.assert_called_once_with("/usr/share/fonts/truetype/arial.ttf")

    def test_is_resolved_with_no_file(self) -> None:
        """Test is_resolved() returns False when font has no file path."""
        font_info = FontInfo(
            postscript_name="ArialMT",
            file="",
            family="Arial",
            style="Regular",
            weight=80.0,
        )

        assert font_info.is_resolved() is False

    def test_is_resolved_with_empty_string_file(self) -> None:
        """Test is_resolved() returns False when font file is empty string."""
        # Note: FontInfo.file is typed as str, not str | None, so we test empty string
        font_info = FontInfo(
            postscript_name="ArialMT",
            file="",
            family="Arial",
            style="Regular",
            weight=80.0,
        )

        assert font_info.is_resolved() is False

    @patch("os.path.exists")
    def test_is_resolved_with_nonexistent_file(self, mock_exists: MagicMock) -> None:
        """Test is_resolved() returns False when file path doesn't exist."""
        mock_exists.return_value = False

        font_info = FontInfo(
            postscript_name="ArialMT",
            file="/nonexistent/path/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )

        assert font_info.is_resolved() is False
        mock_exists.assert_called_once_with("/nonexistent/path/arial.ttf")

    @patch("psd2svg.core.font_utils.HAS_FONTCONFIG", False)
    @patch("psd2svg.core.font_utils.HAS_WINDOWS_FONTS", False)
    @patch("os.path.exists")
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_is_resolved_from_static_mapping(self, mock_exists: MagicMock) -> None:
        """Test is_resolved() returns False for font from static mapping (no file)."""
        # Static mapping doesn't provide file paths
        # Mock platform-specific resolution as unavailable to force static mapping
        font_info = FontInfo.find("ArialMT")

        assert font_info is not None
        assert font_info.file == ""
        assert font_info.is_resolved() is False

        # Should not call os.path.exists for empty string
        mock_exists.assert_not_called()


class TestCreateFileUrl:
    """Tests for create_file_url() function."""

    def test_create_file_url_unix(self, tmp_path: Path) -> None:
        """Test file URL creation on Linux/macOS."""
        font_file = tmp_path / "test.ttf"
        font_file.write_bytes(b"FAKE")

        url = create_file_url(str(font_file))

        # Should be file:// + absolute path
        assert url.startswith("file:///")
        assert Path(font_file).as_posix() in url

    def test_create_file_url_with_spaces(self, tmp_path: Path) -> None:
        """Test file URL with spaces in path."""
        font_dir = tmp_path / "My Fonts"
        font_dir.mkdir()
        font_file = font_dir / "Test Font.ttf"
        font_file.write_bytes(b"FAKE")

        url = create_file_url(str(font_file))

        # Spaces should be encoded as %20
        assert "My%20Fonts" in url
        assert "Test%20Font" in url
        assert " " not in url  # No literal spaces

    def test_create_file_url_with_unicode(self, tmp_path: Path) -> None:
        """Test file URL with non-ASCII characters."""
        font_dir = tmp_path / "日本語"
        font_dir.mkdir()
        font_file = font_dir / "font.ttf"
        font_file.write_bytes(b"FAKE")

        url = create_file_url(str(font_file))

        # Unicode should be percent-encoded
        assert url.startswith("file:///")
        assert "%" in url  # Has encoded characters

    def test_create_file_url_nonexistent(self, tmp_path: Path) -> None:
        """Test error handling for nonexistent file."""
        nonexistent = tmp_path / "missing.ttf"

        with pytest.raises(FileNotFoundError, match="Font file not found"):
            create_file_url(str(nonexistent))

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_create_file_url_windows(self, tmp_path: Path) -> None:
        """Test file URL creation on Windows."""
        font_file = tmp_path / "test.ttf"
        font_file.write_bytes(b"FAKE")

        url = create_file_url(str(font_file))

        # Should be file:///C:/... format
        assert url.startswith("file:///")
        assert ":" in url  # Drive letter
        assert "\\" not in url  # No backslashes
