"""Tests for ResvgRasterizer."""

import logging
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from psd2svg.rasterizer import ResvgRasterizer


@pytest.fixture
def simple_svg() -> str:
    """Simple SVG for basic testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
    <rect x="10" y="10" width="80" height="80" fill="red"/>
</svg>"""


@pytest.fixture
def vertical_text_svg() -> str:
    """SVG with vertical text using SVG features."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
    <text x="100" y="50" writing-mode="vertical-rl"
          font-family="sans-serif" font-size="20" fill="black">
        Text
    </text>
</svg>"""


@pytest.fixture
def svg_with_viewbox_only() -> str:
    """SVG with only viewBox (no width/height attributes)."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 150">
    <circle cx="100" cy="75" r="50" fill="blue"/>
</svg>"""


@pytest.fixture
def svg_with_gradient() -> str:
    """SVG with gradient fill."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
    <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:rgb(255,255,0);stop-opacity:1" />
            <stop offset="100%" style="stop-color:rgb(255,0,0);stop-opacity:1" />
        </linearGradient>
    </defs>
    <rect width="200" height="200" fill="url(#grad1)" />
</svg>"""


@pytest.fixture
def svg_with_embedded_image() -> str:
    """SVG with embedded image (data URI)."""
    # 1x1 red pixel PNG as base64 data URI
    base64_data = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8Dw"
        "HwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="100" height="100" viewBox="0 0 100 100">
    <image x="10" y="10" width="80" height="80"
           xlink:href="data:image/png;base64,{base64_data}" />
</svg>"""


def test_rasterizer_basic(simple_svg: str) -> None:
    """Test basic rasterization functionality."""
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(simple_svg)

    # Verify image properties
    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (100, 100)


def test_rasterizer_default_dpi(simple_svg: str) -> None:
    """Test rasterization with default DPI (0 = 96 DPI)."""
    rasterizer = ResvgRasterizer()
    image = rasterizer.from_string(simple_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (100, 100)


def test_rasterizer_from_file(simple_svg: str) -> None:
    """Test rasterization from file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".svg", delete=False, encoding="utf-8"
    ) as f:
        f.write(simple_svg)
        svg_path = f.name

    try:
        rasterizer = ResvgRasterizer(dpi=96)
        image = rasterizer.from_file(svg_path)

        assert isinstance(image, Image.Image)
        assert image.mode == "RGBA"
        assert image.size == (100, 100)
    finally:
        os.unlink(svg_path)


def test_rasterizer_dpi_scaling() -> None:
    """Test DPI scaling with physical dimensions (e.g., inches)."""
    # SVG with physical dimensions (1 inch x 1 inch)
    svg_inches = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1in" height="1in" viewBox="0 0 100 100">
    <rect x="10" y="10" width="80" height="80" fill="red"/>
</svg>"""

    rasterizer_96 = ResvgRasterizer(dpi=96)
    image_96 = rasterizer_96.from_string(svg_inches)

    rasterizer_192 = ResvgRasterizer(dpi=192)
    image_192 = rasterizer_192.from_string(svg_inches)

    # 1 inch at 96 DPI = 96 pixels, at 192 DPI = 192 pixels
    assert image_96.size == (96, 96)
    assert image_192.size == (192, 192)


def test_rasterizer_dpi_zero_renders_physical_units() -> None:
    """Test that dpi=0 resolves physical units at 96 DPI rather than at 0."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1in" height="1in">'
        '<rect width="1in" height="1in" fill="red"/></svg>'
    )

    assert ResvgRasterizer(dpi=0).from_string(svg).size == (96, 96)


def test_rasterizer_dpi_does_not_scale_twice() -> None:
    """Test that DPI scales the rendering, not the physical units within it."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        '<rect width="1in" height="1in" fill="red"/></svg>'
    )

    image = ResvgRasterizer(dpi=192).from_string(svg)

    # The inch square stays an inch: 96 CSS pixels, rendered at a 2x scale
    assert image.size == (400, 400)
    assert image.getchannel("A").getbbox() == (0, 0, 192, 192)


def test_rasterizer_dpi_rounds_half_up() -> None:
    """Test that a scale landing on a half pixel rounds up, as a browser does."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<rect width="100" height="100" fill="red"/></svg>'
    )

    # 100 x 300/96 is exactly 312.5
    assert ResvgRasterizer(dpi=300).from_string(svg).size == (313, 313)


def test_rasterizer_dpi_scales_pixel_dimensions() -> None:
    """Test that DPI scales a document sized in pixels, not only in physical units."""
    svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" viewBox="0 0 100 50">
    <rect x="0" y="0" width="50" height="50" fill="red"/>
