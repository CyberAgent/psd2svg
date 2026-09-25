"""Tests for PlaywrightRasterizer."""

import asyncio
import os
import tempfile
from typing import Any, NoReturn

import pytest
from PIL import Image

from psd2svg.rasterizer import PlaywrightRasterizer
from tests.conftest import requires_playwright


def test_is_available() -> None:
    """Test that is_available() correctly detects playwright availability.

    This test runs in all environments to verify that is_available()
    returns the correct value based on whether playwright is installed.
    """
    has_pw = PlaywrightRasterizer.is_available()

    # Try to actually import playwright to verify is_available() is correct
    try:
        import playwright.sync_api  # noqa: F401, PLC0415

        # If import succeeded, is_available() should return True
        assert has_pw is True, (
            "is_available() returned False but playwright is installed"
        )
    except ImportError:
        # If import failed, is_available() should return False
        assert has_pw is False, (
            "is_available() returned True but playwright is not installed"
        )


@pytest.fixture
def simple_svg() -> str:
    """Simple SVG for basic testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
    <rect x="10" y="10" width="80" height="80" fill="red"/>
</svg>"""


@pytest.fixture
def vertical_text_svg() -> str:
    """SVG with vertical text using SVG 2.0 features."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
    <text x="100" y="50" writing-mode="vertical-rl" text-orientation="upright"
          font-family="sans-serif" font-size="20" fill="black">
        縦書き
    </text>
</svg>"""


@pytest.fixture
def svg_with_viewbox_only() -> str:
    """SVG with only viewBox (no width/height attributes)."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 150">
    <circle cx="100" cy="75" r="50" fill="blue"/>
</svg>"""


@requires_playwright
def test_rasterizer_basic(simple_svg: str) -> None:
    """Test basic rasterization functionality."""
    rasterizer = PlaywrightRasterizer(dpi=96)

    try:
        image = rasterizer.from_string(simple_svg)

        # Verify image properties
        assert isinstance(image, Image.Image)
        assert image.mode == "RGBA"
        assert image.size == (100, 100)

    finally:
        rasterizer.close()


