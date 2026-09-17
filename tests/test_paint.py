"""Tests for paint functionality."""

from typing import Any
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from psd_tools import PSDImage
from psd_tools.api.layers import Layer
from psd_tools.constants import Tag
from psd_tools.psd import descriptor
from psd_tools.psd.tagged_blocks import ListElement, TaggedBlocks
from psd_tools.terminology import Key, Unit

from psd2svg.core.converter import Converter
from psd2svg.core.paint import PaintConverter
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
