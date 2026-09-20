"""Font mapping helper functions and data.

This module contains helper functions for generating font weight variants.
The actual font mappings are stored as JSON resource files in src/psd2svg/data/:
- default_fonts.json: 539 core fonts
- morisawa_fonts.json: 4,042 Morisawa fonts

Hiragino fonts are generated dynamically using the pattern-based approach below.

Weight values follow fontconfig conventions:
- 0 = thin (CSS 100)
- 40 = extralight (CSS 200)
- 50 = light (CSS 300)
- 55 = demilight (CSS 350)
- 75 = book (CSS 380)
- 80 = regular/normal (CSS 400)
- 100 = medium (CSS 500)
- 180 = semibold (CSS 600)
- 200 = bold (CSS 700)
- 205 = extrabold (CSS 800)
- 210 = black (CSS 900)
- 215 = extrablack (CSS 1000)

Values between these points interpolate; see core.font_weights.
"""

from typing import Any

# Japanese weight system (W0-W9) used by Hiragino fonts
# Note: W1-W3 mappings were corrected in v0.8.0 to match actual font weights:
#   W1: 0.0 → 40.0 (extralight)
#   W2: 0.0 → 45.0 (between extralight and light)
#   W3: 0.0 → 50.0 (light)
# These round-trip to the faces' own OS/2.usWeightClass (W0-W9 →
# 100/200/250/300/400/500/600/700/800/900) via core.font_weights.
_JAPANESE_WEIGHTS = {
    "W0": 0.0,
    "W1": 40.0,
    "W2": 45.0,
    "W3": 50.0,
    "W4": 80.0,
    "W5": 100.0,
    "W6": 180.0,
    "W7": 200.0,
    "W8": 205.0,
    "W9": 210.0,
}

# Hiragino font base names with their family names
# All weight variants (W0-W9) will be automatically generated
_HIRAGINO_BASE_FONTS = [
    # Modern Hiragino Sans/Serif (macOS 10.11+)
    ("HiraginoSans", "Hiragino Sans"),
    ("HiraginoSerif", "Hiragino Serif"),
    ("HiraginoSansGB", "Hiragino Sans GB"),
    # Hiragino Kaku Gothic Std/Pro/ProN (角ゴ - Square Gothic)
    ("HiraKakuStd", "Hiragino Kaku Gothic Std"),
    ("HiraKakuPro", "Hiragino Kaku Gothic Pro"),
    ("HiraKakuProN", "Hiragino Kaku Gothic ProN"),
    ("HiraKakuStdN", "Hiragino Kaku Gothic StdN"),
    # Hiragino Sans Pr6N/Upr variants (newer naming)
    ("HiraginoSansPr6N", "Hiragino Sans"),
    ("HiraginoSansUpr", "Hiragino Sans"),
    # Hiragino Maru Gothic (丸ゴ - Rounded Gothic)
    ("HiraMaruStd", "Hiragino Maru Gothic Std"),
    ("HiraMaruPro", "Hiragino Maru Gothic Pro"),
    ("HiraMaruProN", "Hiragino Maru Gothic ProN"),
    ("HiraMaruStdN", "Hiragino Maru Gothic StdN"),
    # Hiragino Sans R (Rounded) Pr6N/Upr variants
    ("HiraginoSansRPr6N", "Hiragino Maru Gothic"),
    ("HiraginoSansRUpr", "Hiragino Maru Gothic"),
    # Hiragino Mincho (明朝 - Serif/Ming)
    ("HiraMinStd", "Hiragino Mincho Std"),
    ("HiraMinPro", "Hiragino Mincho Pro"),
    ("HiraMinProN", "Hiragino Mincho ProN"),
    ("HiraMinStdN", "Hiragino Mincho StdN"),
    # Hiragino Serif Pr6N/Upr variants
    ("HiraginoSerifPr6N", "Hiragino Serif"),
    ("HiraginoSerifUpr", "Hiragino Serif"),
    # Hiragino Gyosho (行書 - Semi-cursive/Running script)
    ("HiraGyoStd", "Hiragino Gyosho Std"),
    ("HiraGyoStdN", "Hiragino Gyosho StdN"),
    # Hiragino UD (Universal Design) series
    ("HiraginoUDSansStd", "Hiragino UD Sans Std"),
    ("HiraginoUDSansStdN", "Hiragino UD Sans StdN"),
    ("HiraginoUDSansFStd", "Hiragino UD Sans F Std"),
    ("HiraginoUDSansFStdN", "Hiragino UD Sans F StdN"),
    ("HiraginoUDSansRStd", "Hiragino UD Maru Gothic Std"),
    ("HiraginoUDSansRStdN", "Hiragino UD Maru Gothic StdN"),
    ("HiraginoUDSerifStd", "Hiragino UD Serif Std"),
    ("HiraginoUDSerifStdN", "Hiragino UD Serif StdN"),
    # Hiragino Sans Old variants
    ("HiraSansOldStd", "Hiragino Sans Old Std"),
    ("HiraSansOldStdN", "Hiragino Sans Old StdN"),
    ("HiraginoSansROldStd", "Hiragino Maru Gothic Old Std"),
    ("HiraginoSansROldStdN", "Hiragino Maru Gothic Old StdN"),
    # Other Hiragino variants
    ("KoburinaGoStd", "Koburina Gothic Std"),
    ("KoburinaGoStdN", "Koburina Gothic StdN"),
]


def _generate_weight_variants(
    base_fonts: list[tuple[str, str]],
    weights: dict[str, float],
    suffix_pattern: str = "-{weight}",
) -> dict[str, dict[str, Any]]:
    """
    Generate font entries with weight variants.

    Args:
        base_fonts: List of (base_name, family_name) tuples
        weights: Dict mapping weight suffix (e.g., "W0") to weight value
        suffix_pattern: Pattern for generating PostScript names (default: "-{weight}")

    Returns:
        Dictionary of generated font entries
    """
    entries = {}
    for base_name, family_name in base_fonts:
        for weight_suffix, weight_value in weights.items():
            postscript_name = base_name + suffix_pattern.format(weight=weight_suffix)
            entries[postscript_name] = {
                "family": family_name,
                "style": weight_suffix,
                "weight": weight_value,
            }
    return entries
