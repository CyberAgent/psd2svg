import base64
import dataclasses
import logging
import os
import sys
import urllib.parse
import warnings
from pathlib import Path
from typing import Any

try:
    from typing import Self  # type: ignore
except ImportError:
    from typing_extensions import Self

try:
    import fontconfig

    HAS_FONTCONFIG = True
except ImportError:
    HAS_FONTCONFIG = False

from psd2svg import font_subsetting
from psd2svg.core import font_mapping as _font_mapping
from psd2svg.core.font_weights import fontconfig_to_opentype_weight

# Windows font resolution
if sys.platform == "win32":
    from psd2svg.core import windows_fonts as _windows_fonts  # type: ignore[import]

    HAS_WINDOWS_FONTS = True
else:
    _windows_fonts = None  # type: ignore[assignment]
    HAS_WINDOWS_FONTS = False

logger = logging.getLogger(__name__)


# ==============================================================================
# Font Suffix Parsing for PostScript Names
# ==============================================================================
# These constants support suffix-based inference in FontInfo.lookup_static().
# Conservative design: only suffixes present in the 572-entry static mapping.
# See FontInfo._parse_postscript_name_suffix() for algorithm details.

# Weight suffix mappings (fontconfig weight values)
WEIGHT_SUFFIXES: dict[str, tuple[str, float]] = {
    "Thin": ("Thin", 0.0),
    "ExtraLight": ("ExtraLight", 40.0),
    "Light": ("Light", 50.0),
    "Regular": ("Regular", 80.0),
    "Medium": ("Medium", 100.0),
    "SemiBold": ("SemiBold", 180.0),
    "Semibold": ("SemiBold", 180.0),  # Alternative spelling
    "DemiBold": ("SemiBold", 180.0),  # Alternative name for SemiBold
    "Demibold": ("SemiBold", 180.0),  # Alternative spelling
    "Bold": ("Bold", 200.0),
    "ExtraBold": ("ExtraBold", 205.0),
    "Extrabold": ("ExtraBold", 205.0),  # Alternative spelling
    "UltraBold": ("Ultra", 210.0),  # UltraBold variant
    "Ultrabold": ("Ultra", 210.0),  # Alternative spelling
    "Black": ("Black", 210.0),
    "Heavy": ("Heavy", 210.0),
    "Ultra": ("Ultra", 210.0),
    "Roman": ("Roman", 80.0),  # Times-Roman
    "MT": ("Regular", 80.0),  # Mac Type suffix
    # Abbreviated suffixes (common in Japanese fonts)
    "B": ("Bold", 200.0),  # Bold abbreviation
    "DB": ("SemiBold", 180.0),  # DemiBold abbreviation (short)
    "DeBold": ("SemiBold", 180.0),  # DemiBold abbreviation (medium)
    "EB": ("ExtraBold", 205.0),  # ExtraBold abbreviation (short)
    "ExBold": ("ExtraBold", 205.0),  # ExtraBold abbreviation (medium)
    "ExLight": ("ExtraLight", 40.0),  # ExtraLight abbreviation
    "UB": ("Ultra", 210.0),  # UltraBold abbreviation
}

# Japanese font weight notation (Hiragino fonts)
# Complete W0-W9 range based on macOS Hiragino Sans system fonts
JAPANESE_WEIGHT_SUFFIXES: dict[str, tuple[str, float]] = {
    "W0": ("W0", 0.0),
    "W1": ("W1", 40.0),
    "W2": ("W2", 45.0),
    "W3": ("W3", 50.0),
    "W4": ("W4", 80.0),
    "W5": ("W5", 100.0),
    "W6": ("W6", 180.0),
    "W7": ("W7", 200.0),
    "W8": ("W8", 205.0),
    "W9": ("W9", 210.0),
}

# Compound suffixes (weight + style)
COMPOUND_SUFFIXES: dict[str, tuple[str, float]] = {
    # Ordered by length (longest first for matching)
    "ExtraBoldItalic": ("ExtraBold Italic", 205.0),
    "ExtraLightItalic": ("ExtraLight Italic", 40.0),
    "SemiBoldItalic": ("SemiBold Italic", 180.0),
    "BoldItalic": ("Bold Italic", 200.0),
    "MediumItalic": ("Medium Italic", 100.0),
    "LightItalic": ("Light Italic", 50.0),
    "BoldOblique": ("Bold Oblique", 200.0),
    "ExtraBoldOblique": ("ExtraBold Oblique", 205.0),
    "SemiBoldOblique": ("SemiBold Oblique", 180.0),
}

# Safe suffixes for camelCase parsing (to avoid false positives)
# NOTE: Abbreviated suffixes (B, DB, EB, UB) are intentionally excluded
# to prevent false positives like "WebDB", "TestEB", etc.
# They work fine with hyphenated patterns (Phase 1).
SAFE_CAMELCASE_SUFFIXES: list[str] = [
    # Order matters: check longest first
    "UltraBold",  # Must come before "Bold"
    "DemiBold",  # Must come before "Bold"
    "ExtraBold",
    "ExtraLight",
    "SemiBold",
    "Semibold",
    "Black",
    "Heavy",
    "Medium",
    "Light",
    "Bold",
    "Thin",
    "Italic",
]


