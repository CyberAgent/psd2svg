"""Tests for SVGDocument class functionality.

This module tests various SVGDocument methods including:
- Font encoding and embedding (@font-face CSS generation)
- Image handling (embedding vs file saving)
- String and file serialization (tostring, save)
- Rasterization with different backends
"""

import logging
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from psd_tools import PSDImage

from psd2svg import SVGDocument, svg_utils
from psd2svg.core.font_utils import FontInfo, create_file_url, encode_font_data_uri
from psd2svg.core.text import TextWrappingMode
from psd2svg.core.typesetting import TypeSetting
from psd2svg.rasterizer import PlaywrightRasterizer, ResvgRasterizer
from tests.conftest import get_fixture, requires_playwright


class TestEncodeFontDataUri:
    """Tests for encode_font_data_uri function."""

    def test_encode_ttf_font(self, tmp_path: Path) -> None:
        """Test encoding TTF font file to data URI."""
        # Create a minimal fake TTF file
        font_file = tmp_path / "test.ttf"
        font_file.write_bytes(b"FAKE_TTF_DATA")

        data_uri = encode_font_data_uri(str(font_file))

        assert data_uri.startswith("data:font/ttf;base64,")
        assert "RkFLRV9UVEZfREFUQQ==" in data_uri  # base64 of "FAKE_TTF_DATA"

    def test_encode_otf_font(self, tmp_path: Path) -> None:
        """Test encoding OTF font file uses correct MIME type."""
        font_file = tmp_path / "test.otf"
        font_file.write_bytes(b"FAKE_OTF_DATA")

        data_uri = encode_font_data_uri(str(font_file))

        assert data_uri.startswith("data:font/otf;base64,")

    def test_encode_woff_font(self, tmp_path: Path) -> None:
        """Test encoding WOFF font file uses correct MIME type."""
        font_file = tmp_path / "test.woff"
        font_file.write_bytes(b"FAKE_WOFF_DATA")

        data_uri = encode_font_data_uri(str(font_file))

        assert data_uri.startswith("data:font/woff;base64,")

    def test_encode_woff2_font(self, tmp_path: Path) -> None:
        """Test encoding WOFF2 font file uses correct MIME type."""
        font_file = tmp_path / "test.woff2"
        font_file.write_bytes(b"FAKE_WOFF2_DATA")

        data_uri = encode_font_data_uri(str(font_file))

        assert data_uri.startswith("data:font/woff2;base64,")

    def test_encode_unknown_extension_defaults_to_ttf(self, tmp_path: Path) -> None:
        """Test unknown font extension defaults to font/ttf MIME type."""
        font_file = tmp_path / "test.xyz"
        font_file.write_bytes(b"UNKNOWN_FONT_DATA")

        data_uri = encode_font_data_uri(str(font_file))

        assert data_uri.startswith("data:font/ttf;base64,")

    def test_encode_nonexistent_font_raises_error(self) -> None:
        """Test encoding non-existent font file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Font file not found"):
            encode_font_data_uri("/nonexistent/path/to/font.ttf")

    def test_encode_unreadable_font_raises_error(self, tmp_path: Path) -> None:
        """Test encoding unreadable font file raises IOError."""
        font_file = tmp_path / "test.ttf"
        font_file.write_bytes(b"FAKE_TTF_DATA")

        # Make file unreadable (only works on Unix-like systems)
        if sys.platform != "win32":
            os.chmod(font_file, 0o000)
            try:
                with pytest.raises(IOError, match="Failed to read font file"):
                    encode_font_data_uri(str(font_file))
            finally:
                # Restore permissions for cleanup
                os.chmod(font_file, 0o644)


class TestFontInfoToFontFaceCss:
    """Tests for FontInfo.to_font_face_css method."""

    def test_to_font_face_css_regular(self) -> None:
        """Test CSS generation for regular font."""
        font = FontInfo(
            postscript_name="ArialMT",
            file="/path/to/arial.ttf",
            family="Arial",
            style="Regular",
            weight=80.0,
        )

        css = font.to_font_face_css("data:font/ttf;base64,ABC123")

        assert "@font-face {" in css
        assert "font-family: 'Arial';" in css
        assert "src: url(data:font/ttf;base64,ABC123);" in css
        assert "font-weight: 400;" in css
        assert "font-style: normal;" in css
        assert "}" in css

    def test_to_font_face_css_bold(self) -> None:
        """Test CSS generation for bold font."""
        font = FontInfo(
            postscript_name="Arial-BoldMT",
            file="/path/to/arial-bold.ttf",
            family="Arial",
            style="Bold",
            weight=200.0,
        )

        css = font.to_font_face_css("data:font/ttf;base64,XYZ789")

        assert "font-weight: 700;" in css
        assert "font-style: normal;" in css

    def test_to_font_face_css_italic(self) -> None:
        """Test CSS generation for italic font."""
        font = FontInfo(
            postscript_name="Arial-ItalicMT",
            file="/path/to/arial-italic.ttf",
            family="Arial",
            style="Italic",
            weight=80.0,
        )

        css = font.to_font_face_css("data:font/ttf;base64,DEF456")

        assert "font-weight: 400;" in css
        assert "font-style: italic;" in css

    def test_to_font_face_css_bold_italic(self) -> None:
        """Test CSS generation for bold italic font."""
        font = FontInfo(
            postscript_name="Arial-BoldItalicMT",
            file="/path/to/arial-bolditalic.ttf",
            family="Arial",
            style="Bold Italic",
            weight=200.0,
        )

        css = font.to_font_face_css("data:font/ttf;base64,GHI012")

        assert "font-weight: 700;" in css
        assert "font-style: italic;" in css


class TestFontFaceCollision:
    """Tests for @font-face descriptor collision detection (issue #337)."""

    @staticmethod
    def _font(
        postscript_name: str,
        path: Path,
        weight: float,
        charset: set[int] | None = None,
    ) -> FontInfo:
        path.write_bytes(b"")
        return FontInfo(
            postscript_name=postscript_name,
            file=str(path),
            family="Test Family",
            style="Test",
            weight=weight,
            charset=charset,
        )

    def test_colliding_descriptors_are_reported(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Two faces with the same (family, weight, style) shadow each other.

        The collision is reported but both rules are still emitted: each face
        carries its own subset, so dropping one would take its glyphs with it.
        """
        doc = SVGDocument(svg=ET.Element("svg"), images={})
        first = tmp_path / "a.ttf"
        second = tmp_path / "b.ttf"
        fonts = [
            self._font("Test-A", first, 50.0),
            self._font("Test-B", second, 50.0),
        ]

        with caplog.at_level(logging.WARNING):
            rules = doc._generate_css_rules_for_fonts(
                fonts, subset_fonts=False, font_format="woff2", use_data_uri=False
            )

        assert len(rules) == 2
        assert first.name in rules[0]
        assert second.name in rules[1]
        assert str(second) in caplog.text

    def test_colliding_faces_keep_their_own_charsets(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A collision must not cost either face the glyphs only it covers."""
        doc = SVGDocument(svg=ET.Element("svg"), images={})
        first = self._font("Test-A", tmp_path / "a.ttf", 50.0, {ord("A")})
        second = self._font("Test-B", tmp_path / "b.ttf", 50.0, {ord("B")})

        with caplog.at_level(logging.WARNING):
            rules = doc._generate_css_rules_for_fonts(
                [first, second],
                subset_fonts=True,
                font_format="woff2",
                use_data_uri=False,
            )

        assert len(rules) == 2

    def test_distinct_descriptors_both_emitted(self, tmp_path: Path) -> None:
        """Neighbouring weights stay distinguishable, so both rules survive."""
        doc = SVGDocument(svg=ET.Element("svg"), images={})
        fonts = [
            self._font("Test-W2", tmp_path / "w2.ttf", 45.0),
            self._font("Test-W3", tmp_path / "w3.ttf", 50.0),
        ]

        rules = doc._generate_css_rules_for_fonts(
            fonts, subset_fonts=False, font_format="woff2", use_data_uri=False
        )

        assert len(rules) == 2
        assert "font-weight: 250;" in rules[0]
        assert "font-weight: 300;" in rules[1]


class TestSVGDocumentImageHandling:
    """Tests for SVGDocument image handling behavior."""

    def test_tostring_default_no_images(self) -> None:
        """Test tostring() with default parameters works when no images present."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "rect", x="10", y="10", width="80", height="80")

        document = SVGDocument(svg=svg_elem, images={})

        # Should work with no parameters (embed_images=True by default)
        result = document.tostring()

        assert "<svg>" in result
        assert "<rect" in result
        assert 'x="10"' in result

    def test_tostring_default_with_images(self) -> None:
        """Test tostring() with default parameters embeds images."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="red")},
        )

        # Should embed images by default
        result = document.tostring()

        assert "data:image/webp;base64," in result
        assert "href=" in result

    def test_tostring_embed_images_false_no_prefix_raises_error(self) -> None:
        """Test tostring() with embed_images=False and no prefix raises error."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="red")},
        )

        # Should raise ValueError when images exist but no output method specified
        with pytest.raises(
            ValueError,
            match="Either embed_images must be True or image_prefix must be provided",
        ):
            document.tostring(embed_images=False)

    def test_tostring_with_image_prefix_saves_files(self, tmp_path: Path) -> None:
        """Test tostring() with image_prefix saves images to files."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="blue")},
        )

        # Change to tmp_path directory to use relative path
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Use relative image_prefix
            result = document.tostring(image_prefix="img")

            # Should contain filename reference, not data URI
            assert "data:image/" not in result
            assert "img01.webp" in result

            # File should be created
            assert (tmp_path / "img01.webp").exists()
        finally:
            os.chdir(old_cwd)

    @pytest.mark.parametrize(
        ("image_format", "mime_type"),
        [(None, "image/webp"), ("png", "image/png")],
    )
    def test_rasterize_image_format(
        self, image_format: str | None, mime_type: str
    ) -> None:
        """Test rasterize() embeds images in the requested format."""
        svg_elem = ET.Element("svg", width="10", height="10")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="red")},
        )

        with patch.object(ResvgRasterizer, "from_string") as mock_from_string:
            mock_from_string.return_value = Image.new("RGBA", (10, 10))
            if image_format is None:
                document.rasterize()
            else:
                document.rasterize(image_format=image_format)

        svg_arg = mock_from_string.call_args[0][0]
        assert f"data:{mime_type};base64," in svg_arg

    def test_handle_images_empty_document(self) -> None:
        """Test _handle_images() returns early when no images present."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "rect")

        document = SVGDocument(svg=svg_elem, images={})

        # Should work with any combination when no images
        result1 = document.tostring(embed_images=True)
        result2 = document.tostring(embed_images=False)

        assert "<rect" in result1
        assert "<rect" in result2
        # Both should produce same output since no images to handle
        assert result1 == result2


class TestSVGDocumentEmbedFonts:
    """Tests for SVGDocument font embedding functionality."""

    def test_tostring_with_embed_fonts_false(self) -> None:
        """Test tostring with embed_fonts=False doesn't add style element."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "rect")

        document = SVGDocument(svg=svg_elem, images={})
        result = document.tostring(embed_images=True, embed_fonts=False)

        assert "<style>" not in result
        assert "@font-face" not in result

    def test_tostring_with_embed_fonts_true_no_fonts(self) -> None:
        """Test tostring with embed_fonts=True but no fonts.

        Should not add style element.
        """
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "rect")

        document = SVGDocument(svg=svg_elem, images={})
        result = document.tostring(embed_images=True, embed_fonts=True)

        assert "<style>" not in result

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_tostring_with_embed_fonts_true(
        self, mock_resolve: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """Test tostring with embed_fonts=True adds style element."""
        mock_encode.return_value = "data:font/ttf;base64,MOCKDATA"

        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")

        # Mock FontInfo to return a font pointing to our test file
        mock_font = FontInfo(
            postscript_name="ArialMT",
            family="Arial",
            style="Regular",
            weight=80.0,
            file=str(font_file),
        )
        mock_resolve.return_value = mock_font

        svg_elem = ET.Element("svg")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "ArialMT")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})
        result = document.tostring(
            embed_images=True, embed_fonts=True, subset_fonts=False
        )

        assert "<style>" in result
        assert "@font-face" in result
        assert "font-family: 'Arial'" in result
        assert "data:font/ttf;base64,MOCKDATA" in result
        mock_encode.assert_called_once_with(str(font_file))

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_save_with_embed_fonts_true(
        self, mock_resolve: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """Test save with embed_fonts=True writes style element to file."""
        mock_encode.return_value = "data:font/ttf;base64,MOCKDATA"

        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")
        output_file = tmp_path / "output.svg"

        # Mock FontInfo to return a font pointing to our test file
        mock_font = FontInfo(
            postscript_name="ArialMT",
            family="Arial",
            style="Regular",
            weight=80.0,
            file=str(font_file),
        )
        mock_resolve.return_value = mock_font

        svg_elem = ET.Element("svg")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "ArialMT")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})
        document.save(
            str(output_file), embed_images=True, embed_fonts=True, subset_fonts=False
        )

        content = output_file.read_text()
        assert "<style>" in content
        assert "@font-face" in content
        assert "font-family: 'Arial'" in content

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.find")
    def test_embed_fonts_deduplicates_same_font(
        self, mock_find: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """Test that duplicate fonts are not embedded multiple times."""
        mock_encode.return_value = "data:font/ttf;base64,MOCKDATA"

        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")

        # Mock FontInfo to return a font pointing to our test file
        mock_font = FontInfo(
            postscript_name="ArialMT",
            family="Arial",
            style="Regular",
            weight=80.0,
            file=str(font_file),
        )
        mock_find.return_value = mock_font

        svg_elem = ET.Element("svg")
        # Add two text elements with the same PostScript font name
        text_elem1 = ET.SubElement(svg_elem, "text")
        text_elem1.set("font-family", "ArialMT")
        text_elem1.text = "Test1"
        text_elem2 = ET.SubElement(svg_elem, "text")
        text_elem2.set("font-family", "ArialMT")
        text_elem2.text = "Test2"

        document = SVGDocument(svg=svg_elem, images={})
        result = document.tostring(
            embed_images=True, embed_fonts=True, subset_fonts=False
        )

        # Should only encode once
        mock_encode.assert_called_once()

        # Should only have one @font-face rule
        assert result.count("@font-face") == 1

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.find")
    def test_embed_fonts_caches_encoded_data(
        self, mock_find: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """Test that encoded font data is cached across multiple calls."""
        mock_encode.return_value = "data:font/ttf;base64,MOCKDATA"

        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")

        # Mock FontInfo to return a font pointing to our test file
        mock_font = FontInfo(
            postscript_name="ArialMT",
            family="Arial",
            style="Regular",
            weight=80.0,
            file=str(font_file),
        )
        mock_find.return_value = mock_font

        svg_elem = ET.Element("svg")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "ArialMT")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})

        # Call tostring twice
        document.tostring(embed_images=True, embed_fonts=True, subset_fonts=False)
        document.tostring(embed_images=True, embed_fonts=True, subset_fonts=False)

        # Should only encode once due to caching
        mock_encode.assert_called_once()

    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_embed_fonts_handles_missing_font_gracefully(
        self, mock_resolve: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that missing fonts are skipped with a warning."""
        # Mock font resolution to return None (font not found)
        mock_resolve.return_value = None

        svg_elem = ET.Element("svg")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "MissingFont")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})
        result = document.tostring(
            embed_images=True, embed_fonts=True, subset_fonts=False
        )

        # Should not raise exception
        assert "<style>" not in result

        # Should log warning about no fonts embedded (font resolution returned None)
        assert "No resolved fonts found; skipping font embedding" in caplog.text

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_embed_fonts_with_multiple_fonts(
        self, mock_resolve: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """Test embedding multiple different fonts."""

        def mock_encode_func(path: str) -> str:
            return f"data:font/ttf;base64,MOCK_{Path(path).stem}"

        mock_encode.side_effect = mock_encode_func

        font1_file = tmp_path / "arial.ttf"
        font1_file.write_bytes(b"FAKE_FONT1")
        font2_file = tmp_path / "times.ttf"
        font2_file.write_bytes(b"FAKE_FONT2")

        # Mock FontInfo.resolve to handle both PostScript names and family names
        def mock_find_func(font_name: str, **kwargs: object) -> FontInfo:
            _ = kwargs  # Unused but needed for signature
            # Handle PostScript names (ArialMT) and family names (Arial)
            if font_name in ("ArialMT", "Arial"):
                return FontInfo(
                    postscript_name="ArialMT",
                    family="Arial",
                    style="Regular",
                    weight=80.0,
                    file=str(font1_file),
                )
            else:  # TimesNewRomanMT or "Times New Roman"
                return FontInfo(
                    postscript_name="TimesNewRomanMT",
                    family="Times New Roman",
                    style="Regular",
                    weight=80.0,
                    file=str(font2_file),
                )

        mock_resolve.side_effect = mock_find_func

        svg_elem = ET.Element("svg")
        # Add text elements with different PostScript font names
        text_elem1 = ET.SubElement(svg_elem, "text")
        text_elem1.set("font-family", "ArialMT")
        text_elem1.text = "Arial text"
        text_elem2 = ET.SubElement(svg_elem, "text")
        text_elem2.set("font-family", "TimesNewRomanMT")
        text_elem2.text = "Times text"

        document = SVGDocument(svg=svg_elem, images={})
        result = document.tostring(
            embed_images=True, embed_fonts=True, subset_fonts=False
        )

        assert result.count("@font-face") == 2
        assert "font-family: 'Arial'" in result
        assert "font-family: 'Times New Roman'" in result
        assert "MOCK_arial" in result
        assert "MOCK_times" in result

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_font_embedding_with_foreignobject_mode(
        self, mock_resolve: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """Test font embedding works with foreignObject XHTML elements."""
        # Setup mock font
        font_file = tmp_path / "times.ttf"
        font_file.write_bytes(b"FAKE_TIMES_FONT")
        mock_resolve.return_value = FontInfo(
            postscript_name="Times-Roman",
            family="Times New Roman",
            file=str(font_file),
            weight=80.0,
            style="Regular",
            charset=set(),
        )
        mock_encode.return_value = "data:font/ttf;base64,FAKE_TIMES"

        # Load PSD and convert with foreignObject mode
        psdimage = PSDImage.open(
            get_fixture("texts/paragraph-shapetype1-justification0.psd")
        )
        doc = SVGDocument.from_psd(
            psdimage,
            text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
        )

        # Convert with font embedding
        result = doc.tostring(embed_fonts=True)

        # Verify fonts were resolved and embedded
        assert "@font-face" in result
        # Verify XHTML structure exists
        assert "<p" in result or "<span" in result
        # Verify font resolution was called (PostScript names were processed)
        assert mock_resolve.called

    def test_static_font_resolution_foreignobject(self, tmp_path: Path) -> None:
        """Test static font resolution with foreignObject mode."""
        # Load PSD and convert with foreignObject mode
        psdimage = PSDImage.open(
            get_fixture("texts/paragraph-shapetype1-justification0.psd")
        )
        doc = SVGDocument.from_psd(
            psdimage,
            text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
        )

        # Convert with static font resolution only (no embedding)
        result = doc.tostring(embed_fonts=False)

        # Verify XHTML structure exists
        assert "<p" in result or "<span" in result

        # Verify font-family is present in style attributes
        # (Even if not resolved, should have font names)
        assert "font-family:" in result or 'font-family="' in result

    def test_foreignobject_weight_and_style_land_in_css(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A resolved bold italic face reaches a <foreignObject> span as CSS.

        XHTML has no font-weight/font-style attributes, so writing them as
        attributes left the span rendering in the family's Regular face.
        See GitHub issue #376.
        """
        # Times-BoldItalic is in the static mapping, so this resolves to
        # Times / 700 / italic without touching the system fonts.
        monkeypatch.setattr(
            TypeSetting, "get_postscript_name", lambda self, index: "Times-BoldItalic"
        )
        psdimage = PSDImage.open(
            get_fixture("texts/paragraph-shapetype1-justification0.psd")
        )
        doc = SVGDocument.from_psd(
            psdimage,
            text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
        )

        result = doc.tostring(embed_fonts=False)

        spans = svg_utils.fromstring(result).findall(
            ".//{http://www.w3.org/1999/xhtml}span"
        )
        assert spans, "Should have xhtml spans"
        for span in spans:
            style = span.get("style", "")
            assert "font-weight: 700" in style, f"Unexpected styles: {style}"
            assert "font-style: italic" in style, f"Unexpected styles: {style}"
            # The inert attribute form must not survive serialization.
            assert "font-weight" not in span.attrib
            assert "font-style" not in span.attrib

    def test_foreignobject_paragraph_takes_the_family_alone(self) -> None:
        """The strut on a <p> names a family and stops there.

        A <p> inside a <foreignObject> names a font only to size its line
        boxes (issue #421); the text is in its spans. Weight and style inherit,
        so a bold strut would reach every span that resolved to another face.
        """
        svg = svg_utils.fromstring(
            '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject>'
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            "<p style=\"line-height: 38.4px; font-family: 'Times-BoldItalic'\">"
            "<span style=\"font-family: 'Times-BoldItalic'\">Bold</span>"
            "<span style=\"font-family: 'Times-Roman'\">Regular</span>"
            "</p></div></foreignObject></svg>"
        )
        SVGDocument(svg, {})._resolve_postscript_names_static(svg)

        paragraph = svg.find(".//{http://www.w3.org/1999/xhtml}p")
        assert paragraph is not None
        style = paragraph.get("style", "")
        assert "font-family: 'Times'" in style, f"Unexpected styles: {style}"
        assert "font-weight" not in style, f"Unexpected styles: {style}"
        assert "font-style" not in style, f"Unexpected styles: {style}"

        bold, regular = svg.findall(".//{http://www.w3.org/1999/xhtml}span")
        assert "font-weight: 700" in bold.get("style", "")
        assert "font-style: italic" in bold.get("style", "")
        assert "font-weight" not in regular.get("style", "")
        assert "font-style" not in regular.get("style", "")

    @patch("psd2svg.core.font_utils.encode_font_data_uri")
    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_foreignobject_weight_and_style_land_in_css_when_embedding(
        self, mock_resolve: MagicMock, mock_encode: MagicMock, tmp_path: Path
    ) -> None:
        """The embedding path resolves into CSS too, not just the static one.

        embed_fonts=True goes through _resolve_and_collect_fonts() instead of
        _resolve_postscript_names_static(). See GitHub issue #376.
        """
        font_file = tmp_path / "times-bolditalic.ttf"
        font_file.write_bytes(b"FAKE_TIMES_BOLD_ITALIC")
        mock_resolve.return_value = FontInfo(
            postscript_name="Times-BoldItalic",
            family="Times New Roman",
            file=str(font_file),
            weight=200.0,
            style="Bold Italic",
            charset=set(),
        )
        mock_encode.return_value = "data:font/ttf;base64,FAKE"

        psdimage = PSDImage.open(
            get_fixture("texts/paragraph-shapetype1-justification0.psd")
        )
        doc = SVGDocument.from_psd(
            psdimage,
            text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
        )

        result = doc.tostring(embed_fonts=True)

        spans = svg_utils.fromstring(result).findall(
            ".//{http://www.w3.org/1999/xhtml}span"
        )
        assert spans, "Should have xhtml spans"
        for span in spans:
            style = span.get("style", "")
            assert "font-weight: 700" in style, f"Unexpected styles: {style}"
            assert "font-style: italic" in style, f"Unexpected styles: {style}"
            assert "font-weight" not in span.attrib
            assert "font-style" not in span.attrib

    def test_native_text_keeps_presentation_attributes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SVG text still carries the weight and style as attributes (#376)."""
        monkeypatch.setattr(
            TypeSetting, "get_postscript_name", lambda self, index: "Times-BoldItalic"
        )
        psdimage = PSDImage.open(
            get_fixture("texts/paragraph-shapetype1-justification0.psd")
        )
        doc = SVGDocument.from_psd(psdimage)

        result = doc.tostring(embed_fonts=False)

        elements = svg_utils.fromstring(result).findall(
            ".//{http://www.w3.org/2000/svg}text"
        )
        assert elements, "Should have text elements"
        for element in elements:
            assert element.get("font-weight") == "700"
            assert element.get("font-style") == "italic"
            assert "font-weight" not in element.get("style", "")


class TestSVGDocumentRasterizeWithFonts:
    """Tests for font embedding in rasterize() method."""

    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_rasterize_with_resvg_uses_font_files(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """Test that ResvgRasterizer extracts font files from @font-face CSS."""
        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")

        # Mock FontInfo to return a font pointing to our test file
        font = FontInfo(
            postscript_name="ArialMT",
            file=str(font_file),
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        mock_resolve.return_value = font

        svg_elem = ET.Element("svg", width="100", height="100")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "ArialMT")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})

        with patch.object(ResvgRasterizer, "from_string") as mock_from_string:
            mock_from_string.return_value = Image.new("RGBA", (100, 100))

            rasterizer = ResvgRasterizer()
            document.rasterize(rasterizer=rasterizer)

            # Verify from_string was called
            assert mock_from_string.call_count == 1
            svg_arg = mock_from_string.call_args[0][0]

            # Should embed fonts in SVG with file:// URLs
            assert "@font-face" in svg_arg
            # Check for properly formatted file URL (cross-platform)
            expected_url = create_file_url(str(font_file))
            assert expected_url in svg_arg

    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_rasterize_with_playwright_embeds_fonts(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """Test that PlaywrightRasterizer gets fonts embedded with file:// URLs.

        Note: This test was updated to reflect the new behavior where fonts are
        embedded using local file:// URLs instead of data URIs for better performance.
        """
        try:
            # Optional dependency - Playwright may not be installed
            from psd2svg.rasterizer import PlaywrightRasterizer  # noqa: PLC0415
        except ImportError:
            pytest.skip("PlaywrightRasterizer not available")

        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")

        # Mock FontInfo to return a font pointing to our test file
        font = FontInfo(
            postscript_name="ArialMT",
            file=str(font_file),
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        mock_resolve.return_value = font

        svg_elem = ET.Element("svg", width="100", height="100")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "ArialMT")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})

        with patch.object(PlaywrightRasterizer, "from_string") as mock_from_string:
            mock_from_string.return_value = Image.new("RGBA", (100, 100))

            rasterizer = PlaywrightRasterizer()
            document.rasterize(rasterizer=rasterizer)

            # Should embed fonts in SVG with file:// URLs (not data URIs)
            assert mock_from_string.call_count == 1
            svg_arg = mock_from_string.call_args[0][0]
            assert "@font-face" in svg_arg
            assert "font-family: 'Arial'" in svg_arg
            # NEW: Uses file:// URLs instead of data URIs
            assert "file://" in svg_arg
            assert str(font_file) in svg_arg or font_file.as_posix() in svg_arg

    @requires_playwright
    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_rasterize_with_playwright_uses_file_urls(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """Test that PlaywrightRasterizer gets fonts embedded with file:// URLs."""

        # Create fake font file
        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT_DATA")

        # Mock FontInfo to return a font pointing to our test file
        font = FontInfo(
            postscript_name="ArialMT",
            file=str(font_file),
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        mock_resolve.return_value = font

        # Create SVG with text
        svg_elem = ET.Element("svg", width="100", height="100")
        text_elem = ET.SubElement(svg_elem, "text", x="10", y="50")
        text_elem.set("font-family", "ArialMT")  # Use PostScript name
        text_elem.text = "Hello World"

        document = SVGDocument(svg=svg_elem, images={})

        # Mock the rasterizer to capture the SVG string
        with patch.object(PlaywrightRasterizer, "from_string") as mock_from_string:
            mock_from_string.return_value = Image.new("RGBA", (100, 100))

            rasterizer = PlaywrightRasterizer()
            document.rasterize(rasterizer=rasterizer)

            # Verify the call
            assert mock_from_string.call_count == 1
            svg_arg = mock_from_string.call_args[0][0]

            # Should have @font-face with file:// URL
            assert "@font-face" in svg_arg
            assert "font-family: 'Arial'" in svg_arg

            # Should use file:// URL (NOT data URI)
            assert "file://" in svg_arg
            # Font file path should be in the URL
            assert str(font_file) in svg_arg or font_file.as_posix() in svg_arg

            # Should NOT have data URI
            assert "data:font" not in svg_arg
            assert "base64" not in svg_arg

    @requires_playwright
    def test_rasterize_with_playwright_file_url_fallback(self, tmp_path: Path) -> None:
        """Test graceful fallback when font file is missing."""

        # Create SVG with text
        svg_elem = ET.Element("svg", width="100", height="100")
        text_elem = ET.SubElement(svg_elem, "text", x="10", y="50")
        text_elem.set("font-family", "Arial")
        text_elem.text = "Hello"

        # Note: With the new architecture, fonts are resolved from SVG tree
        # This test verifies graceful fallback when font resolution fails
        # (no font file found for the font-family in the SVG)

        document = SVGDocument(svg=svg_elem, images={})

        with patch.object(PlaywrightRasterizer, "from_string") as mock_from_string:
            mock_from_string.return_value = Image.new("RGBA", (100, 100))

            rasterizer = PlaywrightRasterizer()

            # Should not raise an error (graceful fallback)
            document.rasterize(rasterizer=rasterizer)

            # Verify it still called rasterizer (without fonts)
            assert mock_from_string.call_count == 1
            svg_arg = mock_from_string.call_args[0][0]

            # Should NOT have @font-face (font failed)
            # SVG should still be valid and render
            assert isinstance(svg_arg, str)
            assert "<svg" in svg_arg


class TestPathTraversalProtection:
    """Tests for path traversal protection in image_prefix parameter."""

    def test_image_prefix_rejects_parent_directory_traversal(self) -> None:
        """Test that image_prefix with '..' raises ValueError."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="red")},
        )

        # Should raise ValueError for path traversal attempt
        with pytest.raises(
            ValueError,
            match=(
                "image_prefix cannot contain '\\.\\.' \\(path traversal not allowed\\)"
            ),
        ):
            document.tostring(image_prefix="../../../tmp/malicious")

    def test_image_prefix_rejects_absolute_path_without_svg_filepath(self) -> None:
        """Test that absolute image_prefix without svg_filepath raises ValueError."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="red")},
        )

        # Use platform-appropriate absolute path
        # On Windows: C:\tmp\absolute_path
        # On Unix: /tmp/absolute_path
        if sys.platform == "win32":
            absolute_path = "C:\\tmp\\absolute_path"
        else:
            absolute_path = "/tmp/absolute_path"

        # Should raise ValueError for absolute path in tostring case
        with pytest.raises(
            ValueError,
            match="image_prefix must be relative when svg_filepath is not provided",
        ):
            document.tostring(image_prefix=absolute_path)

    def test_image_prefix_allows_absolute_path_with_svg_filepath(
        self, tmp_path: Path
    ) -> None:
        """Test that absolute image_prefix is allowed when svg_filepath is provided."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="red")},
        )

        svg_file = tmp_path / "output.svg"
        image_dir = tmp_path / "images"
        image_dir.mkdir()

        # Should work with absolute path when svg_filepath is provided
        document.save(str(svg_file), image_prefix=str(image_dir / "img"))

        # Verify image was saved
        assert (image_dir / "img01.webp").exists()

    def test_image_prefix_allows_valid_relative_path(self, tmp_path: Path) -> None:
        """Test that valid relative paths work correctly."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="blue")},
        )

        svg_file = tmp_path / "output.svg"

        # Valid relative path should work
        document.save(str(svg_file), image_prefix="images/img")

        # Should save file successfully
        content = svg_file.read_text()
        # On Windows, paths use backslashes; on Unix, forward slashes
        assert "img01.webp" in content
        assert (tmp_path / "images" / "img01.webp").exists()

    def test_image_prefix_special_dot_case(self, tmp_path: Path) -> None:
        """Test that special '.' prefix still works."""
        svg_elem = ET.Element("svg")
        ET.SubElement(svg_elem, "image", id="image")

        document = SVGDocument(
            svg=svg_elem,
            images={"image": Image.new("RGB", (10, 10), color="green")},
        )

        svg_file = tmp_path / "output.svg"

        # Special '.' case should work
        document.save(str(svg_file), image_prefix=".")

        # Should save image with just counter, no prefix
        assert (tmp_path / "01.webp").exists()


