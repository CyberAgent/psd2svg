"""Tests for blend mode warning functionality."""

import logging
from typing import Any
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from psd_tools.constants import BlendMode
from psd_tools.terminology import Enum

from psd2svg.core.constants import BLEND_MODE, INACCURATE_BLEND_MODES
from psd2svg.core.layer import LayerConverter


class TestBlendModeWarnings:
    """Test that warnings are emitted for inaccurate blend modes."""

    @pytest.fixture
    def converter(self) -> Any:
        """Create a minimal LayerConverter instance for testing."""
        converter = Mock(spec=LayerConverter)
        converter.set_blend_mode = LayerConverter.set_blend_mode.__get__(
            converter, LayerConverter
        )
        return converter

    @pytest.fixture
    def node(self) -> Any:
        """Create a test XML element."""
        return ET.Element("g")

    def test_dissolve_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that dissolve blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.DISSOLVE, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "DISSOLVE" in caplog.text or "Dissolve" in caplog.text
        assert "normal" in caplog.text

    def test_linear_burn_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that linear burn blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.LINEAR_BURN, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "LINEAR_BURN" in caplog.text or "Linear" in caplog.text
        assert "plus-darker" in caplog.text

    def test_linear_dodge_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that linear dodge blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.LINEAR_DODGE, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "LINEAR_DODGE" in caplog.text or "Linear" in caplog.text
        assert "plus-lighter" in caplog.text

    def test_bytes_linear_burn_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that bytes linearBurn also triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.LINEAR_BURN, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "plus-darker" in caplog.text

    def test_bytes_linear_dodge_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that bytes linearDodge also triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.LINEAR_DODGE, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "plus-lighter" in caplog.text

    def test_pin_light_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that pin light blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.PIN_LIGHT, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "normal" in caplog.text

    def test_hard_mix_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that hard mix blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.HARD_MIX, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "normal" in caplog.text

    def test_darker_color_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that darker color blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.DARKER_COLOR, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "darken" in caplog.text

    def test_lighter_color_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that lighter color blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.LIGHTER_COLOR, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "lighten" in caplog.text

    def test_vivid_light_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that vivid light blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.VIVID_LIGHT, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "lighten" in caplog.text

    def test_linear_light_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that linear light blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.LINEAR_LIGHT, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "darken" in caplog.text

    def test_subtract_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that subtract blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.SUBTRACT, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "difference" in caplog.text

    def test_divide_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that divide blend mode triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.DIVIDE, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "difference" in caplog.text

    def test_enum_dissolve_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that Enum.Dissolve also triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(Enum.Dissolve, node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "normal" in caplog.text

    def test_bytes_vivid_light_blend_mode_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that bytes blend mode also triggers a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(b"vividLight", node)

        assert len(caplog.records) == 1
        assert "not accurately supported" in caplog.text
        assert "lighten" in caplog.text

    def test_accurate_blend_mode_no_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that accurate blend modes don't trigger warnings."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.MULTIPLY, node)

        # Should have no warnings
        assert len(caplog.records) == 0

    def test_normal_blend_mode_no_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that normal blend mode doesn't trigger a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.NORMAL, node)

        assert len(caplog.records) == 0

    def test_screen_blend_mode_no_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that screen blend mode doesn't trigger a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.SCREEN, node)

        assert len(caplog.records) == 0

    def test_overlay_blend_mode_no_warning(
        self, converter: Any, node: Any, caplog: Any
    ) -> None:
        """Test that overlay blend mode doesn't trigger a warning."""
        with caplog.at_level(logging.WARNING):
            converter.set_blend_mode(BlendMode.OVERLAY, node)

        assert len(caplog.records) == 0

    def test_unsupported_blend_mode_raises_error(
        self, converter: Any, node: Any
    ) -> None:
        """Test that completely unsupported blend modes raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported blend mode"):
            converter.set_blend_mode(b"unsupported_mode", node)


class TestDescriptorBlendModes:
    """Test descriptor blend modes written as long string IDs.

    Photoshop writes an enumerated blend mode either as the four-character key
    or as the long string ID. Recent versions always write the long form, so
    both spellings must map to the same SVG blend mode.
    """

    # (four-character key, long string ID) as reported by typeIDToStringID().
    EQUIVALENTS = [
        (Enum.Normal, b"normal"),
        (Enum.Dissolve, b"dissolve"),
        (Enum.Darken, b"darken"),
        (Enum.Multiply, b"multiply"),
        (Enum.ColorBurn, b"colorBurn"),
        (Enum.Lighten, b"lighten"),
        (Enum.Screen, b"screen"),
        (Enum.ColorDodge, b"colorDodge"),
        (Enum.Overlay, b"overlay"),
        (Enum.SoftLight, b"softLight"),
        (Enum.HardLight, b"hardLight"),
        (Enum.Difference, b"difference"),
        (Enum.Exclusion, b"exclusion"),
        (Enum.Hue, b"hue"),
        (Enum.Saturation, b"saturation"),
        (Enum.Color, b"color"),
        (Enum.Luminosity, b"luminosity"),
    ]

    @pytest.mark.parametrize("char_id, string_id", EQUIVALENTS)
    def test_string_id_matches_char_id(self, char_id: bytes, string_id: bytes) -> None:
        """Test that both spellings map to the same SVG blend mode."""
        assert BLEND_MODE[string_id] == BLEND_MODE[char_id]

    @pytest.mark.parametrize("char_id, string_id", EQUIVALENTS)
    def test_string_id_accuracy_matches_char_id(
        self, char_id: bytes, string_id: bytes
    ) -> None:
        """Test that both spellings agree on whether the mapping is accurate."""
        assert (string_id in INACCURATE_BLEND_MODES) == (
            char_id in INACCURATE_BLEND_MODES
        )

    def test_pass_through_string_id(self) -> None:
        """Test that the long pass-through spelling is recognized."""
        assert BLEND_MODE[b"passThrough"] == "pass-through"

    def test_normal_string_id_sets_no_style(self) -> None:
        """Test that a long normal blend mode converts without a style."""
        converter = Mock(spec=LayerConverter)
        converter.set_blend_mode = LayerConverter.set_blend_mode.__get__(
            converter, LayerConverter
        )
        node = ET.Element("g")
        converter.set_blend_mode(b"normal", node)
        assert "style" not in node.attrib

    def test_multiply_string_id_sets_style(self) -> None:
        """Test that a long multiply blend mode converts to mix-blend-mode."""
        converter = Mock(spec=LayerConverter)
        converter.set_blend_mode = LayerConverter.set_blend_mode.__get__(
            converter, LayerConverter
        )
        node = ET.Element("g")
        converter.set_blend_mode(b"multiply", node)
        assert "mix-blend-mode: multiply" in node.attrib["style"]