@dataclasses.dataclass
class FontInfo:
    """Font information from fontconfig.

    Attributes:
        postscript_name: PostScript name of the font.
        file: Path to the font file.
        family: Family name.
        style: Style name.
        weight: Weight value. 80.0 is regular and 200.0 is bold.
        charset: Optional set of Unicode codepoints (integers) used with this font.
            This is populated during font resolution to track which characters are
            actually used with this font for subsetting purposes. The codepoints
            are converted to characters only when needed for font subsetting.
    """

    postscript_name: str
    file: str
    family: str
    style: str
    weight: float
    charset: set[int] | None = None

    @property
    def family_name(self) -> str:
        """Get the family name."""
        return self.family

    @property
    def bold(self) -> bool:
        """Whether the font is bold."""
        # NOTE: Should we consider style names as well?
        return self.weight >= 200

    @property
    def italic(self) -> bool:
        """Whether the font is italic."""
        return "italic" in self.style.lower()

    def is_resolved(self) -> bool:
        """Check if font has been resolved to an actual system font file.

        A font is considered resolved if it has a valid file path pointing
        to an existing font file on the system.

        Returns:
            True if font has a valid file path, False otherwise.

        Example:
            >>> # Font from static mapping (not resolved)
            >>> font_info = FontInfo.lookup_static('ArialMT')
            >>> font_info.is_resolved()
            False
            >>> # Font with file path (resolved)
            >>> resolved = FontInfo.resolve('ArialMT')
            >>> if resolved:
            ...     resolved.is_resolved()
            True
        """
        return bool(self.file and os.path.exists(self.file))

    def get_css_weight(self, semantic: bool = False) -> int | str:
        """Get CSS font-weight value from fontconfig weight.

        Converts through :func:`fontconfig_to_opentype_weight`, so the result is
        the font's own ``OS/2.usWeightClass`` and neighbouring faces stay
        distinguishable (Hiragino W2 -> 250, W3 -> 300).

        Args:
            semantic: If True, return semantic keyword for common weights
                     ("normal", "bold") instead of numeric values.
                     Numeric values are more precise and work better with
                     variable fonts.

        Returns:
            CSS font-weight value (1-1000) or semantic keyword
            ("normal" for 400, "bold" for 700).
        """
        numeric_weight = fontconfig_to_opentype_weight(self.weight)

        # Return semantic keyword if requested and applicable
        if semantic:
            if numeric_weight == 400:
                return "normal"
            elif numeric_weight == 700:
                return "bold"

        return numeric_weight

    @property
    def css_weight(self) -> int:
        """Get numeric CSS font-weight value (1-1000).

        This is a convenience property that calls get_css_weight(semantic=False).
        For more control, use get_css_weight() directly.

        Returns:
            CSS font-weight value (1-1000).
        """
        result = self.get_css_weight(semantic=False)
        assert isinstance(result, int)
        return result

    def to_dict(self) -> dict[str, str | float]:
        """Convert FontInfo to a serializable dictionary.

        Returns:
            Dictionary representation of the font information.
        """
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str | float]) -> Self:
        """Create FontInfo from a dictionary.

        Args:
            data: Dictionary containing font information.

        Returns:
            FontInfo instance.
        """
        return cls(
            postscript_name=str(data["postscript_name"]),
            file=str(data["file"]),
            family=str(data["family"]),
            style=str(data["style"]),
            weight=float(data["weight"]),
        )

    def to_font_face_css(self, data_uri: str) -> str:
        """Generate @font-face CSS rule for this font.

        Args:
            data_uri: Base64 data URI for the font file
                (e.g., 'data:font/ttf;base64,...').

        Returns:
            CSS @font-face rule string.

        Example:
            >>> font_info = FontInfo.find('Arial-Regular')
            >>> data_uri = encode_font_data_uri(font_info.file)
            >>> css = font_info.to_font_face_css(data_uri)
            >>> print(css)
            @font-face {
              font-family: 'Arial';
              src: url(data:font/ttf;base64,...);
              font-weight: 400;
              font-style: normal;
            }
        """
        font_style = "italic" if self.italic else "normal"
        css_weight = self.css_weight

        return f"""@font-face {{
  font-family: '{self.family}';
  src: url({data_uri});
  font-weight: {css_weight};
  font-style: {font_style};
}}"""

    @staticmethod
    def _match_fontconfig(
        postscriptname: str, charset_codepoints: set[int] | None
    ) -> dict[str, Any] | None:
        """Match font via fontconfig with optional charset support.

        This is a low-level helper that performs the actual fontconfig matching
        with optional charset-based filtering. Used by both find() and resolve().

        Args:
            postscriptname: PostScript name of the font.
            charset_codepoints: Optional set of Unicode codepoints for charset matching.
                               Empty sets are treated as None (no charset matching).

        Returns:
            fontconfig match result dict with keys: file, family, style, weight.
            None if no match found.

        Raises:
            Exception: If fontconfig matching fails and charset_codepoints is None
                or empty.
        """
        try:
            if charset_codepoints:
                # Use charset-based matching
                logger.debug(
                    f"Using charset with {len(charset_codepoints)} codepoints "
                    f"for '{postscriptname}'"
                )
                charset = fontconfig.CharSet.from_codepoints(sorted(charset_codepoints))
                match = fontconfig.match(
                    properties={
                        "postscriptname": postscriptname,
                        "charset": charset,
                    },
                    select=("file", "family", "style", "weight"),
                )
            else:
                # Standard PostScript name matching
                match = fontconfig.match(
                    pattern=f":postscriptname={postscriptname}",
                    select=("file", "family", "style", "weight"),
                )
            return match  # type: ignore
        except Exception as e:
            # Graceful degradation: fall back to name-only matching
            if charset_codepoints:
                logger.warning(
                    f"Charset-based matching failed for '{postscriptname}': {e}. "
                    "Falling back to name-only matching"
                )
                match = fontconfig.match(
                    pattern=f":postscriptname={postscriptname}",
                    select=("file", "family", "style", "weight"),
                )
                return match  # type: ignore
            else:
                # If name-only matching also failed, re-raise
                raise

    @staticmethod
    def _match_windows(
        postscriptname: str, charset_codepoints: set[int] | None
    ) -> dict[str, Any] | None:
        """Match font via Windows registry with optional charset support.

        This is a low-level helper that performs the actual Windows registry matching
        with optional charset-based filtering. Used by both find() and resolve().

        Args:
            postscriptname: PostScript name of the font.
            charset_codepoints: Optional set of Unicode codepoints for charset matching.
                               Empty sets are treated as None (no charset matching).

        Returns:
            Windows font resolver match result dict with keys:
                file, family, style, weight. None if no match found.

        Raises:
            Exception: If Windows matching fails and charset_codepoints is None
                or empty.
        """
        resolver = _windows_fonts.get_windows_font_resolver()  # type: ignore[attr-defined]

        try:
            if charset_codepoints:
                # Use charset-based matching
                logger.debug(
                    f"Using charset with {len(charset_codepoints)} codepoints "
                    f"for '{postscriptname}'"
                )
                match = resolver.find_with_charset(postscriptname, charset_codepoints)
            else:
                # Standard PostScript name matching
                match = resolver.find(postscriptname)
            return match  # type: ignore
        except Exception as e:
            # Graceful degradation: fall back to name-only matching
            if charset_codepoints:
                logger.warning(
                    f"Charset-based matching failed for '{postscriptname}': {e}. "
                    "Falling back to name-only matching"
                )
                match = resolver.find(postscriptname)
                return match  # type: ignore
            else:
                # If name-only matching also failed, re-raise
                raise

    @staticmethod
    def _resolve_via_fontconfig(
        postscriptname: str, charset_codepoints: set[int] | None
    ) -> Self | None:
        """Resolve font via fontconfig with optional charset matching.

        Args:
            postscriptname: PostScript name of the font.
            charset_codepoints: Optional set of Unicode codepoints for charset matching.
                               Empty sets are treated as None (no charset matching).

        Returns:
            FontInfo object if found, None otherwise. If charset_codepoints is provided
            and non-empty, the returned FontInfo will have charset populated for
            later resolution.
        """
        logger.debug(
            f"Font '{postscriptname}' not in static mapping, trying fontconfig..."
        )

        match = FontInfo._match_fontconfig(postscriptname, charset_codepoints)

        if match:
            logger.debug(
                f"Resolved '{postscriptname}' via fontconfig fallback: "
                f"{match['family']}"
            )
            # Store codepoints directly
            charset: set[int] | None = charset_codepoints

            return FontInfo(
                postscript_name=postscriptname,
                file=match["file"],  # type: ignore
                family=match["family"],  # type: ignore
                style=match["style"],  # type: ignore
                weight=match["weight"],  # type: ignore
                charset=charset,
            )

        return None

    @staticmethod
    def _resolve_via_windows(
        postscriptname: str, charset_codepoints: set[int] | None
    ) -> Self | None:
        """Resolve font via Windows registry with optional charset matching.

        Args:
            postscriptname: PostScript name of the font.
            charset_codepoints: Optional set of Unicode codepoints for charset matching.
                               Empty sets are treated as None (no charset matching).

        Returns:
            FontInfo object if found, None otherwise. If charset_codepoints is provided
            and non-empty, the returned FontInfo will have charset populated for
            later resolution.
        """
        logger.debug(
            f"Font '{postscriptname}' not in static mapping, trying Windows registry..."
        )

        match = FontInfo._match_windows(postscriptname, charset_codepoints)

        if match:
            logger.debug(
                f"Resolved '{postscriptname}' via Windows registry fallback: "
                f"{match['family']}"
            )
            # Store codepoints directly
            charset: set[int] | None = charset_codepoints

            return FontInfo(
                postscript_name=postscriptname,
                file=str(match["file"]),
                family=str(match["family"]),
                style=str(match["style"]),
                weight=float(match["weight"]),
                charset=charset,
            )

        return None

    @staticmethod
    def find(
        postscriptname: str,
        font_mapping: dict[str, dict[str, float | str]] | None = None,
        charset_codepoints: set[int] | None = None,
        disable_static_mapping: bool = False,
    ) -> Self | None:
        """Find font information by PostScript name (backward-compatible wrapper).

        .. deprecated:: 0.7.0
            FontInfo.find() is deprecated due to its confusing API.
            Use explicit methods instead:

            - For CSS family names (embed_fonts=False): Use ``lookup_static()``
            - For font embedding (embed_fonts=True): Use ``resolve()``

            This method will be removed in version 1.0.0.

        This wrapper delegates to the appropriate method based on
        disable_static_mapping:
        - If disable_static_mapping=False: Uses lookup_static() (name resolution only)
        - If disable_static_mapping=True: Uses resolve() (with file paths)

        Args:
            postscriptname: PostScript name of the font (e.g., "ArialMT").
            font_mapping: Optional custom font mapping dictionary. Format:
                {"PostScriptName": {"family": str, "style": str, "weight": float}}
            charset_codepoints: Optional set of Unicode codepoints for charset-based
                               font matching. Only used when disable_static_mapping=True
                               (platform resolution). Empty sets are treated as None
                               (no charset matching). Default: None.
            disable_static_mapping: If True, use find_with_files(); if False,
                use find_static(). Default: False.

        Returns:
            FontInfo object with font metadata, or None if font not found.

        Example:
            >>> # Standard resolution (static mapping)
            >>> font = FontInfo.find('ArialMT')
            >>> # Is equivalent to:
            >>> font = FontInfo.lookup_static('ArialMT')
            >>>
            >>> # Font embedding resolution (platform-specific)
            >>> font = FontInfo.find('ArialMT', disable_static_mapping=True)
            >>> # Is equivalent to:
            >>> font = FontInfo.resolve('ArialMT')
        """
        # Emit deprecation warning
        if disable_static_mapping:
            warnings.warn(
                "FontInfo.find(disable_static_mapping=True) is deprecated. "
                "Use FontInfo.resolve() instead for explicit platform font resolution. "
                "This method will be removed in version 1.0.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            return FontInfo.resolve(postscriptname, font_mapping, charset_codepoints)
        else:
            warnings.warn(
                "FontInfo.find() is deprecated. "
                "Use FontInfo.lookup_static() instead for explicit "
                "static font mapping. "
                "This method will be removed in version 1.0.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            return FontInfo.lookup_static(postscriptname, font_mapping)

    @staticmethod
    def _clean_family_name(base_name: str) -> str:
        """Convert CamelCase to space-separated family name.

        This helper converts PostScript base names like "HelveticaNeue" to
        "Helvetica Neue" by inserting spaces before uppercase letters that
        follow lowercase letters.

        Args:
            base_name: Base font name without suffix (e.g., "HelveticaNeue").

        Returns:
            Space-separated family name (e.g., "Helvetica Neue").

        Example:
            >>> FontInfo._clean_family_name("HelveticaNeue")
            'Helvetica Neue'
            >>> FontInfo._clean_family_name("NotoSansJP")
            'Noto Sans JP'
        """
        result = []
        for i, char in enumerate(base_name):
            if i > 0 and char.isupper() and base_name[i - 1].islower():
                result.append(" ")
            result.append(char)

        family = "".join(result)

        # Preserve two-letter abbreviations commonly used in font names
        family = family.replace(" J P", " JP")
        family = family.replace(" K R", " KR")
        family = family.replace(" S C", " SC")
        family = family.replace(" T C", " TC")

        return family

    @staticmethod
    def _parse_suffix_component(suffix: str) -> dict[str, str | float] | None:
        """Parse suffix to extract style and weight.

        This helper parses a single PostScript suffix (e.g., "Bold", "BoldItalic")
        and returns the corresponding style string and fontconfig weight value.

        Case-insensitive: "bold" and "Bold" are treated the same.

        Args:
            suffix: Font suffix (e.g., "Bold", "Italic", "BoldItalic", "W6").

        Returns:
            Dict with "style" and "weight" keys, or None if suffix not recognized.

        Example:
            >>> FontInfo._parse_suffix_component("Bold")
            {'style': 'Bold', 'weight': 200.0}
            >>> FontInfo._parse_suffix_component("bold")
            {'style': 'Bold', 'weight': 200.0}
            >>> FontInfo._parse_suffix_component("BoldItalic")
            {'style': 'Bold Italic', 'weight': 200.0}
            >>> FontInfo._parse_suffix_component("Unknown")
            None
        """
        # Case-insensitive matching: try suffix as-is first, then uppercase version
        # This handles both exact matches and case variations

        # Check compound patterns first (longest matches) - case-sensitive first
        if suffix in COMPOUND_SUFFIXES:
            style, weight = COMPOUND_SUFFIXES[suffix]
            return {"style": style, "weight": weight}

        # Try case-insensitive compound lookup
        for key, (style, weight) in COMPOUND_SUFFIXES.items():
            if key.lower() == suffix.lower():
                return {"style": style, "weight": weight}

        # Check Japanese weight notation (case-insensitive)
        suffix_upper = suffix.upper()
        if suffix_upper in JAPANESE_WEIGHT_SUFFIXES:
            style, weight = JAPANESE_WEIGHT_SUFFIXES[suffix_upper]
            return {"style": style, "weight": weight}

        # Check simple weight suffixes - case-sensitive first
        if suffix in WEIGHT_SUFFIXES:
            style, weight = WEIGHT_SUFFIXES[suffix]
            return {"style": style, "weight": weight}

        # Try case-insensitive weight suffix lookup
        for key, (style, weight) in WEIGHT_SUFFIXES.items():
            if key.lower() == suffix.lower():
                return {"style": style, "weight": weight}

        # Standalone Italic/Oblique (edge case) - case-insensitive
        if suffix.lower() in ("italic", "oblique"):
            # Return capitalized form
            return {"style": suffix.capitalize(), "weight": 80.0}

        return None

    @staticmethod
    def _parse_postscript_name_suffix(
        postscript_name: str,
    ) -> dict[str, str | float] | None:
        """Parse PostScript name suffix to infer family, style, and weight.

        This method attempts to extract font metadata from PostScript names that
        are not in the static mapping by parsing common suffix patterns.

        Two-phase algorithm:
        1. Hyphenated patterns (e.g., "CustomFont-Bold") - primary approach
        2. CamelCase patterns (e.g., "RobotoBold") - conservative fallback

        Args:
            postscript_name: Full PostScript name (e.g., "CustomFont-Bold").

        Returns:
            Dict with "family", "style", "weight" if parsing succeeds, None otherwise.

        Example:
            >>> FontInfo._parse_postscript_name_suffix("CustomFont-Bold")
            {'family': 'Custom Font', 'style': 'Bold', 'weight': 200.0}
            >>> FontInfo._parse_postscript_name_suffix("MyFont-BoldItalic")
            {'family': 'My Font', 'style': 'Bold Italic', 'weight': 200.0}
            >>> FontInfo._parse_postscript_name_suffix("UnknownPattern")
            None
        """
        # Phase 1: Hyphenated patterns (primary approach)
        if "-" in postscript_name:
            parts = postscript_name.rsplit("-", 1)
            if len(parts) == 2:
                base, suffix = parts
                parsed = FontInfo._parse_suffix_component(suffix)
                if parsed:
                    family = FontInfo._clean_family_name(base)
                    return {
                        "family": family,
                        "style": parsed["style"],
                        "weight": parsed["weight"],
                    }

        # Phase 2: CamelCase (safe suffixes only, to avoid false positives)
        for suffix in SAFE_CAMELCASE_SUFFIXES:
            if postscript_name.endswith(suffix):
                base = postscript_name[: -len(suffix)]
                # Validate base name to avoid false positives
                if len(base) >= 3 and base[0].isupper():
                    parsed = FontInfo._parse_suffix_component(suffix)
                    if parsed:
                        family = FontInfo._clean_family_name(base)
                        return {
                            "family": family,
                            "style": parsed["style"],
                            "weight": parsed["weight"],
                        }

        return None

    @staticmethod
    def lookup_static(
        postscriptname: str,
        font_mapping: dict[str, dict[str, float | str]] | None = None,
    ) -> Self | None:
        """Lookup font metadata using custom and static mappings only
        (no platform resolution).

        This method resolves PostScript names to CSS font families without accessing
        system fonts. It is suitable for SVG generation when embed_fonts=False, where
        only CSS font family names are needed and platform-specific font substitution
        would cause visual artifacts.

        Resolution order:
        1. Custom font mapping (if provided)
        2. Static font mapping
           (~4,950 fonts: 539 default + 370 Hiragino + 4,042 Morisawa)
        3. Suffix parsing fallback (infer from common PostScript patterns)
        4. Return None if not found (preserves PostScript name in SVG)

        Args:
            postscriptname: PostScript name of the font (e.g., "ArialMT").
            font_mapping: Optional custom font mapping dictionary. Takes priority
                over static mapping. Format:
                {"PostScriptName": {"family": str, "style": str, "weight": float}}

        Returns:
            FontInfo object with family/style/weight (no file path),
            or None if not found. When None is returned, the PostScript name
            will be preserved in the SVG output.

        Example:
            >>> # Resolve common font (found in static mapping)
            >>> font = FontInfo.lookup_static('ArialMT')
            >>> assert font.family == 'Arial'
            >>> assert font.file == ''  # No file path
            >>>
            >>> # Resolve uncommon font (not in static mapping)
            >>> font = FontInfo.lookup_static('UnknownFont')
            >>> assert font is None  # Preserves PostScript name in SVG
        """
        # 1. Check custom mapping first
        if font_mapping:
            custom_data = _font_mapping.find_in_mapping(postscriptname, font_mapping)
            if custom_data:
                logger.debug(
                    f"Resolved '{postscriptname}' via custom font mapping: "
                    f"{custom_data['family']}"
                )
                return FontInfo(
                    postscript_name=postscriptname,
                    file="",
                    family=str(custom_data["family"]),
                    style=str(custom_data["style"]),
                    weight=float(custom_data["weight"]),
                )

        # 2. Check static mapping
        static_data = _font_mapping.find_in_mapping(postscriptname, None)
        if static_data:
            logger.debug(
                f"Resolved '{postscriptname}' via static font mapping: "
                f"{static_data['family']}"
            )
            return FontInfo(
                postscript_name=postscriptname,
                file="",
                family=str(static_data["family"]),
                style=str(static_data["style"]),
                weight=float(static_data["weight"]),
            )

        # 3. Try suffix parsing fallback
        parsed = FontInfo._parse_postscript_name_suffix(postscriptname)
        if parsed:
            logger.debug(
                f"Resolved '{postscriptname}' via suffix parsing: "
                f"{parsed['family']} ({parsed['style']}, weight={parsed['weight']})"
            )
            return FontInfo(
                postscript_name=postscriptname,
                file="",
                family=str(parsed["family"]),
                style=str(parsed["style"]),
                weight=float(parsed["weight"]),
            )

        # 4. Not found - return None (no platform fallback)
        logger.debug(
            f"Font '{postscriptname}' not found in mappings or suffix parsing. "
            "Keeping PostScript name in SVG."
        )
        return None

    @staticmethod
    def _resolve_from_custom_mapping_with_file(
        postscriptname: str,
        font_mapping: dict[str, dict[str, float | str]],
        charset_codepoints: set[int] | None = None,
    ) -> Self | None:
        """Resolve font from custom mapping with file validation.

        This helper method handles custom font mapping resolution when file paths
        are required (e.g., for font embedding). It validates that the mapping
        contains all required fields and that the font file exists.

        Args:
            postscriptname: PostScript name of the font (e.g., "ArialMT").
            font_mapping: Custom font mapping dictionary.
            charset_codepoints: Optional Unicode codepoints (unused but kept for
                               consistency with resolve() signature).

        Returns:
            FontInfo with file path if found and valid, None otherwise.
            Falls back to None if file missing or doesn't exist.
        """
        _ = charset_codepoints  # Unused but kept for signature consistency

        # Check if font exists in custom mapping (access raw data directly)
        if postscriptname not in font_mapping:
            return None

        custom_data = font_mapping[postscriptname]

        # Validate custom mapping has required fields including file path
        if not (
            "family" in custom_data
            and "style" in custom_data
            and "weight" in custom_data
            and "file" in custom_data
            and custom_data["file"]  # Must be non-empty
        ):
            # Custom mapping found but missing file path
            # - fall back to platform resolution
            logger.debug(
                f"Custom mapping for '{postscriptname}' found "
                f"but missing 'file' field. Falling back to platform resolution."
            )
            return None

        file_path = str(custom_data["file"])
        # Validate file exists
        if not os.path.exists(file_path):
            logger.warning(
                f"Custom mapping for '{postscriptname}' specifies file '{file_path}' "
                "but file does not exist. Falling back to platform resolution."
            )
            return None

        logger.debug(
            f"Resolved '{postscriptname}' via custom font mapping with file path: "
            f"{file_path}"
        )
        return FontInfo(
            postscript_name=postscriptname,
            file=file_path,
            family=str(custom_data["family"]),
            style=str(custom_data["style"]),
            weight=float(custom_data["weight"]),
        )

    @staticmethod
    def resolve(
        postscriptname: str,
        font_mapping: dict[str, dict[str, float | str]] | None = None,
        charset_codepoints: set[int] | None = None,
    ) -> Self | None:
        """Resolve font with file path using platform-specific resolution.

        Uses fontconfig (Linux/macOS) or Windows registry to locate font files.
        Suitable for font embedding where actual font files are needed.

        Args:
            postscriptname: PostScript name of the font (e.g., "ArialMT").
            font_mapping: Optional custom mapping with file paths. Must include "file"
                         field with existing font file path. Format:
                         {"PostScriptName": {"family": str, "style": str,
                                            "weight": float, "file": str}}
                         If mapping lacks "file" field or file doesn't exist, falls back
                         to platform resolution.
            charset_codepoints: Optional Unicode codepoints for charset-based matching.
                               Prioritizes fonts with better glyph coverage.
                               Empty sets are treated as None (no charset matching).

        Returns:
            FontInfo with non-empty file path, or None if not found. File path is
            guaranteed to be non-empty when FontInfo is returned.

        Example:
            >>> font = FontInfo.resolve('ArialMT')
            >>> if font:
            ...     print(f"Font file: {font.file}")  # Always has file path
        """
        # 1. Check custom mapping first (must have file path for embedding)
        if font_mapping:
            resolved = FontInfo._resolve_from_custom_mapping_with_file(
                postscriptname, font_mapping, charset_codepoints
            )
            if resolved:
                return resolved

        # 2. Platform-specific resolution (skip static mapping - optimization)
        # Try fontconfig (Linux/macOS)
        if HAS_FONTCONFIG:
            result = FontInfo._resolve_via_fontconfig(
                postscriptname, charset_codepoints
            )
            if result:
                return result

        # Try Windows registry (Windows)
        elif HAS_WINDOWS_FONTS:
            result = FontInfo._resolve_via_windows(postscriptname, charset_codepoints)
            if result:
                return result

        # 3. Not found
        if not HAS_FONTCONFIG and not HAS_WINDOWS_FONTS:
            logger.warning(
                f"Font '{postscriptname}' not found: "
                "platform-specific font resolution not available. "
                "Consider providing a custom font mapping "
                "via the font_mapping parameter."
            )
        else:
            platform_name = "fontconfig" if HAS_FONTCONFIG else "Windows registry"
            logger.warning(
                f"Font '{postscriptname}' not found via {platform_name}. "
                "Make sure the font is installed on your system, or provide a custom "
                "font mapping via the font_mapping parameter."
            )
        return None


def encode_font_data_uri(font_path: str) -> str:
    """Encode a font file as a base64 data URI.

    Args:
        font_path: Absolute path to the font file.

    Returns:
        Data URI string (e.g., 'data:font/ttf;base64,...').

    Raises:
        FileNotFoundError: If font file doesn't exist.
        IOError: If font file can't be read.

    Example:
        >>> data_uri = encode_font_data_uri('/usr/share/fonts/arial.ttf')
        >>> print(data_uri[:50])
        data:font/ttf;base64,AAEAAAATAQAABAAwR1BPUw...
    """
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"Font file not found: {font_path}")

    # Determine MIME type from file extension
    ext = os.path.splitext(font_path)[1].lower()
    mime_types = {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    mime_type = mime_types.get(ext, "font/ttf")  # Default to ttf

    # Read and encode font file
    try:
        with open(font_path, "rb") as f:
            font_data = f.read()
    except IOError as e:
        raise IOError(f"Failed to read font file '{font_path}': {e}") from e

    base64_data = base64.b64encode(font_data).decode("utf-8")
    return f"data:{mime_type};base64,{base64_data}"


def encode_font_bytes_to_data_uri(font_bytes: bytes, font_format: str) -> str:
    """Encode font bytes as a base64 data URI.

    This function is used for embedding subset or converted fonts that
    are already in memory as bytes (e.g., from fontTools subsetting).

    Args:
        font_bytes: Font file data as bytes.
        font_format: Font format - "ttf", "otf", or "woff2".

    Returns:
        Data URI string (e.g., 'data:font/woff2;base64,...').

    Raises:
        ValueError: If font_format is unsupported.

    Example:
        >>> font_bytes = b'...'  # Subset font data
        >>> data_uri = encode_font_bytes_to_data_uri(font_bytes, "woff2")
        >>> print(data_uri[:30])
        data:font/woff2;base64,d09GMg...
    """
    mime_types = {
        "ttf": "font/ttf",
        "otf": "font/otf",
        "woff2": "font/woff2",
    }

    if font_format not in mime_types:
        raise ValueError(
            f"Unsupported font format: {font_format}. "
            f"Supported formats: {', '.join(mime_types.keys())}"
        )

    mime_type = mime_types[font_format]
    base64_data = base64.b64encode(font_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{base64_data}"


def encode_font_with_options(
    font_path: str,
    cache: dict[str, str],
    subset_codepoints: set[int] | None = None,
    font_format: str = "ttf",
) -> str:
    """Encode a font file as a data URI with optional subsetting and caching.

    This helper consolidates the logic for encoding fonts with subsetting
    support and cache management.

    Args:
        font_path: Path to the font file.
        cache: Dictionary to use for caching encoded data URIs.
        subset_codepoints: Optional set of Unicode codepoints (integers)
            to subset the font to. If None, the full font is encoded.
        font_format: Font format for output: "ttf", "otf", or "woff2".

    Returns:
        Data URI string for the encoded font.

    Raises:
        ImportError: If subsetting is requested but fonttools is not available.
        FileNotFoundError: If font file doesn't exist.
        IOError: If font file can't be read.

    Note:
        - Cache keys include format and codepoint count for subset fonts
        - Full fonts use just the file path as cache key
        - Missing codepoints trigger fallback to full font with warning
    """
    # Subsetting path
    if subset_codepoints:
        # Create cache key for subset fonts (include format and codepoint count)
        cache_key = f"{font_path}:{font_format}:{len(subset_codepoints)}"

        if cache_key not in cache:
            logger.debug(
                f"Subsetting font: {font_path} -> {font_format} "
                f"({len(subset_codepoints)} codepoints)"
            )
            try:
                font_bytes = font_subsetting.subset_font(  # type: ignore
                    input_path=font_path,
                    output_format=font_format,
                    unicode_codepoints=subset_codepoints,
                )
                data_uri = encode_font_bytes_to_data_uri(font_bytes, font_format)
                cache[cache_key] = data_uri
            except Exception as e:
                logger.warning(
                    f"Failed to subset font '{font_path}': {e}. "
                    "Falling back to full font"
                )
                # Fall back to full font
                if font_path not in cache:
                    logger.debug(f"Encoding full font: {font_path}")
                    cache[font_path] = encode_font_data_uri(font_path)
                return cache[font_path]
        return cache[cache_key]

    # Full font encoding path
    if font_path not in cache:
        logger.debug(f"Encoding font: {font_path}")
        cache[font_path] = encode_font_data_uri(font_path)
    return cache[font_path]


def create_charset_codepoints(chars: set[str]) -> set[int]:
    """Create set of Unicode codepoints from characters.

    This function converts a set of Unicode characters to a set of
    integer codepoints suitable for charset-based font matching.

    Args:
        chars: Set of Unicode characters (e.g., {"A", "あ", "中"}).

    Returns:
        Set of Unicode codepoints (integers). Returns empty set if chars is empty.
        Multi-codepoint characters (emoji with modifiers) are split into
        individual codepoints.

    Example:
        >>> chars = {"H", "e", "l", "o"}
        >>> codepoints = create_charset_codepoints(chars)
        >>> codepoints
        {72, 101, 108, 111}
        >>> create_charset_codepoints(set())
        set()
    """
    # Convert characters to codepoints (handles multi-codepoint characters like emoji)
    codepoint_set = set()
    for char in chars:
        for code_point in char:
            codepoint_set.add(ord(code_point))

    if codepoint_set:
        logger.debug(
            f"Created {len(codepoint_set)} codepoints from {len(chars)} characters"
        )

    return codepoint_set


def create_file_url(font_path: str) -> str:
    """Create a file:// URL from an absolute font file path.

    This function converts an absolute file path to a properly formatted file:// URL
    suitable for use in CSS @font-face rules with browser-based rasterizers like
    PlaywrightRasterizer.

    Args:
        font_path: Absolute path to the font file.

    Returns:
        File URL string (e.g., 'file:///usr/share/fonts/arial.ttf').

    Raises:
        ValueError: If font_path is not absolute.
        FileNotFoundError: If font file doesn't exist.

    Note:
        - Handles cross-platform paths (Windows, Linux, macOS)
        - Properly escapes special characters (spaces, non-ASCII)
        - Requires absolute paths (relative paths are rejected)
        - URL format: file:// + absolute_path (with proper encoding)

    Example:
        >>> # Linux/macOS
        >>> create_file_url('/usr/share/fonts/arial.ttf')
        'file:///usr/share/fonts/arial.ttf'

        >>> # Windows
        >>> create_file_url('C:\\\\Windows\\\\Fonts\\\\arial.ttf')
        'file:///C:/Windows/Fonts/arial.ttf'

        >>> # Path with spaces
        >>> create_file_url('/usr/share/fonts/My Font.ttf')
        'file:///usr/share/fonts/My%20Font.ttf'

        >>> # Non-ASCII characters
        >>> create_file_url('/fonts/日本語/font.ttf')
        'file:///fonts/%E6%97%A5%E6%9C%AC%E8%AA%9E/font.ttf'
    """
    # Validate file existence
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"Font file not found: {font_path}")

    # Ensure absolute path (required for file:// URLs)
    abs_path = os.path.abspath(font_path)

    # Convert to Path object for cross-platform handling
    path_obj = Path(abs_path)

    # Convert to POSIX path (forward slashes) for URL
    # Windows: C:\Fonts\arial.ttf -> C:/Fonts/arial.ttf -> /C:/Fonts/arial.ttf
    # Unix: /usr/share/fonts/arial.ttf -> /usr/share/fonts/arial.ttf
    if sys.platform == "win32":
        # Windows: Convert backslashes to forward slashes
        posix_path = path_obj.as_posix()
        # Ensure leading slash for Windows drive letters: C:/... -> /C:/...
        if not posix_path.startswith("/"):
            posix_path = "/" + posix_path
    else:
        # Unix: Already has leading slash
        posix_path = str(path_obj)

    # URL-encode the path to handle spaces and special characters
    # Use quote() with safe="/:@" to preserve path structure
    # - "/" must be safe (path separator)
    # - ":" must be safe (Windows drive letters)
    # - "@" is safe for potential UNC paths (though not fully supported)
    encoded_path = urllib.parse.quote(posix_path, safe="/:@")

    # Construct file:// URL
    # Format: file:// + encoded_path (already has leading /)
    # Result: file:///absolute/path or file:///C:/Windows/path
    return f"file://{encoded_path}"
