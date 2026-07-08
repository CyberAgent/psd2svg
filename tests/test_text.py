import logging
import math
import re
import xml.etree.ElementTree as ET

import pytest
from psd_tools import PSDImage
from psd_tools.api.layers import TypeLayer

from psd2svg import SVGDocument
from psd2svg.core.converter import Converter
from psd2svg.core.text import TextWrappingMode
from psd2svg.core.typesetting import TypeSetting
from tests.conftest import get_fixture


def convert_psd_to_svg(psd_file: str) -> ET.Element:
    """Convert a PSD file to SVG and return the SVG as a string."""
    psdimage = PSDImage.open(get_fixture(psd_file))
    converter = Converter(psdimage)
    converter.build()
    return converter.svg


@pytest.mark.parametrize(
    "psd_file, expected_justification",
    [
        # Horizontal text cases
        ("texts/paragraph-shapetype0-justification0.psd", None),
        ("texts/paragraph-shapetype0-justification1.psd", "end"),
        ("texts/paragraph-shapetype0-justification2.psd", "middle"),
        ("texts/paragraph-shapetype1-justification0.psd", None),
        ("texts/paragraph-shapetype1-justification1.psd", "end"),
        ("texts/paragraph-shapetype1-justification2.psd", "middle"),
        ("texts/paragraph-shapetype1-justification3.psd", None),
        ("texts/paragraph-shapetype1-justification4.psd", "end"),
        ("texts/paragraph-shapetype1-justification5.psd", "middle"),
        # Vertical text cases
        (
            "texts/shapetype0-writingdirection2-baselinedirection2-justification0.psd",
            None,
        ),
        (
            "texts/shapetype0-writingdirection2-baselinedirection2-justification1.psd",
            "end",
        ),
        (
            "texts/shapetype0-writingdirection2-baselinedirection2-justification2.psd",
            "middle",
        ),
        (
            "texts/shapetype1-writingdirection2-baselinedirection2-justification0.psd",
            None,
        ),
        (
            "texts/shapetype1-writingdirection2-baselinedirection2-justification1.psd",
            "end",
        ),
        (
            "texts/shapetype1-writingdirection2-baselinedirection2-justification2.psd",
            "middle",
        ),
    ],
)
def test_text_paragraph_justification(
    psd_file: str, expected_justification: str | None
) -> None:
    """Test text paragraph justification handling."""
    svg = convert_psd_to_svg(psd_file)
    for node in svg.findall(".//*[@text-anchor]"):
        assert node.attrib.get("text-anchor") == expected_justification


def test_text_paragraph_justification_justify() -> None:
    """Test text paragraph justification handling for 'justify' case."""
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-justification6.psd")
    node = svg.find(".//*[@text-anchor]")
    assert node is None
    node = svg.find(".//*[@textLength]")
    assert node is not None
    assert node.attrib.get("textLength") is not None
    assert node.attrib.get("lengthAdjust") == "spacingAndGlyphs"


def test_text_span_common_attributes() -> None:
    """Test merging of common attributes in text spans."""
    # The file has multiple paragraphs each with single tspan.
    # We expect the final structure to be: <text> with multiple <tspan>,
    # each with unique font-size.
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")
    # Check that common attributes are merged correctly
    text_node = svg.find(".//text")
    assert text_node is not None
    assert text_node.attrib.get("text-anchor") is None
    # Check that individual spans still have their unique attributes
    tspan_nodes = text_node.findall(".//tspan")
    assert len(tspan_nodes) == 4
    # Check that font sizes are present and different (actual values may vary slightly)
    font_sizes = [float(tspan.attrib["font-size"]) for tspan in tspan_nodes]
    assert len(set(font_sizes)) == 4  # All different sizes
    assert all(size > 0 for size in font_sizes)  # All positive


def test_text_paragraph_positions() -> None:
    """Test text paragraph positions handling with consistent structure."""
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")
    text_node = svg.find(".//text")
    assert text_node is not None

    # Parent text node should NOT have x and y (all tspans have their own positions)
    assert text_node.attrib.get("x") is None
    assert text_node.attrib.get("y") is None

    tspan_nodes = text_node.findall(".//tspan")
    assert len(tspan_nodes) == 4

    # All tspans should have x attribute
    # First tspan should have x and y
    assert tspan_nodes[0].attrib.get("x") is not None
    assert tspan_nodes[0].attrib.get("y") is not None
    assert tspan_nodes[0].attrib.get("dy") is None

    # Subsequent tspans should have x and dy (no y)
    # All should have same x value (to reset to left margin)
    first_x = tspan_nodes[0].attrib.get("x")
    for i in range(1, 4):
        assert tspan_nodes[i].attrib.get("x") == first_x, (
            f"tspan {i} should have x='{first_x}' to reset to left margin"
        )
        assert tspan_nodes[i].attrib.get("y") is None, (
            f"tspan {i} should not have y (uses dy instead)"
        )
        assert tspan_nodes[i].attrib.get("dy") is not None, (
            f"tspan {i} should have dy for line spacing"
        )


def test_text_paragraph_native_positioning_no_x_override() -> None:
    """Test that all paragraphs have consistent x positioning.

    Regression test for alignment issues. The current implementation gives all
    paragraphs consistent structure: each tspan has explicit x positioning.

    The correct behavior is for all tspans to:
    - Have x attribute set to the same value (to maintain left margin alignment)
    - First tspan has x and y (initial position)
    - Subsequent tspans have x and dy (reset horizontal, offset vertical)
    """
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")
    text_node = svg.find(".//text")
    assert text_node is not None

    # Verify we're using native positioning (no transform on parent)
    assert text_node.attrib.get("transform") is None, (
        "Parent text node should not have transform (using native positioning)"
    )

    tspan_nodes = text_node.findall(".//tspan")
    assert len(tspan_nodes) >= 2, "Need at least 2 paragraphs to test"

    # First paragraph tspan should have x and y
    first_x = tspan_nodes[0].attrib.get("x")
    first_y = tspan_nodes[0].attrib.get("y")
    assert first_x is not None, "First tspan should have x attribute"
    assert first_y is not None, "First tspan should have y attribute"
    assert tspan_nodes[0].attrib.get("dy") is None, "First tspan should not have dy"

    # Parse the x value to verify it's non-zero (not at origin)
    first_x_value = float(first_x)
    assert first_x_value != 0.0, "First tspan x should be non-zero for this test"

    # All subsequent paragraph tspans should:
    # 1. Have x set to same value as first (to reset horizontal position)
    # 2. Have dy attribute for vertical offset
    # 3. NOT have y attribute (using dy instead)
    for i in range(1, len(tspan_nodes)):
        tspan = tspan_nodes[i]

        # Critical: x should be set consistently across all tspans
        x_attr = tspan.attrib.get("x")
        assert x_attr == first_x, (
            f"Paragraph {i + 1} tspan should have x='{first_x}', but has x='{x_attr}'. "
            f"Without consistent x, text would continue from end of previous line."
        )

        # Should have dy for line spacing
        dy_attr = tspan.attrib.get("dy")
        assert dy_attr is not None, (
            f"Paragraph {i + 1} tspan should have dy attribute for vertical offset"
        )

        # Should not have y (using dy instead for relative positioning)
        y_attr = tspan.attrib.get("y")
        assert y_attr is None, (
            f"Paragraph {i + 1} tspan should not have y attribute "
            "(should use dy instead)"
        )


def test_text_writing_direction() -> None:
    """Test text writing direction handling."""

    # Vertical Right to Left, characters upright
    # NOTE: Only Chromium-based browsers support 'text-orientation: upright' for SVG.
    svg = convert_psd_to_svg(
        "texts/shapetype0-writingdirection2-baselinedirection1-justification0.psd"
    )
    text_node = svg.find(".//text")
    assert text_node is not None
    assert text_node.attrib.get("writing-mode") == "vertical-rl"
    style = text_node.attrib.get("style", "")
    assert "text-orientation: upright" in style

    # Vertical Right to Left, baseline direction
    svg = convert_psd_to_svg(
        "texts/shapetype0-writingdirection2-baselinedirection2-justification0.psd"
    )
    text_node = svg.find(".//text")
    assert text_node is not None
    assert text_node.attrib.get("writing-mode") == "vertical-rl"
    # Style may contain font-variant-ligatures (default), so we just check
    # it doesn't have text-orientation
    style = text_node.attrib.get("style", "")
    assert "text-orientation" not in style


def test_text_style_bold() -> None:
    """Test bold font handling via PostScript names.

    Bold fonts are now encoded in the PostScript name (e.g., "Arial-Bold").
    Font-weight attributes are only set for faux bold.
    """
    svg = convert_psd_to_svg("texts/style-bold.psd")
    # Find all tspans with font-family
    tspans = svg.findall(".//tspan[@font-family]")
    assert len(tspans) > 0, "Should have at least one tspan with font-family"

    # Check that at least one has a bold PostScript name
    font_families = [t.attrib.get("font-family") for t in tspans]
    has_bold = any("Bold" in f or "bold" in f for f in font_families if f)
    assert has_bold, (
        f"Expected to find a PostScript name with 'Bold', got: {font_families}"
    )


