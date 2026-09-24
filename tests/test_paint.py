"""Tests for paint functionality."""

import logging
from typing import Any
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from psd_tools import PSDImage
from psd_tools.api.layers import Layer
from psd_tools.constants import Tag
from psd_tools.psd import descriptor
from psd_tools.psd.descriptor import UnitFloat
from psd_tools.psd.tagged_blocks import ListElement, TaggedBlocks
from psd_tools.terminology import Key, Unit

from psd2svg.core.converter import Converter
from psd2svg.core.paint import PaintConverter, get_dash_offset_in_pixels
from tests.conftest import get_fixture


class TestPatternTransform:
    """Test pattern transform handling."""

    @pytest.fixture
    def converter(self) -> Any:
        """Create a minimal PaintConverter instance for testing."""
        converter = Mock(spec=PaintConverter)
        converter.set_pattern_transform = PaintConverter.set_pattern_transform.__get__(
            converter, PaintConverter
        )
        return converter

    @pytest.fixture
    def layer(self) -> Any:
        """Create a mock layer."""
        layer = Mock(spec=Layer)
        layer.tagged_blocks = TaggedBlocks()
        layer.tagged_blocks.set_data(Tag.REFERENCE_POINT, ListElement([0, 0]))  # type: ignore[list-item]
        return layer

    @pytest.fixture
    def offset_layer(self) -> Any:
        """Create a mock layer."""
        layer = Mock(spec=Layer)
        layer.tagged_blocks = TaggedBlocks()
        layer.tagged_blocks.set_data(Tag.REFERENCE_POINT, ListElement([0, 12]))  # type: ignore[list-item]
        return layer

    @pytest.fixture
    def node(self) -> Any:
        """Create a test XML element."""
        return ET.Element("pattern")

    @pytest.fixture
    def empty_setting(self) -> Any:
        """Create a mock empty descriptor setting."""
        desc = descriptor.Descriptor()
        return desc

    @pytest.fixture
    def angle_scale_setting(self) -> Any:
        """Create a mock empty descriptor setting."""
        desc = descriptor.Descriptor()
        desc[Key.Angle] = descriptor.UnitFloat(unit=Unit.Angle, value=45.0)
        desc[Key.Scale] = descriptor.UnitFloat(unit=Unit.Percent, value=50.0)
        return desc

    def test_pattern_transform_empty(
        self, converter: Any, layer: Any, node: Any, empty_setting: Any
    ) -> None:
        """Test that setting an empty descriptor does not have pattern transform."""
        converter.set_pattern_transform(layer, empty_setting, node)
        assert "patternTransform" not in node.attrib

    def test_pattern_transform_angle_scale(
        self, converter: Any, layer: Any, node: Any, angle_scale_setting: Any
    ) -> None:
        """Test that setting angle and scale updates pattern transform."""
        converter.set_pattern_transform(layer, angle_scale_setting, node)
        assert "patternTransform" in node.attrib
        assert node.attrib["patternTransform"] == "scale(0.5) rotate(-45)"

    def test_pattern_transform_with_offset(
        self, converter: Any, offset_layer: Any, node: Any, angle_scale_setting: Any
    ) -> None:
        """Test that setting angle and scale with offset prepends translate."""
        converter.set_pattern_transform(offset_layer, angle_scale_setting, node)
        assert "patternTransform" in node.attrib
        assert (
            node.attrib["patternTransform"] == "translate(0,12) scale(0.5) rotate(-45)"
        )


def test_grayscale_solid_fill_colors() -> None:
    """Grayscale fill descriptors store percent black, so the value is inverted."""
    psdimage = PSDImage.open(get_fixture("paint/color-gray.psd"))
    converter = Converter(psdimage)
    converter.build()

    # The layers are 100% and 25% black. ICC color management is not applied,
    # so these are the naive conversions.
    fills = [node.attrib.get("fill") for node in converter.svg.findall(".//rect")]
    assert fills == ["#000000", "#bfbfbf"]


