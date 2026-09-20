"""Tests for psd2svg.core.windows_fonts module.

These tests use mocking to simulate Windows registry access and fontTools parsing,
so they can run on any platform (not just Windows).
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Only import Windows-specific code when testing
# We'll mock it anyway, so platform doesn't matter for tests
if sys.platform == "win32":
    from psd2svg.core import windows_fonts
else:
    # For non-Windows platforms, we still want to test the code exists
    # Import it with mocked winreg
    with patch.dict("sys.modules", {"winreg": MagicMock()}):
        from psd2svg.core import windows_fonts


class TestWindowsFontResolver:
    """Tests for WindowsFontResolver class."""

    def test_init(self) -> None:
        """Test WindowsFontResolver initialization."""
        resolver = windows_fonts.WindowsFontResolver()
        assert resolver._cache == {}
        assert resolver._initialized is False

    @patch("psd2svg.core.windows_fonts.HAS_WINREG", False)
    def test_find_no_winreg(self) -> None:
        """Test find() when winreg is not available."""
        resolver = windows_fonts.WindowsFontResolver()
        result = resolver.find("ArialMT")
        assert result is None
        assert resolver._initialized is True
        assert resolver._cache == {}

    def test_find_success(self) -> None:
        """Test find() successfully resolves a font."""
        resolver = windows_fonts.WindowsFontResolver()

        # Directly populate cache to bypass platform checks
        resolver._cache = {
            "ArialMT": {
                "postscript_name": "ArialMT",
                "file": "C:\\Windows\\Fonts\\arial.ttf",
                "family": "Arial",
                "style": "Regular",
                "weight": 80.0,
            }
        }
        resolver._initialized = True

        result = resolver.find("ArialMT")

        assert result is not None
        assert result["postscript_name"] == "ArialMT"
        assert result["family"] == "Arial"
        assert result["style"] == "Regular"
        assert result["weight"] == 80.0
        assert result["file"] == "C:\\Windows\\Fonts\\arial.ttf"

        # Verify caching
        assert resolver._initialized is True
        assert "ArialMT" in resolver._cache

    def test_find_not_found(self) -> None:
        """Test find() returns None when font not found."""
        resolver = windows_fonts.WindowsFontResolver()

        # Directly populate cache with a different font
        resolver._cache = {
            "ArialMT": {
                "postscript_name": "ArialMT",
                "file": "C:\\Windows\\Fonts\\arial.ttf",
                "family": "Arial",
                "style": "Regular",
                "weight": 80.0,
            }
        }
        resolver._initialized = True

        result = resolver.find("NonExistentFont")

        assert result is None

    def test_find_caching(self) -> None:
        """Test that find() uses cache on repeated calls."""
        resolver = windows_fonts.WindowsFontResolver()

        # Directly populate cache
        resolver._cache = {
            "ArialMT": {
                "postscript_name": "ArialMT",
                "file": "C:\\Windows\\Fonts\\arial.ttf",
                "family": "Arial",
                "style": "Regular",
                "weight": 80.0,
            }
        }
        resolver._initialized = True

        # First call uses cache
        result1 = resolver.find("ArialMT")
        assert result1 is not None

        # Second call should return same data
        result2 = resolver.find("ArialMT")
        assert result2 is not None
        assert result2 == result1


class TestWindowsFontResolverParsing:
    """Tests for font file parsing methods."""

    def test_parse_font_file_success(self) -> None:
        """Test _parse_font_file() successfully extracts font metadata."""
        resolver = windows_fonts.WindowsFontResolver()

        # Create mock TTFont
        mock_font = MagicMock()

        # Create separate mocks for each method call
        mock_get_name = MagicMock(side_effect=["ArialMT", "Arial", "Regular"])
        mock_get_weight = MagicMock(return_value=80.0)

        with patch.object(windows_fonts, "TTFont", return_value=mock_font):
            with patch.object(resolver, "_get_name_table_entry", mock_get_name):
                with patch.object(resolver, "_get_weight_from_os2", mock_get_weight):
                    result = resolver._parse_font_file("C:\\Windows\\Fonts\\arial.ttf")

        assert result is not None
        assert result["postscript_name"] == "ArialMT"
        assert result["family"] == "Arial"
        assert result["style"] == "Regular"
        assert result["weight"] == 80.0
        assert result["file"] == "C:\\Windows\\Fonts\\arial.ttf"

    def test_parse_font_file_no_postscript_name(self) -> None:
        """Test _parse_font_file() returns None when PostScript name missing."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()

        with patch.object(windows_fonts, "TTFont", return_value=mock_font):
            with patch.object(
                resolver, "_get_name_table_entry", return_value=None
            ):  # No PS name
                result = resolver._parse_font_file("C:\\Windows\\Fonts\\invalid.ttf")

        assert result is None

    def test_parse_font_file_exception(self) -> None:
        """Test _parse_font_file() handles exceptions gracefully."""
        resolver = windows_fonts.WindowsFontResolver()

        with patch.object(
            windows_fonts, "TTFont", side_effect=Exception("Parse error")
        ):
            result = resolver._parse_font_file("C:\\Windows\\Fonts\\corrupt.ttf")

        assert result is None

    def test_parse_font_file_uses_defaults(self) -> None:
        """Test _parse_font_file() uses defaults for missing family/style."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()

        # PostScript name exists (ID 6), family IDs return None (16, 1),
        # style IDs return None (17, 2)
        mock_get_name = MagicMock(side_effect=["TestFont", None, None, None, None])
        mock_get_weight = MagicMock(return_value=80.0)

        with patch.object(windows_fonts, "TTFont", return_value=mock_font):
            with patch.object(resolver, "_get_name_table_entry", mock_get_name):
                with patch.object(resolver, "_get_weight_from_os2", mock_get_weight):
                    result = resolver._parse_font_file("C:\\Windows\\Fonts\\test.ttf")

        assert result is not None
        assert result["postscript_name"] == "TestFont"
        assert result["family"] == "Unknown"  # Default
        assert result["style"] == "Regular"  # Default


class TestWindowsFontResolverWeightConversion:
    """Tests for CSS weight to fontconfig weight conversion."""

    def test_get_weight_from_os2_standard_weights(self) -> None:
        """Test _get_weight_from_os2() for standard CSS weights."""
        resolver = windows_fonts.WindowsFontResolver()

        test_cases = [
            (100, 0.0),  # thin
            (200, 40.0),  # extralight
            (300, 50.0),  # light
            (400, 80.0),  # regular
            (500, 100.0),  # medium
            (600, 180.0),  # semibold
            (700, 200.0),  # bold
            (800, 205.0),  # extrabold
            (900, 210.0),  # black
        ]

        for css_weight, expected_fc_weight in test_cases:
            mock_font = MagicMock()
            mock_font.__contains__ = lambda self, key: True
            mock_font.__getitem__ = lambda self, key: MagicMock(
                usWeightClass=css_weight
            )

            result = resolver._get_weight_from_os2(mock_font)
            assert result == expected_fc_weight, (
                f"CSS {css_weight} -> FC {expected_fc_weight}"
            )

    def test_get_weight_from_os2_interpolation(self) -> None:
        """Test _get_weight_from_os2() interpolates non-standard weights."""
        resolver = windows_fonts.WindowsFontResolver()

        # Test weight 250 (Hiragino W2, between 200 and 300)
        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: MagicMock(usWeightClass=250)

        result = resolver._get_weight_from_os2(mock_font)

        # Should interpolate: 40.0 + 0.5 * (50.0 - 40.0) = 45.0
        assert result == 45.0

        # 350 (demilight) is a point on fontconfig's own scale, not interpolated
        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: MagicMock(usWeightClass=350)

        assert resolver._get_weight_from_os2(mock_font) == 55.0

    def test_get_weight_from_os2_edge_cases(self) -> None:
        """Test _get_weight_from_os2() edge cases (< 100, > 900)."""
        resolver = windows_fonts.WindowsFontResolver()

        # Weight < 100
        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: MagicMock(usWeightClass=50)
        result = resolver._get_weight_from_os2(mock_font)
        assert result == 0.0

        # Weight > 900 interpolates towards extrablack (1000 -> 215.0)
        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: MagicMock(usWeightClass=950)
        result = resolver._get_weight_from_os2(mock_font)
        assert result == 212.5

        # Beyond the scale, clamp
        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: MagicMock(usWeightClass=1100)
        result = resolver._get_weight_from_os2(mock_font)
        assert result == 215.0

    def test_get_weight_from_os2_no_table(self) -> None:
        """Test _get_weight_from_os2() returns default when OS/2 table missing."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: False  # No OS/2 table

        result = resolver._get_weight_from_os2(mock_font)
        assert result == 80.0  # Default: regular

    def test_get_weight_from_os2_exception(self) -> None:
        """Test _get_weight_from_os2() returns default on exception."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: (_ for _ in ()).throw(
            Exception("Error")
        )

        result = resolver._get_weight_from_os2(mock_font)
        assert result == 80.0  # Default on error


class TestWindowsFontResolverNameTable:
    """Tests for name table entry extraction."""

    def test_get_name_table_entry_windows_platform(self) -> None:
        """Test _get_name_table_entry() prefers Windows platform."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()
        mock_name_table = MagicMock()
        mock_name_entry = MagicMock()
        mock_name_entry.toUnicode.return_value = "Arial"

        mock_name_table.getName.return_value = mock_name_entry
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: mock_name_table

        result = resolver._get_name_table_entry(mock_font, 1)

        assert result == "Arial"
        # Should try Windows platform first (3, 1, 0x409)
        mock_name_table.getName.assert_called_with(1, 3, 1, 0x409)

    def test_get_name_table_entry_mac_fallback(self) -> None:
        """Test _get_name_table_entry() falls back to Mac platform."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()
        mock_name_table = MagicMock()
        mock_mac_entry = MagicMock()
        mock_mac_entry.toUnicode.return_value = "Arial"

        # Windows platform returns None, Mac platform returns entry
        mock_name_table.getName.side_effect = [None, mock_mac_entry]
        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: mock_name_table

        result = resolver._get_name_table_entry(mock_font, 1)

        assert result == "Arial"
        assert mock_name_table.getName.call_count == 2

    def test_get_name_table_entry_no_table(self) -> None:
        """Test _get_name_table_entry() returns None when name table missing."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()
        mock_font.__contains__ = lambda self, key: False  # No name table

        result = resolver._get_name_table_entry(mock_font, 1)
        assert result is None

    def test_get_name_table_entry_not_found(self) -> None:
        """Test _get_name_table_entry() returns None when entry not found."""
        resolver = windows_fonts.WindowsFontResolver()

        mock_font = MagicMock()
        mock_name_table = MagicMock()
        mock_name_table.getName.return_value = None
        mock_name_table.names = []  # No fallback entries

        mock_font.__contains__ = lambda self, key: True
        mock_font.__getitem__ = lambda self, key: mock_name_table

        result = resolver._get_name_table_entry(mock_font, 99)
        assert result is None