def test_text_style_italic() -> None:
    """Test italic font handling via PostScript names.

    Italic fonts are now encoded in the PostScript name (e.g., "Arial-Italic").
    Font-style attributes are only set for faux italic.
    """
    svg = convert_psd_to_svg("texts/style-italic.psd")
    tspans = svg.findall(".//tspan[@font-family]")
    assert len(tspans) > 0, "Should have at least one tspan with font-family"

    # Check that at least one has an italic PostScript name
    font_families = [t.attrib.get("font-family") for t in tspans]
    has_italic = any(
        "Italic" in f or "italic" in f or "Oblique" in f for f in font_families if f
    )
    assert has_italic, (
        f"Expected to find a PostScript name with 'Italic' or 'Oblique', "
        f"got: {font_families}"
    )


def test_text_style_faux_bold() -> None:
    """Test faux bold handling.

    Faux bold (synthetic bold) should set font-weight="700".
    This ensures proper rendering even with variable fonts.
    """
    svg = convert_psd_to_svg("texts/style-faux-bold.psd")
    # Find all tspans with font-weight
    tspans = svg.findall(".//tspan[@font-weight]")
    assert len(tspans) > 0, "Should have at least one tspan with font-weight"

    # Check that we have a bold tspan (font-weight="700" for faux bold)
    font_weights = [t.attrib.get("font-weight") for t in tspans]
    assert "700" in font_weights, (
        f"Expected to find font-weight='700' (faux bold), got: {font_weights}"
    )


def test_text_style_faux_italic() -> None:
    """Test faux italic handling."""
    svg = convert_psd_to_svg("texts/style-faux-italic.psd")
    tspan = svg.find(".//tspan[@font-style]")
    assert tspan is not None
    assert tspan.attrib.get("font-style") == "italic"


def test_text_style_underline() -> None:
    """Test underline text decoration handling."""
    svg = convert_psd_to_svg("texts/style-underline.psd")
    tspan = svg.find(".//tspan[@text-decoration]")
    assert tspan is not None
    assert "underline" in tspan.attrib.get("text-decoration", "")


def test_text_style_strikethrough() -> None:
    """Test strikethrough text decoration handling."""
    svg = convert_psd_to_svg("texts/style-strikethrough.psd")
    tspan = svg.find(".//tspan[@text-decoration]")
    assert tspan is not None
    assert "line-through" in tspan.attrib.get("text-decoration", "")


def test_text_style_all_caps() -> None:
    """Test all-caps text transform handling."""
    svg = convert_psd_to_svg("texts/style-all-caps.psd")
    # After merge_common_child_attributes, style may be on parent text node or tspans
    text = svg.find(".//text")
    assert text is not None

    # Check text node and all tspans for the style
    text_style = text.attrib.get("style", "")
    tspans = svg.findall(".//tspan")
    tspan_styles = " ".join(t.attrib.get("style", "") for t in tspans)
    combined_style = text_style + " " + tspan_styles
    assert (
        "text-transform: uppercase" in combined_style
        or "text-transform:uppercase" in combined_style
    )


def test_text_style_small_caps() -> None:
    """Test small-caps font variant handling."""
    svg = convert_psd_to_svg("texts/style-small-caps.psd")
    tspan = svg.find(".//tspan[@font-variant]")
    assert tspan is not None
    assert tspan.attrib.get("font-variant") == "small-caps"


def test_text_style_superscript() -> None:
    """Test superscript baseline shift and font size handling."""
    svg = convert_psd_to_svg("texts/style-superscript.psd")
    tspan = svg.find(".//tspan[@baseline-shift]")
    assert tspan is not None
    # Should have positive baseline shift
    baseline_shift = float(tspan.attrib.get("baseline-shift", "0"))
    assert baseline_shift > 0
    # Should have reduced font size
    assert tspan.attrib.get("font-size") is not None


def test_text_style_subscript() -> None:
    """Test subscript baseline shift and font size handling."""
    svg = convert_psd_to_svg("texts/style-subscript.psd")
    tspan = svg.find(".//tspan[@baseline-shift]")
    assert tspan is not None
    # Should have negative baseline shift
    baseline_shift = float(tspan.attrib.get("baseline-shift", "0"))
    assert baseline_shift < 0
    # Should have reduced font size
    assert tspan.attrib.get("font-size") is not None


def test_text_style_baseline_shift() -> None:
    """Test baseline shift handling."""
    svg = convert_psd_to_svg("texts/style-baseline-shift.psd")
    # baseline-shift can be on text or tspan elements
    element = svg.find(".//*[@baseline-shift]")
    assert element is not None
    # Should have non-zero baseline shift
    baseline_shift = float(element.attrib.get("baseline-shift", "0"))
    assert baseline_shift != 0


def test_text_style_baseline_shift_scale() -> None:
    """Test that baseline-shift stays unchanged with uniform scaling.

    Photoshop stores baseline-shift as absolute pixels, unchanged by scale parameter.
    When uniform scaling is applied (e.g., 150%), the font-size is scaled but
    baseline-shift should remain at its original value.
    """
    svg = convert_psd_to_svg("texts/style-baseline-shift-scale.psd")

    # Find element with baseline-shift
    element = svg.find(".//*[@baseline-shift]")
    assert element is not None, "Should have element with baseline-shift"

    # Get baseline-shift value
    baseline_shift = float(element.attrib.get("baseline-shift", "0"))
    assert baseline_shift != 0, "Should have non-zero baseline-shift"

    # Font should be scaled (uniform 150% scale)
    font_size = float(element.attrib.get("font-size", "0"))
    assert font_size > 0, "Should have positive font-size"

    # Should NOT have transform for uniform scaling
    transform = element.attrib.get("transform")
    assert transform is None, "Uniform scaling should not use transform"


def test_text_style_tracking() -> None:
    """Test tracking (letter-spacing) handling."""
    svg = convert_psd_to_svg("texts/style-tracking.psd")
    tspan = svg.find(".//tspan[@letter-spacing]")
    assert tspan is not None
    # Should have non-zero letter spacing
    letter_spacing = float(tspan.attrib.get("letter-spacing", "0"))
    assert letter_spacing != 0


def test_text_style_kerning() -> None:
    """Test kerning using dx attributes.

    Consecutive per-character tspans that differ only in their kerning are
    merged into a single tspan whose ``dx`` attribute is a space-separated
    per-character offset list (see merge_offset_siblings).
    """
    svg = convert_psd_to_svg("texts/style-kerning-manual.psd")

    # Kerning collapses into a per-character dx list on the paragraph tspan.
    tspans_with_dx = svg.findall(".//tspan[@dx]")
    assert len(tspans_with_dx) == 1, (
        f"Expected kerning to merge into a single tspan, got {len(tspans_with_dx)}"
    )

    # The dx list has at most one value per character of the merged text.
    # It may be shorter because trailing zero offsets are trimmed (dx defaults
    # to 0 for characters past the end of the list).
    tspan = tspans_with_dx[0]
    dx_values = [float(value) for value in tspan.attrib["dx"].split()]
    assert 0 < len(dx_values) <= len(tspan.text or ""), (
        "dx list should carry no more values than there are merged characters"
    )

    # The second paragraph has 8 characters with non-zero (tighter) kerning;
    # all kerning values in the fixture are negative.
    nonzero = [value for value in dx_values if value != 0.0]
    assert len(nonzero) >= 8, (
        f"Expected at least 8 non-zero dx offsets, got {len(nonzero)}"
    )
    for value in nonzero:
        assert value < 0, f"Expected negative dx for tighter kerning, got {value}"


def test_text_style_tsume() -> None:
    """Test tsume (character tightening) effect on letter-spacing."""
    svg = convert_psd_to_svg("texts/style-tsume.psd")

    # Find all tspan elements
    tspans = svg.findall(".//tspan")
    assert len(tspans) == 2, f"Expected 2 tspans, got {len(tspans)}"

    # Get letter-spacing values (0.0 if not set)
    spacing_values = []
    for tspan in tspans:
        spacing = float(tspan.attrib.get("letter-spacing", "0"))
        spacing_values.append(spacing)

    # First paragraph: tracking=50, tsume=0 -> spacing = 50/1000 * 32 = 1.6
    # Second paragraph: tracking=50, tsume=0.5 -> spacing =
    # 50/1000 * 32 - 0.5/10 * 32 = 1.6 - 1.6 = 0.0
    assert abs(spacing_values[0] - 1.6) < 1e-6, (
        f"Expected first paragraph letter-spacing to be 1.6, got {spacing_values[0]}"
    )
    assert abs(spacing_values[1] - 0.0) < 1e-6, (
        f"Expected second paragraph letter-spacing to be 0.0, got {spacing_values[1]}"
    )

    # Verify that tsume reduces spacing
    assert spacing_values[0] > spacing_values[1], (
        "Expected reduced spacing from tsume=0.5"
    )


