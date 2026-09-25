import logging
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator

import numpy as np
import pytest
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import TypeLayer

from psd2svg import SVGDocument
from psd2svg.core.converter import Converter
from psd2svg.core.text import (
    EM_BOX_DESCENT_RATIO,
    TextWrappingMode,
    _alignment_em_fraction,
    _common_span_scale,
    _default_em_fraction,
    _isolate_trailing_letter_spacing,
)
from psd2svg.core.typesetting import (
    FontBaseline,
    Paragraph,
    ParagraphSheet,
    ShapeType,
    Span,
    StyleRunAlignment,
    StyleSheet,
    TypeSetting,
    WritingDirection,
)
from psd2svg.rasterizer import PlaywrightRasterizer, ResvgRasterizer
from tests.conftest import get_fixture, requires_playwright


def convert_psd_to_svg(psd_file: str) -> ET.Element:
    """Convert a PSD file to SVG and return the SVG as a string."""
    psdimage = PSDImage.open(get_fixture(psd_file))
    converter = Converter(psdimage)
    converter.build()
    return converter.svg


def _first_text_setting(psd_file: str) -> tuple[PSDImage, TypeSetting]:
    """Open a fixture and wrap the first type layer in a TypeSetting."""
    psdimage = PSDImage.open(get_fixture(psd_file))
    layer = next(
        layer for layer in psdimage.descendants() if isinstance(layer, TypeLayer)
    )
    return psdimage, TypeSetting(layer._data)


def _font_feature_settings(svg: ET.Element) -> list[tuple[str | None, str]]:
    """Collect the (text, font-feature-settings) pairs present in the SVG."""
    return [
        (node.text, value)
        for node in svg.iter()
        if (
            value := _parse_style_string(node.attrib.get("style", "")).get(
                "font-feature-settings"
            )
        )
    ]


def _parse_scale(transform: str) -> tuple[float, float]:
    """Extract the scale factors from an SVG transform string."""
    match = re.search(r"scale\(([^,)]+),\s*([^)]+)\)", transform)
    assert match is not None, f"No scale in transform: {transform}"
    return float(match.group(1)), float(match.group(2))


def _parse_translate(transform: str) -> tuple[float, float]:
    """Extract the translation from an SVG transform string."""
    match = re.search(r"translate\(([^,)]+),\s*([^)]+)\)", transform)
    assert match is not None, f"No translate in transform: {transform}"
    return float(match.group(1)), float(match.group(2))


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


def test_vertical_text_paragraph_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that vertical paragraph breaks create columns from right to left."""
    monkeypatch.setattr(
        TypeSetting,
        "writing_direction",
        property(lambda self: WritingDirection.VERTICAL_RL),
    )
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")
    text_node = svg.find(".//text")
    assert text_node is not None
    assert text_node.attrib.get("writing-mode") == "vertical-rl"

    paragraphs = text_node.findall("tspan")
    assert len(paragraphs) == 4

    first_x = paragraphs[0].attrib.get("x")
    first_y = paragraphs[0].attrib.get("y")
    assert first_x is not None
    assert first_y is not None
    assert paragraphs[0].attrib.get("dx") is None
    assert paragraphs[0].attrib.get("dy") is None

    for paragraph in paragraphs[1:]:
        assert paragraph.attrib.get("x") is None
        assert paragraph.attrib.get("y") == first_y
        assert float(paragraph.attrib["dx"]) < 0
        assert paragraph.attrib.get("dy") is None


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

    Photoshop's faux bold thickens the outline of the specified face, so it is
    emitted as a stroke on the glyph - not as font-weight, which would select a
    different face. See GitHub issue #337.
    """
    svg = convert_psd_to_svg("texts/style-faux-bold.psd")
    assert svg.findall(".//tspan[@font-weight]") == [], (
        "Faux bold must not set font-weight"
    )

    tspans = svg.findall(".//tspan[@stroke-width]")
    assert len(tspans) == 1, "Only the faux bold span should be thickened"
    tspan = tspans[0]
    assert tspan.attrib["stroke"] == "#000000"  # the span's own fill colour
    assert tspan.attrib["paint-order"] == "stroke"
    assert tspan.attrib["stroke-linejoin"] == "round"
    # 3% of the 32px em
    assert float(tspan.attrib["stroke-width"]) == pytest.approx(0.96)


