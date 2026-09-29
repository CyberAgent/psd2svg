"""Font subsetting utilities for reducing embedded font file sizes."""

import html
import io
import logging
import re
import xml.etree.ElementTree as ET

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

logger = logging.getLogger(__name__)


def extract_used_unicode(svg_tree: ET.Element) -> dict[str, set[str]]:
    """Extract Unicode characters per font-family from SVG text elements.

    This function analyzes all <text>, <tspan>, and XHTML text elements (p, span
    from foreignObject) in the SVG tree to determine which Unicode characters are
    used by each font family.

    Args:
        svg_tree: Root SVG element to analyze.

    Returns:
        Dictionary mapping font-family names to sets of Unicode characters.
        Example: {"Arial": {"A", "B", "C"}, "Noto Sans JP": {"あ", "い"}}

    Note:
        - Handles nested <tspan> elements and XHTML elements
        - Decodes XML entities (e.g., &lt;, &#x4E00;)
        - Extracts font-family from style attributes
        - Returns empty dict if no text elements found
    """
    font_usage: dict[str, set[str]] = {}

    # Build parent map for inheritance lookup
    parent_map = {c: p for p in svg_tree.iter() for c in p}

    # Find all text, tspan, and XHTML text elements (p, span from foreignObject)
    for element in svg_tree.iter():
        tag_name = _get_local_tag_name(element)
        if tag_name not in ("text", "tspan", "p", "span"):
            continue

        # Extract font-family from element or parent
        font_family = _extract_font_family_with_inheritance(element, parent_map)
        if not font_family:
            continue

        # Extract text content for this element only (not children)
        text_content = _extract_direct_text_content(element)
        if not text_content:
            continue

        # Add characters to the set for this font
        if font_family not in font_usage:
            font_usage[font_family] = set()

        font_usage[font_family].update(text_content)

    logger.debug(
        f"Extracted Unicode usage: {len(font_usage)} font(s), "
        f"{sum(len(chars) for chars in font_usage.values())} unique char(s) total"
    )

    return font_usage


def load_font_face(
    input_path: str, face_index: int = 0, named_instance: int | None = None
) -> TTFont:
    """Load one face of a font file, pinned to a named instance if given.

    Args:
        input_path: Path to the font file.
        face_index: Zero-based face index for TTC/OTC files.
        named_instance: Zero-based index into the ``fvar`` named instances of a
            variable font. The instance's axis coordinates are applied, producing
            a static font. None keeps the font as stored.

    Returns:
        The loaded font.

    Raises:
        ValueError: If named_instance is out of range for the font.
    """
    font = TTFont(input_path, fontNumber=face_index)
    if named_instance is None:
        return font

    instances = font["fvar"].instances if "fvar" in font else []
    if not 0 <= named_instance < len(instances):
        font.close()
        raise ValueError(
            f"Named instance {named_instance} not found in face {face_index} "
            f"of '{input_path}' ({len(instances)} instance(s))"
        )
    coordinates = instances[named_instance].coordinates
    return instancer.instantiateVariableFont(font, coordinates, inplace=True)