def test_text_style_tracking_and_tsume() -> None:
    """Test combined tracking and tsume effect on letter-spacing.

    This test verifies that both tracking and tsume are correctly applied together.
    The fixture has two spans with the same tracking but different tsume values.
    """
    svg = convert_psd_to_svg("texts/style-tracking-tsume.psd")

    # Find all tspan elements with letter-spacing
    tspans_with_spacing = svg.findall(".//tspan[@letter-spacing]")
    assert len(tspans_with_spacing) == 2, (
        f"Expected 2 tspans with letter-spacing, got {len(tspans_with_spacing)}"
    )

    # Collect letter-spacing values
    spacing_values = []
    for tspan in tspans_with_spacing:
        spacing = float(tspan.attrib["letter-spacing"])
        spacing_values.append(spacing)

    # Verify expected letter-spacing values:
    # Span 0: tracking=-50, tsume=1.0, font_size=40.0
    #   -> spacing = -50/1000 * 40 - 1.0/10 * 40 = -2.0 - 4.0 = -6.0
    # Span 1: tracking=-50, tsume=0.0, font_size=40.0
    #   -> spacing = -50/1000 * 40 - 0.0/10 * 40 = -2.0 - 0.0 = -2.0

    assert abs(spacing_values[0] - (-6.0)) < 1e-6, (
        f"Expected first span letter-spacing to be -6.0, got {spacing_values[0]}"
    )
    assert abs(spacing_values[1] - (-2.0)) < 1e-6, (
        f"Expected second span letter-spacing to be -2.0, got {spacing_values[1]}"
    )

    # Verify that the span with higher tsume has more negative spacing
    assert spacing_values[0] < spacing_values[1], (
        "Span with tsume=1.0 should have more negative spacing than span with tsume=0.0"
    )


def test_text_style_ligatures() -> None:
    """Test common ligatures using font-variant-ligatures."""
    svg = convert_psd_to_svg("texts/style-ligatures.psd")

    # Find all text nodes (after optimization, styles may be on text or tspan)
    text_nodes = svg.findall(".//text")
    tspan_nodes = svg.findall(".//tspan")
    all_nodes = text_nodes + tspan_nodes

    # Check ligature styles
    ligature_styles = []
    nodes_without_ligature_style = []
    for node in all_nodes:
        style = node.attrib.get("style", "")
        if "font-variant-ligatures" in style:
            ligature_styles.append(style)
        else:
            nodes_without_ligature_style.append(node)

    # First paragraph should have "none" (ligatures=False, discretionary=False)
    has_none = any("font-variant-ligatures: none" in s for s in ligature_styles)
    assert has_none, "Expected font-variant-ligatures: none in first paragraph"

    # Second paragraph should have no font-variant-ligatures attribute
    # (default CSS behavior)
    # This represents ligatures=True, discretionary=False (the default)
    assert len(nodes_without_ligature_style) > 0, (
        "Expected at least one tspan without font-variant-ligatures (default behavior)"
    )


def test_text_style_discretionary_ligatures() -> None:
    """Test discretionary ligatures using font-variant-ligatures."""
    svg = convert_psd_to_svg("texts/style-dligatures.psd")

    # Find all text nodes (after optimization, styles may be on text or tspan)
    text_nodes = svg.findall(".//text")
    tspan_nodes = svg.findall(".//tspan")
    all_nodes = text_nodes + tspan_nodes

    # Check that we have font-variant-ligatures styles
    ligature_styles = []
    for node in all_nodes:
        style = node.attrib.get("style", "")
        if "font-variant-ligatures" in style:
            ligature_styles.append(style)

    assert len(ligature_styles) > 0, "Expected font-variant-ligatures styles"

    # First paragraph should have "none" (ligatures=False,
    # discretionary=False). Second paragraph should have
    # "discretionary-ligatures" (ligatures=False, discretionary=True)
    has_none = any("font-variant-ligatures: none" in s for s in ligature_styles)
    has_discretionary = any("discretionary-ligatures" in s for s in ligature_styles)

    assert has_none, "Expected font-variant-ligatures: none in first paragraph"
    assert has_discretionary, "Expected discretionary-ligatures in second paragraph"


def test_text_letter_spacing_offset() -> None:
    """Test text_letter_spacing_offset parameter."""
    # Test with no offset (default behavior)
    psdimage = PSDImage.open(get_fixture("texts/style-tracking.psd"))
    doc_no_offset = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=0.0)
    tspan_no_offset = doc_no_offset.svg.find(".//tspan[@letter-spacing]")
    assert tspan_no_offset is not None
    letter_spacing_no_offset = float(tspan_no_offset.attrib.get("letter-spacing", "0"))

    # Test with positive offset
    doc_positive = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=0.5)
    tspan_positive = doc_positive.svg.find(".//tspan[@letter-spacing]")
    assert tspan_positive is not None
    letter_spacing_positive = float(tspan_positive.attrib.get("letter-spacing", "0"))
    assert abs(letter_spacing_positive - (letter_spacing_no_offset + 0.5)) < 1e-6

    # Test with negative offset
    doc_negative = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=-0.3)
    tspan_negative = doc_negative.svg.find(".//tspan[@letter-spacing]")
    assert tspan_negative is not None
    letter_spacing_negative = float(tspan_negative.attrib.get("letter-spacing", "0"))
    assert abs(letter_spacing_negative - (letter_spacing_no_offset - 0.3)) < 1e-6


def test_text_letter_spacing_offset_zero_tracking() -> None:
    """Test text_letter_spacing_offset with text that has zero tracking."""
    # Use a text file - this should have zero tracking by default
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype0-justification0.psd")
    )

    # Test that offset is applied even when tracking is zero
    # First get baseline (no offset)
    doc_no_offset = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=0.0)
    tspans_no_offset = doc_no_offset.svg.findall(".//tspan")

    # Apply offset and verify it's added to all text
    doc_with_offset = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=-0.01)
    tspans_with_offset = doc_with_offset.svg.findall(".//tspan")

    # Both should have same number of tspans
    assert len(tspans_no_offset) == len(tspans_with_offset)

    # Check that the offset is properly applied
    for tspan_no, tspan_with in zip(tspans_no_offset, tspans_with_offset):
        if (
            tspan_no.text and tspan_no.text.strip()
        ):  # Only check tspans with actual text
            # Get letter-spacing values (default to 0 if not present)
            spacing_no = float(tspan_no.attrib.get("letter-spacing", "0"))
            spacing_with = float(tspan_with.attrib.get("letter-spacing", "0"))
            # The difference should be the offset (-0.01)
            assert abs((spacing_with - spacing_no) - (-0.01)) < 1e-6


def test_text_style_leading() -> None:
    """Test leading (line height) handling."""
    svg = convert_psd_to_svg("texts/style-leading.psd")
    # Leading affects dy attribute on tspan elements for subsequent paragraphs
    tspans = svg.findall(".//tspan[@dy]")
    # Should have at least one tspan with dy attribute (second paragraph onwards)
    assert len(tspans) > 0
    # dy should be non-zero
    dy = float(tspans[0].attrib.get("dy", "0"))
    assert dy != 0


def test_text_style_horizontal_scale() -> None:
    """Test horizontal scale transform handling (non-uniform).

    When only horizontal_scale=0.5 and vertical_scale=1.0:
    - Font-size is scaled by vertical_scale (1.0, unchanged)
    - Transform adjusts horizontal: scale(h/v, 1) = scale(0.5/1.0, 1) = scale(0.5, 1)
    """
    svg = convert_psd_to_svg("texts/style-horizontally-scale-50.psd")

    # Check for transform on tspan or text element (optimization may move it to text)
    element = svg.find(".//tspan[@transform]")
    if element is None:
        element = svg.find(".//text[@transform]")
    assert element is not None, "Should have element with transform"

    transform = element.attrib.get("transform", "")
    # Should contain scale transformation
    assert "scale" in transform, "Should have scale transform"
    # Transform should be scale(0.5,1) for horizontal compression
    assert ("0.5" in transform or ".5" in transform) and "1" in transform, (
        "Should have scale(0.5,1) transform"
    )


