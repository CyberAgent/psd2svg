import logging
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from typing import Union, cast

from PIL import Image

logger = logging.getLogger(__name__)

#: DPI at which one CSS pixel is one device pixel.
DEFAULT_DPI = 96

# Absolute CSS length units, in pixels.
_UNIT_TO_PX = {
    "": 1.0,
    "px": 1.0,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
    "in": 96.0,
    "mm": 96.0 / 25.4,
    "cm": 96.0 / 2.54,
    "q": 96.0 / 101.6,
}

_LENGTH_RE = re.compile(
    r"\A\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*|%)\s*\Z"
)

# Enough to hold a root <svg> start tag; the rest of the document is never read.
_CHUNK_SIZE = 8192


class BaseRasterizer(ABC):
    """Base class for SVG rasterizer implementations.

    This abstract base class defines the interface for converting SVG documents
    to raster images (PIL Image objects). Subclasses must implement the
    `from_file` method to provide the actual rasterization logic.
    """

    def from_string(self, svg_content: Union[str, bytes]) -> Image.Image:
        """Rasterize SVG content from a string or bytes to a PIL Image.

        This is a convenience method that writes the SVG content to a temporary
        file and calls `from_file`. Subclasses may override this for more
        efficient implementations.

        Args:
            svg_content: SVG content as string or bytes.

        Returns:
            PIL Image object containing the rasterized SVG.
        """
        with tempfile.NamedTemporaryFile(suffix=".svg", mode="wb", delete=False) as f:
            content_bytes = (
                svg_content
                if isinstance(svg_content, bytes)
                else svg_content.encode("utf-8")
            )
            f.write(content_bytes)
            f.flush()
            return self.from_file(f.name)

    @abstractmethod
    def from_file(self, filepath: str) -> Image.Image:
        """Rasterize an SVG file to a PIL Image.

        This is the primary method that subclasses must implement to provide
        the actual rasterization logic.

        Args:
            filepath: Path to the SVG file to rasterize.

        Returns:
            PIL Image object containing the rasterized SVG.
        """
        raise NotImplementedError

    @staticmethod
    def _dpi_scale(dpi: int) -> float:
        """Render scale for a DPI setting, where 0 and 96 both mean 1:1."""
        return dpi / DEFAULT_DPI if dpi > 0 else 1.0

    @staticmethod
    def _parse_length(value: str, percent_of: float | None = None) -> float | None:
        """Convert a CSS length to pixels, where ``1in`` is 96px.

        Args:
            value: Attribute value such as "100", "100px", "1in" or "50%".
            percent_of: Length a percentage is relative to. Percentages are
                rejected when this is None.

        Returns:
            The length in CSS pixels, or None when the value is empty,
            malformed, not finite, or relative to something else ("2em").
        """
        match = _LENGTH_RE.match(value)
        if match is None:
            return None
        unit = match.group(2).lower()
        if unit == "%":
            if percent_of is None:
                return None
            factor = percent_of / 100.0
        else:
            unit_px = _UNIT_TO_PX.get(unit)
            if unit_px is None:
                return None
            factor = unit_px
        length = float(match.group(1)) * factor
        return length if math.isfinite(length) else None

    @staticmethod
    def _parse_svg_root(chunks: Iterable[Union[str, bytes]]) -> ET.Element | None:
        """Parse an SVG only as far as its root start tag.

        Args:
            chunks: Successive pieces of the document.

        Returns:
            The root element, or None when the document has no element or is
            malformed before the root start tag closes. Attributes are
            available; children are not.
        """

        def first_start(parser: ET.XMLPullParser) -> ET.Element | None:
            events = cast(Iterator[tuple[str, ET.Element]], parser.read_events())
            for _, element in events:
                return element
            return None

        parser = ET.XMLPullParser(["start"])
        try:
            for chunk in chunks:
                parser.feed(chunk)
                element = first_start(parser)
                if element is not None:
                    return element
        except ET.ParseError:
            return None

        # The parser buffers the tail of the last chunk, so a root start tag
        # that ends there only reaches read_events() once the feed is closed.
        try:
            parser.close()
        except ET.ParseError:
            pass
        return first_start(parser)

    @classmethod
    def _root_dimensions(cls, root: ET.Element) -> tuple[float, float] | None:
        """Read the CSS pixel size of a root ``<svg>`` element.

        Each axis is resolved on its own, and an axis that has no absolute
        length of its own falls back to the viewBox, so a document that sizes
        only one of them keeps the other.
        """
        viewbox = cls._parse_viewbox(root.get("viewBox", ""))
        width = cls._axis_length(root.get("width", ""), viewbox[0] if viewbox else None)
        height = cls._axis_length(
            root.get("height", ""), viewbox[1] if viewbox else None
        )
        return None if width is None or height is None else (width, height)

    @classmethod
    def _axis_length(cls, value: str, viewbox_length: float | None) -> float | None:
        """Resolve one axis of a root ``<svg>`` size against its viewBox."""
        length = cls._parse_length(value, percent_of=viewbox_length)
        if length is not None and length > 0:
            return length
        return viewbox_length

    @staticmethod
    def _parse_viewbox(value: str) -> tuple[float, float] | None:
        """Read the width and height of a viewBox, or None if it has neither."""
        parts = value.replace(",", " ").split()
        if len(parts) != 4:
            return None
        try:
            width, height = float(parts[2]), float(parts[3])
        except ValueError:
            return None
        if not (math.isfinite(width) and math.isfinite(height)):
            return None
        return (width, height) if width > 0 and height > 0 else None

    @classmethod
    def _svg_root(cls, svg_content: str) -> ET.Element | None:
        """Root element of an SVG document, or None if it has no parsable one."""
        return cls._parse_svg_root(
            svg_content[offset : offset + _CHUNK_SIZE]
            for offset in range(0, len(svg_content), _CHUNK_SIZE)
        )

    @classmethod
    def _svg_dimensions(cls, svg_content: str) -> tuple[float, float] | None:
        """CSS pixel width and height of an SVG document.

        Args:
            svg_content: SVG content as string.

        Returns:
            (width, height) in CSS pixels, or None when neither the root
            width/height nor the viewBox gives an absolute size.
        """
        root = cls._svg_root(svg_content)
        return None if root is None else cls._root_dimensions(root)

    @classmethod
    def _has_absolute_size(cls, root: ET.Element) -> bool:
        """Whether a root ``<svg>`` sizes both axes itself, zero included."""
        return (
            cls._parse_length(root.get("width", "")) is not None
            and cls._parse_length(root.get("height", "")) is not None
        )

    @classmethod
    def _svg_file_dimensions(cls, filepath: str) -> tuple[float, float] | None:
        """CSS pixel width and height of an SVG file.

        Only the head of the file is read.

        Args:
            filepath: Path to the SVG file.

        Returns:
            (width, height) in CSS pixels, or None when the file cannot be
            read, or when neither the root width/height nor the viewBox gives
            an absolute size. An unreadable file is reported by the caller
            that goes on to render it.
        """
        try:
            with open(filepath, "rb") as f:
                root = cls._parse_svg_root(iter(lambda: f.read(_CHUNK_SIZE), b""))
        except OSError:
            return None
        return None if root is None else cls._root_dimensions(root)

    def _composite_background(self, image: Image.Image) -> Image.Image:
        """Composite image onto a transparent background to normalize alpha.

        This utility method ensures consistent handling of transparent pixels
        by compositing the image onto a fully transparent RGBA background.
        This prevents artifacts and ensures proper alpha channel handling.

        Args:
            image: Input PIL Image, typically with RGBA mode.

        Returns:
            PIL Image with normalized alpha channel.
        """
        background = Image.new("RGBA", size=image.size, color=(255, 255, 255, 0))
        background.alpha_composite(image)
        return background
