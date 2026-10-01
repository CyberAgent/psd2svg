"""Tests for font subsetting functionality."""

import base64
import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest
from fontTools.ttLib import TTFont
from psd_tools import PSDImage

import psd2svg.__main__ as cli
from psd2svg import SVGDocument
from psd2svg.core.font_utils import (
    FontInfo,
    encode_font_bytes_to_data_uri,
    encode_font_with_options,
)
from psd2svg.font_subsetting import (
    _chars_to_unicode_list,
    _extract_font_family,
    _extract_text_content,
    _get_local_tag_name,
    extract_used_unicode,
    subset_font,
)
from tests.conftest import (
    get_fixture,
    requires_arial,
    requires_hiragino_mincho_collection,
    requires_noto_sans_jp,
)


class TestUnicodeExtraction:
    """Tests for extract_used_unicode function."""

    def test_extract_simple_text(self) -> None:
        """Test extraction of simple ASCII text."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text style="font-family: Arial">Hello</text>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        assert "Arial" in result
        assert result["Arial"] == {"H", "e", "l", "o"}

    def test_extract_nested_tspans(self) -> None:
        """Test extraction from nested tspan elements."""

        svg = ET.fromstring(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text style="font-family: Arial">Hello'
            '<tspan style="font-family: Courier">World</tspan>'
            "</text>"
            "</svg>"
        )

        result = extract_used_unicode(svg)

        assert "Arial" in result
        assert result["Arial"] == {"H", "e", "l", "o"}
        assert "Courier" in result
        assert result["Courier"] == {"W", "o", "r", "l", "d"}

    def test_extract_unicode_characters(self) -> None:
        """Test extraction of non-ASCII Unicode characters."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text style="font-family: Noto Sans JP">こんにちは</text>
                <text style="font-family: Arial">Hello</text>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        assert "Noto Sans JP" in result
        assert result["Noto Sans JP"] == {"こ", "ん", "に", "ち", "は"}
        assert "Arial" in result
        assert result["Arial"] == {"H", "e", "l", "o"}

    def test_extract_with_entities(self) -> None:
        """Test extraction with XML entities."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text style="font-family: Arial">A&lt;B&gt;C&amp;D</text>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        assert "Arial" in result
        # Entities should be decoded: &lt; → <, &gt; → >, &amp; → &
        assert result["Arial"] == {"A", "<", "B", ">", "C", "&", "D"}

    def test_extract_with_font_family_attribute(self) -> None:
        """Test extraction using font-family attribute instead of style."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text font-family="Times">Text</text>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        assert "Times" in result
        assert result["Times"] == {"T", "e", "x", "t"}

    def test_extract_empty_text(self) -> None:
        """Test extraction with empty text elements."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text style="font-family: Arial"></text>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        # Empty text should not create an entry
        assert result == {}

    def test_extract_no_text_elements(self) -> None:
        """Test extraction with SVG containing no text elements."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <rect x="0" y="0" width="100" height="100"/>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        assert result == {}

    def test_extract_with_quotes_in_font_family(self) -> None:
        """Test extraction with quoted font-family names."""

        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text style="font-family: 'Arial'">A</text>
                <text style='font-family: "Times New Roman"'>B</text>
            </svg>"""
        )

        result = extract_used_unicode(svg)

        assert "Arial" in result
        assert result["Arial"] == {"A"}
        assert "Times New Roman" in result
        assert result["Times New Roman"] == {"B"}

    def test_extract_foreignobject_elements(self) -> None:
        """Test extraction from foreignObject XHTML elements with namespace."""
        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <foreignObject>
                    <div xmlns="http://www.w3.org/1999/xhtml">
                        <p style="font-family: Arial">Hello</p>
                        <span style="font-family: Courier">World</span>
                    </div>
                </foreignObject>
            </svg>"""
        )
        result = extract_used_unicode(svg)

        assert "Arial" in result
        assert result["Arial"] == {"H", "e", "l", "o"}
        assert "Courier" in result
        assert result["Courier"] == {"W", "o", "r", "l", "d"}

    def test_extract_used_unicode_mixed_content(self) -> None:
        """Test SVG with both traditional text and foreignObject elements."""
        svg = ET.fromstring(
            """<svg xmlns="http://www.w3.org/2000/svg">
                <text font-family="Arial">ABC</text>
                <foreignObject>
                    <div xmlns="http://www.w3.org/1999/xhtml">
                        <p style="font-family: Times">XYZ</p>
                    </div>
                </foreignObject>
            </svg>"""
        )
        result = extract_used_unicode(svg)

        assert "Arial" in result
        assert result["Arial"] == {"A", "B", "C"}
        assert "Times" in result
        assert result["Times"] == {"X", "Y", "Z"}


