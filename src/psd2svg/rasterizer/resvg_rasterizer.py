"""Resvg-based rasterizer module.

This module provides SVG rasterization using the resvg library via resvg-py,
offering fast and accurate rendering with no external dependencies.
"""

import logging
import math
import os
import re
from io import BytesIO
from typing import Union

import resvg_py
from PIL import Image

from .base_rasterizer import DEFAULT_DPI, BaseRasterizer

logger = logging.getLogger(__name__)

# Largest canvas resvg can be asked for; beyond this the scale is dropped.
_MAX_RENDER_SIZE = 2**31 - 1


class ResvgRasterizer(BaseRasterizer):
    """High-performance SVG rasterizer using resvg.

    This rasterizer uses the resvg library (via resvg-py) to convert SVG
    documents to raster images. Resvg is a fast, accurate SVG renderer
    written in Rust that provides excellent quality with minimal dependencies.

    Note:
        Resvg does not support CSS @font-face rules with embedded fonts (data URIs).
        This implementation automatically extracts font file paths from @font-face
        src: url("file://...") declarations and passes them to resvg's native font
        loading API. The @font-face CSS rules themselves are ignored by resvg.
        Data URIs (data:font/...) are not supported and will be silently ignored.

    Example:
        >>> rasterizer = ResvgRasterizer(dpi=96)
        >>> image = rasterizer.from_file('input.svg')
        >>> image.save('output.png')

        >>> svg_content = '<svg>...</svg>'
        >>> image = rasterizer.from_string(svg_content)
        >>> image.save('output.png')
    """

    def __init__(self, dpi: int = 0) -> None:
        """Initialize the resvg rasterizer.

        Args:
            dpi: Dots per inch for rendering. Default is 96 DPI (standard
                screen resolution); 0 also means 96 DPI. Higher values produce
                larger, higher resolution images (e.g., 300 DPI for print
                quality).
        """
        self.dpi = dpi

    def _render_width(self, dimensions: tuple[float, float] | None) -> int | None:
        """Pixel width that renders a document of this size at ``self.dpi``.

        resvg scales the rendering to the requested width and derives the
        height from the document's aspect ratio. Its own ``dpi`` option only
        converts physical units, so it cannot scale a document sized in pixels.

        Args:
            dimensions: CSS pixel size of the document, or None if unknown.

        Returns:
            The target width in pixels, or None to render at the document's
            own CSS size.
        """
        scale = self._dpi_scale(self.dpi)
        if scale == 1.0:
            return None
        if dimensions is None:
            logger.warning(
                f"Could not determine SVG dimensions; rendering at {DEFAULT_DPI} "
                f"DPI instead of {self.dpi}"
            )
            return None
        # resvg derives the height from the width, so both axes have to fit.
        scaled = [length * scale for length in dimensions]
        if any(not math.isfinite(axis) or axis > _MAX_RENDER_SIZE for axis in scaled):
            # Leave resvg to reject a canvas it could never allocate, so it
            # fails the same way it does at 96 DPI.
            logger.warning(
                f"Rendering {dimensions[0]:g}x{dimensions[1]:g} CSS pixels at "
                f"{self.dpi} DPI would exceed {_MAX_RENDER_SIZE} pixels; "
                f"rendering at {DEFAULT_DPI} DPI"
            )
            return None
        target = scaled[0]
        # Round half up, as a browser scales a viewport, so that both
        # backends give the same size for the same document.
        return max(1, math.floor(target + 0.5))

    @staticmethod
    def _extract_font_file_paths(svg_content: str) -> list[str]:
        """Extract font file paths from @font-face CSS rules in SVG.

        Args:
            svg_content: SVG content as string.

        Returns:
            List of valid font file paths found in src: url("file://...") declarations.
            Invalid paths (non-existent files or non-font extensions) are filtered out
            with a warning.

        Note:
            This method validates extracted paths to prevent:
            - Access to non-existent files
            - Access to non-font files (security mitigation)
            - Log pollution from invalid paths
        """
        # Valid font file extensions
        VALID_FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".ttc"}

        font_files = []
        # Pattern to match: src: url("file:///path/to/font.ttf")
        pattern = re.compile(r'src:\s*url\(["\']?(file://[^"\')]+)["\']?\)')

        matches = pattern.findall(svg_content)
        for match in matches:
            # Remove file:// prefix to get the actual path
            font_path = match.replace("file://", "")

            # Validate file extension
            _, ext = os.path.splitext(font_path.lower())
            if ext not in VALID_FONT_EXTENSIONS:
                logger.warning(
                    f"Skipping invalid font file extension: {font_path} "
                    f"(expected one of {VALID_FONT_EXTENSIONS})"
                )
                continue

            # Validate file existence
            if not os.path.isfile(font_path):
                logger.warning(f"Skipping non-existent font file: {font_path}")
                continue

            font_files.append(font_path)

        return font_files

    def from_file(
        self, filepath: str, font_files: list[str] | None = None
    ) -> Image.Image:
        """Rasterize an SVG file to a PIL Image.

        Args:
            filepath: Path to the SVG file to rasterize.
            font_files: Optional list of font file paths to use for rendering.

        Returns:
            PIL Image object in RGBA mode containing the rasterized SVG.

        Raises:
            ValueError: If the SVG file does not exist or the content is invalid.
        """
        try:
            png_bytes = resvg_py.svg_to_bytes(
                svg_path=filepath,
                dpi=DEFAULT_DPI,
                width=self._render_width(self._svg_file_dimensions(filepath)),
                font_files=font_files,
            )
            image = Image.open(BytesIO(png_bytes))
            return self._composite_background(image)
        except ValueError as e:
            raise ValueError(f"Failed to rasterize SVG file '{filepath}': {e}") from e

    def from_string(
        self, svg_content: Union[str, bytes], font_files: list[str] | None = None
    ) -> Image.Image:
        """Rasterize SVG content from a string to a PIL Image.

        This method provides an optimized implementation that directly
        rasterizes the SVG content without creating a temporary file.

        If font_files is not provided, this method automatically extracts
        font file paths from @font-face CSS rules in the SVG content
        (file:// URLs).

        Args:
            svg_content: SVG content as string or bytes.
            font_files: Optional list of font file paths to use for rendering.
                If None, font paths are extracted from the SVG content.

        Returns:
            PIL Image object in RGBA mode containing the rasterized SVG.

        Raises:
            ValueError: If the SVG content is invalid.
        """
        # Convert bytes to string if necessary
        svg_string = (
            svg_content.decode("utf-8")
            if isinstance(svg_content, bytes)
            else svg_content
        )

        # Auto-extract font files from @font-face CSS if not provided
        if font_files is None:
            font_files = self._extract_font_file_paths(svg_string)
            if font_files:
                logger.debug(f"Extracted {len(font_files)} font file(s) from SVG")

        try:
            png_bytes = resvg_py.svg_to_bytes(
                svg_string=svg_string,
                dpi=DEFAULT_DPI,
                width=self._render_width(self._svg_dimensions(svg_string)),
                font_files=font_files,
            )
            image = Image.open(BytesIO(png_bytes))
            return self._composite_background(image)
        except ValueError as e:
            raise ValueError(f"Failed to rasterize SVG content: {e}") from e
