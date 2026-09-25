"""Playwright-based rasterizer module.

This module provides SVG rasterization using headless browser automation via
Playwright, offering accurate rendering of SVG 2.0 features and vertical text
that may not be supported by other rasterizers.
"""

import asyncio
import concurrent.futures
import logging
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal, Union

from PIL import Image

from .base_rasterizer import BaseRasterizer

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Playwright, ViewportSize

logger = logging.getLogger(__name__)


class PlaywrightRasterizer(BaseRasterizer):
    """Browser-based SVG rasterizer using Playwright.

    This rasterizer uses Playwright's headless Chromium to render SVG documents,
    providing accurate support for advanced SVG features including vertical text,
    text-orientation, dominant-baseline, and other SVG 2.0 features that may not
    be supported by native rasterizers.

    Note:
        Requires Playwright to be installed: `uv sync --group browser`
        After installation, run: `uv run playwright install chromium`

    Advantages:
        - Full SVG 2.0 feature support
        - Accurate vertical text rendering
        - Matches browser rendering exactly

    Disadvantages:
        - Slower than native rasterizers (browser startup overhead)
        - Requires Chromium binary (~300MB)
        - More resource intensive

    Example:
        >>> rasterizer = PlaywrightRasterizer(dpi=96)
        >>> image = rasterizer.from_file('input.svg')
        >>> image.save('output.png')

        >>> # Use as context manager for automatic cleanup
        >>> with PlaywrightRasterizer(dpi=96) as rasterizer:
        ...     image = rasterizer.from_string('<svg>...</svg>')
        ...     image.save('output.png')
    """

    @classmethod
    def is_available(cls) -> bool:
        """Check if Playwright is available.

        Returns:
            True if Playwright is installed and can be used, False otherwise.

        Example:
            >>> if PlaywrightRasterizer.is_available():
            ...     rasterizer = PlaywrightRasterizer()
            ... else:
            ...     print("Playwright not available")
        """
        try:
            import playwright.sync_api  # noqa: F401, PLC0415

            return True
        except ImportError:
            return False

    def __init__(
        self,
        dpi: int = 96,
        browser_type: Literal["chromium", "firefox", "webkit"] = "chromium",
    ) -> None:
        """Initialize the Playwright rasterizer.

        Args:
            dpi: Dots per inch for rendering. Higher values produce larger,
                higher resolution images (e.g., 300 DPI for print quality).
                Default is 96 DPI (standard screen resolution); 0 also means
                96 DPI.
            browser_type: Browser engine to use. Options are:
                - "chromium": Best SVG support (recommended)
                - "firefox": Good compatibility
                - "webkit": Safari engine
                Default is "chromium".
        """
        self.dpi = dpi
        self.browser_type = browser_type
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._executor: Any = None  # ThreadPoolExecutor if running in event loop
        self._in_event_loop = False

    def _ensure_browser(self) -> None:
        """Lazily initialize the browser instance.

        This method starts Playwright and launches the browser only when needed,
        avoiding startup overhead if the rasterizer is created but not used.

        Raises:
            ImportError: If Playwright is not installed.
            RuntimeError: If browser launch fails.
        """
        if self._browser is not None:
            return

        try:
            # Optional dependency - only available when installed
            from playwright.sync_api import sync_playwright  # noqa: F401, PLC0415
        except ImportError as e:
            raise ImportError(
                "Playwright is required for PlaywrightRasterizer. "
                "Install with: uv sync --group browser && "
                "uv run playwright install chromium"
            ) from e

        # Check if we're in an asyncio event loop (e.g., Jupyter notebook)
        try:
            asyncio.get_running_loop()
            # We're inside an event loop - need to run sync code in a dedicated thread
            logger.debug(
                f"Starting Playwright with {self.browser_type} browser "
                "(running in dedicated thread due to existing event loop)"
            )
            self._in_event_loop = True
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = self._executor.submit(self._start_browser_sync)
            future.result()
        except RuntimeError:
            # No event loop running - we can use sync API directly
            logger.debug(f"Starting Playwright with {self.browser_type} browser")
            self._start_browser_sync()

    def _start_browser_sync(self) -> None:
        """Start the browser using sync API (helper for thread execution)."""
        # Optional dependency - only available when installed
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        self._playwright = sync_playwright().start()
        browser_launcher = getattr(self._playwright, self.browser_type)
        self._browser = browser_launcher.launch(headless=True)

    def from_file(self, filepath: str) -> Image.Image:
        """Rasterize an SVG file to a PIL Image.

        Args:
            filepath: Path to the SVG file to rasterize.

        Returns:
            PIL Image object in RGBA mode containing the rasterized SVG.

        Raises:
            FileNotFoundError: If the SVG file does not exist.
            ImportError: If Playwright is not installed.
        """
        with open(filepath, "rb") as f:
            svg_content = f.read()
        return self.from_string(svg_content)

    def from_string(self, svg_content: Union[str, bytes]) -> Image.Image:
        """Rasterize SVG content from a string to a PIL Image.

        This method renders the SVG by loading it into a headless browser page
        and taking a screenshot.

        Args:
            svg_content: SVG content as string or bytes.

        Returns:
            PIL Image object in RGBA mode containing the rasterized SVG.

        Raises:
            ImportError: If Playwright is not installed.
            ValueError: If the SVG content is invalid.
        """
        self._ensure_browser()

        # If running in event loop, delegate to thread executor
        if self._in_event_loop and self._executor is not None:
            future = self._executor.submit(self._rasterize_sync, svg_content)
            return future.result()

        # Otherwise run directly
        return self._rasterize_sync(svg_content)

    def _rasterize_sync(self, svg_content: Union[str, bytes]) -> Image.Image:
        """Internal synchronous rasterization method (runs in thread if needed)."""
        # Convert bytes to string if necessary
        svg_str = (
            svg_content.decode("utf-8")
            if isinstance(svg_content, bytes)
            else svg_content
        )

        # Parse SVG to get dimensions
        dimensions = self._get_svg_dimensions(svg_str)

        # The viewport holds the document's CSS size; DPI scaling comes from
        # device_scale_factor, which multiplies the screenshot's device pixels.
        # Both are passed to new_page(): set_viewport_size() takes no timeout
        # and can hang, and device_scale_factor is creation-only.
        viewport: ViewportSize = {
            "width": int(dimensions["width"]),
            "height": int(dimensions["height"]),
        }

        # Create page and set content
        assert self._browser is not None
        page = self._browser.new_page(
            viewport=viewport,
            device_scale_factor=self.dpi / 96.0 if self.dpi > 0 else 1.0,
        )

        try:
            # Embed SVG in minimal HTML
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 0;
            width: {dimensions["width"]}px;
            height: {dimensions["height"]}px;
        }}
        svg {{
            display: block;
        }}
    </style>