def subset_font(
    input_path: str,
    output_format: str,
    unicode_codepoints: set[int],
    face_index: int = 0,
    named_instance: int | None = None,
) -> bytes:
    """Subset a font file to include only specified Unicode codepoints.

    This function uses fontTools (pyftsubset) to create a minimal font file
    containing only the glyphs needed for the specified codepoints.

    Args:
        input_path: Path to input font file (TTF/OTF).
        output_format: Output format - "ttf", "otf", or "woff2".
        unicode_codepoints: Set of Unicode codepoints (integers) to include in
            the subset.
        face_index: Zero-based face index for TTC/OTC input files.
        named_instance: Zero-based ``fvar`` named instance to pin a variable
            font to before subsetting. None keeps the font as stored.

    Returns:
        Subset font file as bytes.

    Raises:
        ImportError: If fonttools package is not installed.
        Exception: If subsetting fails (invalid font, I/O error, etc.).

    Example:
        >>> codepoints = {0x41, 0x42, 0x43, 0x3042}  # A, B, C, あ
        >>> font_bytes = subset_font("/usr/share/fonts/arial.ttf", "woff2", codepoints)
        >>> len(font_bytes)  # Much smaller than original
        8432
    """
    if output_format not in ("ttf", "otf", "woff2"):
        raise ValueError(
            f"Unsupported font format: {output_format}. "
            f"Supported formats: ttf, otf, woff2"
        )

    if not unicode_codepoints:
        logger.warning(
            "No Unicode codepoints provided for subsetting, using all glyphs"
        )

    # Convert to sorted list for fontTools
    unicodes = sorted(unicode_codepoints)

    logger.debug(
        f"Subsetting font: {input_path} -> {output_format} "
        f"({len(unicode_codepoints)} codepoint(s))"
    )

    try:
        # Load the font
        font = load_font_face(input_path, face_index, named_instance)

        # Create subsetter with options
        subsetter = subset.Subsetter()

        # Subset options
        options = subset.Options()
        options.drop_tables = []  # Keep all tables by default
        options.layout_features = ["*"]  # Preserve all OpenType features
        options.name_IDs = ["*"]  # Preserve all name table entries
        options.name_languages = ["*"]  # Preserve all languages
        options.notdef_outline = True  # Keep .notdef glyph
        options.glyph_names = True  # Preserve glyph names (helps debugging)

        subsetter.options = options

        # Populate subset with Unicode characters
        if unicodes:
            subsetter.populate(unicodes=unicodes)
        else:
            # If no characters specified, include all glyphs
            subsetter.populate(glyphs=font.getGlyphOrder())

        # Perform subsetting
        subsetter.subset(font)

        # Save to bytes (using a temporary in-memory approach)
        output_buffer = io.BytesIO()

        # Set flavor for WOFF2 on the font object before saving
        if output_format == "woff2":
            font.flavor = "woff2"

        font.save(output_buffer)
        font_bytes = output_buffer.getvalue()

        logger.debug(
            f"Subsetting complete: {len(font_bytes)} bytes "
            f"(~{len(font_bytes) / 1024:.1f} KB)"
        )

        return font_bytes

    except Exception as e:
        logger.error(f"Font subsetting failed for {input_path}: {e}")
        raise


def _get_local_tag_name(element: ET.Element) -> str:
    """Extract local tag name from element (handles namespaces).

    Args:
        element: XML element.

    Returns:
        Local tag name without namespace prefix.

    Example:
        >>> elem.tag = "{http://www.w3.org/2000/svg}text"
        >>> _get_local_tag_name(elem)
        "text"
    """
    tag = element.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_font_family(element: ET.Element) -> str | None:
    """Extract font-family from element, returning LAST font in fallback chain.

    For fallback chains like "Arial", "DejaVu Sans", returns "DejaVu Sans"
    (the actually embedded font for subsetting).

    Args:
        element: XML element (text or tspan).

    Returns:
        Font family name (last in chain), or None if not found.

    Example:
        >>> _extract_font_family(
        ...     <text style="font-family: 'Arial', 'DejaVu Sans'; ...">
        ... )
        "DejaVu Sans"
        >>> _extract_font_family(<text font-family="'Helvetica', 'Arial'">)
        "Arial"
    """
    # Try style attribute first
    style = element.get("style", "")
    if style:
        match = re.search(r"font-family:\s*([^;]+)", style)
        if match:
            font_family_value = match.group(1).strip()
            # Parse comma-separated list of fonts
            families = [f.strip().strip("'\"") for f in font_family_value.split(",")]
            # Return last font (the embedded one in fallback chain)
            return families[-1] if families else None

    # Try direct font-family attribute
    font_family = element.get("font-family")
    if font_family:
        # Parse comma-separated list
        families = [f.strip().strip("'\"") for f in font_family.split(",")]
        # Return last font (the embedded one in fallback chain)
        return families[-1] if families else None

    return None