@requires_playwright
def test_rasterizer_from_file(simple_svg: str) -> None:
    """Test rasterization from file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".svg", delete=False, encoding="utf-8"
    ) as f:
        f.write(simple_svg)
        svg_path = f.name

    try:
        rasterizer = PlaywrightRasterizer(dpi=96)
        try:
            image = rasterizer.from_file(svg_path)

            assert isinstance(image, Image.Image)
            assert image.mode == "RGBA"
            assert image.size == (100, 100)

        finally:
            rasterizer.close()
    finally:
        os.unlink(svg_path)


@requires_playwright
def test_rasterizer_context_manager(simple_svg: str) -> None:
    """Test rasterizer as context manager."""
    with PlaywrightRasterizer(dpi=96) as rasterizer:
        image = rasterizer.from_string(simple_svg)

        assert isinstance(image, Image.Image)
        assert image.mode == "RGBA"


@requires_playwright
def test_rasterizer_dpi_scaling(simple_svg: str) -> None:
    """Test DPI scaling scales the content, not just the canvas."""
    with PlaywrightRasterizer(dpi=96) as rasterizer_96:
        image_96 = rasterizer_96.from_string(simple_svg)

    with PlaywrightRasterizer(dpi=192) as rasterizer_192:
        image_192 = rasterizer_192.from_string(simple_svg)

    # 192 DPI should produce 2x resolution
    assert image_96.size == (100, 100)
    assert image_192.size == (200, 200)

    # The rect drawn at (10, 10)-(90, 90) must scale with the canvas
    assert image_96.getchannel("A").getbbox() == (10, 10, 90, 90)
    assert image_192.getchannel("A").getbbox() == (20, 20, 180, 180)


@requires_playwright
def test_rasterizer_zero_dpi(simple_svg: str) -> None:
    """Test that dpi=0 renders at 96 DPI rather than collapsing the scale."""
    with PlaywrightRasterizer(dpi=0) as rasterizer:
        image = rasterizer.from_string(simple_svg)

    assert image.size == (100, 100)
    assert image.getchannel("A").getbbox() == (10, 10, 90, 90)


@requires_playwright
def test_rasterizer_vertical_text(vertical_text_svg: str) -> None:
    """Test rendering of vertical text with SVG 2.0 features.

    This is a key use case for PlaywrightRasterizer, as resvg doesn't
    support text-orientation: upright.
    """
    with PlaywrightRasterizer(dpi=96) as rasterizer:
        image = rasterizer.from_string(vertical_text_svg)

        assert isinstance(image, Image.Image)
        assert image.mode == "RGBA"
        assert image.size == (200, 200)


@requires_playwright
def test_rasterizer_viewbox_only(svg_with_viewbox_only: str) -> None:
    """Test SVG with only viewBox (no width/height attributes)."""
    with PlaywrightRasterizer(dpi=96) as rasterizer:
        image = rasterizer.from_string(svg_with_viewbox_only)

        assert isinstance(image, Image.Image)
        assert image.mode == "RGBA"
        # Should use viewBox dimensions
        assert image.size == (200, 150)


@requires_playwright
@pytest.mark.parametrize(
    "browser_type",
    ["chromium", "firefox", "webkit"],
)
def test_rasterizer_browser_types(
    simple_svg: str,
    browser_type: str,  # type: ignore[misc]
) -> None:
    """Test different browser types."""
    # Note: This test may fail if browsers aren't installed
    # Run: uv run playwright install to install all browsers
    try:
        # Use type ignore for Literal type compatibility
        with PlaywrightRasterizer(dpi=96, browser_type=browser_type) as rasterizer:  # type: ignore[arg-type]
            image = rasterizer.from_string(simple_svg)

            assert isinstance(image, Image.Image)
            assert image.mode == "RGBA"
            assert image.size == (100, 100)
    except Exception as e:
        # Skip if browser not installed
        pytest.skip(f"{browser_type} not installed: {e}")


@requires_playwright
def test_rasterizer_transparency(simple_svg: str) -> None:
    """Test that transparency is preserved."""
    with PlaywrightRasterizer(dpi=96) as rasterizer:
        image = rasterizer.from_string(simple_svg)

        # Image should have alpha channel
        assert image.mode == "RGBA"

        # Check that corners are transparent (outside the red rectangle)
        # Red rectangle is at (10, 10) to (90, 90)
        pixel = image.getpixel((5, 5))  # Top-left corner
        # Pixel should be a tuple in RGBA mode
        assert isinstance(pixel, tuple)
        assert pixel[3] == 0  # Alpha should be 0 (transparent)


@requires_playwright
def test_rasterizer_bytes_input(simple_svg: str) -> None:
    """Test rasterization with bytes input."""
    svg_bytes = simple_svg.encode("utf-8")

    with PlaywrightRasterizer(dpi=96) as rasterizer:
        image = rasterizer.from_string(svg_bytes)

        assert isinstance(image, Image.Image)
        assert image.mode == "RGBA"
        assert image.size == (100, 100)


@requires_playwright
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

    with PlaywrightRasterizer(dpi=96) as rasterizer:
        image1 = rasterizer.from_string(svg1)
        image2 = rasterizer.from_string(svg2)

        assert image1.size == (50, 50)
        assert image2.size == (100, 100)


@requires_playwright
def test_rasterizer_invalid_svg() -> None:
    """Test handling of invalid SVG content."""
    invalid_svg = "<svg>invalid</not-svg>"

    with PlaywrightRasterizer(dpi=96) as rasterizer:
        with pytest.raises(ValueError, match="Could not determine SVG dimensions"):
            rasterizer.from_string(invalid_svg)


@requires_playwright
def test_rasterizer_missing_file() -> None:
    """Test handling of missing file."""
    with PlaywrightRasterizer(dpi=96) as rasterizer:
        with pytest.raises(FileNotFoundError):
            rasterizer.from_file("/nonexistent/file.svg")


@requires_playwright
def test_rasterizer_in_async_context(simple_svg: str) -> None:
    """Test that PlaywrightRasterizer works inside an asyncio event loop.

    This simulates usage in Jupyter notebooks or other async environments
    where an event loop is already running.
    """

    async def test_async() -> None:
        """Test rasterization inside an async context."""
        with PlaywrightRasterizer(dpi=96) as rasterizer:
            image = rasterizer.from_string(simple_svg)

            assert isinstance(image, Image.Image)
            assert image.mode == "RGBA"
            assert image.size == (100, 100)

    # Run inside asyncio event loop (simulates Jupyter environment)
    asyncio.run(test_async())


@requires_playwright
def test_rasterizer_does_not_resize_viewport(
    simple_svg: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that rasterization never calls the unbounded set_viewport_size()."""
    from playwright.sync_api import Page  # noqa: PLC0415

    def fail(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("set_viewport_size() must not be called")

    monkeypatch.setattr(Page, "set_viewport_size", fail)

    with PlaywrightRasterizer(dpi=192) as rasterizer:
        image = rasterizer.from_string(simple_svg)

    assert image.size == (200, 200)


@requires_playwright
def test_rasterizer_closes_page_when_rendering_fails(
    simple_svg: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a failed render propagates and still closes the page."""
    from playwright.sync_api import Page  # noqa: PLC0415
    from playwright.sync_api import (  # noqa: PLC0415
        TimeoutError as PlaywrightTimeoutError,
    )

    closed: list[Page] = []
    real_close = Page.close

    def fail(*args: object, **kwargs: object) -> NoReturn:
        raise PlaywrightTimeoutError("Page.screenshot: Timeout 30000ms exceeded.")

    def spy_close(self: Page, **kwargs: Any) -> None:
        closed.append(self)
        real_close(self, **kwargs)

    monkeypatch.setattr(Page, "screenshot", fail)
    monkeypatch.setattr(Page, "close", spy_close)

    with PlaywrightRasterizer(dpi=96) as rasterizer:
        with pytest.raises(PlaywrightTimeoutError):
            rasterizer.from_string(simple_svg)

    assert closed, "page.close() was not called on the failure path"