def test_dashed_stroke_is_converted() -> None:
    """Cover the dashed branch of stroke conversion end to end.

    The rounding it depends on is unit-tested separately in
    ``tests/test_svg_utils.py``; what is asserted here is that the whole path
    produces the right attributes for a 72 ppi document, where the
    points-to-pixels scale is 1.
    """
    psdimage = PSDImage.open(get_fixture("paint/stroke-2-dashed.psd"))
    converter = Converter(psdimage)
    converter.build()

    nodes = [
        node for node in converter.svg.iter() if "stroke-dashoffset" in node.attrib
    ]
    assert len(nodes) == 1
    # Photoshop stores 1.3333333; unformatted it would reach the SVG in full.
    # This fixture is 72 ppi, so the points-to-pixels scale is 1.
    assert nodes[0].attrib["stroke-dashoffset"] == "1.33"
    # Dash set entries are unitless multiples of the line width, so they are
    # scaled by it.
    assert nodes[0].attrib["stroke-width"] == "8"
    assert nodes[0].attrib["stroke-dasharray"] == "24,16"


def test_dash_offset_is_scaled_from_points_to_pixels() -> None:
    """The dash offset is stored in points, the rest of the stroke in pixels.

    This fixture is 144 ppi with a 7 pt offset, so the correct pixel value is
    14. Emitting the stored 7 unchanged shifts the dash phase by 7 px against
    a 40 px period.
    """
    psdimage = PSDImage.open(get_fixture("paint/stroke-3-dash-offset-144ppi.psd"))
    converter = Converter(psdimage)
    converter.build()

    nodes = [
        node for node in converter.svg.iter() if "stroke-dashoffset" in node.attrib
    ]
    assert len(nodes) == 1
    assert nodes[0].attrib["stroke-dashoffset"] == "14"
    # The line width is in pixels and the dash set is multiples of it;
    # neither is rescaled by the resolution.
    assert nodes[0].attrib["stroke-width"] == "8"
    assert nodes[0].attrib["stroke-dasharray"] == "24,16"


def test_dash_offset_in_pixels_honors_the_stored_unit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only a points offset is scaled; a pixels offset is already user units."""
    psdimage = PSDImage.open(get_fixture("paint/stroke-3-dash-offset-144ppi.psd"))
    stroke = next(
        layer.stroke for layer in psdimage.descendants() if layer.has_stroke()
    )
    assert stroke is not None
    assert get_dash_offset_in_pixels(stroke) == 14.0

    stroke._data[b"strokeStyleLineDashOffset"] = UnitFloat(unit=Unit.Pixels, value=7.0)
    assert get_dash_offset_in_pixels(stroke) == 7.0

    # Any other unit is passed through unconverted, but noisily.
    stroke._data[b"strokeStyleLineDashOffset"] = UnitFloat(
        unit=Unit.Millimeters, value=7.0
    )
    with caplog.at_level(logging.WARNING, logger="psd2svg.core.paint"):
        assert get_dash_offset_in_pixels(stroke) == 7.0
    assert "Unsupported dash offset unit" in caplog.text


def test_gradient_stops_keep_sub_percent_precision() -> None:
    """Gradient stops are not rounded to a whole percent.

    Photoshop stores stop positions on a 0-4096 scale, so a position set in the
    UI rarely lands on a whole percent: 82 fixtures have a fractional offset.
    This is the only one that also carries fractional opacities, so it pins
    both attributes at once.
    """
    psdimage = PSDImage.open(get_fixture("paint/linear-gradient-8-stops.psd"))
    converter = Converter(psdimage)
    converter.build()

    # Rounded to whole percents the offsets would read 0/33/90/100% and the
    # opacities 25/25/88/100%. The colors are asserted alongside them so that
    # the interpolated stops this fixture adds are covered too.
    assert [node.attrib for node in converter.svg.findall(".//stop")] == [
        {"offset": "0%", "stop-color": "#12d5df", "stop-opacity": "25.1%"},
        {"offset": "33.03%", "stop-color": "#668cea", "stop-opacity": "25.1%"},
        {"offset": "89.67%", "stop-color": "#f70fff", "stop-opacity": "88.45%"},
        {"offset": "100%", "stop-color": "#f70fff", "stop-opacity": "100%"},
    ]