def _extract_font_family_with_inheritance(
    element: ET.Element, parent_map: dict[ET.Element, ET.Element]
) -> str | None:
    """Extract font-family from element or inherited from parent.

    Walks up the element tree to find the first font-family declaration.
    This handles cases where <tspan> elements inherit font-family from
    their parent <text> element.

    Args:
        element: XML element (text or tspan).
        parent_map: Dictionary mapping child elements to their parents.

    Returns:
        Font family name, or None if not found in element or ancestors.

    Example:
        >>> <text font-family="Arial"><tspan>Hello</tspan></text>
        >>> _extract_font_family_with_inheritance(tspan_element, parent_map)
        "Arial"
    """
    # Try current element first
    font_family = _extract_font_family(element)
    if font_family:
        return font_family

    # Walk up parent tree to find inherited font-family
    current = element
    while current in parent_map:
        current = parent_map[current]
        font_family = _extract_font_family(current)
        if font_family:
            return font_family

    return None


def _extract_text_content(element: ET.Element) -> str:
    """Extract and decode all text content from element (including entities).

    Args:
        element: XML element.

    Returns:
        Decoded text content with XML entities resolved and control characters filtered.

    Note:
        - Handles numeric character references (&#x4E00;, &#20013;)
        - Handles named entities (&lt;, &gt;, &amp;, etc.)
        - Recursively includes text from child elements
        - Filters out control characters (codepoints 0-31) which are not rendered in SVG
    """
    # Collect all text (element.text and tail from all descendants)
    text_parts = []

    if element.text:
        text_parts.append(element.text)

    for child in element:
        # Recursively get text from children
        child_text = _extract_text_content(child)
        if child_text:
            text_parts.append(child_text)
        # Also include tail text (text after child element)
        if child.tail:
            text_parts.append(child.tail)

    raw_text = "".join(text_parts)

    # Decode HTML/XML entities
    decoded_text = html.unescape(raw_text)

    # Filter out control characters (C0: 0-31, DEL: 127, C1: 128-159)
    # These are not rendered in SVG text and cause incorrect font matching
    # (e.g., newline causes Arial to be substituted with LastResort on macOS)
    decoded_text = "".join(
        char
        for char in decoded_text
        if ord(char) >= 32 and not (127 <= ord(char) <= 159)
    )

    return decoded_text


def _extract_direct_text_content(element: ET.Element) -> str:
    """Extract text content directly owned by this element (not children).

    This function extracts only the text that belongs to the current element,
    not text from child elements. This is important for font subsetting because
    child elements may have different font-family attributes.

    Args:
        element: XML element.

    Returns:
        Decoded text content (only element.text, not children).

    Example:
        <text>Hello<tspan>World</tspan></text>
        Returns: "Hello" (not "HelloWorld")
    """
    if element.text:
        # Decode HTML/XML entities
        return html.unescape(element.text)
    return ""


def get_font_usage_from_svg(svg_tree: ET.Element) -> dict[str, set[str]]:
    """Get font usage information from SVG for subsetting.

    This is a convenience wrapper around extract_used_unicode() that
    logs appropriate messages about font usage.

    Args:
        svg_tree: Root SVG element to analyze.

    Returns:
        Dictionary mapping font-family names to sets of Unicode characters.
    """
    font_usage = extract_used_unicode(svg_tree)
    logger.debug(
        f"Extracted {len(font_usage)} font(s) with "
        f"{sum(len(chars) for chars in font_usage.values())} unique char(s)"
    )
    return font_usage


def _chars_to_unicode_list(chars: set[str]) -> list[int]:
    """Convert set of characters to list of Unicode code points.

    Args:
        chars: Set of Unicode characters (e.g., {"A", "あ", "中"}).

    Returns:
        List of Unicode code points (e.g., [0x41, 0x3042, 0x4E2D]).

    Note:
        - Handles multi-codepoint characters (emoji, combining marks)
        - Returns unique code points sorted for deterministic output
    """
    codepoints = set()

    for char in chars:
        # Each character may contain multiple code points (e.g., emoji with modifiers)
        for code_point in char:
            codepoints.add(ord(code_point))

    return sorted(codepoints)