class TestAppendCss:
    """Tests for SVGDocument.append_css method."""

    def test_append_css_basic(self) -> None:
        """Test basic CSS injection into SVG."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        css = "text { font-variant-east-asian: proportional-width; }"
        document.append_css(css)

        svg_string = document.tostring()
        assert "<style>" in svg_string
        assert "font-variant-east-asian: proportional-width" in svg_string

    def test_append_css_creates_style_element(self) -> None:
        """Test that append_css creates <style> element if not present."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        # Initially no style element
        style_elem = svg_elem.find("style")
        assert style_elem is None

        document.append_css("text { color: red; }")

        # Now style element should exist
        style_elem = svg_elem.find("style")
        assert style_elem is not None
        assert style_elem.text is not None
        assert "text { color: red; }" in style_elem.text

    def test_append_css_multiple_calls(self) -> None:
        """Test that multiple append_css calls accumulate CSS."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        document.append_css("text { color: red; }")
        document.append_css("rect { fill: blue; }")

        svg_string = document.tostring()
        assert "text { color: red; }" in svg_string
        assert "rect { fill: blue; }" in svg_string

    def test_append_css_idempotent(self) -> None:
        """Test that appending the same CSS multiple times is idempotent."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        css = "text { font-variant-east-asian: proportional-width; }"
        document.append_css(css)
        document.append_css(css)
        document.append_css(css)

        svg_string = document.tostring()
        # Should only appear once (duplicate detection)
        count = svg_string.count("font-variant-east-asian: proportional-width")
        assert count == 1

    def test_append_css_with_media_query(self) -> None:
        """Test appending CSS with media query."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        css = "@media print { .no-print { display: none; } }"
        document.append_css(css)

        svg_string = document.tostring()
        assert "@media print" in svg_string
        assert "no-print" in svg_string

    @patch("psd2svg.core.font_utils.FontInfo.resolve")
    def test_append_css_with_font_embedding(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """Test that append_css works alongside font embedding."""
        font_file = tmp_path / "arial.ttf"
        font_file.write_bytes(b"FAKE_FONT")

        # Mock FontInfo to return a font pointing to our test file
        font = FontInfo(
            postscript_name="ArialMT",
            file=str(font_file),
            family="Arial",
            style="Regular",
            weight=80.0,
        )
        mock_resolve.return_value = font

        svg_elem = ET.Element("svg", width="100", height="100")
        # Add text element with PostScript font name
        text_elem = ET.SubElement(svg_elem, "text")
        text_elem.set("font-family", "ArialMT")
        text_elem.text = "Test"

        document = SVGDocument(svg=svg_elem, images={})

        # Add custom CSS
        document.append_css("text { font-variant-east-asian: proportional-width; }")

        # Get string with font embedding
        with patch("psd2svg.core.font_utils.encode_font_data_uri") as mock_encode:
            mock_encode.return_value = "data:font/ttf;base64,MOCKDATA"
            svg_string = document.tostring(embed_fonts=True)

        # Should contain both custom CSS and font-face
        assert "font-variant-east-asian: proportional-width" in svg_string
        assert "@font-face" in svg_string
        assert "font-family: 'Arial'" in svg_string

    def test_append_css_empty_string(self) -> None:
        """Test that appending empty CSS string doesn't cause issues."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        document.append_css("")

        svg_string = document.tostring()
        # Should work without errors (may or may not create style element)
        assert "<svg" in svg_string

    def test_append_css_with_save(self, tmp_path: Path) -> None:
        """Test that append_css works with save method."""
        svg_elem = ET.Element("svg", width="100", height="100")
        document = SVGDocument(svg=svg_elem, images={})

        document.append_css("text { color: green; }")

        output_file = tmp_path / "output.svg"
        document.save(str(output_file))

        # Read file and verify CSS is present
        svg_content = output_file.read_text()
        assert "text { color: green; }" in svg_content
