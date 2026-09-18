import pytest
from psd_tools.psd.descriptor import Descriptor, Double
from psd_tools.terminology import Enum, Klass

from psd2svg.core.color_utils import (
    cmyk2rgb,
    cmyk2rgb_float,
    descriptor2hex,
    descriptor2rgb,
)


@pytest.mark.parametrize(
    "values, expected",
    [
        ((0.0, 0.0, 0.0, 0.0), (255, 255, 255)),  # white
        ((0.0, 0.0, 0.0, 1.0), (0, 0, 0)),  # black
        ((1.0, 0.0, 0.0, 0.0), (0, 255, 255)),  # cyan
        ((0.0, 1.0, 0.0, 0.0), (255, 0, 255)),  # magenta
        ((0.0, 0.0, 1.0, 0.0), (255, 255, 0)),  # yellow
        ((0.5, 0.5, 0.5, 0.0), (128, 128, 128)),
        ((0.0, 0.0, 0.0, 0.5), (128, 128, 128)),
    ],
)
def test_cmyk2rgb(values: tuple[float, ...], expected: tuple[int, ...]) -> None:
    """CMYK fractions convert to the full 0-255 RGB range."""
    assert cmyk2rgb(values) == expected


def test_cmyk2rgb_float() -> None:
    """The fractional variant keeps full precision."""
    assert cmyk2rgb_float((0.0, 0.0, 0.0, 0.0)) == (1.0, 1.0, 1.0)
    assert cmyk2rgb_float((1.0, 0.0, 0.0, 0.0)) == (0.0, 1.0, 1.0)
    assert cmyk2rgb_float((0.0, 0.0, 0.0, 0.5)) == (0.5, 0.5, 0.5)


def _cmyk_descriptor(c: float, m: float, y: float, k: float) -> Descriptor:
    """Build a CMYKColor descriptor with percent-scaled components."""
    desc = Descriptor(classID=Klass.CMYKColor)
    desc[Enum.Cyan] = Double(c)
    desc[Enum.Magenta] = Double(m)
    desc[Enum.Yellow] = Double(y)
    desc[Enum.Black] = Double(k)
    return desc


@pytest.mark.parametrize(
    "cmyk, expected_rgb, expected_hex",
    [
        ((0.0, 0.0, 0.0, 0.0), (255.0, 255.0, 255.0), "#ffffff"),
        ((100.0, 0.0, 0.0, 0.0), (0.0, 255.0, 255.0), "#00ffff"),
        ((0.0, 0.0, 0.0, 100.0), (0.0, 0.0, 0.0), "#000000"),
        ((0.0, 0.0, 0.0, 50.0), (127.5, 127.5, 127.5), "#808080"),
    ],
)
def test_cmyk_descriptor_conversion(
    cmyk: tuple[float, ...], expected_rgb: tuple[float, ...], expected_hex: str
) -> None:
    """CMYK descriptors used by shape fills and effects convert correctly."""
    desc = _cmyk_descriptor(*cmyk)
    assert descriptor2rgb(desc) == expected_rgb
    assert descriptor2hex(desc) == expected_hex


def _grayscale_descriptor(gray: float) -> Descriptor:
    """Build a Grayscale descriptor with a percent-black component."""
    desc = Descriptor(classID=Klass.Grayscale)
    desc[Enum.Gray] = Double(gray)
    return desc


@pytest.mark.parametrize(
    "gray, expected_rgb, expected_hex",
    [
        (0.0, (255.0, 255.0, 255.0), "#ffffff"),
        (25.0, (191.25, 191.25, 191.25), "#bfbfbf"),
        (50.0, (127.5, 127.5, 127.5), "#808080"),
        (100.0, (0.0, 0.0, 0.0), "#000000"),
    ],
)
def test_grayscale_descriptor_conversion(
    gray: float, expected_rgb: tuple[float, ...], expected_hex: str
) -> None:
    """Grayscale descriptors store percent black, so the value is inverted."""
    desc = _grayscale_descriptor(gray)
    assert descriptor2rgb(desc) == expected_rgb
    assert descriptor2hex(desc) == expected_hex


def test_grayscale_descriptor_defaults_to_white() -> None:
    """A Grayscale descriptor without a component means 0% black."""
    desc = Descriptor(classID=Klass.Grayscale)
    assert descriptor2rgb(desc) == (255.0, 255.0, 255.0)
    assert descriptor2hex(desc) == "#ffffff"
