"""Tests for the fontconfig <-> OpenType/CSS weight scale conversion."""

import pytest

from psd2svg.core.font_utils import FontInfo
from psd2svg.core.font_weights import (
    fontconfig_to_opentype_weight,
    opentype_to_fontconfig_weight,
)


@pytest.mark.parametrize(
    "opentype, fontconfig",
    [
        (100, 0.0),  # thin
        (200, 40.0),  # extralight
        (250, 45.0),  # Hiragino W2
        (300, 50.0),  # light
        (350, 55.0),  # demilight
        (380, 75.0),  # book
        (400, 80.0),  # regular
        (500, 100.0),  # medium
        (600, 180.0),  # semibold
        (700, 200.0),  # bold
        (800, 205.0),  # extrabold
        (900, 210.0),  # black
        (1000, 215.0),  # extrablack
    ],
)
def test_weight_round_trip(opentype: int, fontconfig: float) -> None:
    """Both directions agree on every point of fontconfig's scale."""
    assert opentype_to_fontconfig_weight(opentype) == fontconfig
    assert fontconfig_to_opentype_weight(fontconfig) == opentype


@pytest.mark.parametrize(
    "weight, expected",
    [
        (-10.0, 100),  # below the scale
        (1000.0, 1000),  # above the scale
        (190.0, 650),  # interpolated between semibold and bold
    ],
)
def test_fontconfig_to_opentype_out_of_range(weight: float, expected: int) -> None:
    """Values outside the listed points clamp or interpolate."""
    assert fontconfig_to_opentype_weight(weight) == expected


def test_japanese_weights_are_distinct() -> None:
    """Hiragino W0-W9 must not collapse onto shared CSS weights.

    Each W-suffixed face is separately installed, and two faces sharing a CSS
    weight also produce colliding @font-face rules. See GitHub issue #337.
    """
    weights = []
    for index in range(10):
        font = FontInfo.lookup_static(f"HiraginoSans-W{index}")
        assert font is not None
        weights.append(font.css_weight)

    # The faces' own OS/2.usWeightClass values.
    assert weights == [100, 200, 250, 300, 400, 500, 600, 700, 800, 900]