</head>
<body>
{svg_str}
</body>
</html>"""

            page.set_content(html, wait_until="networkidle")

            # Take screenshot with transparency
            screenshot_bytes = page.screenshot(type="png", omit_background=True)

            # Convert to PIL Image
            pil_image: Image.Image = Image.open(BytesIO(screenshot_bytes))

            # Ensure image is in RGBA mode (sometimes PNG can be RGB)
            if pil_image.mode != "RGBA":
                pil_image = pil_image.convert("RGBA")

            return self._composite_background(pil_image)

        finally:
            page.close()

    def _get_svg_dimensions(self, svg_content: str) -> dict[str, float]:
        """Extract width and height from SVG content.

        Args:
            svg_content: SVG content as string.

        Returns:
            Dictionary with 'width' and 'height' keys in pixels.

        Raises:
            ValueError: If SVG dimensions cannot be determined.
        """
        try:
            root = ET.fromstring(svg_content)

            # Try to get width and height attributes
            width_str = root.get("width", "")
            height_str = root.get("height", "")

            # Parse dimensions (assuming px units or unitless)
            width = self._parse_dimension(width_str)
            height = self._parse_dimension(height_str)

            if width and height:
                return {"width": width, "height": height}

            # Fall back to viewBox if width/height not specified
            viewbox = root.get("viewBox", "")
            if viewbox:
                parts = viewbox.split()
                if len(parts) == 4:
                    return {"width": float(parts[2]), "height": float(parts[3])}

            raise ValueError("Could not determine SVG dimensions")

        except ET.ParseError as e:
            raise ValueError("Could not determine SVG dimensions") from e

    def _parse_dimension(self, value: str) -> float | None:
        """Parse dimension value from SVG attribute.

        Args:
            value: Dimension string (e.g., "100", "100px", "10cm").

        Returns:
            Dimension in pixels, or None if parsing fails.
        """
        if not value:
            return None

        # Remove common units (assuming px or unitless)
        value = value.strip().lower()
        value = value.replace("px", "").replace("pt", "").strip()

        try:
            return float(value)
        except ValueError:
            return None

    def close(self) -> None:
        """Close the browser and cleanup resources.

        This method should be called when the rasterizer is no longer needed
        to free browser resources. Alternatively, use the context manager
        interface (with statement) for automatic cleanup.
        """
        # If running in event loop, cleanup must happen in the same thread
        if self._in_event_loop and self._executor is not None:
            future = self._executor.submit(self._close_sync)
            future.result()
            # Shutdown executor
            self._executor.shutdown(wait=True)
            self._executor = None
        else:
            self._close_sync()

    def _close_sync(self) -> None:
        """Internal synchronous cleanup method (runs in thread if needed)."""
        if self._browser is not None:
            logger.debug("Closing Playwright browser")
            self._browser.close()
            self._browser = None

        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self) -> "PlaywrightRasterizer":
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager and cleanup resources."""
        self.close()

    def __del__(self) -> None:
        """Destructor to ensure cleanup."""
        self.close()