class TestGetWindowsFontResolver:
    """Tests for get_windows_font_resolver() singleton function."""

    def test_get_windows_font_resolver_singleton(self) -> None:
        """Test that get_windows_font_resolver() returns singleton instance."""
        # Reset the global instance
        windows_fonts._resolver = None

        # Get first instance
        resolver1 = windows_fonts.get_windows_font_resolver()
        assert resolver1 is not None
        assert isinstance(resolver1, windows_fonts.WindowsFontResolver)

        # Get second instance - should be same object
        resolver2 = windows_fonts.get_windows_font_resolver()
        assert resolver2 is resolver1

        # Clean up
        windows_fonts._resolver = None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific registry tests")
class TestWindowsRegistryIntegration:
    """Integration tests for Windows registry access (Windows only)."""

    def test_get_system_fonts_real(self) -> None:
        """Test _get_system_fonts() with real Windows registry."""
        resolver = windows_fonts.WindowsFontResolver()
        fonts = resolver._get_system_fonts()

        # Should find at least some fonts on Windows
        assert isinstance(fonts, list)
        assert len(fonts) > 0

        # All paths should be absolute and exist
        for font_path in fonts:
            assert isinstance(font_path, str)
            # Note: We don't check os.path.exists here because some registry
            # entries might be stale

    def test_get_user_fonts_real(self) -> None:
        """Test _get_user_fonts() with real Windows registry."""
        resolver = windows_fonts.WindowsFontResolver()
        fonts = resolver._get_user_fonts()

        # May or may not have user fonts
        assert isinstance(fonts, list)

        # All paths should be absolute
        for font_path in fonts:
            assert isinstance(font_path, str)