</svg>"""

    assert ResvgRasterizer(dpi=0).from_string(svg).size == (100, 50)
    assert ResvgRasterizer(dpi=96).from_string(svg).size == (100, 50)
    assert ResvgRasterizer(dpi=144).from_string(svg).size == (150, 75)
    assert ResvgRasterizer(dpi=192).from_string(svg).size == (200, 100)

    # The content scales with the canvas: the rect still covers the left half
    image = ResvgRasterizer(dpi=192).from_string(svg)
    assert image.getchannel("A").getbbox() == (0, 0, 100, 100)


def test_rasterizer_dpi_scales_without_viewbox() -> None:
    """Test that DPI scales a document that has no viewBox."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        '<rect x="0" y="0" width="50" height="50" fill="red"/></svg>'
    )

    image = ResvgRasterizer(dpi=192).from_string(svg)

    assert image.size == (200, 100)
    assert image.getchannel("A").getbbox() == (0, 0, 100, 100)


@pytest.mark.parametrize(
    ("root_size", "expected_96", "expected_192"),
    [
        ('width="200"', (200, 100), (400, 200)),
        ('height="200"', (100, 200), (200, 400)),
        ('width="50%" height="50%"', (50, 50), (100, 100)),
        ('width="200" height="50%"', (200, 50), (400, 100)),
    ],
)
def test_rasterizer_dpi_scales_partially_sized_root(
    root_size: str, expected_96: tuple[int, int], expected_192: tuple[int, int]
) -> None:
    """Test that DPI scales a root that sizes only one axis, or sizes it relatively.

    Each axis resolves on its own, so the scale stays dpi / 96 rather than
    being skewed by the viewBox of the axis that is left out.
    """
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" {root_size}'
        ' viewBox="0 0 100 100"><rect width="100" height="100" fill="red"/></svg>'
    )

    assert ResvgRasterizer(dpi=96).from_string(svg).size == expected_96
    assert ResvgRasterizer(dpi=192).from_string(svg).size == expected_192


def test_rasterizer_dpi_oversized_document(caplog: pytest.LogCaptureFixture) -> None:
    """Test that an unrenderable canvas still fails as a ValueError."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1e30" height="1e30">'
        '<rect width="10" height="10" fill="red"/></svg>'
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="Failed to rasterize SVG content"):
            ResvgRasterizer(dpi=192).from_string(svg)

    assert "exceed" in caplog.text


def test_rasterizer_dpi_non_finite_dimensions() -> None:
    """Test that a non-finite root size renders unscaled instead of overflowing."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1e400" height="1e400">'
        '<rect width="10" height="10" fill="red"/></svg>'
    )

    assert ResvgRasterizer(dpi=192).from_string(svg).size == (10, 10)


def test_rasterizer_dpi_overflows_when_scaled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a finite root size that only overflows once the scale is applied."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1e308" height="1e308">'
        '<rect width="10" height="10" fill="red"/></svg>'
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="Failed to rasterize SVG content"):
            ResvgRasterizer(dpi=300).from_string(svg)

    assert "exceed" in caplog.text