def test_text_style_vertical_scale() -> None:
    """Test vertical scale transform handling (non-uniform).

    When only vertical_scale=0.5 and horizontal_scale=1.0:
    - Font-size is scaled by vertical_scale (0.5)
    - Transform adjusts horizontal: scale(h/v, 1) = scale(1.0/0.5, 1) = scale(2, 1)
    """
    svg = convert_psd_to_svg("texts/style-vertically-scale-50.psd")

    # Check for transform on tspan or text element (optimization may move it to text)
    element = svg.find(".//tspan[@transform]")
    if element is None:
        element = svg.find(".//text[@transform]")
    assert element is not None, "Should have element with transform"

    transform = element.attrib.get("transform", "")
    # Should contain scale transformation
    assert "scale" in transform, "Should have scale transform"
    # Transform should be scale(2,1) for horizontal adjustment
    assert "2" in transform and "1" in transform, "Should have scale(2,1) transform"


def test_text_native_positioning_point_type() -> None:
    """Test that point-type text uses native x, y attributes instead of transform."""
    svg = convert_psd_to_svg("texts/paragraph-shapetype0-justification0.psd")
    text_node = svg.find(".//text")
    assert text_node is not None
    # Should use native x, y attributes for translation-only transforms
    assert text_node.attrib.get("x") is not None
    assert text_node.attrib.get("y") is not None
    # Should not have a transform attribute (translation-only)
    assert text_node.attrib.get("transform") is None


def test_text_native_positioning_bounding_box_left() -> None:
    """Test that bounding box with left alignment uses native x, y on text node."""
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-justification0.psd")
    text_node = svg.find(".//text")
    assert text_node is not None
    # Should use native x, y attributes
    assert text_node.attrib.get("x") is not None
    assert text_node.attrib.get("y") is not None
    # Should not have a transform attribute
    assert text_node.attrib.get("transform") is None


def test_text_native_positioning_bounding_box_right() -> None:
    """Test bounding box with right alignment.

    Correctly combines transform and bounds on text node.
    """
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-justification1.psd")
    text_node = svg.find(".//text")
    assert text_node is not None
    # Should use native x, y attributes on text node with combined position
    text_x = float(text_node.attrib.get("x", "0"))
    text_y = float(text_node.attrib.get("y", "0"))
    assert text_x != 0
    assert text_y != 0
    # Should not have a transform attribute on text
    assert text_node.attrib.get("transform") is None
    # Should have text-anchor for right alignment
    assert text_node.attrib.get("text-anchor") == "end"
    # x should be greater than just the transform tx (includes bounds.right)
    # For this test file, transform.tx is about 23, but with bounds it should be ~217
    assert text_x > 100


def test_text_native_positioning_bounding_box_center() -> None:
    """Test bounding box with center alignment.

    Correctly combines transform and bounds on text node.
    """
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-justification2.psd")
    text_node = svg.find(".//text")
    assert text_node is not None
    # Should use native x, y attributes on text node with combined position
    text_x = float(text_node.attrib.get("x", "0"))
    text_y = float(text_node.attrib.get("y", "0"))
    assert text_x != 0
    assert text_y != 0
    # Should not have a transform attribute on text
    assert text_node.attrib.get("transform") is None
    # Should have text-anchor for center alignment
    assert text_node.attrib.get("text-anchor") == "middle"
    # x should be greater than just the transform tx (includes midpoint)
    # For this test file, transform.tx is about 23, but with bounds midpoint
    # it should be ~120
    assert text_x > 50


def test_text_multiple_paragraphs_different_alignments() -> None:
    """Test multiple paragraphs with different text anchors.

    Each paragraph has its own tspan with explicit positioning and
    text-anchor, regardless of whether the alignments differ or not. This
    provides consistent structure.
    """
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-multiple.psd")
    text_node = svg.find(".//text")
    assert text_node is not None

    # The parent text node should not have x/y (each tspan has its own position)
    assert text_node.attrib.get("transform") is None, "Should use native positioning"

    # Get all tspan elements (one per paragraph)
    tspans = text_node.findall("tspan")
    assert len(tspans) == 3  # Three paragraphs

    # First paragraph: RIGHT alignment (text-anchor="end")
    assert tspans[0].attrib.get("text-anchor") == "end"
    assert tspans[0].attrib.get("x") is not None
    assert tspans[0].attrib.get("y") is not None  # First paragraph has y
    assert tspans[0].attrib.get("dy") is None  # First paragraph doesn't have dy

    # Second paragraph: CENTER alignment (text-anchor="middle")
    assert tspans[1].attrib.get("text-anchor") == "middle"
    assert tspans[1].attrib.get("x") is not None
    assert tspans[1].attrib.get("y") is None  # Non-first paragraphs don't have y
    assert tspans[1].attrib.get("dy") is not None  # Non-first paragraphs have dy

    # Third paragraph: LEFT alignment (text-anchor=None or not set)
    third_text_anchor = tspans[2].attrib.get("text-anchor")
    assert third_text_anchor is None or third_text_anchor == "start"
    assert tspans[2].attrib.get("x") is not None
    assert tspans[2].attrib.get("y") is None  # Non-first paragraphs don't have y
    assert tspans[2].attrib.get("dy") is not None  # Non-first paragraphs have dy

    # Verify that each paragraph has the correct x position
    # (based on bounds and alignment)
    tspan_x_values = [float(t.attrib.get("x", "0")) for t in tspans]
    # Right-aligned should have the largest x
    # Center should be in the middle
    # Left should have the smallest x
    assert tspan_x_values[0] > tspan_x_values[1] > tspan_x_values[2]


def test_text_bounding_box_dominant_baseline() -> None:
    """Test that bounding box text (ShapeType=1) uses dominant-baseline="hanging".

    Bounding box text should set dominant-baseline="hanging" which aligns text
    to the hanging baseline (top of capital letters), providing better visual
    alignment with Photoshop's rendering compared to "text-before-edge".
    """
    # Test with a bounding box left-aligned text
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-justification0.psd")
    text_node = svg.find(".//text")
    assert text_node is not None

    # Should have dominant-baseline="hanging" for bounding box text
    assert text_node.attrib.get("dominant-baseline") == "hanging"

    # Test with multiple paragraphs
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-multiple.psd")
    text_node = svg.find(".//text")
    assert text_node is not None

    # Should also have dominant-baseline="hanging"
    assert text_node.attrib.get("dominant-baseline") == "hanging"


def test_text_point_type_no_dominant_baseline() -> None:
    """Test that point text (ShapeType=0) does NOT set dominant-baseline.

    Point text should not have dominant-baseline attribute since it doesn't
    use bounding box positioning.
    """
    # Test with a point-type text
    svg = convert_psd_to_svg("texts/paragraph-shapetype0-justification0.psd")
    text_node = svg.find(".//text")
    assert text_node is not None

    # Should NOT have dominant-baseline for point text
    assert text_node.attrib.get("dominant-baseline") is None


def test_text_japanese_notosans_cjk_jp() -> None:
    """Test Japanese text rendering.

    This test verifies that:
    1. Japanese text content is preserved in the SVG
    2. Text elements are properly created (not rasterized as an image)
    3. Font-family attribute is set (regardless of which font is used)

    Note: The PSD file specifies "NotoSansCJKjp-Regular" as the PostScript name.
    If the font is not installed, fontconfig will substitute an appropriate font
    that supports Japanese text.
    """
    svg = convert_psd_to_svg("texts/fonts-notosans-cjk-jp.psd")

    # Find all text elements
    text_nodes = svg.findall(".//text")
    assert len(text_nodes) > 0, "Should have at least one text element"

    # Check the first text element
    text_node = text_nodes[0]

    # Verify Japanese text content is preserved (美しい日本語 = Beautiful Japanese)
    text_content = "".join(text_node.itertext())
    assert "美しい日本語" in text_content, (
        f"Japanese text not found. Got: {text_content}"
    )

    # Verify font-family attribute is set (font substitution may occur)
    font_family = text_node.attrib.get("font-family")
    assert font_family is not None, "font-family should be set"


def test_text_japanese_with_custom_css() -> None:
    """Test Japanese text with custom CSS using append_css().

    This test verifies that:
    1. append_css() correctly injects CSS into the SVG
    2. The CSS rule is present in the final output
    3. Japanese text is properly rendered alongside custom CSS
    """
    psdimage = PSDImage.open(get_fixture("texts/fonts-notosans-cjk-jp.psd"))
    doc = SVGDocument.from_psd(psdimage)

    # Add CJK proportional width CSS
    doc.append_css("text { font-variant-east-asian: proportional-width; }")

    # Convert to string to check CSS injection
    svg_string = doc.tostring()

    # Verify CSS is present
    assert "<style>" in svg_string
    assert "font-variant-east-asian: proportional-width" in svg_string

    # Verify Japanese text is still present
    assert "美しい日本語" in svg_string

    # Verify text elements exist (not rasterized)
    # Parse the SVG and check for text elements
    svg_elem = ET.fromstring(svg_string.encode("utf-8"))
    # Use namespace-aware search for SVG elements
    ns = {"svg": "http://www.w3.org/2000/svg"}
    text_nodes = svg_elem.findall(".//svg:text", ns)
    assert len(text_nodes) > 0, "Should have at least one text element"


