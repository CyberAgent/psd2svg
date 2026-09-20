"""Conversion between the fontconfig and OpenType/CSS weight scales.

fontconfig stores weights on its own scale, while OpenType
(``OS/2.usWeightClass``) and CSS share the 1-1000 scale. fontconfig's
``fcweight.c`` defines the correspondence below and interpolates linearly
between the listed points; both helpers here reproduce that, so a weight
survives the round trip.

Bucketing fontconfig weights into multiples of 100 instead would collapse
neighbouring faces onto one CSS weight - Hiragino W2 (fontconfig 45,
``usWeightClass`` 250) and W3 (50, 300) are the motivating case.
"""

_WEIGHT_SCALE: tuple[tuple[float, float], ...] = (
    (100.0, 0.0),  # thin
    (200.0, 40.0),  # extralight
    (300.0, 50.0),  # light
    (350.0, 55.0),  # demilight
    (380.0, 75.0),  # book
    (400.0, 80.0),  # regular
    (500.0, 100.0),  # medium
    (600.0, 180.0),  # semibold
    (700.0, 200.0),  # bold
    (800.0, 205.0),  # extrabold
    (900.0, 210.0),  # black
    (1000.0, 215.0),  # extrablack
)


def _interpolate(value: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear lookup over (input, output) points sorted by input."""
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return points[-1][1]


def fontconfig_to_opentype_weight(weight: float) -> int:
    """Convert a fontconfig weight to the OpenType/CSS 1-1000 scale.

    Args:
        weight: Weight on the fontconfig scale (0-215).

    Returns:
        Weight on the OpenType/CSS scale, clamped to 1-1000.

    Example:
        >>> fontconfig_to_opentype_weight(80.0)  # regular
        400
        >>> fontconfig_to_opentype_weight(45.0)  # Hiragino W2
        250
    """
    points = [(fc, ot) for ot, fc in _WEIGHT_SCALE]
    return max(1, min(1000, round(_interpolate(weight, points))))


def opentype_to_fontconfig_weight(weight: float) -> float:
    """Convert an OpenType/CSS weight to the fontconfig scale.

    Args:
        weight: Weight on the OpenType/CSS scale (1-1000), typically read from
            ``OS/2.usWeightClass``.

    Returns:
        Weight on the fontconfig scale (0-215).

    Example:
        >>> opentype_to_fontconfig_weight(400)  # regular
        80.0
        >>> opentype_to_fontconfig_weight(250)  # Hiragino W2
        45.0
    """
    return _interpolate(weight, [(ot, fc) for ot, fc in _WEIGHT_SCALE])