def test_rasterizer_dpi_scales_viewbox_only() -> None:
    """Test that DPI scales a document sized by its viewBox alone."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 150">'
        '<rect width="200" height="150" fill="blue"/></svg>'
    )

    assert ResvgRasterizer(dpi=96).from_string(svg).size == (200, 150)
    assert ResvgRasterizer(dpi=192).from_string(svg).size == (400, 300)


def test_rasterizer_dpi_scales_file(tmp_path: Path) -> None:
    """Test that from_file() honours DPI the same way from_string() does."""
    svg_path = tmp_path / "input.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"'
        ' viewBox="0 0 100 50"><rect width="100" height="50" fill="red"/></svg>',
        encoding="utf-8",
    )

    assert ResvgRasterizer(dpi=96).from_file(str(svg_path)).size == (100, 50)
    assert ResvgRasterizer(dpi=192).from_file(str(svg_path)).size == (200, 100)


def test_rasterizer_dpi_unknown_dimensions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that an unsizable document renders at 96 DPI with a warning."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">'
        '<rect width="100" height="100" fill="red"/></svg>'
    )

    with caplog.at_level(logging.WARNING):
        image = ResvgRasterizer(dpi=192).from_string(svg)

    assert image.size == (100, 100)
    assert "Could not determine SVG dimensions" in caplog.text


def test_rasterizer_high_dpi() -> None:
    """Test high DPI rendering (print quality)."""
    # SVG with physical dimensions for DPI testing
    svg_inches = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1in" height="1in" viewBox="0 0 100 100">
    <rect x="10" y="10" width="80" height="80" fill="red"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=300)
    image = rasterizer.from_string(svg_inches)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    # 1 inch at 300 DPI = 300 pixels
    assert image.size == (300, 300)


def test_rasterizer_vertical_text(vertical_text_svg: str) -> None:
    """Test rendering of vertical text.

    Note: resvg may not support all vertical text features like
    text-orientation: upright, but it should render the SVG without errors.
    """
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(vertical_text_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (200, 200)


def test_rasterizer_viewbox_only(svg_with_viewbox_only: str) -> None:
    """Test SVG with only viewBox (no width/height attributes)."""
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(svg_with_viewbox_only)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    # Should use viewBox dimensions
    assert image.size == (200, 150)


def test_rasterizer_gradient(svg_with_gradient: str) -> None:
    """Test rendering of gradients."""
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(svg_with_gradient)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (200, 200)

    # Check that gradient produces varying colors (not solid)
    pixel_tl = image.getpixel((10, 10))
    pixel_br = image.getpixel((190, 190))

    assert isinstance(pixel_tl, tuple)
    assert isinstance(pixel_br, tuple)

    # Colors should be different at gradient endpoints
    assert pixel_tl[:3] != pixel_br[:3]


def test_rasterizer_embedded_image(svg_with_embedded_image: str) -> None:
    """Test rendering of SVG with embedded images."""
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(svg_with_embedded_image)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (100, 100)


def test_rasterizer_transparency(simple_svg: str) -> None:
    """Test that transparency is preserved."""
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(simple_svg)

    # Image should have alpha channel
    assert image.mode == "RGBA"

    # Check that corners are transparent (outside the red rectangle)
    # Red rectangle is at (10, 10) to (90, 90)
    pixel = image.getpixel((5, 5))  # Top-left corner
    # Pixel should be a tuple in RGBA mode
    assert isinstance(pixel, tuple)
    assert pixel[3] == 0  # Alpha should be 0 (transparent)


def test_rasterizer_bytes_input(simple_svg: str) -> None:
    """Test rasterization with bytes input."""
    svg_bytes = simple_svg.encode("utf-8")

    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(svg_bytes)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (100, 100)


def test_rasterizer_string_input(simple_svg: str) -> None:
    """Test rasterization with string input."""
    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(simple_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (100, 100)


def test_rasterizer_reuse() -> None:
    """Test that rasterizer can be reused for multiple renders."""
    svg1 = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50">'
        '<rect width="50" height="50" fill="red"/></svg>'
    )
    svg2 = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<circle cx="50" cy="50" r="40" fill="blue"/></svg>'
    )

    rasterizer = ResvgRasterizer(dpi=96)
    image1 = rasterizer.from_string(svg1)
    image2 = rasterizer.from_string(svg2)

    assert image1.size == (50, 50)
    assert image2.size == (100, 100)


def test_rasterizer_with_font_files(simple_svg: str) -> None:
    """Test rasterization with font_files parameter."""
    rasterizer = ResvgRasterizer(dpi=96)

    # Test with empty font list (should not error)
    image = rasterizer.from_string(simple_svg, font_files=[])
    assert isinstance(image, Image.Image)
    assert image.size == (100, 100)

    # Test with None font list (should not error)
    image = rasterizer.from_string(simple_svg, font_files=None)
    assert isinstance(image, Image.Image)
    assert image.size == (100, 100)


# Note: As of resvg-py 0.2.5, malformed SVG, missing files, and empty SVG
# properly raise Python exceptions (ValueError) instead of crashing with SIGABRT.
# Tests for these edge cases are included below.


def test_rasterizer_malformed_svg() -> None:
    """Test that malformed SVG raises ValueError instead of crashing.

    Note: This test requires resvg-py >= 0.2.5. Earlier versions would
    crash (SIGABRT) instead of raising exceptions.
    """
    malformed_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
    <rect x="10" y="10" width="80" height=bad_value fill="red"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    with pytest.raises(ValueError, match="Failed to rasterize SVG content"):
        rasterizer.from_string(malformed_svg)


@pytest.mark.parametrize("dpi", [96, 300])
def test_rasterizer_missing_file(dpi: int) -> None:
    """Test that missing SVG file raises ValueError instead of crashing.

    Note: This test requires resvg-py >= 0.2.5. Earlier versions would
    crash (SIGABRT) instead of raising exceptions. The library raises
    ValueError for missing files rather than FileNotFoundError.
    """
    rasterizer = ResvgRasterizer(dpi=dpi)
    nonexistent_path = "/nonexistent/path/to/file.svg"

    with pytest.raises(ValueError, match="Failed to rasterize SVG file"):
        rasterizer.from_file(nonexistent_path)


def test_rasterizer_empty_svg() -> None:
    """Test that empty/invalid SVG raises ValueError instead of crashing.

    Note: This test requires resvg-py >= 0.2.5. Earlier versions would
    crash (SIGABRT) instead of raising exceptions.
    """
    empty_svg = ""

    rasterizer = ResvgRasterizer(dpi=96)
    with pytest.raises(ValueError, match="Failed to rasterize SVG content"):
        rasterizer.from_string(empty_svg)


def test_rasterizer_corrupted_svg_structure() -> None:
    """Test that severely corrupted SVG raises ValueError.

    Tests SVG with mismatched tags and invalid structure.
    """
    corrupted_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
    <rect x="10" y="10" width="80" height="80" fill="red">
    <circle cx="50" cy="50" r="30"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    with pytest.raises(ValueError, match="Failed to rasterize SVG content"):
        rasterizer.from_string(corrupted_svg)


def test_rasterizer_large_svg() -> None:
    """Test rendering of large SVG dimensions."""
    large_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000"
     viewBox="0 0 1000 1000">
    <rect x="100" y="100" width="800" height="800" fill="green"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(large_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (1000, 1000)


def test_rasterizer_complex_shapes() -> None:
    """Test rendering of complex path shapes."""
    complex_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
    <path d="M 100 10 L 40 198 L 190 78 L 10 78 L 160 198 Z"
          fill="gold" stroke="orange" stroke-width="2"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(complex_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (200, 200)


def test_rasterizer_with_transforms() -> None:
    """Test rendering of SVG with transforms."""
    transform_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
    <rect x="50" y="50" width="50" height="50" fill="purple"
          transform="rotate(45 100 100)"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(transform_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (200, 200)


def test_rasterizer_with_opacity() -> None:
    """Test rendering of semi-transparent elements."""
    opacity_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
    <rect x="50" y="50" width="100" height="100" fill="red" opacity="0.5"/>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(opacity_svg)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"

    # Check that opacity is applied (pixel should be semi-transparent)
    pixel = image.getpixel((100, 100))
    assert isinstance(pixel, tuple)
    assert 0 < pixel[3] < 255  # Alpha should be between 0 and 255


def test_rasterizer_composite_background() -> None:
    """Test that _composite_background is applied correctly."""
    rasterizer = ResvgRasterizer(dpi=96)

    # Create a simple test image
    test_image = Image.new("RGBA", (100, 100), (255, 0, 0, 128))

    # Apply composite background
    result = rasterizer._composite_background(test_image)

    assert result.mode == "RGBA"
    assert result.size == (100, 100)


def test_rasterizer_from_string_optimized() -> None:
    """Test that from_string uses optimized implementation.

    Not via temp file.
    """
    simple_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<rect width="100" height="100" fill="blue"/></svg>'
    )

    rasterizer = ResvgRasterizer(dpi=96)

    # Both bytes and string should work without temp files
    image_str = rasterizer.from_string(simple_svg)
    image_bytes = rasterizer.from_string(simple_svg.encode("utf-8"))

    assert image_str.size == (100, 100)
    assert image_bytes.size == (100, 100)


def test_rasterizer_ignores_foreign_object() -> None:
    """Test that resvg ignores foreignObject elements.

    When a foreignObject contains text, resvg should not render it,
    resulting in a flat/empty image (all pixels transparent or uniform).
    This verifies that foreignObject is not supported by resvg/resvg-py.
    """
    # SVG with only a foreignObject containing text
    svg_with_foreign_object = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
    <foreignObject x="10" y="10" width="180" height="80">
        <div xmlns="http://www.w3.org/1999/xhtml" style="font-size: 20px; color: red;">
            This text should not be rendered by resvg
        </div>
    </foreignObject>
</svg>"""

    rasterizer = ResvgRasterizer(dpi=96)
    image = rasterizer.from_string(svg_with_foreign_object)

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (200, 100)

    # Check that all pixels are transparent (alpha = 0)
    # If resvg rendered the foreignObject text, there would be non-transparent pixels
    pixels = list(image.getdata())
    all_transparent = all(pixel[3] == 0 for pixel in pixels)

    assert all_transparent, (
        "resvg should ignore foreignObject elements, "
        "but some pixels are not transparent (foreignObject may have been rendered)"
    )