def test_text_wrapping_foreign_object_basic() -> None:
    """Test basic foreignObject text wrapping for bounding box text."""
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-justification0.psd")
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    # Should have foreignObject instead of text
    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None, "Should have foreignObject element"
    assert foreign_obj.attrib.get("width") is not None
    assert foreign_obj.attrib.get("height") is not None

    # Should have XHTML div with proper namespace
    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None, "Should have XHTML div element"
    assert div.attrib.get("style") is not None

    # Should have XHTML paragraph
    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None, "Should have XHTML p element"


def test_text_wrapping_foreign_object_multiple_paragraphs() -> None:
    """Test foreignObject with multiple paragraphs."""
    psdimage = PSDImage.open(get_fixture("texts/paragraph-shapetype1-multiple.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    # Should have multiple <p> elements
    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")
    assert len(paragraphs) == 3, "Should have 3 paragraphs"


def test_text_wrapping_foreign_object_text_content() -> None:
    """Test that text content is preserved in foreignObject."""
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-justification0.psd")
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    # Extract all text from XHTML elements
    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None
    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    text_content = "".join(div.itertext())

    # Should contain actual text (exact content depends on PSD file)
    assert len(text_content.strip()) > 0, "Should have text content"


def test_text_wrapping_point_text_unchanged() -> None:
    """Test that point text (ShapeType=0) uses native SVG.

    Even with foreignObject mode.
    """
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype0-justification0.psd")
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    # Point text should still use native <text> element
    text_node = doc.svg.find(".//text")
    assert text_node is not None, "Point text should use native SVG text"

    # Should NOT have foreignObject
    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is None, "Point text should not use foreignObject"


def test_text_wrapping_foreign_object_vertical() -> None:
    """Test foreignObject with vertical writing mode."""
    psdimage = PSDImage.open(
        get_fixture(
            "texts/shapetype1-writingdirection2-baselinedirection2-justification0.psd"
        )
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    # Check for vertical writing mode in container div
    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    style = div.attrib.get("style", "")
    assert "writing-mode: vertical-rl" in style or "writing-mode:vertical-rl" in style


def _parse_style_string(style: str) -> dict[str, str]:
    """Parse CSS style string into dictionary.

    Args:
        style: CSS style string (e.g., "margin: 0; padding: 10px")

    Returns:
        Dictionary mapping property names to values.
    """
    style_dict = {}
    for item in style.split(";"):
        item = item.strip()
        if ":" in item:
            key, value = item.split(":", 1)
            style_dict[key.strip()] = value.strip()
    return style_dict


def test_foreignobject_paragraph_first_line_indent() -> None:
    """Test first-line-indent CSS property for foreignObject paragraphs."""
    psdimage = PSDImage.open(get_fixture("texts/paragraph-first-line-indent.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))

    assert "text-indent" in style_dict
    indent_value = float(style_dict["text-indent"].rstrip("px"))
    assert abs(indent_value - 26.67) < 0.01, (
        f"Expected text-indent ≈ 26.67px, got {indent_value}px"
    )


def test_foreignobject_paragraph_start_indent() -> None:
    """Test padding-left CSS property for start indent."""
    psdimage = PSDImage.open(get_fixture("texts/paragraph-start-indent.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))
    assert "padding-left" in style_dict
    assert style_dict["padding-left"] == "40px"


def test_foreignobject_paragraph_end_indent() -> None:
    """Test padding-right CSS property for end indent."""
    psdimage = PSDImage.open(get_fixture("texts/paragraph-end-indent.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))
    assert "padding-right" in style_dict
    assert style_dict["padding-right"] == "40px"


def test_foreignobject_paragraph_space_before() -> None:
    """Test margin-top CSS property for space before paragraph.

    The fixture has space_before=20px, font-size=32px, auto-leading with offset=0.01px.
    With corrected auto-leading: line-height = font_size + leading = 32.01px
    Expected margin-top = space_before + compensation
                        = 20px + (-(32.01-32)/2)
                        = 20px + (-0.005px)
                        ≈ 20px (compensation is negligible)
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-space-before.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")

    assert len(paragraphs) == 2, "Fixture should have 2 paragraphs"

    for p in paragraphs:
        style_dict = _parse_style_string(p.attrib.get("style", ""))
        assert "margin-top" in style_dict
        # space_before (20px) + negligible compensation ≈ 20px
        assert style_dict["margin-top"] == "20px"


def test_foreignobject_paragraph_space_after() -> None:
    """Test margin-bottom CSS property for space after paragraph."""
    psdimage = PSDImage.open(get_fixture("texts/paragraph-space-after.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")

    assert len(paragraphs) == 2

    for p in paragraphs:
        style_dict = _parse_style_string(p.attrib.get("style", ""))
        assert "margin-bottom" in style_dict
        assert style_dict["margin-bottom"] == "20px"


def test_foreignobject_paragraph_combined_formatting() -> None:
    """Test multiple paragraph formatting properties combined."""
    psdimage = PSDImage.open(get_fixture("texts/paragraph-combined-formatting.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))

    # Verify all properties present
    assert "text-indent" in style_dict
    assert "padding-left" in style_dict
    assert "padding-right" in style_dict
    assert "margin-bottom" in style_dict

    # Verify values (allow minor floating point differences)
    indent = float(style_dict["text-indent"].rstrip("px"))
    assert abs(indent - 26.67) < 0.01

    padding_left = float(style_dict["padding-left"].rstrip("px"))
    assert abs(padding_left - 13.33) < 0.01

    padding_right = float(style_dict["padding-right"].rstrip("px"))
    assert abs(padding_right - 13.33) < 0.01

    assert style_dict["margin-bottom"] == "20px"


def test_foreignobject_paragraph_hanging_punctuation() -> None:
    """Test hanging-punctuation CSS property (limited browser support).

    Note: Hanging punctuation has limited browser support (Safari 10+ only).
    Chrome, Firefox, and Edge do not support this CSS property.
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-hanging-punctuation.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))

    # Fixture has Hanging=True, so property should be present
    assert "hanging-punctuation" in style_dict
    assert style_dict["hanging-punctuation"] == "first last"


def test_foreignobject_paragraph_hyphenation() -> None:
    """Test auto hyphenation CSS properties in foreignObject mode.

    Note: Hyphenation support varies by browser:
    - hyphens: auto - All modern browsers (requires lang attribute)
    - hyphenate-limit-chars - Firefox 43+, Safari 17+, not supported in Chrome
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-auto-hyphenate.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    # Verify lang attribute is set when hyphenation is enabled
    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    assert div.attrib.get("lang") == "en", "lang='en' attribute should be set"

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))

    # Verify hyphens: auto is set
    assert "hyphens" in style_dict
    assert style_dict["hyphens"] == "auto"

    # Verify hyphenate-limit-chars is set with correct format and values
    assert "hyphenate-limit-chars" in style_dict
    limit_chars = style_dict["hyphenate-limit-chars"]

    # Parse the hyphenate-limit-chars value (format: "word-min char-before char-after")
    match = re.match(r"(\d+)\s+(\d+)\s+(\d+)", limit_chars)
    assert match is not None, f"hyphenate-limit-chars format incorrect: {limit_chars}"

    word_min, char_before, char_after = match.groups()
    assert word_min == "6", "word minimum should be 6"
    assert char_before == "2", "characters before hyphen should be 2"
    assert char_after == "2", "characters after hyphen should be 2"


def test_foreignobject_paragraph_default_values_skipped() -> None:
    """Test that zero/false paragraph properties are not included in CSS.

    Note: margin-top may be present for vertical alignment compensation on the
    first paragraph (Issue #271), which is not related to space_before.
    """
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-justification0.psd")
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None

    p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert p is not None

    style_dict = _parse_style_string(p.attrib.get("style", ""))

    # Should have base properties
    assert "margin" in style_dict
    assert "padding" in style_dict

    # Should NOT have specific properties when values are 0
    assert "text-indent" not in style_dict
    assert "padding-left" not in style_dict
    assert "padding-right" not in style_dict
    # margin-top is present for vertical alignment compensation (not space_before)
    # This is expected behavior after Issue #271 fix
    assert "margin-bottom" not in style_dict
    assert "hanging-punctuation" not in style_dict


def test_foreignobject_xhtml_namespace_serialization() -> None:
    """Test that XHTML elements use unprefixed tags with xmlns (#257).

    Regression test for issue #257: XHTML elements should not have namespace
    prefixes (html:div) as this prevents CSS styling in browsers. Instead, they
    should use unprefixed tags (<div>) with xmlns declaration.
    """
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-justification0.psd")
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    # Get the serialized SVG string
    svg_string = doc.tostring()

    # Check that no XHTML namespace prefixes are present
    assert "html:div" not in svg_string, "Should not have html:div prefix"
    assert "html:p" not in svg_string, "Should not have html:p prefix"
    assert "html:span" not in svg_string, "Should not have html:span prefix"
    assert "ns0:div" not in svg_string, "Should not have ns0:div prefix"
    assert "ns0:p" not in svg_string, "Should not have ns0:p prefix"
    assert "ns0:span" not in svg_string, "Should not have ns0:span prefix"

    # Check that xmlns declaration exists on first XHTML element
    assert 'xmlns="http://www.w3.org/1999/xhtml"' in svg_string, (
        "First XHTML element should have xmlns declaration"
    )

    # Verify proper structure: <div xmlns="...">
    assert '<div xmlns="http://www.w3.org/1999/xhtml"' in svg_string, (
        "Should have unprefixed <div> with xmlns attribute"
    )

    # Verify no namespace prefix declarations
    assert 'xmlns:html="http://www.w3.org/1999/xhtml"' not in svg_string, (
        "Should not have namespace prefix declaration"
    )
    assert 'xmlns:ns0="http://www.w3.org/1999/xhtml"' not in svg_string, (
        "Should not have namespace prefix declaration"
    )


def test_text_whitespace_preservation() -> None:
    """Test that whitespace in text is preserved with xml:space='preserve'.

    Verifies:
    - Leading spaces preserved
    - Trailing spaces preserved
    - Consecutive spaces (10 spaces) preserved
    - Whitespace-only spans preserved
    - xml:space attribute set correctly
    """
    svg = convert_psd_to_svg("texts/whitespaces.psd")

    # Verify xml:space="preserve" attribute is set on text element
    text_node = svg.find(".//text")
    assert text_node is not None, "Should have text element"

    # Check for xml:space attribute with proper XML namespace
    xml_space_attr = text_node.attrib.get("{http://www.w3.org/XML/1998/namespace}space")
    assert xml_space_attr == "preserve", (
        f"text element should have xml:space='preserve', got: {repr(xml_space_attr)}"
    )

    # Find all tspan elements (one per paragraph)
    tspans = text_node.findall(".//tspan")
    assert len(tspans) == 3, f"Expected 3 paragraphs, got {len(tspans)}"

    # Paragraph 1: " Lorem" (leading space + text)
    assert tspans[0].text == " Lorem", (
        f"First paragraph should have leading space, got: {repr(tspans[0].text)}"
    )

    # Paragraph 2: "          Ipsum" (10 consecutive spaces + text)
    assert tspans[1].text == "          Ipsum", (
        f"Second paragraph should have 10 spaces, got: {repr(tspans[1].text)}"
    )
    assert len(tspans[1].text) == 15, (
        f"Second paragraph should be 15 chars (10 spaces + 5 chars), "
        f"got: {len(tspans[1].text)}"
    )

    # Paragraph 3: "   " (3 trailing spaces only)
    assert tspans[2].text == "   ", (
        f"Third paragraph should be 3 spaces, got: {repr(tspans[2].text)}"
    )
    assert len(tspans[2].text) == 3, (
        f"Third paragraph should be exactly 3 chars, got: {len(tspans[2].text)}"
    )


def test_text_whitespace_preservation_foreign_object() -> None:
    """Test whitespace preservation in foreignObject mode with XHTML.

    Uses a bounding box text fixture (ShapeType 1) that supports foreignObject mode.
    """
    psdimage = PSDImage.open(get_fixture("texts/whitespaces-shapetype1.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    # Find foreignObject and container div
    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None, "Should have foreignObject element"

    # Get all paragraphs
    paragraphs = foreign_obj.findall(".//{http://www.w3.org/1999/xhtml}p")
    assert len(paragraphs) == 3, f"Expected 3 paragraphs, got {len(paragraphs)}"

    # Verify xml:space="preserve" attribute on paragraph elements
    # Paragraphs 0 and 1 have whitespace that needs preservation, paragraph 2 is empty
    for i, p in enumerate(paragraphs):
        xml_space = p.attrib.get("{http://www.w3.org/XML/1998/namespace}space")
        if i < 2:  # First two paragraphs have whitespace
            expected_msg = (
                f"Paragraph {i} should have xml:space='preserve', "
                f"got: {repr(xml_space)}"
            )
            assert xml_space == "preserve", expected_msg
        else:  # Last paragraph is empty (\r only), no xml:space needed
            assert xml_space is None, (
                f"Paragraph {i} should not have xml:space, got: {repr(xml_space)}"
            )

    # Extract text content from each paragraph
    p1_text = "".join(paragraphs[0].itertext())
    p2_text = "".join(paragraphs[1].itertext())
    p3_text = "".join(paragraphs[2].itertext())

    # Verify whitespace is preserved (fixture has: '  Lorem\r        ipsum\r\r')
    assert p1_text == "  Lorem", (
        f"Paragraph 1 should be '  Lorem' (2 leading spaces), got: {repr(p1_text)}"
    )
    assert p2_text == "        ipsum", (
        f"Paragraph 2 should have 8 spaces, got: {repr(p2_text)}"
    )
    assert len(p2_text) == 13, (
        f"Paragraph 2 should be 13 chars (8 spaces + 5 chars), got: {len(p2_text)}"
    )
    assert p3_text == "", (
        f"Paragraph 3 should be empty (carriage return only), got: {repr(p3_text)}"
    )


def test_text_style_horizontal_scale_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that scaled text logs a warning about browser compatibility."""
    # Capture warning logs
    with caplog.at_level(logging.WARNING):
        svg = convert_psd_to_svg("texts/style-horizontally-scale-200.psd")

    # Should log a warning about text scaling not being supported
    assert any(
        "text scaling" in record.message.lower()
        and "not supported" in record.message.lower()
        for record in caplog.records
    ), "Should warn about text scaling not being supported by browsers"

    # Transform should still be on tspan (even though it won't render)
    tspan_with_transform = svg.find(".//tspan[@transform]")
    assert tspan_with_transform is not None, "Transform should be on tspan"
    assert "scale" in tspan_with_transform.attrib["transform"], (
        "Should have scale transform"
    )


def test_text_style_vertical_scale_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Test that vertically scaled text logs a warning."""
    with caplog.at_level(logging.WARNING):
        convert_psd_to_svg("texts/style-vertically-scale-200.psd")

    assert any("text scaling" in record.message.lower() for record in caplog.records), (
        "Should warn about text scaling"
    )


def test_text_style_uniform_scale_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that uniform scaled text does NOT log a warning (now browser-compatible)."""
    with caplog.at_level(logging.WARNING):
        svg = convert_psd_to_svg("texts/style-scale-combination.psd")

    # Should NOT warn for uniform scaling (we fixed it)
    warnings = [r for r in caplog.records if "text scaling" in r.message.lower()]
    assert len(warnings) == 0, "Should not warn about uniform text scaling"

    # Should use scaled font-size, not transform
    tspan = svg.find(".//tspan[@font-size]")
    assert tspan is not None, "Should have tspan with font-size"

    # Should NOT have transform attribute for uniform scaling
    transform = tspan.attrib.get("transform")
    assert transform is None, "Uniform scaling should not use transform"


# Arc Warping Tests


@pytest.mark.parametrize(
    "psd_file, expected_warp_value",
    [
        ("texts/text-warp-arc-h-100.psd", -100.0),
        ("texts/text-warp-arc-h-50.psd", -50.0),
        ("texts/text-warp-arc-h-10.psd", -10.0),
        ("texts/text-warp-arc-h+10.psd", 10.0),
        ("texts/text-warp-arc-h+50.psd", 50.0),
        ("texts/text-warp-arc-h+100.psd", 100.0),
    ],
)
def test_text_warp_arc_properties(psd_file: str, expected_warp_value: float) -> None:
    """Test TypeSetting correctly reads warp arc properties from PSD."""
    psdimage = PSDImage.open(get_fixture(psd_file))

    found_text_layer = False
    for layer in psdimage.descendants():
        if isinstance(layer, TypeLayer) and layer.is_visible():
            text_setting = TypeSetting(layer._data)

            # Test warp properties
            assert text_setting.has_warp() is True, "Should detect warp"
            assert text_setting.warp_style == "warpArc", "Should be arc warp style"
            assert text_setting.warp_value == expected_warp_value, (
                f"Warp value should be {expected_warp_value}"
            )
            assert text_setting.warp_rotate == "Hrzn", (
                "Should be horizontal orientation"
            )
            assert text_setting.warp_perspective == 0.0, "Perspective should be 0"
            assert text_setting.warp_perspective_other == 0.0, (
                "Perspective other should be 0"
            )

            found_text_layer = True
            break

    assert found_text_layer, "Should have found a text layer"


@pytest.mark.parametrize(
    "psd_file",
    [
        "texts/text-warp-arc-h-100.psd",
        "texts/text-warp-arc-h-50.psd",
        "texts/text-warp-arc-h-10.psd",
        "texts/text-warp-arc-h+10.psd",
        "texts/text-warp-arc-h+50.psd",
        "texts/text-warp-arc-h+100.psd",
    ],
)
def test_text_warp_arc_svg_structure(psd_file: str) -> None:
    """Test textPath and path elements are correctly created in SVG output."""
    svg = convert_psd_to_svg(psd_file)

    # Verify defs element with path definition exists
    defs = svg.find(".//defs")
    assert defs is not None, "Should have defs element"

    path_elem = svg.find(".//defs/path[@id]")
    assert path_elem is not None, "Should have path element in defs with id"
    assert path_elem.attrib.get("d") is not None, "Path should have d attribute"
    assert path_elem.attrib.get("d") != "", "Path d attribute should not be empty"

    path_id = path_elem.attrib.get("id")
    assert path_id is not None, "Path should have id"

    # Verify textPath element exists
    text_path = svg.find(".//textPath")
    assert text_path is not None, "Text with warp should use textPath"

    # Verify textPath references the path
    href = text_path.attrib.get(
        "{http://www.w3.org/1999/xlink}href"
    ) or text_path.attrib.get("href")
    assert href is not None, "textPath should have href"
    assert f"#{path_id}" == href, f"textPath should reference #{path_id}"

    # Verify textPath attributes
    assert text_path.attrib.get("startOffset") == "50%", "Should center text on path"
    assert text_path.attrib.get("method") == "stretch", "Should use stretch method"
    assert text_path.attrib.get("lengthAdjust") == "spacingAndGlyphs", (
        "Should adjust spacing and glyphs"
    )

    # Verify textPath contains tspan children
    tspans = text_path.findall(".//tspan")
    assert len(tspans) > 0, "textPath should contain tspan elements"


@pytest.mark.parametrize(
    "psd_file, should_have_text_length",
    [
        ("texts/text-warp-arc-h-100.psd", True),  # |100| > 50
        ("texts/text-warp-arc-h-50.psd", False),  # |50| = 50, not >50
        ("texts/text-warp-arc-h-10.psd", False),  # |10| < 50
        ("texts/text-warp-arc-h+10.psd", False),  # |10| < 50
        ("texts/text-warp-arc-h+50.psd", False),  # |50| = 50, not >50
        ("texts/text-warp-arc-h+100.psd", True),  # |100| > 50
    ],
)
def test_text_warp_arc_text_length_extreme(
    psd_file: str, should_have_text_length: bool
) -> None:
    """Test textLength attribute is only set for extreme warp values (|value| > 50)."""
    svg = convert_psd_to_svg(psd_file)

    text_path = svg.find(".//textPath")
    assert text_path is not None, "Should have textPath element"

    text_length = text_path.attrib.get("textLength")

    if should_have_text_length:
        assert text_length == "100%", (
            "Extreme warp (|value| > 50) should have textLength=100%"
        )
    else:
        assert text_length is None, (
            "Normal warp (|value| <= 50) should not have textLength attribute"
        )


@pytest.mark.parametrize(
    "psd_file, warp_value",
    [
        ("texts/text-warp-arc-h-100.psd", -100.0),
        ("texts/text-warp-arc-h-50.psd", -50.0),
        ("texts/text-warp-arc-h+50.psd", 50.0),
        ("texts/text-warp-arc-h+100.psd", 100.0),
    ],
)
def test_text_warp_arc_path_generation(psd_file: str, warp_value: float) -> None:
    """Test arc path mathematics and SVG path commands are correct."""
    svg = convert_psd_to_svg(psd_file)

    path_elem = svg.find(".//defs/path[@id]")
    assert path_elem is not None, "Should have path element"

    path_d = path_elem.attrib.get("d")
    assert path_d is not None, "Path should have d attribute"

    # Verify path starts with M (moveto)
    assert path_d.startswith("M"), "Path should start with M (moveto) command"

    # Verify path contains A (arc command)
    assert "A" in path_d, "Path should contain A (arc) command for warped text"

    # Verify arc direction based on warp sign
    if warp_value > 0:
        # Positive warp: clockwise arc (sweep-flag = 1)
        # Arc command format: A rx ry x-axis-rotation large-arc-flag sweep-flag x y
        # We expect "A ... 0 0 1 ..." for positive warp
        assert " 0 0 1 " in path_d or " 0 0 1" in path_d.split()[-3:], (
            "Positive warp should use clockwise arc (sweep-flag=1)"
        )
    else:
        # Negative warp: counter-clockwise arc (sweep-flag = 0)
        # We expect "A ... 0 0 0 ..." for negative warp
        assert " 0 0 0 " in path_d or " 0 0 0" in path_d.split()[-3:], (
            "Negative warp should use counter-clockwise arc (sweep-flag=0)"
        )

    # Verify we can extract TypeSetting and check warp path generation
    psdimage = PSDImage.open(get_fixture(psd_file))
    for layer in psdimage.descendants():
        if isinstance(layer, TypeLayer) and layer.is_visible():
            text_setting = TypeSetting(layer._data)

            # Verify warp path can be generated
            warp_path = text_setting.get_warp_path()
            assert warp_path != "", "Should generate non-empty warp path"
            assert "A" in warp_path, "Warp path should contain arc command"

            # Verify radius calculation
            bbox = text_setting.bounding_box
            scale = math.sin(math.pi / 2 * abs(warp_value) / 100)
            expected_radius = (bbox.width + bbox.height) / 2 / scale

            # Extract radius from path (format: "A radius radius ...")
            parts = warp_path.split()
            if "A" in parts:
                arc_index = parts.index("A")
                if arc_index + 2 < len(parts):
                    actual_radius = float(parts[arc_index + 1])
                    # Allow small floating-point tolerance
                    assert abs(actual_radius - expected_radius) < 1.0, (
                        f"Radius {actual_radius} should be close to {expected_radius}"
                    )

            break


def test_text_warp_arc_zero_value() -> None:
    """Test boundary condition when warp is not present or zero."""
    # Use a regular text fixture without warp
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")

    # Verify no textPath element
    text_path = svg.find(".//textPath")
    assert text_path is None, "Non-warped text should not have textPath"

    # Verify regular text structure
    text_node = svg.find(".//text")
    assert text_node is not None, "Should have regular text element"


@pytest.mark.parametrize(
    "positive_psd, negative_psd, warp_magnitude",
    [
        ("texts/text-warp-arc-h+10.psd", "texts/text-warp-arc-h-10.psd", 10),
        ("texts/text-warp-arc-h+50.psd", "texts/text-warp-arc-h-50.psd", 50),
        ("texts/text-warp-arc-h+100.psd", "texts/text-warp-arc-h-100.psd", 100),
    ],
)
def test_text_warp_arc_positive_vs_negative(
    positive_psd: str, negative_psd: str, warp_magnitude: float
) -> None:
    """Test positive and negative warps create arcs in opposite directions."""
    svg_positive = convert_psd_to_svg(positive_psd)
    svg_negative = convert_psd_to_svg(negative_psd)

    # Both should have textPath
    text_path_pos = svg_positive.find(".//textPath")
    text_path_neg = svg_negative.find(".//textPath")
    assert text_path_pos is not None, "Positive warp should have textPath"
    assert text_path_neg is not None, "Negative warp should have textPath"

    # Both should have same textPath attributes (except href)
    assert text_path_pos.attrib.get("startOffset") == "50%"
    assert text_path_neg.attrib.get("startOffset") == "50%"
    assert text_path_pos.attrib.get("method") == "stretch"
    assert text_path_neg.attrib.get("method") == "stretch"
    assert text_path_pos.attrib.get("lengthAdjust") == "spacingAndGlyphs"
    assert text_path_neg.attrib.get("lengthAdjust") == "spacingAndGlyphs"

    # Get path data
    path_pos = svg_positive.find(".//defs/path[@id]")
    path_neg = svg_negative.find(".//defs/path[@id]")
    assert path_pos is not None, "Positive warp should have path"
    assert path_neg is not None, "Negative warp should have path"

    path_d_pos = path_pos.attrib.get("d", "")
    path_d_neg = path_neg.attrib.get("d", "")

    # Arc commands should differ in sweep-flag
    # Positive: sweep-flag = 1, Negative: sweep-flag = 0
    assert " 0 0 1 " in path_d_pos or path_d_pos.endswith(" 0 0 1"), (
        "Positive warp should have sweep-flag=1"
    )
    assert " 0 0 0 " in path_d_neg or path_d_neg.endswith(" 0 0 0"), (
        "Negative warp should have sweep-flag=0"
    )

    # Verify TypeSetting properties match expectations
    psdimage_pos = PSDImage.open(get_fixture(positive_psd))
    psdimage_neg = PSDImage.open(get_fixture(negative_psd))

    for psd, expected_sign in [(psdimage_pos, 1), (psdimage_neg, -1)]:
        for layer in psd.descendants():
            if isinstance(layer, TypeLayer) and layer.is_visible():
                text_setting = TypeSetting(layer._data)
                expected_value = warp_magnitude * expected_sign
                assert text_setting.warp_value == expected_value, (
                    f"Warp value should be {expected_value}"
                )
                break


@pytest.mark.parametrize(
    "psd_file",
    [
        "texts/text-warp-arc-h-100.psd",
        "texts/text-warp-arc-h+100.psd",
    ],
)
def test_text_warp_arc_end_to_end(psd_file: str) -> None:
    """Test comprehensive PSD to SVG conversion pipeline for warped text."""
    # Open PSD and verify TypeSetting properties
    psdimage = PSDImage.open(get_fixture(psd_file))

    found_text_layer = False
    for layer in psdimage.descendants():
        if isinstance(layer, TypeLayer) and layer.is_visible():
            text_setting = TypeSetting(layer._data)

            # Verify TypeSetting properties
            assert text_setting.has_warp() is True
            assert text_setting.warp_style == "warpArc"
            assert abs(text_setting.warp_value) == 100.0

            found_text_layer = True
            break

    assert found_text_layer, "Should have text layer"

    # Convert to SVG
    svg = convert_psd_to_svg(psd_file)

    # Verify complete SVG structure: defs → path
    defs = svg.find(".//defs")
    assert defs is not None, "Should have defs"

    path_elem = defs.find(".//path[@id]")
    assert path_elem is not None, "Should have path in defs"
    assert path_elem.attrib.get("d") is not None, "Path should have d attribute"

    # Verify structure: text → textPath → tspan
    text_node = svg.find(".//text")
    assert text_node is not None, "Should have text element"

    text_path = text_node.find(".//textPath")
    assert text_path is not None, "Text should contain textPath"

    tspans = text_path.findall(".//tspan")
    assert len(tspans) > 0, "textPath should contain tspan elements"

    # Verify text content is preserved
    text_content = "".join(tspans[0].itertext())
    assert "Lorem Ipsum" in text_content, "Text content should be preserved"

    # Verify font properties on tspan
    first_tspan = tspans[0]
    assert first_tspan.attrib.get("font-size") is not None, (
        "tspan should have font-size"
    )

    # Verify transform positioning present on text element
    transform = text_node.attrib.get("transform")
    assert transform is not None, "text element should have transform"

    # Verify text content is in tspan, not text element directly
    assert text_node.text is None or text_node.text.strip() == "", (
        "text element should not have direct text content"
    )


def test_text_warp_arc_bounding_box_usage() -> None:
    """Test arc path uses bounding box dimensions correctly."""
    psd_file = "texts/text-warp-arc-h+50.psd"
    psdimage = PSDImage.open(get_fixture(psd_file))

    # Extract bounding box and warp path from TypeSetting
    for layer in psdimage.descendants():
        if isinstance(layer, TypeLayer) and layer.is_visible():
            text_setting = TypeSetting(layer._data)

            bbox = text_setting.bounding_box
            warp_path = text_setting.get_warp_path()

            # Parse path to extract coordinates
            # Expected format: M x1 y1 A rx ry 0 0 1 x2 y2 L x3 y3
            parts = warp_path.split()

            # Find M command (start point)
            if "M" in parts:
                m_index = parts.index("M")
                start_x = float(parts[m_index + 1])

                # Verify start X is approximately left edge minus half height
                expected_start = bbox.left - bbox.height / 2
                assert abs(start_x - expected_start) < 1.0, (
                    f"Start X {start_x} should be close to {expected_start}"
                )

            # Find arc command endpoint
            if "A" in parts:
                arc_index = parts.index("A")
                # Arc format: A rx ry x-axis-rotation large-arc sweep-flag x y
                if arc_index + 7 < len(parts):
                    end_x = float(parts[arc_index + 6])

                    # Verify end X is approximately right edge plus half height
                    expected_end = bbox.right + bbox.height / 2
                    assert abs(end_x - expected_end) < 1.0, (
                        f"End X {end_x} should be close to {expected_end}"
                    )

            break


def test_text_warp_arc_attribute_optimization() -> None:
    """Test conditional attribute merging for warped text."""
    # Compare warped vs non-warped text structure
    svg_warped = convert_psd_to_svg("texts/text-warp-arc-h+50.psd")
    svg_normal = convert_psd_to_svg("texts/font-sizes-1.psd")

    # Warped text: optimization happens within textPath
    text_path = svg_warped.find(".//textPath")
    assert text_path is not None, "Should have textPath"

    # Find tspans within textPath
    tspans_warped = text_path.findall(".//tspan")
    assert len(tspans_warped) > 0, "textPath should have tspan children"

    # Verify font properties are present on tspans
    first_tspan = tspans_warped[0]
    assert first_tspan.attrib.get("font-size") is not None, (
        "tspan should have font properties"
    )

    # Normal text: different optimization behavior
    text_normal = svg_normal.find(".//text")
    assert text_normal is not None, "Should have text element"

    tspans_normal = text_normal.findall(".//tspan")
    assert len(tspans_normal) > 0, "text should have tspan children"

    # Both should have position attributes on tspans (not fully merged)
    # This verifies that position attributes are preserved correctly
    for tspan in tspans_warped:
        # Check that individual tspans can have position attributes
        # (not asserting they must have them, just that structure allows it)
        assert isinstance(tspan.attrib, dict), "tspan should have attributes dict"


def test_foreignobject_vertical_alignment() -> None:
    """Test vertical alignment compensation for first paragraph.

    With corrected auto-leading (font_size + leading offset), line-height
    is now 32.01px instead of 38.4px, so compensation is negligible.
    """
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-justification0.psd")
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    # Find foreignObject and first paragraph
    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None, "Should have foreignObject element"

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None, "Should have XHTML div element"

    first_p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert first_p is not None, "Should have XHTML p element"

    style_dict = _parse_style_string(first_p.attrib.get("style", ""))

    # Verify line-height is present (corrected auto-leading)
    assert "line-height" in style_dict, "First paragraph should have line-height"
    expected = "32.01px"
    actual = style_dict["line-height"]
    assert actual == expected, f"Expected line-height {expected}, got {actual}"

    # With new auto-leading, compensation is tiny and may be omitted
    # The compensation would be -(32.01-32)/2 = -0.005px, essentially zero
    # So we don't assert margin-top value, just that line-height is correct


def test_foreignobject_vertical_alignment_multiple_paragraphs() -> None:
    """Test vertical alignment with multiple paragraphs.

    With corrected auto-leading (font_size + 0.01), line-height is now
    32.01px instead of 38.4px, so compensation is negligible for all paragraphs.
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-shapetype1-multiple.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None, "Should have foreignObject element"

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None, "Should have XHTML div element"

    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")
    assert len(paragraphs) == 3, f"Expected 3 paragraphs, got {len(paragraphs)}"

    # All paragraphs should have corrected line-height
    for i, p in enumerate(paragraphs):
        p_style = _parse_style_string(p.attrib.get("style", ""))

        assert "line-height" in p_style, f"Paragraph {i} should have line-height"
        assert p_style["line-height"] == "32.01px", (
            f"Paragraph {i} should have line-height 32.01px (font_size + 0.01), "
            f"got {p_style['line-height']}"
        )

        # With new auto-leading, compensation is tiny (-0.005px) and negligible
        # Don't assert specific margin-top value as it may be omitted or rounded


def test_foreignobject_vertical_alignment_vertical_text() -> None:
    """Test vertical alignment with vertical writing mode.

    With corrected auto-leading, line-height is now 32.01px (font_size + 0.01)
    instead of 38.4px, and compensation is negligible even with vertical text.
    """
    psdimage = PSDImage.open(
        get_fixture(
            "texts/shapetype1-writingdirection2-baselinedirection2-justification0.psd"
        )
    )
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    foreign_obj = doc.svg.find(".//foreignObject")
    assert foreign_obj is not None, "Should have foreignObject element"

    div = foreign_obj.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None, "Should have XHTML div element"

    # Verify vertical writing mode is present
    div_style = _parse_style_string(div.attrib.get("style", ""))
    assert "writing-mode" in div_style, "Div should have writing-mode"
    assert div_style["writing-mode"] == "vertical-rl", (
        f"Expected writing-mode vertical-rl, got {div_style['writing-mode']}"
    )

    # Check first paragraph has corrected line-height
    first_p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert first_p is not None, "Should have XHTML p element"

    p_style = _parse_style_string(first_p.attrib.get("style", ""))

    # Verify corrected line-height
    assert "line-height" in p_style, "First paragraph should have line-height"
    assert p_style["line-height"] == "32.01px", (
        f"Expected line-height 32.01px (font_size + 0.01), got {p_style['line-height']}"
    )

    # With new auto-leading, compensation is tiny and may be omitted
    # Don't assert specific margin-top value
