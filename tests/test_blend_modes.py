"""Tests for blend mode warning functionality."""

import logging
from typing import Any
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from psd_tools import PSDImage
from psd_tools.constants import BlendMode
from psd_tools.terminology import Enum

from psd2svg import SVGDocument
from psd2svg.core.constants import BLEND_MODE, INACCURATE_BLEND_MODES
from psd2svg.core.layer import LayerConverter
from tests.conftest import get_fixture


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


class TestFilterBlendModes:
    """Test the exact filter route for blend modes CSS cannot express."""

    @staticmethod
    def _overlay(psd_file: str) -> tuple[ET.Element, ET.Element]:
        """Convert a fixture and return its single overlay filter and its user."""
        document = SVGDocument.from_psd(PSDImage.open(get_fixture(psd_file)))
        filters = document.svg.findall(".//{*}filter")
        assert len(filters) == 1
        uses = document.svg.findall(".//{*}use[@filter]")
        assert len(uses) == 1
        return filters[0], uses[0]

    @staticmethod
    def _tags(filter: ET.Element) -> list[str]:
        return [child.tag.rpartition("}")[2] for child in filter]

    def test_divide_inverts_the_fill_and_dodges(self) -> None:
        """Test that Divide becomes color-dodge on an inverted fill."""
        filter, use = self._overlay("blend-modes/effect-divide.psd")
        assert filter.get("color-interpolation-filters") == "sRGB"
        assert self._tags(filter) == ["feImage", "feComponentTransfer", "feComposite"]
        assert [child.get("tableValues") for child in filter[1]] == ["1 0"] * 3
        assert filter[2].get("operator") == "in"
        assert filter[2].get("in2") == "SourceAlpha"
        assert "mix-blend-mode: color-dodge" in use.get("style", "")

    @pytest.mark.parametrize(
        "psd_file, inverts, offset",
        [
            ("blend-modes/effect-subtract.psd", True, "-1"),
            ("blend-modes/effect-linear-burn.psd", False, "-1"),
            ("blend-modes/effect-linear-dodge.psd", False, "0"),
        ],
    )
    def test_sums_use_arithmetic_composite(
        self, psd_file: str, inverts: bool, offset: str
    ) -> None:
        """Test that the additive modes sum the fill and the layer in the filter."""
        filter, use = self._overlay(psd_file)
        assert filter.get("color-interpolation-filters") == "sRGB"
        assert "mix-blend-mode" not in use.get("style", "")
        expected = ["feImage"]
        if inverts:
            expected.append("feComponentTransfer")
        expected += ["feComponentTransfer", "feComposite", "feComposite"]
        assert self._tags(filter) == expected

        # The sum runs against an opaque copy of the layer, so that the constant
        # offset is not applied to premultiplied values.
        opaque = filter[-3]
        assert opaque.get("in") == "SourceGraphic"
        assert [
            (child.tag.rpartition("}")[2], child.get("tableValues")) for child in opaque
        ] == [("feFuncA", "1 1")]
        assert filter[-4].get("result") == "fill"

        arithmetic = filter[-2]
        assert arithmetic.get("operator") == "arithmetic"
        assert arithmetic.get("in") == "fill"
        assert arithmetic.get("in2") == opaque.get("result")
        assert (
            arithmetic.get("k1"),
            arithmetic.get("k2"),
            arithmetic.get("k3"),
            arithmetic.get("k4"),
        ) == ("0", "1", "1", offset)

        # ... and the layer alpha is re-applied to the sum.
        assert filter[-1].get("operator") == "in"
        assert filter[-1].get("in2") == "SourceAlpha"

    @pytest.mark.parametrize(
        "psd_file",
        [
            "blend-modes/effect-divide.psd",
            "blend-modes/effect-subtract.psd",
            "blend-modes/effect-linear-burn.psd",
            "blend-modes/effect-linear-dodge.psd",
        ],
    )
    def test_no_approximation_warning(self, psd_file: str, caplog: Any) -> None:
        """Test that the exact route does not warn about an approximation."""
        with caplog.at_level(logging.WARNING):
            SVGDocument.from_psd(PSDImage.open(get_fixture(psd_file)))

        assert not [
            r for r in caplog.records if "not accurately supported" in r.message
        ]