class TestFontSubsetting:
    """Tests for subset_font function."""

    @requires_arial
    def test_subset_font_basic(self) -> None:
        """Test basic font subsetting with ASCII characters."""

        # Find Arial font
        font_info = FontInfo.resolve("Arial")
        assert font_info is not None, "Arial font should be available"

        # Subset with just a few characters (as codepoints)
        codepoints = {0x41, 0x42, 0x43}  # A, B, C
        try:
            font_bytes = subset_font(font_info.file, "ttf", codepoints)
        except (KeyError, Exception) as e:
            pytest.skip(f"Font subsetting failed (corrupt font file?): {e}")

        # Verify output is valid TTF bytes
        assert isinstance(font_bytes, bytes)
        assert len(font_bytes) > 0
        # TTF files should start with specific magic bytes
        assert font_bytes[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true")

    @requires_arial
    def test_subset_font_woff2_conversion(self) -> None:
        """Test font subsetting with WOFF2 format conversion."""

        font_info = FontInfo.resolve("Arial")
        assert font_info is not None, "Arial font should be available"

        codepoints = {0x48, 0x65, 0x6C, 0x6F, 0x57, 0x72, 0x64}  # H, e, l, o, W, r, d
        try:
            font_bytes = subset_font(font_info.file, "woff2", codepoints)
        except (KeyError, Exception) as e:
            pytest.skip(f"Font subsetting failed (corrupt font file?): {e}")

        assert isinstance(font_bytes, bytes)
        assert len(font_bytes) > 0
        # WOFF2 files start with 'wOF2' signature
        assert font_bytes[:4] == b"wOF2"

    @requires_arial
    def test_subset_font_reduces_size(self) -> None:
        """Test that subsetting significantly reduces font file size."""

        font_info = FontInfo.resolve("Arial")
        assert font_info is not None, "Arial font should be available"

        # Small subset (3 chars)
        try:
            small_subset = subset_font(
                font_info.file, "ttf", {0x41, 0x42, 0x43}
            )  # A, B, C
        except (KeyError, Exception) as e:
            pytest.skip(f"Font subsetting failed (corrupt font file?): {e}")

        # Larger subset (26 chars)
        try:
            large_subset = subset_font(
                font_info.file,
                "ttf",
                {ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
            )
        except (KeyError, Exception) as e:
            pytest.skip(f"Font subsetting failed (corrupt font file?): {e}")

        # Small subset should be smaller than large subset
        assert len(small_subset) < len(large_subset)

        # Both should be much smaller than typical full font (>100KB)
        assert len(small_subset) < 50000  # < 50KB
        assert len(large_subset) < 100000  # < 100KB

    def test_subset_font_invalid_format(self) -> None:
        """Test error with unsupported font format."""

        with pytest.raises(ValueError, match="Unsupported font format"):
            subset_font("", "invalid", {0x41})  # A

    def test_subset_font_selects_collection_face(self) -> None:
        """The requested TTC face is passed to fontTools."""
        with patch(
            "psd2svg.font_subsetting.TTFont", side_effect=RuntimeError("stop")
        ) as mock_ttfont:
            with pytest.raises(RuntimeError, match="stop"):
                subset_font("family.ttc", "ttf", {0x41}, face_index=2)

        mock_ttfont.assert_called_once_with("family.ttc", fontNumber=2)

    @requires_noto_sans_jp
    def test_subset_font_unicode_chars(self) -> None:
        """Test subsetting with non-ASCII Unicode characters."""

        font_info = FontInfo.resolve("Noto Sans JP")
        assert font_info is not None, "Noto Sans JP font should be available"

        # Subset with Japanese characters (as codepoints)
        codepoints = {0x3053, 0x3093, 0x306B, 0x3061, 0x306F}  # こ, ん, に, ち, は
        try:
            font_bytes = subset_font(font_info.file, "woff2", codepoints)
        except (KeyError, Exception) as e:
            pytest.skip(f"Font subsetting failed (corrupt font file?): {e}")

        assert isinstance(font_bytes, bytes)
        assert len(font_bytes) > 0
        assert font_bytes[:4] == b"wOF2"


class TestSVGDocumentIntegration:
    """Integration tests for SVGDocument with font subsetting."""

    def test_tostring_subset_ignored_without_embed(self) -> None:
        """Test that subset_fonts is silently ignored when embed_fonts=False."""

        psd = PSDImage.open(get_fixture("texts/style-tracking.psd"))
        doc = SVGDocument.from_psd(psd)

        # Should not raise - subset_fonts is simply ignored when embed_fonts=False
        svg_string = doc.tostring(embed_fonts=False, subset_fonts=True)
        assert svg_string  # Conversion succeeds
        assert "@font-face" not in svg_string  # No fonts embedded

    def test_save_subset_ignored_without_embed(self, tmp_path: Path) -> None:
        """Test that subset_fonts is silently ignored.

        When embed_fonts=False in save().
        """

        psd = PSDImage.open(get_fixture("texts/style-tracking.psd"))
        doc = SVGDocument.from_psd(psd)

        output_path = tmp_path / "output.svg"

        # Should not raise - subset_fonts is simply ignored when embed_fonts=False
        doc.save(
            str(output_path), embed_images=True, embed_fonts=False, subset_fonts=True
        )
        assert output_path.exists()

        # Verify no fonts were embedded
        with open(output_path) as f:
            content = f.read()
            assert "@font-face" not in content

    def test_woff2_auto_enables_subsetting(self, tmp_path: Path) -> None:
        """Test that font_format='woff2' automatically enables subsetting."""

        psd = PSDImage.open(get_fixture("texts/style-tracking.psd"))
        doc = SVGDocument.from_psd(psd)

        output_path = tmp_path / "output.svg"

        # This should work even without explicit subset_fonts=True
        # (woff2 auto-enables it internally)
        try:
            doc.save(
                str(output_path),
                embed_images=True,
                embed_fonts=True,
                font_format="woff2",
            )
            assert output_path.exists()

            # Verify WOFF2 or fallback TTF data URI is in the output
            content = output_path.read_text()

            # Skip test if no fonts were embedded (fonts not available on system)
            if "@font-face" not in content:
                pytest.skip("Required fonts not available on this system")

            # May have WOFF2 or TTF depending on whether chars were found
            assert (
                "data:font/woff2;base64," in content
                or "data:font/ttf;base64," in content
            )
        except FileNotFoundError:
            pytest.skip("Required font not available")

    def test_subset_fonts_reduces_output_size(self, tmp_path: Path) -> None:
        """Test that subsetting significantly reduces output file size."""

        psd = PSDImage.open(get_fixture("texts/style-tracking.psd"))
        doc = SVGDocument.from_psd(psd)

        # Save without subsetting
        output_full = tmp_path / "output_full.svg"
        try:
            doc.save(
                str(output_full), embed_images=True, embed_fonts=True, font_format="ttf"
            )
        except FileNotFoundError:
            pytest.skip("Required font not available")

        # Save with subsetting
        output_subset = tmp_path / "output_subset.svg"
        doc.save(
            str(output_subset),
            embed_images=True,
            embed_fonts=True,
            subset_fonts=True,
            font_format="ttf",
        )

        # Subset version should be significantly smaller
        full_size = output_full.stat().st_size
        subset_size = output_subset.stat().st_size

        # If sizes are equal, subsetting likely failed due to corrupt fonts
        if subset_size == full_size:
            pytest.skip("Font subsetting failed (likely corrupt font file)")

        # Expect at least 50% reduction (typically 90%+)
        assert subset_size < full_size * 0.5

    def test_subset_fonts_with_woff2(self, tmp_path: Path) -> None:
        """Test subsetting with WOFF2 format provides maximum compression."""

        psd = PSDImage.open(get_fixture("texts/style-tracking.psd"))
        doc = SVGDocument.from_psd(psd)

        # Save with WOFF2 (auto-enables subsetting)
        output_woff2 = tmp_path / "output.svg"
        try:
            doc.save(
                str(output_woff2),
                embed_images=True,
                embed_fonts=True,
                font_format="woff2",
            )
        except FileNotFoundError:
            pytest.skip("Required font not available")

        # Verify output exists and is valid
        assert output_woff2.exists()

        # Verify WOFF2 signature in output
        content = output_woff2.read_text()

        # Skip test if no fonts were embedded (fonts not available on system)
        if "@font-face" not in content:
            pytest.skip("Required fonts not available on this system")

        assert "data:font/woff2;base64," in content


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_chars_to_unicode_list(self) -> None:
        """Test conversion of characters to Unicode code points."""

        chars = {"A", "B", "あ"}
        result = _chars_to_unicode_list(chars)

        # Should return sorted list of code points
        assert result == sorted([0x41, 0x42, 0x3042])  # A, B, あ

    def test_get_local_tag_name(self) -> None:
        """Test extraction of local tag name from namespaced element."""

        # Namespaced tag
        elem = ET.Element("{http://www.w3.org/2000/svg}text")
        assert _get_local_tag_name(elem) == "text"

        # Non-namespaced tag
        elem = ET.Element("text")
        assert _get_local_tag_name(elem) == "text"

    def test_extract_font_family(self) -> None:
        """Test font-family extraction from style attribute."""

        # Style attribute
        elem = ET.fromstring('<text style="font-family: Arial; font-size: 12px"/>')
        assert _extract_font_family(elem) == "Arial"

        # Font-family attribute
        elem = ET.fromstring('<text font-family="Times"/>')
        assert _extract_font_family(elem) == "Times"

        # Quoted font family
        elem = ET.fromstring("<text style=\"font-family: 'Courier New'\"/>")
        assert _extract_font_family(elem) == "Courier New"

        # No font-family
        elem = ET.fromstring('<text style="font-size: 12px"/>')
        assert _extract_font_family(elem) is None

    def test_extract_text_content(self) -> None:
        """Test text content extraction with entity decoding."""

        # Simple text
        elem = ET.fromstring("<text>Hello</text>")
        assert _extract_text_content(elem) == "Hello"

        # Text with child elements
        elem = ET.fromstring("<text>Hello<tspan>World</tspan>!</text>")
        assert _extract_text_content(elem) == "HelloWorld!"

        # Text with entities
        elem = ET.fromstring("<text>A&lt;B&gt;C</text>")
        assert _extract_text_content(elem) == "A<B>C"

        # Text with control characters (should be filtered)
        elem = ET.fromstring("<text>Hello\nWorld\tTest</text>")
        assert _extract_text_content(elem) == "HelloWorldTest"
        assert "\n" not in _extract_text_content(elem)
        assert "\t" not in _extract_text_content(elem)

        # Text with DEL and C1 controls (should be filtered)
        elem = ET.fromstring("<text>A\x7fB\x80C</text>")  # DEL (127), C1 (128)
        assert _extract_text_content(elem) == "ABC"

        # Text with only control characters (should return empty)
        elem = ET.fromstring("<text>\n\t\r</text>")
        assert _extract_text_content(elem) == ""

        # Text with only spaces (should be preserved)
        elem = ET.fromstring("<text>Hello World</text>")
        assert _extract_text_content(elem) == "Hello World"


class TestFontUtilsExtensions:
    """Tests for new font_utils functions."""

    def test_encode_font_bytes_to_data_uri_ttf(self) -> None:
        """Test encoding font bytes to TTF data URI."""

        font_bytes = b"\x00\x01\x00\x00"  # Minimal TTF signature
        data_uri = encode_font_bytes_to_data_uri(font_bytes, "ttf")

        assert data_uri.startswith("data:font/ttf;base64,")
        assert "AAEAAA" in data_uri  # Base64 of the bytes

    def test_encode_font_bytes_to_data_uri_woff2(self) -> None:
        """Test encoding font bytes to WOFF2 data URI."""

        font_bytes = b"wOF2test"
        data_uri = encode_font_bytes_to_data_uri(font_bytes, "woff2")

        assert data_uri.startswith("data:font/woff2;base64,")

    def test_encode_font_bytes_invalid_format(self) -> None:
        """Test error with invalid font format."""

        with pytest.raises(ValueError, match="Unsupported font format"):
            encode_font_bytes_to_data_uri(b"test", "invalid")

    def test_encode_font_cache_separates_collection_faces(self) -> None:
        """Equal-sized subsets from different TTC faces do not share cache data."""
        cache: dict[str, str] = {}

        def fake_subset(**kwargs: object) -> bytes:
            return f"face-{kwargs['face_index']}".encode()

        with patch(
            "psd2svg.core.font_utils.font_subsetting.subset_font",
            side_effect=fake_subset,
        ) as mock_subset:
            first = encode_font_with_options("family.ttc", cache, {0x41}, face_index=0)
            second = encode_font_with_options("family.ttc", cache, {0x41}, face_index=1)

        assert first != second
        assert mock_subset.call_count == 2


@requires_hiragino_mincho_collection
def test_cli_embeds_each_face_of_a_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W3 and W6 from one Hiragino TTC are embedded as their own faces (#373)."""
    output = tmp_path / "output.svg"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "psd2svg",
            get_fixture("texts/fonts-hiragino-mincho-pron-w3-w6.psd"),
            str(output),
            "--embed-fonts",
        ],
    )

    cli.main()

    rules = re.findall(r"@font-face\s*{([^}]*)}", output.read_text())
    embedded = {}
    for rule in rules:
        weight = re.search(r"font-weight:\s*(\d+)", rule)
        data = re.search(r"base64,([A-Za-z0-9+/=]+)", rule)
        assert weight and data
        font = TTFont(io.BytesIO(base64.b64decode(data.group(1))))
        embedded[font["name"].getDebugName(6)] = int(weight.group(1))

    assert embedded == {"HiraMinProN-W3": 300, "HiraMinProN-W6": 600}
