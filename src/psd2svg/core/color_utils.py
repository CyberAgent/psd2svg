import logging
from typing import Sequence

from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Klass

logger = logging.getLogger(__name__)


def rgb2hex(values: Sequence[int]) -> str:
    """Convert RGB color to hex string."""
    assert len(values) == 3
    return (
        f"#{clip_int(values[0]):02x}{clip_int(values[1]):02x}{clip_int(values[2]):02x}"
    )


def rgba2hex(values: Sequence[int], alpha: float = 1.0) -> str:
    """Convert RGBA color to hex string, considering alpha channel."""
    assert len(values) == 3
    if alpha >= 1.0:
        return rgb2hex(values)
    r = clip_int(values[0])
    g = clip_int(values[1])
    b = clip_int(values[2])
    a = max(0, min(255, int(alpha * 255)))
    return f"#{r:02x}{g:02x}{b:02x}{a:02x}"


def cmyk2rgb_float(values: Sequence[float]) -> tuple[float, float, float]:
    """Convert CMYK color to RGB color, both as fractions in the range 0.0-1.0.

    Args:
        values: Tuple of (c, m, y, k) as fractions in the range 0.0-1.0.

    Returns:
        Tuple of (r, g, b) as floats in the range 0.0-1.0.
    """
    assert len(values) == 4
    c, m, y, k = (float(value) for value in values)
    return ((1.0 - c) * (1.0 - k), (1.0 - m) * (1.0 - k), (1.0 - y) * (1.0 - k))


def cmyk2rgb(values: Sequence[float]) -> tuple[int, int, int]:
    """Convert CMYK color to 8-bit RGB color.

    Args:
        values: Tuple of (c, m, y, k) as fractions in the range 0.0-1.0.

    Returns:
        Tuple of (r, g, b) as integers in the range 0-255.
    """
    r, g, b = cmyk2rgb_float(values)
    return (float2uint8(r), float2uint8(g), float2uint8(b))


def descriptor2rgb(desc: Descriptor) -> tuple[float, float, float]:
    """Convert a color descriptor to RGB float tuple (0.0-255.0).

    Args:
        desc: Color descriptor.

    Returns:
        Tuple of (r, g, b) as floats in range 0.0-255.0.

    Raises:
        ValueError: If color format is unsupported.
    """
    if desc.classID == Klass.RGBColor:
        if Enum.Red in desc:
            # Integer format: b'Rd  ', b'Grn ', b'Bl  '
            r = float(desc.get(Enum.Red, 0))
            g = float(desc.get(Enum.Green, 0))
            b = float(desc.get(Enum.Blue, 0))
            return (r, g, b)
        elif "redFloat" in desc:
            # Float format: 'redFloat', 'greenFloat', 'blueFloat'
            r = float(desc.get("redFloat", 0)) * 255.0
            g = float(desc.get("greenFloat", 0)) * 255.0
            b = float(desc.get("blueFloat", 0)) * 255.0
            return (r, g, b)
        else:
            raise ValueError(f"Unsupported RGB color format: {desc}")

    if desc.classID == Klass.CMYKColor:
        c = desc.get(Enum.Cyan, 0)
        m = desc.get(Enum.Magenta, 0)
        y = desc.get(Enum.Yellow, 0)
        k = desc.get(Enum.Black, 0)
        r, g, b = cmyk2rgb_float((c / 100, m / 100, y / 100, k / 100))
        return (r * 255.0, g * 255.0, b * 255.0)

    if desc.classID == Klass.Grayscale:
        gray = desc.get(Enum.Gray, 0)
        assert isinstance(gray, float)
        gray_val = float(gray * 255.0)
        return (gray_val, gray_val, gray_val)

    raise ValueError(f"Unsupported color mode: {desc.classID!r}")


def descriptor2hex(desc: Descriptor | None, fallback: str = "none") -> str:
    """Convert a color descriptor to an RGB hex string.

    Args:
        desc: Color descriptor, or None.
        fallback: Fallback color string when desc is None or unsupported.

    Returns:
        RGB hex string like "#rrggbb", or fallback value.
    """
    if desc is None:
        return fallback

    if desc.classID == Klass.RGBColor:
        if Enum.Red in desc:
            r = desc.get(Enum.Red, 0)
            g = desc.get(Enum.Green, 0)
            b = desc.get(Enum.Blue, 0)
            return f"#{int(r):02x}{int(g):02x}{int(b):02x}"
        elif "redFloat" in desc:
            r = float2uint8(desc.get("redFloat", 0))
            g = float2uint8(desc.get("greenFloat", 0))
            b = float2uint8(desc.get("blueFloat", 0))
            return f"#{r:02x}{g:02x}{b:02x}"
        else:
            raise ValueError(f"Unsupported RGB color format: {desc}")

    if desc.classID == Klass.CMYKColor:
        c = desc.get(Enum.Cyan, 0)
        m = desc.get(Enum.Magenta, 0)
        y = desc.get(Enum.Yellow, 0)
        k = desc.get(Enum.Black, 0)
        r, g, b = cmyk2rgb((c / 100, m / 100, y / 100, k / 100))
        return f"#{r:02x}{g:02x}{b:02x}"

    if desc.classID == Klass.Grayscale:
        gray = desc.get(Enum.Gray, 0)
        assert isinstance(gray, float)
        gray = float2uint8(gray)
        return f"#{gray:02x}{gray:02x}{gray:02x}"

    logger.warning("Unsupported color mode: %s", desc.classID)
    return fallback


def float2uint8(v: float) -> int:
    """Convert a float in the range [0.0, 1.0] to an integer in the range [0, 255].

    The value is rounded rather than truncated; truncation systematically
    darkens colors and turns values such as ``0.2`` into 50 instead of 51.
    """
    return clip_int(round(255 * v))


def clip_int(value: int | float, min_value: int = 0, max_value: int = 255) -> int:
    """Clip an int value to the specified range."""
    return max(min_value, min(max_value, int(value)))