class TestFontFilePathValidation:
    """Tests for font file path validation in ResvgRasterizer."""

    def test_extract_font_file_paths_valid(self, tmp_path: Path) -> None:
        """Test extraction of valid font file paths."""
        # Create a dummy font file
        font_file = tmp_path / "test.ttf"
        font_file.write_bytes(b"FAKE_FONT_DATA")

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg">
            <style>
            @font-face {{
                font-family: 'TestFont';
                src: url("file://{font_file}");
            }}
            </style>
        </svg>
        """

        paths = ResvgRasterizer._extract_font_file_paths(svg_content)
        assert len(paths) == 1
        assert paths[0] == str(font_file)

    def test_extract_font_file_paths_invalid_extension(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that invalid font extensions are rejected."""
        # Create a non-font file
        non_font_file = tmp_path / "passwd"
        non_font_file.write_text("root:x:0:0:root:/root:/bin/bash")

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg">
            <style>
            @font-face {{
                font-family: 'Evil';
                src: url("file://{non_font_file}");
            }}
            </style>
        </svg>
        """

        paths = ResvgRasterizer._extract_font_file_paths(svg_content)
        assert len(paths) == 0
        assert "Skipping invalid font file extension" in caplog.text

    def test_extract_font_file_paths_nonexistent_file(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that non-existent font files are rejected."""
        svg_content = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <style>
            @font-face {
                font-family: 'Missing';
                src: url("file:///nonexistent/path/font.ttf");
            }
            </style>
        </svg>
        """

        paths = ResvgRasterizer._extract_font_file_paths(svg_content)
        assert len(paths) == 0
        assert "Skipping non-existent font file" in caplog.text

    def test_extract_font_file_paths_multiple_fonts(self, tmp_path: Path) -> None:
        """Test extraction of multiple valid font files."""
        # Create multiple font files
        font1 = tmp_path / "font1.ttf"
        font1.write_bytes(b"FAKE_FONT_1")
        font2 = tmp_path / "font2.otf"
        font2.write_bytes(b"FAKE_FONT_2")
        font3 = tmp_path / "font3.woff"
        font3.write_bytes(b"FAKE_FONT_3")

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg">
            <style>
            @font-face {{
                font-family: 'Font1';
                src: url("file://{font1}");
            }}
            @font-face {{
                font-family: 'Font2';
                src: url("file://{font2}");
            }}
            @font-face {{
                font-family: 'Font3';
                src: url("file://{font3}");
            }}
            </style>
        </svg>
        """

        paths = ResvgRasterizer._extract_font_file_paths(svg_content)
        assert len(paths) == 3
        assert str(font1) in paths
        assert str(font2) in paths
        assert str(font3) in paths

    def test_extract_font_file_paths_mixed_valid_invalid(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test extraction with mix of valid and invalid paths."""
        # Create one valid font and one invalid file
        valid_font = tmp_path / "valid.ttf"
        valid_font.write_bytes(b"FAKE_FONT")
        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("not a font")

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg">
            <style>
            @font-face {{
                font-family: 'ValidFont';
                src: url("file://{valid_font}");
            }}
            @font-face {{
                font-family: 'InvalidFont';
                src: url("file://{invalid_file}");
            }}
            @font-face {{
                font-family: 'MissingFont';
                src: url("file:///nonexistent/font.otf");
            }}
            </style>
        </svg>
        """

        paths = ResvgRasterizer._extract_font_file_paths(svg_content)
        # Only valid font should be extracted
        assert len(paths) == 1
        assert paths[0] == str(valid_font)
        assert "Skipping invalid font file extension" in caplog.text
        assert "Skipping non-existent font file" in caplog.text

    def test_extract_font_file_paths_all_extensions(self, tmp_path: Path) -> None:
        """Test that all valid font extensions are accepted."""
        valid_extensions = [".ttf", ".otf", ".woff", ".woff2", ".ttc"]
        font_files = []

        svg_parts = ['<svg xmlns="http://www.w3.org/2000/svg"><style>']

        for ext in valid_extensions:
            font_file = tmp_path / f"font{ext}"
            font_file.write_bytes(b"FAKE_FONT")
            font_files.append(font_file)
            svg_parts.append(
                f'@font-face {{ font-family: "Font{ext}"; '
                f'src: url("file://{font_file}"); }}'
            )

        svg_parts.append("</style></svg>")
        svg_content = "\n".join(svg_parts)

        paths = ResvgRasterizer._extract_font_file_paths(svg_content)
        assert len(paths) == len(valid_extensions)
        for font_file in font_files:
            assert str(font_file) in paths
