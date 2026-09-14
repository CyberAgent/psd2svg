"""Tests for the SVG structure produced by layer conversion."""

from xml.etree import ElementTree as ET

import pytest
from psd_tools import PSDImage

from psd2svg import SVGDocument
from tests.conftest import get_fixture

SVG_NS = "{http://www.w3.org/2000/svg}"


def build_svg(psd_file: str, optimize: bool = False) -> ET.Element:
    """Convert a fixture and parse the resulting SVG."""
    document = SVGDocument.from_psd(PSDImage.open(get_fixture(psd_file)))
    return ET.fromstring(document.tostring(optimize=optimize))


class TestGroupFillOpacity:
    """Test that group fill opacity is applied to the content only."""

    @pytest.mark.parametrize("optimize", [False, True])
    def test_fill_opacity_multiplies_layer_opacity(self, optimize: bool) -> None:
        """Test fill opacity without effects, in document order.

        The fixture groups are 'Fill 50 Pass Through', 'Fill 50 Normal',
        'Fill 0' and 'Fill 25 Opacity 50' (0.25 * 0.5 rounds to 0.13).
        """
        svg = build_svg("layer-types/group-fill-opacity.psd", optimize)
        groups = svg.findall(f"{SVG_NS}g")
        assert [g.get("opacity") for g in groups] == ["0.5", "0.5", "0", "0.13"]

    @pytest.mark.parametrize("optimize", [False, True])
    def test_fill_opacity_is_not_applied_to_effects(self, optimize: bool) -> None:
        """Test that layer effects keep the original alpha of the content.

        The fixture groups are 'Overlay Fill 50', 'Overlay Fill 0' and
        'Overlay Fill 50 Multiply', each with a color overlay at 50% effect
        opacity. The content is faded by the fill opacity while the overlay
        keeps its own opacity, so the second group renders as its overlay only.
        """
        svg = build_svg("effects/color-overlay-10-group-fill-opacity.psd", optimize)

        # The content is defined in <defs> and keeps the original alpha.
        definitions = [
            g for defs in svg.iter(f"{SVG_NS}defs") for g in defs.findall(f"{SVG_NS}g")
        ]
        assert len(definitions) == 3
        assert all("opacity" not in g.attrib for g in definitions)

        uses = svg.findall(f"{SVG_NS}use")
        fills = [use for use in uses if "filter" not in use.attrib]
        effects = [use for use in uses if "filter" in use.attrib]
        assert [use.get("opacity") for use in fills] == ["0.5", "0", "0.5"]
        assert [use.get("opacity") for use in effects] == ["0.5", "0.5", "0.5"]

        # Every element references a definition rather than duplicating it.
        ids = {g.get("id") for g in definitions}
        assert {use.get("href") for use in uses} == {f"#{id_}" for id_ in ids}

    @pytest.mark.parametrize("optimize", [False, True])
    def test_group_blend_mode_is_applied_to_the_fill(self, optimize: bool) -> None:
        """Test that the group blend mode travels with the fill, not the effect.

        Only the third fixture group blends, so exactly one element may carry
        mix-blend-mode, and it must be the one carrying the fill opacity.
        """
        svg = build_svg("effects/color-overlay-10-group-fill-opacity.psd", optimize)
        blended = [
            use
            for use in svg.findall(f"{SVG_NS}use")
            if "mix-blend-mode" in use.get("style", "")
        ]
        assert len(blended) == 1
        assert "mix-blend-mode: multiply" in blended[0].get("style", "")
        assert "filter" not in blended[0].attrib
        assert blended[0].get("opacity") == "0.5"

    @pytest.mark.parametrize("optimize", [False, True])
    def test_reduced_fill_opacity_isolates_the_content(self, optimize: bool) -> None:
        """Test that a group with reduced fill opacity composites on its own.

        Photoshop stops treating a pass-through group as pass-through once its
        fill opacity drops below 100%, so the content must not blend with the
        backdrop through the <use> reference.
        """
        svg = build_svg("effects/color-overlay-10-group-fill-opacity.psd", optimize)
        definitions = [
            g for defs in svg.iter(f"{SVG_NS}defs") for g in defs.findall(f"{SVG_NS}g")
        ]
        assert len(definitions) == 3
        assert all("isolation: isolate" in g.get("style", "") for g in definitions)