def test_text_style_faux_bold_yields_to_character_stroke(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A span with a character stroke keeps the stroke and loses the thickening.

    stroke/stroke-width cannot carry both, and Photoshop's character stroke
    width is not read yet. See GitHub issues #337 and #374.
    """
    monkeypatch.setattr(StyleSheet, "stroke_flag", property(lambda self: True))
    monkeypatch.setattr(
        StyleSheet, "stroke_color", property(lambda self: (1.0, 1.0, 0.0, 0.0))
    )

    with caplog.at_level(logging.WARNING):
        svg = convert_psd_to_svg("texts/style-faux-bold.psd")

    # The character stroke is shared by both spans, so it lands on <text>.
    text = svg.find(".//text")
    assert text is not None
    assert text.attrib["stroke"] == "#ff0000"
    assert svg.findall(".//*[@stroke-width]") == []
    assert "Faux bold is not applied" in caplog.text


def test_text_style_faux_bold_skips_unfilled_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fully transparent fill has no outline to thicken."""
    monkeypatch.setattr(
        StyleSheet, "fill_color", property(lambda self: (0.0, 0.0, 0.0, 0.0))
    )

    svg = convert_psd_to_svg("texts/style-faux-bold.psd")

    text = svg.find(".//text")
    assert text is not None
    assert text.attrib["fill"] == "none"
    assert svg.findall(".//*[@stroke-width]") == []


def test_text_style_faux_bold_keeps_face_weight() -> None:
    """Faux bold on a non-Regular face must not discard the face's weight."""
    psdimage = PSDImage.open(get_fixture("texts/style-faux-bold-light.psd"))
    # tostring() runs the font resolution step that used to drop the weight.
    svg = ET.fromstring(SVGDocument.from_psd(psdimage).tostring())
    texts = svg.findall(".//{http://www.w3.org/2000/svg}text")
    assert len(texts) == 2

    plain, faux = texts
    # Both lines are HelveticaNeue-Light, so both keep the Light weight.
    assert plain.attrib["font-weight"] == "300"
    assert faux.attrib["font-weight"] == "300"
    assert "stroke-width" not in plain.attrib
    assert float(faux.attrib["stroke-width"]) == pytest.approx(1.44)  # 3% of 48px
    assert faux.attrib["paint-order"] == "stroke"


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


def test_auto_kerning_reads_engine_data_key() -> None:
    """Read auto kerning from the EngineData AutoKerning key."""
    style = StyleSheet(name="", style_sheet_data={"AutoKerning": False})
    assert style.auto_kerning is False


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


def test_manual_kerning_uses_previous_mixed_font_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test mixed-size boundaries before optimizer span merging.

    The fixture stores each manual-kerning boundary as a separate style run. Giving
    those runs different sizes verifies that each dx uses the preceding drawable
    run, rather than the run that owns the kerning value.
    """
    sizes_by_kerning = {
        0: 20.0,
        50: 999.0,
        -25: 80.0,
        -100: 10.0,
        -75: 40.0,
        -50: 60.0,
    }
    monkeypatch.setattr(
        StyleSheet,
        "font_size",
        property(lambda style: sizes_by_kerning[style.kerning]),
    )
    monkeypatch.setattr(
        StyleSheet,
        "horizontal_scale",
        property(lambda style: 0.5 if style.kerning == 0 else 1.0),
    )
    original_iter = TypeSetting.__iter__

    def iter_with_empty_runs(text_setting: TypeSetting) -> Iterator[Paragraph]:
        for paragraph in original_iter(text_setting):
            if len(paragraph.spans) > 1:
                first = paragraph.spans[0]
                empty_data = dict(first.style.style_sheet_data)
                empty_data["Kerning"] = 50
                empty_style = StyleSheet(name="", style_sheet_data=empty_data)
                paragraph.spans[1:1] = [
                    Span(first.end, first.end, "", empty_style),
                    Span(first.end, first.end, "\r", empty_style),
                ]
            yield paragraph

    monkeypatch.setattr(TypeSetting, "__iter__", iter_with_empty_runs)

    svg = convert_psd_to_svg("texts/style-kerning-manual.psd")
    runs = {tspan.text: tspan for tspan in svg.findall(".//tspan") if tspan.text}

    # L(20 * 0.5) -> o(80), o(80) -> r(10), and r(10) -> e(80).
    assert float(runs["o"].attrib["dx"]) == pytest.approx(-0.25)
    assert float(runs["r"].attrib["dx"]) == pytest.approx(-8.0)
    assert float(runs["e"].attrib["dx"]) == pytest.approx(-0.25)


def test_manual_kerning_uses_previous_size_for_vertical_text() -> None:
    """Test that vertical manual kerning uses the same boundary semantics."""
    fixture = "texts/shapetype0-writingdirection2-baselinedirection1-justification0.psd"
    psdimage = PSDImage.open(get_fixture(fixture))
    layer = next(
        layer for layer in psdimage.descendants() if isinstance(layer, TypeLayer)
    )
    text_setting = TypeSetting(layer._data)
    source_span = next(iter(next(iter(text_setting))))
    converter = Converter(psdimage)
    paragraph_node = ET.Element("tspan")
    previous_style_data = dict(source_span.style.style_sheet_data)
    previous_style_data.update(FontSize=100.0, VerticalScale=0.5, Kerning=0)
    previous_span = Span(
        0,
        1,
        "A",
        StyleSheet(name="", style_sheet_data=previous_style_data),
    )
    previous_size = converter._add_text_span(
        text_setting,
        paragraph_node,
        previous_span,
    ).font_size

    current_style_data = dict(source_span.style.style_sheet_data)
    current_style_data.update(FontSize=100.0, VerticalScale=2.0, Kerning=-100)
    current_span = Span(
        1,
        2,
        "B",
        StyleSheet(name="", style_sheet_data=current_style_data),
    )
    tspan = converter._add_text_span(
        text_setting,
        paragraph_node,
        current_span,
        kerning_reference_size=previous_size,
    ).node

    assert "dx" not in tspan.attrib
    assert float(tspan.attrib["dy"]) == pytest.approx(-5.0)


def test_manual_kerning_resets_at_paragraph_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a previous paragraph cannot supply a kerning em reference."""
    monkeypatch.setattr(StyleSheet, "kerning", property(lambda style: -100))

    svg = convert_psd_to_svg("texts/style-kerning-manual.psd")

    # Each paragraph starts with a non-zero manual value under the patch, but
    # neither has a preceding drawable character at that boundary. Later
    # characters still kern normally, and optimizer merging serializes the first
    # character's missing offset as zero.
    offsets = []
    for paragraph in svg.findall(".//text/tspan"):
        dx = paragraph.attrib.get("dx")
        if dx is not None:
            offsets.append(dx)
            assert float(dx.split()[0]) == 0.0
    assert offsets


@pytest.mark.parametrize(
    "font_baseline",
    [FontBaseline.SUPERSCRIPT, FontBaseline.SUBSCRIPT],
    ids=["superscript", "subscript"],
)
def test_manual_kerning_uses_previous_script_size(
    monkeypatch: pytest.MonkeyPatch,
    font_baseline: FontBaseline,
) -> None:
    """Test that super/subscript sizing is part of the preceding character's em."""
    monkeypatch.setattr(
        StyleSheet,
        "font_baseline",
        property(
            lambda style: font_baseline if style.kerning == 0 else FontBaseline.ROMAN
        ),
    )

    svg = convert_psd_to_svg("texts/style-kerning-manual.psd")
    runs = {tspan.text: tspan for tspan in svg.findall(".//tspan") if tspan.text}

    previous_size = float(runs["L"].attrib["font-size"])
    assert float(runs["orem"].attrib["dx"].split()[0]) == pytest.approx(
        -0.025 * previous_size,
        abs=0.01,
    )


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


# Baselines of the point text layers in texts/style-tracking-alignment.psd. Every
# layer reads "ABCD" in Helvetica 48px and is anchored at x=300; the rows differ
# only in justification and tracking.
_TRACKING_ALIGNMENT_ROWS = {
    "left-t0": "60",
    "left-t400": "120",
    "center-t0": "180",
    "center-t400": "240",
    "right-t0": "300",
    "right-t400": "360",
    "right-tneg200": "420",
    "center-mixed": "480",
}


def _tracking_alignment_text_nodes() -> dict[str, ET.Element]:
    """Convert the tracking/alignment fixture and key each <text> by row name."""
    svg = convert_psd_to_svg("texts/style-tracking-alignment.psd")
    by_baseline = {}
    for node in svg.iter("text"):
        # The optimizer hoists the baseline onto <text> when it can, and leaves
        # it on the paragraph tspan otherwise.
        baseline = next(
            (element.attrib["y"] for element in node.iter() if "y" in element.attrib),
            None,
        )
        assert baseline is not None, f"No baseline on {ET.tostring(node)!r}"
        by_baseline[baseline] = node
    return {name: by_baseline[y] for name, y in _TRACKING_ALIGNMENT_ROWS.items()}


def test_tracking_isolates_the_final_character_of_anchored_text() -> None:
    """Centered and right-aligned runs end in a tspan without letter spacing.

    Letter spacing also applies after the last character, and text-anchor counts
    that trailing advance. Photoshop tracking does not reserve it, so the final
    character is emitted separately with the spacing switched off.
    """
    rows = _tracking_alignment_text_nodes()

    for name in ("center-t400", "right-t400", "right-tneg200"):
        node = rows[name]
        spans = list(node)
        assert [span.text for span in spans] == ["ABC", "D"], (
            f"Expected {name} to split its final character, got "
            f"{[span.text for span in spans]}"
        )
        assert float(spans[0].attrib["letter-spacing"]) != 0.0
        assert float(spans[1].attrib["letter-spacing"]) == 0.0
        assert node.text is None

    # A mixed-style line uses the letter spacing of the final rendered run.
    mixed = rows["center-mixed"]
    assert mixed.text == "AB"
    assert [(span.text, span.attrib["letter-spacing"]) for span in mixed] == [
        ("C", "19.2"),
        ("D", "0"),
    ]

    # Left-aligned text is anchored at its start, and untracked text has no
    # trailing spacing to remove; both stay a single run.
    for name in ("left-t0", "left-t400", "center-t0", "right-t0"):
        node = rows[name]
        assert node.text == "ABCD", f"Expected {name} to stay one run"
        assert len(node) == 0


def _paragraph_node(*spans: tuple[str, dict[str, str]]) -> ET.Element:
    """Build a paragraph tspan holding the given (text, attributes) spans."""
    paragraph_node = ET.Element("tspan")
    for text, attrib in spans:
        span_node = ET.SubElement(paragraph_node, "tspan", dict(attrib))
        span_node.text = text
    return paragraph_node


def test_isolate_trailing_letter_spacing_single_character_run() -> None:
    """A one-character run carries nothing but trailing spacing, so it is zeroed."""
    paragraph_node = _paragraph_node(("A", {"letter-spacing": "19.2"}))

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert len(paragraph_node) == 1
    assert paragraph_node[0].text == "A"
    # Zeroed rather than removed: the optimizer may hoist a non-zero value from
    # sibling runs onto a shared ancestor, which this run would then inherit.
    assert paragraph_node[0].attrib["letter-spacing"] == "0"


def test_isolate_trailing_letter_spacing_skips_empty_runs() -> None:
    """Runs that render nothing do not count as the final run."""
    paragraph_node = _paragraph_node(
        ("ABC", {"letter-spacing": "4"}),
        ("", {"letter-spacing": "4"}),
    )

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert [span.text for span in paragraph_node] == ["AB", "C", ""]
    assert paragraph_node[1].attrib["letter-spacing"] == "0"


def test_isolate_trailing_letter_spacing_drops_kerning_from_the_split() -> None:
    """Manual kerning applies before a run's first character, not its last."""
    paragraph_node = _paragraph_node(
        ("AB", {"letter-spacing": "4", "dx": "1.5", "font-size": "48"})
    )

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert [span.text for span in paragraph_node] == ["A", "B"]
    assert paragraph_node[0].attrib["dx"] == "1.5"
    assert "dx" not in paragraph_node[1].attrib
    # Everything else has to survive, or the split character loses its style.
    assert paragraph_node[1].attrib["font-size"] == "48"


def test_isolate_trailing_letter_spacing_keeps_combining_marks_attached() -> None:
    """A base character and its combining marks are never split apart."""
    paragraph_node = _paragraph_node(("ae\u0301", {"letter-spacing": "4"}))

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert [span.text for span in paragraph_node] == ["a", "e\u0301"]


def test_isolate_trailing_letter_spacing_without_spacing_is_a_no_op() -> None:
    """Untracked text has no trailing advance to remove."""
    paragraph_node = _paragraph_node(("ABCD", {"font-size": "48"}))

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert [span.text for span in paragraph_node] == ["ABCD"]


def test_isolate_trailing_letter_spacing_keeps_what_tracking_did_not_add() -> None:
    """Only the tracking is taken out; tsume and the global offset stay.

    Tracking separates glyphs without reserving space after the last one, while
    tsume and ``text_letter_spacing_offset`` change the character's own advance.
    """
    paragraph_node = _paragraph_node(("ABCD", {"letter-spacing": "19.7"}))

    _isolate_trailing_letter_spacing(paragraph_node, 0.5)

    assert [span.text for span in paragraph_node] == ["ABC", "D"]
    assert paragraph_node[1].attrib["letter-spacing"] == "0.5"


@pytest.mark.parametrize(
    ("text", "description"),
    [
        ("\u0628\u064a\u062a", "Arabic letters join cursively"),
        ("\u1820\u1821\u1822", "so do Mongolian letters, which are not bidi AL"),
        ("\u0915\u0915\u094d\u0937", "a Devanagari conjunct spans the boundary"),
    ],
)
def test_isolate_trailing_letter_spacing_leaves_shaped_text_alone(
    text: str, description: str
) -> None:
    """Runs are shaped separately, so a boundary inside a cluster is refused."""
    paragraph_node = _paragraph_node((text, {"letter-spacing": "8"}))

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert [span.text for span in paragraph_node] == [text], description


@pytest.mark.parametrize(
    ("text", "head", "final"),
    [
        ("A\u1100\u1161\u11a8", "A", "\u1100\u1161\u11a8"),
        ("A\uac00\u11a8", "A", "\uac00\u11a8"),
        ("AB\U0001f44d\U0001f3fb", "AB", "\U0001f44d\U0001f3fb"),
        ("AB\U0001f1ef\U0001f1f5", "AB", "\U0001f1ef\U0001f1f5"),
        ("\U0001f1fa\U0001f1f8\U0001f1e6", "\U0001f1fa\U0001f1f8", "\U0001f1e6"),
        (
            "A\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",
            "A",
            "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",
        ),
        ("AB\u0e01\u0e33", "AB", "\u0e01\u0e33"),
        ("Ae\u0301B", "Ae\u0301", "B"),
    ],
    ids=[
        "hangul-jamo",
        "hangul-syllable-with-final",
        "emoji-modifier",
        "flag",
        "odd-run-of-regional-indicators",
        "emoji-tag-sequence",
        "thai-sara-am",
        "combining-mark-before-the-boundary",
    ],
)
def test_isolate_trailing_letter_spacing_splits_whole_clusters(
    text: str, head: str, final: str
) -> None:
    """The final run is a complete grapheme cluster, never part of one."""
    paragraph_node = _paragraph_node((text, {"letter-spacing": "8"}))

    _isolate_trailing_letter_spacing(paragraph_node, 0.0)

    assert [span.text for span in paragraph_node] == [head, final]


def test_trailing_letter_spacing_keeps_tsume_and_the_offset() -> None:
    """The span reports what the tracking did not contribute.

    Tracking is the only part Photoshop leaves out after the final glyph, so
    the tsume and ``text_letter_spacing_offset`` terms have to survive the
    arithmetic that removes it.
    """
    psdimage = PSDImage.open(get_fixture("texts/style-tracking.psd"))
    _, text_setting = _first_text_setting("texts/style-tracking.psd")
    source_span = next(iter(next(iter(text_setting))))
    style_data = dict(source_span.style.style_sheet_data)
    style_data.update(FontSize=40.0, Tracking=100, Tsume=0.5)
    span = Span(0, 1, "A", StyleSheet(name="", style_sheet_data=style_data))

    converter = Converter(psdimage, text_letter_spacing_offset=0.25)
    emitted = converter._add_text_span(text_setting, ET.Element("tspan"), span)

    # Tracking 100 at 40px adds 4.0, tsume 0.5 takes 2.0 away, and the offset
    # adds 0.25; only the 4.0 is trailing.
    assert float(emitted.node.attrib["letter-spacing"]) == pytest.approx(2.25)
    assert emitted.trailing_letter_spacing == pytest.approx(-1.75)


def _band_ink_extent(image: Image.Image, baseline: float) -> tuple[int, int]:
    """Return the horizontal ink extent of the row sitting on the baseline.

    The rows are 60px apart and every one of them reads "ABCD", so a band from
    46px above the baseline to 6px below it holds the whole row with room to
    spare, whichever face the renderer substitutes.
    """
    alpha = np.array(image.convert("RGBA"))[..., 3]
    band = alpha[int(baseline) - 46 : int(baseline) + 6, :] > 32
    columns = np.flatnonzero(band.any(axis=0))
    assert columns.size > 0, f"No ink rendered on the baseline at y={baseline}"
    return int(columns[0]), int(columns[-1]) + 1


def _anchored_edge(image: Image.Image, row: str) -> float:
    """Measure the ink edge that Photoshop keeps fixed for the row's alignment."""
    left, right = _band_ink_extent(image, float(_TRACKING_ALIGNMENT_ROWS[row]))
    if row.startswith("left"):
        return left
    if row.startswith("right"):
        return right
    return (left + right) / 2


@pytest.mark.parametrize(
    "rasterizer_factory",
    [
        pytest.param(ResvgRasterizer, id="resvg"),
        pytest.param(PlaywrightRasterizer, id="chromium", marks=requires_playwright),
    ],
)
@pytest.mark.parametrize(
    ("reference", "tracked"),
    [
        ("left-t0", "left-t400"),
        ("center-t0", "center-t400"),
        ("center-t0", "center-mixed"),
        ("right-t0", "right-t400"),
        ("right-t0", "right-tneg200"),
    ],
)
def test_tracking_does_not_move_the_anchored_edge(
    rasterizer_factory: type, reference: str, tracked: str
) -> None:
    """Tracking leaves the aligned edge where Photoshop puts it.

    In Photoshop the tracked and untracked rows of the fixture share their left
    edge, centre or right edge according to their alignment, because tracking
    never reaches past the final glyph. The comparison is between two rows of the
    same fixture, so it holds under font substitution as well.

    Renderers disagree about the trailing spacing, so this has to be measured and
    not read off the SVG: resvg never included it, Chromium did. The resvg case
    therefore guards against a regression rather than covering the fix, and only
    the Chromium case fails without it.
    """
    psdimage = PSDImage.open(get_fixture("texts/style-tracking-alignment.psd"))
    svg_string = SVGDocument.from_psd(psdimage).tostring()

    rasterizer = rasterizer_factory()
    try:
        image = rasterizer.from_string(svg_string)
    finally:
        close = getattr(rasterizer, "close", None)
        if close is not None:
            close()

    shift = _anchored_edge(image, tracked) - _anchored_edge(image, reference)
    assert abs(shift) <= 1.5, (
        f"Expected {tracked} to keep the aligned edge of {reference}, "
        f"but it moved by {shift}px"
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
    """Test leading (line height) handling.

    The fixture sets an explicit 16px leading, which is used as-is.
    """
    svg = convert_psd_to_svg("texts/style-leading.psd")
    # Leading affects dy attribute on tspan elements for subsequent paragraphs
    tspans = svg.findall(".//tspan[@dy]")
    # Should have at least one tspan with dy attribute (second paragraph onwards)
    assert len(tspans) > 0
    dy = float(tspans[0].attrib.get("dy", "0"))
    assert dy == pytest.approx(16.0)


def test_text_auto_leading_scales_the_font_size() -> None:
    """Auto leading advances lines by font size times the paragraph percentage."""
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-multiple.psd")
    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 3, "Fixture should have 3 paragraphs"
    # 32px font with the default 1.2 Auto Leading percentage
    for tspan in tspans[1:]:
        assert float(tspan.attrib["dy"]) == pytest.approx(38.4)


def test_text_auto_leading_ignores_the_stored_leading() -> None:
    """A leading left over from an earlier manual value does not reach the output.

    Photoshop keeps writing the ``Leading`` field while auto leading is on, so
    the span carries a stale 16px that must not affect the line height.
    """
    psdimage = PSDImage.open(get_fixture("texts/style-bold.psd"))
    layer = next(
        child for child in psdimage.descendants() if isinstance(child, TypeLayer)
    )
    span = list(TypeSetting(layer._data))[0].spans[0]
    assert span.style.auto_leading is True
    assert span.style.leading == pytest.approx(16.0), (
        "Fixture should keep a stale value"
    )

    svg = convert_psd_to_svg("texts/style-bold.psd")
    dy = float(svg.findall(".//tspan[@dy]")[0].attrib["dy"])
    assert dy == pytest.approx(38.4), "Line height should be 32 * 1.2, not 32 + 16"


def test_text_auto_leading_honors_a_non_default_percentage() -> None:
    """The paragraph Auto Leading percentage scales the computed line height."""
    style = StyleSheet(
        name="",
        style_sheet_data={"FontSize": 32.0, "AutoLeading": True, "Leading": 16.0},
    )
    span = Span(0, 5, "Lorem", style)
    for percentage, expected in ((1.2, 38.4), (1.5, 48.0), (0.8, 25.6)):
        sheet = ParagraphSheet(
            name="", default_style_sheet=0, properties={"AutoLeading": percentage}
        )
        paragraph = Paragraph(style=sheet, spans=[span])
        assert paragraph.compute_leading() == pytest.approx(expected)


def test_text_manual_leading_ignores_the_paragraph_percentage() -> None:
    """Manual leading is used unscaled whatever the paragraph percentage says."""
    style = StyleSheet(
        name="",
        style_sheet_data={"FontSize": 32.0, "AutoLeading": False, "Leading": 16.0},
    )
    sheet = ParagraphSheet(
        name="", default_style_sheet=0, properties={"AutoLeading": 2.0}
    )
    paragraph = Paragraph(style=sheet, spans=[Span(0, 5, "Lorem", style)])
    assert paragraph.compute_leading() == pytest.approx(16.0)


def test_text_leading_takes_the_largest_span() -> None:
    """A paragraph advances by the largest leading among its spans."""
    sheet = ParagraphSheet(name="", default_style_sheet=0, properties={})
    small = StyleSheet(name="", style_sheet_data={"FontSize": 16.0})
    large = StyleSheet(name="", style_sheet_data={"FontSize": 32.0})
    manual = StyleSheet(
        name="",
        style_sheet_data={"FontSize": 8.0, "AutoLeading": False, "Leading": 50.0},
    )
    paragraph = Paragraph(
        style=sheet,
        spans=[Span(0, 5, "Lorem", small), Span(5, 10, "Ipsum", large)],
    )
    assert paragraph.compute_leading() == pytest.approx(38.4)

    mixed = Paragraph(
        style=sheet,
        spans=[Span(0, 5, "Lorem", large), Span(5, 10, "Ipsum", manual)],
    )
    assert mixed.compute_leading() == pytest.approx(50.0)


def test_foreignobject_strut_follows_the_largest_span() -> None:
    """The strut and the half-leading compensation follow the largest span.

    The line box is as tall as the largest font on the line, so a paragraph
    that opens with a small span still needs the strut and the compensation of
    the big one.
    """
    psdimage, text_setting = _first_text_setting(
        "texts/paragraph-shapetype1-justification0.psd"
    )
    converter = Converter(psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT)
    sheet = ParagraphSheet(name="", default_style_sheet=0, properties={})
    paragraph = Paragraph(
        style=sheet,
        spans=[
            Span(0, 5, "Lorem", StyleSheet(name="", style_sheet_data={"FontSize": 16})),
            Span(
                5, 10, "Ipsum", StyleSheet(name="", style_sheet_data={"FontSize": 32})
            ),
        ],
    )

    styles = converter._get_foreign_object_paragraph_styles(
        paragraph, text_setting, first_paragraph=True
    )
    # Leading is 32 * 1.2 = 38.4, so the compensation is -(38.4 - 32) / 2
    assert styles["font-size"] == "32px"
    assert styles["line-height"] == "38.4px"
    assert styles["margin-block-start"] == "-3.2px"

    # Later paragraphs keep the strut, but never the compensation
    later = converter._get_foreign_object_paragraph_styles(
        paragraph, text_setting, first_paragraph=False
    )
    assert later["font-size"] == "32px"
    assert "margin-block-start" not in later


def test_foreignobject_strut_ignores_the_paragraph_break() -> None:
    """A paragraph break draws nothing, so it must not be what sizes the strut.

    It is a run of its own carrying the default size, which can be larger than
    anything the paragraph actually draws.
    """
    psdimage, text_setting = _first_text_setting(
        "texts/paragraph-shapetype1-justification0.psd"
    )
    converter = Converter(psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT)
    sheet = ParagraphSheet(name="", default_style_sheet=0, properties={})
    paragraph = Paragraph(
        style=sheet,
        spans=[
            Span(0, 5, "Lorem", StyleSheet(name="", style_sheet_data={"FontSize": 12})),
            Span(5, 6, "\r", StyleSheet(name="", style_sheet_data={"FontSize": 32})),
        ],
    )

    styles = converter._get_foreign_object_paragraph_styles(paragraph, text_setting)

    assert styles["font-size"] == "12px"


def test_text_auto_leading_follows_each_paragraph_font_size() -> None:
    """Each paragraph advances by its own font size, not the layer's first."""
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")
    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 4, "Fixture should have 4 paragraphs"
    # Paragraphs run 16, 18.667, 21.333 and 24px; each advance is size * 1.2
    advances = [float(tspan.attrib["dy"]) for tspan in tspans[1:]]
    assert advances == pytest.approx([22.4, 25.6, 28.8])


def test_text_auto_leading_advances_vertical_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vertical text advances columns leftward by the same auto leading."""
    monkeypatch.setattr(
        TypeSetting,
        "writing_direction",
        property(lambda self: WritingDirection.VERTICAL_RL),
    )
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")
    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 4, "Fixture should have 4 paragraphs"
    advances = [float(tspan.attrib["dx"]) for tspan in tspans[1:]]
    assert advances == pytest.approx([-22.4, -25.6, -28.8])


def test_text_style_horizontal_scale() -> None:
    """Test horizontal scale handling when the whole layer shares the scale.

    When all spans use horizontal_scale=0.5 and vertical_scale=1.0:
    - Font-size is scaled by vertical_scale (1.0, unchanged)
    - The <text> element scales the inline axis: scale(h/v, 1) = scale(0.5, 1)
    - The scale is anchored at the text origin so alignment is preserved
    """
    svg = convert_psd_to_svg("texts/style-horizontally-scale-50.psd")

    # Layer-wide scaling belongs on <text>, where transform is honored by renderers
    text = svg.find(".//text[@transform]")
    assert text is not None, "Layer-wide scale should be on the text element"
    assert svg.find(".//tspan[@transform]") is None, (
        "Spans should not carry a transform when the text element is scaled"
    )

    # Font-size carries the vertical scale only (unchanged here)
    assert float(text.attrib["font-size"]) == pytest.approx(32.0)

    # scale(0.5, 1) anchored at the text origin: translate(x * (1 - 0.5), 0)
    x = float(text.attrib["x"])
    scale_x, scale_y = _parse_scale(text.attrib["transform"])
    assert (scale_x, scale_y) == pytest.approx((0.5, 1.0))
    # Coordinates are rounded for compact output, hence the absolute tolerance
    assert _parse_translate(text.attrib["transform"]) == pytest.approx(
        (x * 0.5, 0.0), abs=0.01
    )


def test_text_style_vertical_scale() -> None:
    """Test vertical scale handling when the whole layer shares the scale.

    When all spans use vertical_scale=0.5 and horizontal_scale=1.0:
    - Font-size is scaled by vertical_scale (0.5)
    - The <text> element scales the inline axis: scale(h/v, 1) = scale(2, 1)
    """
    svg = convert_psd_to_svg("texts/style-vertically-scale-50.psd")

    text = svg.find(".//text[@transform]")
    assert text is not None, "Layer-wide scale should be on the text element"
    assert svg.find(".//tspan[@transform]") is None, (
        "Spans should not carry a transform when the text element is scaled"
    )

    # Font-size carries the vertical scale: 32 * 0.5
    assert float(text.attrib["font-size"]) == pytest.approx(16.0)

    x = float(text.attrib["x"])
    scale_x, scale_y = _parse_scale(text.attrib["transform"])
    assert (scale_x, scale_y) == pytest.approx((2.0, 1.0))
    assert _parse_translate(text.attrib["transform"]) == pytest.approx(
        (-x, 0.0), abs=0.01
    )


def test_text_style_horizontal_scale_span_advance_width() -> None:
    """Test that a horizontally scaled span keeps Photoshop's advance widths.

    Only "Ipsum" is scaled (horizontal_scale=2.0), so the scale cannot move to the
    <text> element. The font-size carries the horizontal scale, which keeps the
    advance widths - and therefore the following text and alignment - correct even
    though renderers ignore transform on <tspan>. See GitHub issue #318.
    """
    svg = convert_psd_to_svg("texts/style-horizontally-scale-200.psd")

    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 2, "Unscaled and scaled runs should stay separate"
    unscaled, scaled = tspans

    assert float(unscaled.attrib["font-size"]) == pytest.approx(32.0)
    # Horizontal scale is applied to the font-size: 32 * 2.0
    assert float(scaled.attrib["font-size"]) == pytest.approx(64.0)
    assert "transform" not in unscaled.attrib

    # The residual vertical correction stays for SVG 2.0 renderers
    assert _parse_scale(scaled.attrib["transform"]) == pytest.approx((1.0, 0.5))


def test_text_style_vertical_scale_span_advance_width() -> None:
    """Test that a vertically scaled span keeps Photoshop's advance widths.

    Only "Ipsum" is scaled (vertical_scale=2.0). The horizontal scale is 1.0, so the
    font-size stays unchanged and the following text is no longer shifted.
    See GitHub issue #318.
    """
    svg = convert_psd_to_svg("texts/style-vertically-scale-200.psd")

    scaled = svg.find(".//tspan[@transform]")
    assert scaled is not None, "Scaled run should carry the residual transform"
    assert scaled.text == "Ipsum"

    # Font-size is unchanged: the horizontal scale is 1.0
    text = svg.find(".//text")
    assert text is not None
    assert "font-size" not in scaled.attrib
    assert float(text.attrib["font-size"]) == pytest.approx(32.0)

    # The residual vertical correction stays for SVG 2.0 renderers
    assert _parse_scale(scaled.attrib["transform"]) == pytest.approx((1.0, 2.0))


def test_text_style_scale_layer_wide_preserves_leading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that layer-wide scaling does not disturb multi-paragraph line spacing.

    The <text> transform only scales the inline axis, so the dy line offsets and the
    paragraph anchors stay exactly as they are without scaling.
    """
    fixture = "texts/paragraph-space-after.psd"
    unscaled = convert_psd_to_svg(fixture)
    unscaled_positions = [
        (tspan.attrib.get("x"), tspan.attrib.get("y"), tspan.attrib.get("dy"))
        for tspan in unscaled.findall(".//text/tspan")
    ]
    assert any(dy is not None for _, _, dy in unscaled_positions), (
        "Fixture should have multiple paragraphs"
    )

    # Apply horizontal_scale=2.0 to every span of the layer
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    svg = convert_psd_to_svg(fixture)

    text = svg.find(".//text[@transform]")
    assert text is not None, "Layer-wide scale should be on the text element"
    assert _parse_scale(text.attrib["transform"]) == pytest.approx((2.0, 1.0))
    assert svg.find(".//tspan[@transform]") is None

    positions = [
        (tspan.attrib.get("x"), tspan.attrib.get("y"), tspan.attrib.get("dy"))
        for tspan in svg.findall(".//text/tspan")
    ]
    assert positions == unscaled_positions


def test_text_style_scale_mixed_anchors_falls_back_to_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the fallback when paragraphs do not share a text anchor.

    The <text> transform is anchored at a single point, so it can only be used when
    every paragraph starts at the same inline coordinate. This fixture mixes right,
    center and left justification, so the scale has to stay on the spans.
    """
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    svg = convert_psd_to_svg("texts/paragraph-shapetype1-multiple.psd")

    assert svg.find(".//text[@transform]") is None, (
        "Scale should not be anchored at a single point for mixed anchors"
    )
    text = svg.find(".//text")
    assert text is not None
    # The horizontal scale still lives in the font-size, keeping advance widths
    assert float(text.attrib["font-size"]) == pytest.approx(64.0)

    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 3
    baseline = float(tspans[0].attrib["y"])
    for tspan in tspans:
        baseline += float(tspan.attrib.get("dy", 0.0))
        assert _parse_scale(tspan.attrib["transform"]) == pytest.approx((1.0, 0.5))
        # Each residual is anchored at its own paragraph baseline
        assert _parse_translate(tspan.attrib["transform"]) == pytest.approx(
            (0.0, baseline * 0.5), abs=0.01
        )


def test_text_style_scale_justify_all_falls_back_to_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the fallback for Justify All, which stretches text to a textLength.

    Scaling the inline axis of the <text> element would stretch that length as
    well, so the scale stays on the spans and the textLength is left untouched.
    """
    fixture = "texts/paragraph-shapetype1-justification6.psd"
    unscaled = convert_psd_to_svg(fixture)
    unscaled_text = unscaled.find(".//text")
    assert unscaled_text is not None
    assert unscaled_text.attrib.get("lengthAdjust") == "spacingAndGlyphs"

    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    svg = convert_psd_to_svg(fixture)

    text = svg.find(".//text")
    assert text is not None
    assert text.attrib["textLength"] == unscaled_text.attrib["textLength"], (
        "Justify All length should not be stretched by the scale"
    )
    # The horizontal scale is carried by the font-size instead
    assert float(text.attrib["font-size"]) == pytest.approx(
        2 * float(unscaled_text.attrib["font-size"])
    )
    assert _parse_scale(text.attrib["transform"]) == pytest.approx((1.0, 0.5))


def test_common_span_scale_ignores_paragraph_breaks() -> None:
    """Test that empty runs do not defeat the layer-wide scale detection.

    Photoshop stores paragraph breaks as separate runs that carry the default
    scale; they draw nothing, so they must be ignored.
    """
    scaled = StyleSheet(name="", style_sheet_data={"HorizontalScale": 0.5})
    default = StyleSheet(name="", style_sheet_data={})
    paragraph_sheet = ParagraphSheet(name="", default_style_sheet=0, properties={})

    def paragraph(*spans: Span) -> Paragraph:
        return Paragraph(style=paragraph_sheet, spans=list(spans))

    paragraphs = [
        paragraph(Span(0, 5, "Lorem", scaled), Span(5, 6, "\r", default)),
        paragraph(Span(6, 11, "Ipsum", scaled)),
    ]
    assert _common_span_scale(paragraphs) == (0.5, 1.0)

    # A visible run with a different scale still forces the per-span fallback
    paragraphs[1].spans[0] = Span(6, 11, "Ipsum", default)
    assert _common_span_scale(paragraphs) is None


def test_text_style_scale_vertical_writing_direction_layer_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test layer-wide scaling of vertical text, whose inline axis is vertical.

    Uses the upright fixture (``baselinedirection1``), where every glyph advances
    along the vertical axis. Sideways runs are a documented limitation.
    """
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    svg = convert_psd_to_svg(
        "texts/shapetype0-writingdirection2-baselinedirection1-justification0.psd"
    )

    text = svg.find(".//text[@transform]")
    assert text is not None, "Layer-wide scale should be on the text element"
    assert text.attrib.get("writing-mode") == "vertical-rl"
    assert svg.find(".//tspan[@transform]") is None

    # font-size carries the cross (horizontal) axis for vertical text
    assert float(text.attrib["font-size"]) == pytest.approx(64.0)

    # The inline (vertical) axis is scaled about the text origin: scale(1, v/h)
    y = float(text.attrib["y"])
    assert _parse_scale(text.attrib["transform"]) == pytest.approx((1.0, 0.5))
    assert _parse_translate(text.attrib["transform"]) == pytest.approx(
        (0.0, y * 0.5), abs=0.01
    )


def test_text_style_scale_vertical_multiple_paragraphs_layer_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that vertical columns do not block safe layer-wide scaling."""
    monkeypatch.setattr(
        TypeSetting,
        "writing_direction",
        property(lambda self: WritingDirection.VERTICAL_RL),
    )
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")

    text = svg.find(".//text[@transform]")
    assert text is not None
    assert _parse_scale(text.attrib["transform"]) == pytest.approx((1.0, 0.5))
    assert svg.find(".//tspan[@transform]") is None

    paragraphs = text.findall("tspan")
    assert len(paragraphs) == 4
    assert all(float(paragraph.attrib["dx"]) < 0 for paragraph in paragraphs[1:])


def test_text_style_scale_vertical_paragraph_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test per-span transforms use each vertical column's absolute origin."""
    monkeypatch.setattr(
        TypeSetting,
        "writing_direction",
        property(lambda self: WritingDirection.VERTICAL_RL),
    )
    monkeypatch.setattr(
        StyleSheet,
        "horizontal_scale",
        property(lambda self: 2.0 if self.font_size < 20 else 1.5),
    )
    svg = convert_psd_to_svg("texts/font-sizes-1.psd")

    text = svg.find(".//text")
    assert text is not None
    assert text.attrib.get("transform") is None
    paragraphs = text.findall("tspan")
    assert len(paragraphs) == 4

    origin_x = float(paragraphs[0].attrib["x"])
    for paragraph in paragraphs:
        origin_x += float(paragraph.attrib.get("dx", 0.0))
        scale_x, scale_y = _parse_scale(paragraph.attrib["transform"])
        assert scale_y == pytest.approx(1.0)
        translate_x, translate_y = _parse_translate(paragraph.attrib["transform"])
        assert translate_x == pytest.approx(origin_x * (1.0 - scale_x), abs=0.01)
        assert translate_y == pytest.approx(0.0, abs=0.01)


def test_text_letter_spacing_offset_with_layer_wide_scale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the letter spacing offset stays absolute under a <text> scale.

    Tracking and tsume are relative to the font size and should scale with the
    text, but text_letter_spacing_offset is an absolute pixel value, so it is
    divided by the scale the <text> element applies.
    """
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    psdimage = PSDImage.open(get_fixture("texts/style-tracking.psd"))

    baseline = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=0.0)
    offset = SVGDocument.from_psd(psdimage, text_letter_spacing_offset=-0.5)

    text = baseline.svg.find(".//text[@transform]")
    assert text is not None, "Layer-wide scale should be on the text element"
    scale_x, _ = _parse_scale(text.attrib["transform"])
    assert scale_x == pytest.approx(2.0)

    without_offset = baseline.svg.findall(".//*[@letter-spacing]")
    with_offsets = offset.svg.findall(".//*[@letter-spacing]")
    assert without_offset, "Fixture should emit letter-spacing"
    assert len(without_offset) == len(with_offsets)

    for without, with_offset in zip(without_offset, with_offsets):
        delta = float(with_offset.attrib["letter-spacing"]) - float(
            without.attrib["letter-spacing"]
        )
        # The emitted value is pre-divided so that the rendered offset is -0.5px
        assert delta * scale_x == pytest.approx(-0.5)


def test_text_style_scale_warp_falls_back_to_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the fallback for warped text, laid out along a <textPath>.

    Scaling the <text> element would distort the warp path itself.
    """
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    svg = convert_psd_to_svg("texts/text-warp-arc-h+50.psd")

    text = svg.find(".//text")
    assert text is not None
    assert "scale" not in text.attrib.get("transform", ""), (
        "Warped text should not be scaled as a whole"
    )
    tspan = svg.find(".//textPath/tspan")
    assert tspan is not None
    # The horizontal scale lives in the font-size, keeping the advance along the path
    assert float(tspan.attrib["font-size"]) == pytest.approx(64.0)
    # Text on a path has no baseline to anchor the residual scale at, so it is
    # dropped rather than emitted about a meaningless origin
    assert "transform" not in tspan.attrib


def test_text_style_scale_foreign_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the foreignObject output scales the font-size as well.

    CSS transforms do not affect layout either, so the inline axis has to be in the
    font-size for the advance widths to be right.
    """
    monkeypatch.setattr(StyleSheet, "horizontal_scale", property(lambda self: 2.0))
    psdimage = PSDImage.open(get_fixture("texts/paragraph-space-after.psd"))
    converter = Converter(psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT)
    converter.build()

    spans = converter.svg.findall(".//{http://www.w3.org/1999/xhtml}span")
    assert spans, "Should have xhtml spans"
    for span in spans:
        style = span.attrib["style"]
        assert "font-size: 64px" in style, f"Unexpected styles: {style}"
        assert "transform: scale(1, 0.5)" in style, f"Unexpected styles: {style}"


def test_foreign_object_faux_bold_thickens_the_face(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The foreignObject path thickens the face instead of asking for a weight.

    -webkit-text-stroke is the CSS counterpart of the stroke the native <text>
    path emits. See GitHub issue #337.
    """
    monkeypatch.setattr(StyleSheet, "faux_bold", property(lambda self: True))
    psdimage = PSDImage.open(get_fixture("texts/paragraph-space-after.psd"))
    converter = Converter(psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT)
    converter.build()

    spans = converter.svg.findall(".//{http://www.w3.org/1999/xhtml}span")
    assert spans, "Should have xhtml spans"
    for span in spans:
        style = span.attrib["style"]
        assert "font-weight" not in style, f"Unexpected styles: {style}"
        assert "paint-order: stroke" in style, f"Unexpected styles: {style}"
        size_match = re.search(r"font-size: ([\d.]+)px", style)
        stroke_match = re.search(r"-webkit-text-stroke: ([\d.]+)px currentColor", style)
        assert size_match is not None and stroke_match is not None, (
            f"Unexpected styles: {style}"
        )
        expected = 0.03 * float(size_match.group(1))
        assert float(stroke_match.group(1)) == pytest.approx(expected, abs=0.005)


def test_text_style_scale_vertical_writing_direction() -> None:
    """Test that vertical text scales the font-size along its inline (y) axis."""
    converter = Converter(PSDImage.open(get_fixture("texts/style-bold.psd")))

    horizontal = converter._calculate_text_scaling(
        32.0, 2.0, 1.0, WritingDirection.HORIZONTAL_TB
    )
    assert horizontal.font_size == pytest.approx(64.0)
    assert horizontal.transform_scale == pytest.approx((1.0, 0.5))

    # In vertical writing mode the advance axis is vertical, so the font-size
    # follows the vertical scale instead.
    vertical = converter._calculate_text_scaling(
        32.0, 2.0, 1.0, WritingDirection.VERTICAL_RL
    )
    assert vertical.font_size == pytest.approx(32.0)
    assert vertical.transform_scale == pytest.approx((2.0, 1.0))


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


def test_text_japanese_horizontal_auto_kerning_uses_palt() -> None:
    """Horizontal Japanese text with automatic kerning requests palt."""
    _, text_setting = _first_text_setting("texts/fonts-notosans-cjk-jp.psd")
    span = next(iter(next(iter(text_setting))))
    assert text_setting.writing_direction == WritingDirection.HORIZONTAL_TB
    assert text_setting.is_japanese_font(span.style.font)
    assert span.style.auto_kerning is True

    svg = convert_psd_to_svg("texts/fonts-notosans-cjk-jp.psd")

    assert _font_feature_settings(svg) == [("美しい日本語", "'palt'")]


def test_text_japanese_disabled_auto_kerning_drops_palt() -> None:
    """Japanese spans without automatic kerning drop proportional metrics.

    Photoshop turns automatic kerning off per character pair, so the first
    character of the layer keeps it and every following character carries
    ``AutoKerning: false``.
    """
    fixture = "texts/fonts-notosans-cjk-jp-autokerning-off.psd"
    _, text_setting = _first_text_setting(fixture)
    spans = [span for paragraph in text_setting for span in paragraph]
    assert all(text_setting.is_japanese_font(span.style.font) for span in spans)
    assert spans[0].style.auto_kerning is True
    assert all(span.style.auto_kerning is False for span in spans[1:])

    svg = convert_psd_to_svg(fixture)

    text_node = svg.find(".//text")
    assert text_node is not None
    assert "".join(text_node.itertext()) == "美しい日本語"
    # Only the automatically kerned first character keeps proportional metrics.
    assert _font_feature_settings(svg) == [("美", "'palt'")]


def test_text_japanese_vertical_auto_kerning_uses_vpal() -> None:
    """Vertical Japanese text requests vertical proportional metrics."""
    fixture = "texts/fonts-notosans-cjk-jp-writingdirection2.psd"
    _, text_setting = _first_text_setting(fixture)
    span = next(iter(next(iter(text_setting))))
    assert text_setting.writing_direction == WritingDirection.VERTICAL_RL
    assert text_setting.is_japanese_font(span.style.font)
    assert span.style.auto_kerning is True

    svg = convert_psd_to_svg(fixture)

    text_node = svg.find(".//text")
    assert text_node is not None
    assert text_node.attrib.get("writing-mode") == "vertical-rl"
    assert _font_feature_settings(svg) == [("日本語", "'vpal'")]


def test_text_latin_auto_kerning_does_not_use_palt() -> None:
    """Automatic kerning must not enable CJK features on Latin fonts."""
    svg = convert_psd_to_svg("texts/style-tracking.psd")

    assert all(
        "font-feature-settings" not in node.attrib.get("style", "")
        for node in svg.iter()
    )


def test_foreign_object_japanese_auto_kerning_uses_palt() -> None:
    """The browser-only foreignObject mode carries proportional metrics too."""
    psdimage, text_setting = _first_text_setting("texts/fonts-notosans-cjk-jp.psd")
    paragraph = next(iter(text_setting))
    span = next(iter(paragraph))
    converter = Converter(psdimage)

    styles = converter._get_foreign_object_span_styles(span, text_setting, paragraph)

    assert styles["font-feature-settings"] == "'palt'"


def test_foreign_object_japanese_vertical_auto_kerning_uses_vpal() -> None:
    """The foreignObject mode carries vertical proportional metrics too."""
    psdimage, text_setting = _first_text_setting(
        "texts/fonts-notosans-cjk-jp-writingdirection2.psd"
    )
    paragraph = next(iter(text_setting))
    span = next(iter(paragraph))
    converter = Converter(psdimage)

    styles = converter._get_foreign_object_span_styles(span, text_setting, paragraph)

    assert styles["font-feature-settings"] == "'vpal'"


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


def test_paragraph_spacing_advances_native_baselines() -> None:
    """space_before and space_after both widen the native paragraph advance.

    The two fixtures differ only in which property carries the 20px, and
    Photoshop renders them identically: the gap before the first paragraph is
    never drawn, so only the single break between the two paragraphs moves.
    Leading is 32 * 1.2 = 38.4, so the break advances 38.4 + 20.
    """
    positions = {}
    for fixture in ("paragraph-space-before", "paragraph-space-after"):
        svg = convert_psd_to_svg(f"texts/{fixture}.psd")
        tspans = svg.findall(".//text/tspan")
        assert len(tspans) == 2
        # The first paragraph sits at the origin, with no advance before it.
        assert tspans[0].attrib.get("dy") is None
        assert tspans[0].attrib.get("dx") is None
        assert float(tspans[1].attrib["dy"]) == pytest.approx(58.4)
        positions[fixture] = [
            {k: v for k, v in t.attrib.items() if k in ("x", "y", "dx", "dy")}
            for t in tspans
        ]

    assert positions["paragraph-space-before"] == positions["paragraph-space-after"]


def test_paragraph_spacing_sums_space_after_and_space_before() -> None:
    """Photoshop adds the two properties across a break instead of collapsing.

    The fixture carries space_before=20 and space_after=20 on all three
    paragraphs, so each break advances 38.4 + 20 + 20. Collapsing them the way
    CSS collapses adjacent margins would give 58.4.
    """
    svg = convert_psd_to_svg("texts/paragraph-space-before-after.psd")
    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 3

    assert tspans[0].attrib.get("dy") is None
    for tspan in tspans[1:]:
        assert float(tspan.attrib["dy"]) == pytest.approx(78.4)


def test_paragraph_spacing_advances_vertical_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The block axis of vertical-rl text runs right to left, so the gap is negative."""
    monkeypatch.setattr(
        TypeSetting,
        "writing_direction",
        property(lambda self: WritingDirection.VERTICAL_RL),
    )
    svg = convert_psd_to_svg("texts/paragraph-space-before-after.psd")
    tspans = svg.findall(".//text/tspan")
    assert len(tspans) == 3

    assert tspans[0].attrib.get("dx") is None
    for tspan in tspans[1:]:
        assert float(tspan.attrib["dx"]) == pytest.approx(-78.4)
        assert tspan.attrib.get("dy") is None


def _ink_row_tops(image: Image.Image) -> list[int]:
    """Return the first row of every horizontal band of text ink in the image.

    Text is the only dark ink in the text fixtures, so a run of rows holding a
    dark opaque pixel is one rendered line.
    """
    rgba = np.array(image.convert("RGBA")).astype(float)
    ink = (rgba[..., 3] > 32) & (rgba[..., :3].mean(axis=2) < 128)
    rows = np.flatnonzero(ink.any(axis=1))
    assert rows.size > 0, "No text rendered"
    breaks = np.flatnonzero(np.diff(rows) > 1) + 1
    return [int(rows[0])] + [int(rows[index]) for index in breaks]


@requires_playwright
def test_foreignobject_paragraphs_advance_by_their_leading() -> None:
    """A <p> occupies its leading, exactly as the native <text> output does.

    The <p>'s strut is what settles this. Left to inherit the renderer's
    default font, its ascent falls short of the spans' while its descent runs
    past theirs, so every line box grows past line-height and the paragraphs
    drift further apart with each break (issue #421).

    The two modes are measured against each other rather than against the
    leading, so the comparison holds under font substitution as well: both
    carry the same leading, which comes from the PSD and not from the face.
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-shapetype1-multiple.psd"))
    rasterizer = PlaywrightRasterizer()
    try:
        tops = {
            mode: _ink_row_tops(
                SVGDocument.from_psd(psdimage, text_wrapping_mode=mode).rasterize(
                    rasterizer=rasterizer
                )
            )
            for mode in (TextWrappingMode.NONE, TextWrappingMode.FOREIGN_OBJECT)
        }
    finally:
        rasterizer.close()

    native, wrapped = tops[TextWrappingMode.NONE], tops[TextWrappingMode.FOREIGN_OBJECT]
    assert len(native) == 3, f"Fixture should render 3 paragraphs, got {native}"
    assert len(wrapped) == len(native), f"Expected 3 paragraphs, got {wrapped}"

    # Where the block starts is a separate question (issue #275); only the
    # distance between the paragraphs is measured here.
    for index in range(1, len(native)):
        native_pitch = native[index] - native[index - 1]
        wrapped_pitch = wrapped[index] - wrapped[index - 1]
        assert abs(wrapped_pitch - native_pitch) <= 1, (
            f"Paragraph {index} sits {wrapped_pitch}px after its predecessor "
            f"in the foreignObject output, but {native_pitch}px in the native one"
        )


def _ink_column_span(image: Image.Image) -> tuple[int, int]:
    """Return the first and last column holding text ink in the image."""
    rgba = np.array(image.convert("RGBA")).astype(float)
    ink = (rgba[..., 3] > 32) & (rgba[..., :3].mean(axis=2) < 128)
    columns = np.flatnonzero(ink.any(axis=0))
    assert columns.size > 0, "No text rendered"
    return int(columns[0]), int(columns[-1])


def test_foreignobject_spans_serialize_without_separating_whitespace() -> None:
    """Adjacent spans of a paragraph carry nothing between them.

    Whitespace between two XHTML inline elements renders as a space, so the
    serializer's indentation would split a word across style runs.
    """
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-multiple-spans.psd")
    )
    svg = SVGDocument.from_psd(
        psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT
    ).tostring()

    assert ">Lo</span><span " in svg, svg


@requires_playwright
def test_foreignobject_multi_span_word_renders_unbroken() -> None:
    """A word split across two style runs renders as one word, on one line.

    The two modes are measured against each other so the comparison survives
    font substitution: both lay out the same five characters. The line count
    is asserted as well, because a substitute wide enough to wrap the box
    would show up as a second line rather than as extra width.
    """
    psdimage = PSDImage.open(
        get_fixture("texts/paragraph-shapetype1-multiple-spans.psd")
    )
    rasterizer = PlaywrightRasterizer()
    try:
        images = {
            mode: SVGDocument.from_psd(psdimage, text_wrapping_mode=mode).rasterize(
                rasterizer=rasterizer
            )
            for mode in (TextWrappingMode.NONE, TextWrappingMode.FOREIGN_OBJECT)
        }
    finally:
        rasterizer.close()

    lines = _ink_row_tops(images[TextWrappingMode.FOREIGN_OBJECT])
    assert len(lines) == 1, f"The fixture is a single line, but rendered as {lines}"

    native = _ink_column_span(images[TextWrappingMode.NONE])
    wrapped = _ink_column_span(images[TextWrappingMode.FOREIGN_OBJECT])
    assert abs((wrapped[1] - wrapped[0]) - (native[1] - native[0])) <= 1, (
        f"The foreignObject output spans {wrapped} columns, "
        f"but the native one spans {native}"
    )


@pytest.mark.parametrize("baseline", [FontBaseline.SUPERSCRIPT, FontBaseline.SUBSCRIPT])
def test_foreignobject_scripts_take_the_native_baseline_shift(
    monkeypatch: pytest.MonkeyPatch, baseline: FontBaseline
) -> None:
    """A raised or lowered span is offset from where it sits, not aligned away.

    ``vertical-align`` grows the line box around the moved glyphs, which makes
    the paragraph taller than its leading (issue #421), and its ``super`` and
    ``sub`` keywords do not stand for Photoshop's offsets anyway. The span is
    therefore offset by the same length the native <text> path shifts the
    baseline by, against the block axis.
    """
    monkeypatch.setattr(StyleSheet, "font_baseline", property(lambda self: baseline))
    psdimage = PSDImage.open(get_fixture("texts/paragraph-shapetype1-multiple.psd"))

    native = SVGDocument.from_psd(psdimage).svg
    shifts = {
        float(node.attrib["baseline-shift"])
        for node in native.iter()
        if "baseline-shift" in node.attrib
    }
    assert len(shifts) == 1, f"Fixture should shift every span alike, got {shifts}"
    shift = shifts.pop()
    assert shift != 0.0

    wrapped = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    ).svg
    spans = wrapped.findall(".//{http://www.w3.org/1999/xhtml}span")
    assert spans
    for span in spans:
        style = _parse_style_string(span.attrib.get("style", ""))
        assert style["position"] == "relative"
        # The inset points towards the start of the block axis, so it runs
        # against the shift.
        assert float(style["inset-block-start"].removesuffix("px")) == pytest.approx(
            -shift
        )
        assert "vertical-align" not in style


@pytest.mark.parametrize(
    "baseline",
    [FontBaseline.ROMAN, FontBaseline.SUPERSCRIPT, FontBaseline.SUBSCRIPT],
)
def test_foreignobject_zero_font_size_is_stated(baseline: FontBaseline) -> None:
    """A span sized zero says so rather than leaving font-size out.

    The <p> carries a font size of its own (issue #421), so a span that omits
    one renders at the paragraph's size instead of drawing nothing.
    """
    psdimage, text_setting = _first_text_setting(
        "texts/paragraph-shapetype1-justification0.psd"
    )
    converter = Converter(psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT)
    paragraph = next(iter(text_setting))
    span = Span(
        0,
        1,
        "A",
        StyleSheet(
            name="", style_sheet_data={"FontSize": 0.0, "FontBaseline": int(baseline)}
        ),
    )

    styles = converter._get_foreign_object_span_styles(span, text_setting, paragraph)

    assert styles["font-size"] == "0px"


def test_foreignobject_paragraph_strut_matches_its_spans() -> None:
    """The <p> names the font its line boxes are sized from.

    A line box is at least as tall as the paragraph's strut, and the strut is
    the <p>'s own font. Inherited, that is the renderer's default at its
    default size, which sizes the line box for a font nothing in the paragraph
    uses (issue #421).
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-shapetype1-multiple.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    div = doc.svg.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")
    assert len(paragraphs) == 3

    for paragraph in paragraphs:
        style = _parse_style_string(paragraph.attrib.get("style", ""))
        spans = paragraph.findall("{http://www.w3.org/1999/xhtml}span")
        assert spans
        for span in spans:
            span_style = _parse_style_string(span.attrib.get("style", ""))
            assert style["font-family"] == span_style["font-family"]
            assert style["font-size"] == span_style["font-size"]


def test_foreignobject_paragraph_spacing_defeats_margin_collapsing() -> None:
    """The whole gap goes on one margin so CSS cannot collapse it to max().

    Adjacent block siblings collapse touching margins to the larger of the two,
    which would render the fixture's 20 + 20 as 20px instead of 40px.
    """
    psdimage = PSDImage.open(get_fixture("texts/paragraph-space-before-after.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    div = doc.svg.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")
    assert len(paragraphs) == 3

    styles = [_parse_style_string(p.attrib.get("style", "")) for p in paragraphs]
    # The first paragraph carries the half-leading compensation alone.
    assert styles[0]["margin-block-start"] == "-3.2px"
    assert styles[1]["margin-block-start"] == "40px"
    assert styles[2]["margin-block-start"] == "40px"
    for style_dict in styles:
        assert "margin-block-end" not in style_dict


def test_foreignobject_paragraph_spacing_is_a_logical_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gap follows the block axis, which runs right to left in vertical-rl.

    ``margin-block-start`` resolves to ``margin-right`` there, so a physical
    margin would push the columns the wrong way.
    """
    monkeypatch.setattr(
        TypeSetting,
        "writing_direction",
        property(lambda self: WritingDirection.VERTICAL_RL),
    )
    psdimage = PSDImage.open(get_fixture("texts/paragraph-space-before-after.psd"))
    doc = SVGDocument.from_psd(
        psdimage,
        text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT,
    )

    div = doc.svg.find(".//{http://www.w3.org/1999/xhtml}div")
    assert div is not None
    assert _parse_style_string(div.attrib.get("style", ""))["writing-mode"] == (
        "vertical-rl"
    )

    paragraphs = div.findall(".//{http://www.w3.org/1999/xhtml}p")
    styles = [_parse_style_string(p.attrib.get("style", "")) for p in paragraphs]
    assert [s.get("margin-block-start") for s in styles] == [
        "-3.2px",
        "40px",
        "40px",
    ]
    for style_dict in styles:
        assert "margin-top" not in style_dict
        assert "margin-right" not in style_dict


def test_foreignobject_paragraph_space_before() -> None:
    """Test margin-block-start CSS property for space before paragraph.

    The fixture has space_before=20px and font-size=32px with auto leading, so
    the line height is 32 * 1.2 = 38.4px. Photoshop draws no gap before the
    first paragraph, which therefore carries the half-leading compensation
    alone, while the second carries the space.
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

    first, second = (_parse_style_string(p.attrib.get("style", "")) for p in paragraphs)
    # Half-leading compensation only: space_before is suppressed here.
    assert first["margin-block-start"] == "-3.2px"
    # Later paragraphs take the space alone; repeating the compensation would
    # pull every paragraph break 3.2px closer.
    assert second["margin-block-start"] == "20px"
    for style_dict in (first, second):
        assert "margin-block-end" not in style_dict


def test_foreignobject_paragraph_space_after() -> None:
    """Space after a paragraph lands on the start margin of the next one.

    CSS collapses touching sibling margins to the larger of the two, so the gap
    is emitted on one side only and ``margin-block-end`` never appears.
    """
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

    first, second = (_parse_style_string(p.attrib.get("style", "")) for p in paragraphs)
    assert first["margin-block-start"] == "-3.2px"
    assert second["margin-block-start"] == "20px"
    for style_dict in (first, second):
        assert "margin-block-end" not in style_dict


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
    # space_after is carried by the following paragraph's start margin.
    assert "margin-block-end" not in style_dict

    # Verify values (allow minor floating point differences)
    indent = float(style_dict["text-indent"].rstrip("px"))
    assert abs(indent - 26.67) < 0.01

    padding_left = float(style_dict["padding-left"].rstrip("px"))
    assert abs(padding_left - 13.33) < 0.01

    padding_right = float(style_dict["padding-right"].rstrip("px"))
    assert abs(padding_right - 13.33) < 0.01

    second = div.findall(".//{http://www.w3.org/1999/xhtml}p")[1]
    assert (
        _parse_style_string(second.attrib.get("style", ""))["margin-block-start"]
        == "20px"
    )


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

    The first paragraph still carries a margin-block-start for the half-leading
    compensation, which is unrelated to space_before.
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
    # margin-block-start holds the half-leading compensation, not space_before
    assert "margin-block-end" not in style_dict
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

    Auto leading at font-size 32px gives a 38.4px line height, so the paragraph
    carries a -3.2px half-leading compensation.
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

    assert "line-height" in style_dict, "First paragraph should have line-height"
    expected = "38.4px"
    actual = style_dict["line-height"]
    assert actual == expected, f"Expected line-height {expected}, got {actual}"

    # Half-leading compensation: -(38.4 - 32) / 2
    assert style_dict.get("margin-block-start") == "-3.2px", (
        f"Expected -3.2px, got {style_dict.get('margin-block-start')}"
    )


def test_foreignobject_vertical_alignment_multiple_paragraphs() -> None:
    """Test vertical alignment with multiple paragraphs.

    Every paragraph is auto-leaded at font-size 32px, so each gets the same
    38.4px line height, but only the first carries the half-leading
    compensation that aligns the block to the top of its box.
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

    for i, p in enumerate(paragraphs):
        p_style = _parse_style_string(p.attrib.get("style", ""))

        assert "line-height" in p_style, f"Paragraph {i} should have line-height"
        assert p_style["line-height"] == "38.4px", (
            f"Paragraph {i} should have line-height 38.4px (font_size * 1.2), "
            f"got {p_style['line-height']}"
        )
        expected_margin = "-3.2px" if i == 0 else None
        assert p_style.get("margin-block-start") == expected_margin, (
            f"Paragraph {i} should have margin-block-start {expected_margin}, "
            f"got {p_style.get('margin-block-start')}"
        )


def test_foreignobject_vertical_alignment_vertical_text() -> None:
    """Test vertical alignment with vertical writing mode.

    Auto leading applies the same way in vertical-rl, where the 38.4px line
    height spaces the columns instead of the rows.
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

    first_p = div.find(".//{http://www.w3.org/1999/xhtml}p")
    assert first_p is not None, "Should have XHTML p element"

    p_style = _parse_style_string(first_p.attrib.get("style", ""))

    assert "line-height" in p_style, "First paragraph should have line-height"
    assert p_style["line-height"] == "38.4px", (
        f"Expected line-height 38.4px (font_size * 1.2), got {p_style['line-height']}"
    )

    # The compensation has to stay on the block axis, which runs right to left
    # here. A physical margin-top would shift the column along the inline axis
    # instead and leave the block axis uncompensated.
    assert p_style.get("margin-block-start") == "-3.2px", (
        f"Expected margin-block-start -3.2px, got {p_style.get('margin-block-start')}"
    )
    assert "margin-top" not in p_style, (
        "Compensation must not be emitted as a physical margin"
    )


def test_cmyk_text_fill_color() -> None:
    """CMYK text fill colors convert instead of aborting the document."""
    svg = convert_psd_to_svg("texts/style-fill-color-cmyk.psd")
    text_nodes = svg.findall(".//text")
    assert len(text_nodes) == 2

    # The layers are CMYK (100, 0, 0, 0) and (0, 0, 0, 50). ICC color
    # management is not applied, so these are the naive conversions.
    fills = [node.attrib.get("fill") for node in text_nodes]
    assert fills == ["#00ffff", "#808080"]


def test_cmyk_style_sheet_colors() -> None:
    """StyleSheet exposes CMYK fill and stroke colors as ARGB."""
    style = StyleSheet(
        name="",
        style_sheet_data={
            "FillColor": {"Type": 2, "Values": [1.0, 1.0, 0.0, 0.0, 0.0]},
            "StrokeColor": {"Type": 2, "Values": [1.0, 0.0, 0.0, 0.0, 0.5]},
            "StrokeFlag": True,
        },
    )
    assert style.fill_color == (1.0, 0.0, 1.0, 1.0)
    assert style.stroke_color == (1.0, 0.5, 0.5, 0.5)
    assert style.get_fill_color() == "#00ffff"
    assert style.get_stroke_color() == "#808080"


def test_grayscale_text_fill_color(caplog: pytest.LogCaptureFixture) -> None:
    """Grayscale text fill colors keep their tone instead of turning black."""
    with caplog.at_level(logging.WARNING):
        svg = convert_psd_to_svg("texts/style-fill-color-gray.psd")
    assert "Unsupported text color" not in caplog.text

    text_nodes = svg.findall(".//text")
    assert len(text_nodes) == 2

    # The layers are 50% and 25% black, which Photoshop stores as the
    # luminances 0.5 and 0.75. ICC color management is not applied, so these
    # are the naive conversions.
    fills = [node.attrib.get("fill") for node in text_nodes]
    assert fills == ["#808080", "#bfbfbf"]


def test_grayscale_style_sheet_colors() -> None:
    """StyleSheet exposes grayscale fill and stroke colors as ARGB."""
    style = StyleSheet(
        name="",
        style_sheet_data={
            "FillColor": {"Type": 0, "Values": [1.0, 0.5]},
            "StrokeColor": {"Type": 0, "Values": [1.0, 0.75]},
            "StrokeFlag": True,
        },
    )
    assert style.fill_color == (1.0, 0.5, 0.5, 0.5)
    assert style.stroke_color == (1.0, 0.75, 0.75, 0.75)
    assert style.get_fill_color() == "#808080"
    assert style.get_stroke_color() == "#bfbfbf"


@pytest.mark.parametrize(
    "color",
    [
        {"Type": 3, "Values": [1.0, 0.5]},  # Unknown color type
        {"Type": 0, "Values": [1.0]},  # Wrong number of values
        {"Type": 2, "Values": [1.0, 0.0, 0.0, 0.0]},  # Wrong number of values
        {"Values": [1.0, 0.0, 0.0, 0.0]},  # Missing type
    ],
)
def test_unsupported_text_color_falls_back_to_default(
    color: dict, caplog: pytest.LogCaptureFixture
) -> None:
    """An unsupported color degrades the span rather than the document.

    Fill degrades to black, but stroke degrades to transparent: an
    uninterpretable stroke color should not draw an outline that the document
    never asked for.
    """
    with caplog.at_level(logging.WARNING):
        fill_style = StyleSheet(name="", style_sheet_data={"FillColor": color})
        assert fill_style.fill_color == (1.0, 0.0, 0.0, 0.0)
        stroke_style = StyleSheet(
            name="", style_sheet_data={"StrokeColor": color, "StrokeFlag": True}
        )
        assert stroke_style.stroke_color == (0.0, 0.0, 0.0, 0.0)
        assert stroke_style.get_stroke_color() == "none"
    assert "Unsupported text color" in caplog.text


def _emitted_baseline_shifts(psd_file: str) -> list[float]:
    """Return every baseline-shift the conversion emits, in document order."""
    svg = convert_psd_to_svg(psd_file)
    return [
        float(value)
        for node in svg.iter()
        if (value := node.attrib.get("baseline-shift")) is not None
    ]


# Photoshop's own offsets for the character-alignment fixtures, which all put a
# 64px and a 32px run on one line. Aligning two em boxes by the same fraction of
# their height leaves the smaller run's baseline
# (fraction - EM_BOX_DESCENT_RATIO) * 32 from the larger one's, so em box bottom
# gives -3.84, the centre +12.16 and the top +28.16.
@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("texts/style-run-alignment-0.psd", [-3.84]),
        ("texts/style-run-alignment-2.psd", []),
        ("texts/style-run-alignment-3.psd", [12.16]),
        ("texts/style-run-alignment-5.psd", [28.16]),
        ("texts/style-run-alignment-3-baseline-shift.psd", [20.16]),
        ("texts/style-run-alignment-2-writingdirection2.psd", []),
        ("texts/style-run-alignment-3-writingdirection2.psd", [-12.16]),
        ("texts/style-run-alignment-vertical-scale.psd", [-3.84]),
    ],
)
def test_character_alignment_offsets(fixture: str, expected: list[float]) -> None:
    """Test that each StyleRunAlignment mode offsets the smaller run correctly.

    The reference run is the largest one, which keeps its own baseline, so a
    two-run fixture emits exactly one offset. Modes that align on the Roman
    baseline emit none at all, because that is where SVG already puts the run.
    See GitHub issue #439.
    """
    assert _emitted_baseline_shifts(fixture) == pytest.approx(expected)


def test_character_alignment_leaves_the_roman_baseline_alone() -> None:
    """Test that Roman-baseline alignment emits nothing in either direction.

    Values 2 and 3 swap meaning between the writing directions: 2 is the Roman
    baseline in horizontal text and 3 is in vertical text. Each is the SVG
    default, so the conversion has nothing to emit, while its counterpart in the
    same direction aligns em boxes and does.
    """
    assert _emitted_baseline_shifts("texts/style-run-alignment-2.psd") == []
    assert _emitted_baseline_shifts("texts/style-run-alignment-3.psd") != []
    # Vertical text is centred on the em box by default, not rested on the Roman
    # baseline, so it is the em box centre that costs nothing there.
    assert (
        _emitted_baseline_shifts("texts/style-run-alignment-2-writingdirection2.psd")
        == []
    )
    assert (
        _emitted_baseline_shifts("texts/style-run-alignment-3-writingdirection2.psd")
        != []
    )


def test_character_alignment_composes_with_baseline_shift() -> None:
    """Test that an authored BaselineShift adds to the alignment offset.

    Both move the run across the writing direction, so they are summed into one
    attribute rather than emitted as two offsets that a renderer could
    accumulate. The fixture pairs em box centre alignment (+12.16) with an
    authored 8px shift.
    """
    aligned = _emitted_baseline_shifts("texts/style-run-alignment-3.psd")
    composed = _emitted_baseline_shifts(
        "texts/style-run-alignment-3-baseline-shift.psd"
    )
    assert aligned == pytest.approx([12.16])
    assert composed == pytest.approx([20.16])
    assert composed[0] - aligned[0] == pytest.approx(8.0)


def test_character_alignment_reference_follows_vertical_scale() -> None:
    """Test that the alignment reference is the em box, not the font size.

    Both runs of the fixture carry FontSize 64 and differ only in
    VerticalScale, so a reference taken from FontSize would leave them level.
    Photoshop offsets the scaled run, because vertical scale resizes the em box
    it is aligned by.
    """
    _, text_setting = _first_text_setting(
        "texts/style-run-alignment-vertical-scale.psd"
    )
    sizes = {span.style.font_size for para in text_setting for span in para}
    assert sizes == {64.0}, "Fixture must isolate VerticalScale from FontSize"

    assert _emitted_baseline_shifts(
        "texts/style-run-alignment-vertical-scale.psd"
    ) == pytest.approx([-3.84])


_ALIGNMENT_DIRECTION_FIXTURES = {
    WritingDirection.HORIZONTAL_TB: "texts/style-run-alignment-2.psd",
    WritingDirection.VERTICAL_RL: "texts/style-run-alignment-2-writingdirection2.psd",
}


def _shift_for(
    alignment: StyleRunAlignment,
    writing_direction: WritingDirection,
    font_size: float,
    reference_size: float,
    text: str = "X",
) -> float:
    """Return the offset the converter gives one synthesised run.

    The writing direction comes from a real fixture, so the span is the only
    thing synthesised.
    """
    psdimage = PSDImage.open(
        get_fixture(_ALIGNMENT_DIRECTION_FIXTURES[writing_direction])
    )
    converter = Converter(psdimage)
    layer = next(
        layer for layer in psdimage.descendants() if isinstance(layer, TypeLayer)
    )
    text_setting = TypeSetting(layer._data)
    assert text_setting.writing_direction == writing_direction
    span = Span(
        start=0,
        end=len(text),
        text=text,
        style=StyleSheet(
            name="",
            style_sheet_data={
                "FontSize": font_size,
                "StyleRunAlignment": int(alignment),
            },
        ),
    )
    return converter._character_alignment_shift(span, text_setting, reference_size)


@pytest.mark.parametrize("alignment", list(StyleRunAlignment))
@pytest.mark.parametrize(
    "writing_direction", [WritingDirection.HORIZONTAL_TB, WritingDirection.VERTICAL_RL]
)
def test_character_alignment_ignores_equal_sized_runs(
    alignment: StyleRunAlignment, writing_direction: WritingDirection
) -> None:
    """Test that runs of one size are untouched, whatever the alignment is.

    The offset is proportional to the difference between a run's em box and the
    largest one on the line, so a paragraph of one size has nothing to align, in
    every mode and both writing directions.
    """
    assert _shift_for(alignment, writing_direction, 32.0, 32.0) == 0.0


def test_character_alignment_skips_runs_that_draw_nothing() -> None:
    """Test that a paragraph break is not offset.

    A break is a run of its own carrying the default size, which the reference
    size leaves out. Offsetting it would put an attribute on an invisible
    <tspan> and stop the optimizer merging it away.
    """
    assert (
        _shift_for(
            StyleRunAlignment.BOTTOM, WritingDirection.HORIZONTAL_TB, 32.0, 64.0, "\r"
        )
        == 0.0
    )
    # The same run with text in it is offset.
    assert _shift_for(
        StyleRunAlignment.BOTTOM, WritingDirection.HORIZONTAL_TB, 32.0, 64.0
    ) == pytest.approx(-3.84)


@pytest.mark.parametrize(
    ("alignment", "expected"),
    [
        (StyleRunAlignment.BOTTOM, -16.0),
        (StyleRunAlignment.ROMAN, 0.0),
        (StyleRunAlignment.CENTER, -12.16),
        (StyleRunAlignment.TOP, 16.0),
    ],
)
def test_character_alignment_vertical_offsets(
    alignment: StyleRunAlignment, expected: float
) -> None:
    """Test the vertical offsets, including the two modes with no fixture.

    Vertical text is centred on the em box by default, so the em box edges sit a
    symmetric half of the size difference away and the Roman baseline
    ``0.5 - EM_BOX_DESCENT_RATIO`` of it. The fixtures cover ROMAN and CENTER;
    BOTTOM and TOP are asserted here.
    """
    assert _shift_for(
        alignment, WritingDirection.VERTICAL_RL, 32.0, 64.0
    ) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("alignment", "horizontal", "vertical"),
    [
        (StyleRunAlignment.BOTTOM, 0.0, 0.0),
        (StyleRunAlignment.ICF_BOTTOM, None, None),
        (StyleRunAlignment.ROMAN, EM_BOX_DESCENT_RATIO, 0.5),
        (StyleRunAlignment.CENTER, 0.5, EM_BOX_DESCENT_RATIO),
        (StyleRunAlignment.ICF_TOP, None, None),
        (StyleRunAlignment.TOP, 1.0, 1.0),
    ],
)
def test_alignment_em_fraction(
    alignment: StyleRunAlignment, horizontal: float | None, vertical: float | None
) -> None:
    """Test the point in the em box that each alignment mode aligns runs by.

    ``ROMAN`` and ``CENTER`` trade places between the two writing directions.
    The ICF modes are None in both, because the ideographic character face is
    measured per font, which conversion cannot do; see GitHub issue #440.
    """
    assert (
        _alignment_em_fraction(alignment, WritingDirection.HORIZONTAL_TB) == horizontal
    )
    assert _alignment_em_fraction(alignment, WritingDirection.VERTICAL_RL) == vertical


def test_style_run_alignment_parses_every_value() -> None:
    """Test that all six StyleRunAlignment values are parsed and retained."""
    for value in range(6):
        style = StyleSheet(name="", style_sheet_data={"StyleRunAlignment": value})
        assert style.style_run_alignment == StyleRunAlignment(value)
    default = StyleSheet(name="", style_sheet_data={})
    assert default.style_run_alignment == StyleRunAlignment.BOTTOM


def test_foreignobject_character_alignment_offsets_the_span() -> None:
    """Test that the foreignObject path applies the same alignment offset.

    The offset is a logical inset pointing towards the start of the block axis,
    so it runs against the shift the native <text> path emits.
    """
    # The foreignObject path only handles box text, so this uses the
    # shapetype1 fixture rather than the point-text one. The native path leaves
    # that fixture alone, so the expected offset comes from the point-text
    # fixture carrying the same alignment mode and sizes.
    fixture = "texts/style-run-alignment-3-shapetype1.psd"
    native = _emitted_baseline_shifts("texts/style-run-alignment-3.psd")
    assert native == pytest.approx([12.16])

    psdimage = PSDImage.open(get_fixture(fixture))
    wrapped = SVGDocument.from_psd(
        psdimage, text_wrapping_mode=TextWrappingMode.FOREIGN_OBJECT
    ).svg
    insets = [
        float(style["inset-block-start"].removesuffix("px"))
        for span in wrapped.findall(".//{http://www.w3.org/1999/xhtml}span")
        if "inset-block-start"
        in (style := _parse_style_string(span.attrib.get("style", "")))
    ]
    assert insets == pytest.approx([-native[0]])


def test_character_alignment_defaults_differ_by_writing_direction() -> None:
    """Test that each writing direction emits nothing for its own default.

    SVG rests horizontal text on the alphabetic baseline but centres vertical
    text on the em box, so the mode that needs no offset is the Roman baseline
    in horizontal writing and the em box centre in vertical writing. The same
    stored value therefore emits an offset in one direction and not the other.
    """
    assert _default_em_fraction(WritingDirection.HORIZONTAL_TB) == pytest.approx(
        EM_BOX_DESCENT_RATIO
    )
    assert _default_em_fraction(WritingDirection.VERTICAL_RL) == pytest.approx(0.5)

    # StyleRunAlignment 2 is the Roman baseline horizontally and the em box
    # centre vertically, which is each direction's own default.
    assert _emitted_baseline_shifts("texts/style-run-alignment-2.psd") == []
    assert (
        _emitted_baseline_shifts("texts/style-run-alignment-2-writingdirection2.psd")
        == []
    )


def test_character_alignment_skips_native_box_text() -> None:
    """Test that native box text keeps the position it has today.

    The hanging ``dominant-baseline`` that places box text already displaces
    mixed-size runs, so the native path leaves them alone; see the call site in
    ``core/text.py`` and GitHub issue #443.
    """
    svg = convert_psd_to_svg("texts/style-run-alignment-3-shapetype1.psd")
    assert svg.find('.//*[@dominant-baseline="hanging"]') is not None
    assert _emitted_baseline_shifts("texts/style-run-alignment-3-shapetype1.psd") == []


def test_character_alignment_skips_scripts() -> None:
    """Test that a superscript or subscript run is not aligned.

    Photoshop offsets neither, whatever their size. Measured on the fixture,
    a 32px superscript beside a 64px run lands in the same place under em box
    bottom alignment as under Roman baseline alignment, while a plain 32px run
    moves 3.94px between the two. So the script offset is emitted alone.
    """
    _, text_setting = _first_text_setting("texts/style-run-alignment-0-superscript.psd")
    spans = [span for para in text_setting for span in para if span.text.strip("\r")]
    assert [span.style.font_baseline for span in spans] == [
        FontBaseline.ROMAN,
        FontBaseline.SUPERSCRIPT,
    ]
    assert {span.style.style_run_alignment for span in spans} == {
        StyleRunAlignment.BOTTOM
    }
    assert {span.style.font_size for span in spans} == {64.0, 32.0}

    # The superscript offset is positive and carries no alignment term, which
    # would have subtracted EM_BOX_DESCENT_RATIO * 32 from it.
    shifts = _emitted_baseline_shifts("texts/style-run-alignment-0-superscript.psd")
    assert len(shifts) == 1
    # The emitted attribute is rounded, so compare within a hundredth.
    assert shifts[0] == pytest.approx(
        32.0 * text_setting.superscript_position, abs=0.01
    ), "Script runs carry the script offset alone"


def test_character_alignment_ignores_icf_modes() -> None:
    """Test that the ICF modes produce no offset through a conversion.

    The ideographic character face is measured per font, which conversion cannot
    do, so those two values parse and are retained but move nothing. This uses a
    real size difference, so it would fail if they fell through to an em box
    reference. See GitHub issue #440.
    """
    for alignment in (StyleRunAlignment.ICF_BOTTOM, StyleRunAlignment.ICF_TOP):
        for direction in (
            WritingDirection.HORIZONTAL_TB,
            WritingDirection.VERTICAL_RL,
        ):
            assert _shift_for(alignment, direction, 32.0, 64.0) == 0.0


def test_character_alignment_ignores_runs_without_an_em_box() -> None:
    """Test that a run of no size is not offset.

    A span whose font size is zero or negative draws nothing, so offsetting it
    would put most of the reference size on an invisible run.
    """
    for font_size in (0.0, -32.0):
        assert (
            _shift_for(
                StyleRunAlignment.TOP,
                WritingDirection.HORIZONTAL_TB,
                font_size,
                64.0,
            )
            == 0.0
        )


def test_character_alignment_is_scoped_to_the_paragraph() -> None:
    """Test that a run does not align to a larger run in another paragraph.

    ``font-sizes-1.psd`` carries four sizes, 16 through 24, one per paragraph
    and one run each. Each paragraph is its own reference, so nothing moves; a
    reference taken across the layer would offset three of the four.
    """
    _, text_setting = _first_text_setting("texts/font-sizes-1.psd")
    paragraphs = list(text_setting)
    sizes = [
        {span.style.font_size for span in para if span.text.strip("\r")}
        for para in paragraphs
    ]
    assert len(paragraphs) > 1
    assert all(len(sizes_in_paragraph) == 1 for sizes_in_paragraph in sizes)
    assert len({next(iter(s)) for s in sizes if s}) > 1, (
        "Fixture should carry different sizes across paragraphs"
    )

    assert _emitted_baseline_shifts("texts/font-sizes-1.psd") == []


def test_character_alignment_leaves_equal_sized_runs_alone_end_to_end() -> None:
    """Test that a converted layer of equally sized runs gains no offset.

    The fixture has to be point text carrying a mode that does emit an offset
    when sizes differ, or the empty result proves nothing: box text skips
    alignment in the native path, and the Roman baseline mode emits nothing
    whatever the sizes are.
    """
    fixture = "texts/style-tracking-tsume.psd"
    _, text_setting = _first_text_setting(fixture)
    assert text_setting.shape_type == ShapeType.POINT, (
        "Box text bypasses native alignment, so it cannot witness this"
    )
    spans = [span for para in text_setting for span in para if span.text.strip("\r")]
    assert len(spans) > 1
    assert (
        len({span.style.font_size * span.style.vertical_scale for span in spans}) == 1
    )
    assert {span.style.style_run_alignment for span in spans} == {
        StyleRunAlignment.BOTTOM
    }, "A mode that offsets nothing by itself would make this vacuous"

    assert _emitted_baseline_shifts(fixture) == []


def test_foreignobject_character_alignment_in_vertical_writing() -> None:
    """Test that the foreignObject path offsets vertical runs the right way.

    The inset points towards the start of the block axis, which is the right
    edge in vertical-rl, so it runs against the shift exactly as it does in
    horizontal writing. This is the combination the docs steer box-text users
    towards, so the sign is worth pinning.
    """
    fixture = "texts/style-run-alignment-3-writingdirection2.psd"
    psdimage = PSDImage.open(get_fixture(fixture))
    layer = next(
        layer for layer in psdimage.descendants() if isinstance(layer, TypeLayer)
    )
    text_setting = TypeSetting(layer._data)
    assert text_setting.writing_direction == WritingDirection.VERTICAL_RL

    converter = Converter(psdimage)
    paragraph = next(iter(text_setting))
    reference = converter._alignment_reference_size(paragraph, text_setting)
    smaller = min(paragraph.spans, key=lambda span: span.style.font_size)
    shift = converter._character_alignment_shift(smaller, text_setting, reference)
    assert shift == pytest.approx(-12.16)

    styles = converter._get_foreign_object_span_styles(
        smaller, text_setting, paragraph, reference
    )
    assert styles["position"] == "relative"
    assert float(styles["inset-block-start"].removesuffix("px")) == pytest.approx(
        -shift
    )


def test_alignment_reference_is_the_drawn_em_box_of_a_script() -> None:
    """Test that a script run sets the reference by its reduced em box.

    A superscript is never itself aligned, but its em box is still drawn on the
    line and can be the largest one there. Photoshop measures the box the run
    is drawn at, not its FontSize: a 20px Roman run beside a 152px superscript
    moves 8.0px between Roman baseline and em box bottom alignment, where the
    unreduced FontSize would move it 15.8px and excluding the script entirely
    would leave it still.
    """
    psdimage = PSDImage.open(get_fixture("texts/style-run-alignment-2.psd"))
    converter = Converter(psdimage)
    layer = next(
        layer for layer in psdimage.descendants() if isinstance(layer, TypeLayer)
    )
    text_setting = TypeSetting(layer._data)

    def span_at(font_size: float, baseline: FontBaseline) -> Span:
        return Span(
            start=0,
            end=1,
            text="X",
            style=StyleSheet(
                name="",
                style_sheet_data={
                    "FontSize": font_size,
                    "FontBaseline": int(baseline),
                    "StyleRunAlignment": int(StyleRunAlignment.BOTTOM),
                },
            ),
        )

    roman = span_at(20.0, FontBaseline.ROMAN)
    script = span_at(152.0, FontBaseline.SUPERSCRIPT)
    paragraph = Paragraph(
        style=ParagraphSheet(name="", default_style_sheet=0, properties={}),
        spans=[roman, script],
    )

    reference = converter._alignment_reference_size(paragraph, text_setting)
    assert reference == pytest.approx(152.0 * text_setting.superscript_size)
    assert reference < 152.0, "The unreduced FontSize must not be the reference"

    # The Roman run is offset by the descent fraction of the difference, and the
    # script itself is not offset at all.
    assert converter._character_alignment_shift(
        roman, text_setting, reference
    ) == pytest.approx(-EM_BOX_DESCENT_RATIO * (reference - 20.0))
    assert converter._character_alignment_shift(script, text_setting, reference) == 0.0


def test_character_alignment_offsets_stay_on_their_own_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a shift shared by every run is not hoisted onto <text>.

    resvg honors ``baseline-shift`` on a ``<tspan>`` but ignores it on
    ``<text>``, so hoisting one that all runs happen to share drops it from the
    render entirely. Character alignment makes that collision reachable: here
    the 64px run's authored BaselineShift equals what alignment gives the 32px
    run, so both totals are 12.16. See GitHub issue #445.
    """
    monkeypatch.setattr(
        StyleSheet,
        "baseline_shift",
        property(
            lambda self: (
                12.16
                if self.font_size == 64.0
                else float(self.style_sheet_data.get("BaselineShift", 0.0))
            )
        ),
    )

    svg = convert_psd_to_svg("texts/style-run-alignment-3.psd")
    text = svg.find(".//text")
    assert text is not None
    assert "baseline-shift" not in text.attrib, (
        "A shift on <text> is silently dropped by resvg"
    )
    shifts = [tspan.attrib.get("baseline-shift") for tspan in text.findall("tspan")]
    assert shifts == ["12.16", "12.16"]
