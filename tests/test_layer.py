"""Tests for the SVG structure produced by layer conversion."""

from xml.etree import ElementTree as ET

import pytest
from psd_tools import PSDImage
from psd_tools.constants import BlendMode

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


class TestClippingBase:
    """Test that a clipping base paints the same inside and outside the mask."""

    @staticmethod
    def split_fills(svg: ET.Element) -> tuple[list[ET.Element], list[ET.Element]]:
        """Return the main fills inside and outside the clipping mask.

        Effects reference the same definition through a filter, so the main
        fill is the reference that carries no filter. A layer mask is a mask of
        its own, so the clipping mask is the one masking alpha.
        """
        masks = [
            mask
            for mask in svg.iter(f"{SVG_NS}mask")
            if mask.get("mask-type") == "alpha"
        ]
        assert len(masks) == 1
        masked = set(masks[0].iter(f"{SVG_NS}use"))
        fills = [use for use in svg.iter(f"{SVG_NS}use") if "filter" not in use.attrib]
        return (
            [use for use in fills if use in masked],
            [use for use in fills if use not in masked],
        )

    @pytest.mark.parametrize("optimize", [False, True])
    @pytest.mark.parametrize(
        "psd_file",
        [
            "clipping/pixel-with-clip-fill-opacity.psd",
            "clipping/group-with-clip-fill-opacity.psd",
        ],
    )
    def test_fill_opacity_and_blend_mode_survive_clipping(
        self, psd_file: str, optimize: bool
    ) -> None:
        """Test that the visible base keeps the fill opacity and the blend mode.

        Both fixtures hold a base at 25% fill opacity blending in multiply. The
        base has effects, so its content is defined in <defs> and the copy
        painted outside the mask has to repeat the main fill instead of
        referencing the bare definition.
        """
        svg = build_svg(psd_file, optimize)
        masked, visible = self.split_fills(svg)
        assert len(masked) == 1
        assert len(visible) == 1
        assert visible[0].get("href") == masked[0].get("href")
        assert visible[0].get("opacity") == masked[0].get("opacity") == "0.25"
        assert "mix-blend-mode: multiply" in visible[0].get("style", "")

    @pytest.mark.parametrize("optimize", [False, True])
    def test_vector_base_keeps_its_paint(self, optimize: bool) -> None:
        """Test that a shape base with effects is painted and stroked.

        A shape layer that carries a layer mask is clipped through a <mask>,
        where the shape definition holds the geometry only. The stroke of the
        base paints over the clipped layers.
        """
        svg = build_svg("clipping/shape-mask-with-clip-stroke-effect.psd", optimize)

        definitions = list(svg.iter(f"{SVG_NS}path"))
        assert len(definitions) == 1
        assert "fill" not in definitions[0].attrib

        masked, visible = self.split_fills(svg)
        assert len(masked) == 2
        fill, stroke = visible
        assert fill.get("fill") == "#7f7f7f"
        assert stroke.get("fill") == "none"
        assert stroke.get("stroke") == "#000000"
        clipped = [
            image for image in svg.findall(f"{SVG_NS}image") if image.get("mask")
        ]
        assert len(clipped) == 1
        assert list(svg).index(clipped[0]) == list(svg).index(stroke) - 1

    @pytest.mark.parametrize("optimize", [False, True])
    def test_full_fill_opacity_group_references_the_definition(
        self, optimize: bool
    ) -> None:
        """Test that a group base only splits its fill once it is reduced.

        A group with effects keeps its content and its layer attributes on the
        group node while the fill opacity is 100%, so the copy painted outside
        the mask is a plain reference.
        """
        svg = build_svg("clipping/group-with-clip-stroke-effect.psd", optimize)
        masked, visible = self.split_fills(svg)
        assert masked == []
        assert len(visible) == 1
        assert visible[0].attrib.keys() == {"href"}

    @pytest.mark.parametrize("optimize", [False, True])
    def test_fill_opacity_is_not_applied_twice_without_effects(
        self, optimize: bool
    ) -> None:
        """Test that a base without effects keeps carrying its own attributes.

        Without effects the layer node itself carries the fill opacity and the
        blend mode, and the reference painted outside the mask must not apply
        them a second time. No fixture holds that combination, so the base of
        a plain clipping fixture is faded here.
        """
        psdimage = PSDImage.open(get_fixture("clipping/pixel-with-blend.psd"))
        base = next(
            layer for layer in psdimage.descendants() if layer.name == "Rectangle 1"
        )
        base.fill_opacity = 64
        base.blend_mode = BlendMode.MULTIPLY
        svg = ET.fromstring(SVGDocument.from_psd(psdimage).tostring(optimize=optimize))

        masked, visible = self.split_fills(svg)
        assert masked == []
        assert len(visible) == 1
        assert "opacity" not in visible[0].attrib
        assert "mix-blend-mode" not in visible[0].get("style", "")
        image = next(
            image
            for image in svg.iter(f"{SVG_NS}image")
            if image.get("opacity") is not None
        )
        assert image.get("opacity") == "0.25"
        assert "mix-blend-mode: multiply" in image.get("style", "")


class TestTextFill:
    """Test the main fill of a text layer that has effects."""

    @pytest.mark.parametrize("optimize", [False, True])
    def test_fill_carries_fill_opacity_and_blend_mode(self, optimize: bool) -> None:
        """Test that the text content is painted like any other main fill.

        The content is defined in <defs> and referenced once for the text
        itself and once per effect, so the fill opacity and the blend mode
        belong to the reference that carries no filter.
        """
        psdimage = PSDImage.open(get_fixture("effects/stroke-3-text.psd"))
        text = next(layer for layer in psdimage.descendants() if layer.has_effects())
        text.fill_opacity = 64
        text.blend_mode = BlendMode.MULTIPLY
        svg = ET.fromstring(SVGDocument.from_psd(psdimage).tostring(optimize=optimize))

        uses = list(svg.iter(f"{SVG_NS}use"))
        fills = [use for use in uses if "filter" not in use.attrib]
        effects = [use for use in uses if "filter" in use.attrib]
        assert len(fills) == 1
        assert fills[0].get("opacity") == "0.25"
        assert "mix-blend-mode: multiply" in fills[0].get("style", "")
        # Effects keep the original alpha and do not blend with the backdrop.
        assert effects
        assert all("opacity" not in use.attrib for use in effects)
        assert all("mix-blend-mode" not in use.get("style", "") for use in effects)
