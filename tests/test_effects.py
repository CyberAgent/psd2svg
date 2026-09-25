"""Tests for layer effect conversion."""

from psd_tools import PSDImage
from psd_tools.api.effects import Stroke
from psd_tools.api.layers import ShapeLayer
from psd_tools.terminology import Enum, Key

from psd2svg.core.converter import Converter
from psd2svg.core.effects import stroke_position
from tests.conftest import get_fixture


def _build(psd_file: str) -> tuple[PSDImage, Converter]:
    psdimage = PSDImage.open(get_fixture(psd_file))
    converter = Converter(psdimage)
    converter.build()
    return psdimage, converter


def test_vector_stroke_effect_opacity_is_normalized() -> None:
    """Effect opacity is a percentage, but ``stroke-opacity`` is 0-1.

    Photoshop stores the Stroke effect's opacity as 0-100. SVG clamps
    ``stroke-opacity`` to [0, 1], so emitting the percentage verbatim made every
    value from 1% to 99% render fully opaque.
    """
    _, converter = _build("effects/stroke-4-vector-color-opacity.psd")

    nodes = [node for node in converter.svg.iter() if "stroke-opacity" in node.attrib]
    assert len(nodes) == 1
    assert nodes[0].attrib["stroke-opacity"] == "0.5"


def test_stroke_effect_branches_agree_on_alpha() -> None:
    """The vector and raster branches must apply the same effective alpha.

    ``apply_stroke_effect`` strokes the path directly for a shape layer and
    falls back to a filter otherwise, and the two used different scales. The
    raster branch is reached here by handing it a target that already carries a
    ``stroke`` attribute, which is the documented stroke-around-stroke case.
    """
    psdimage, converter = _build("effects/stroke-4-vector-color-opacity.psd")
    layer = next(
        layer for layer in psdimage.descendants() if isinstance(layer, ShapeLayer)
    )

    vector = [node for node in converter.svg.iter() if "stroke-opacity" in node.attrib]
    assert len(vector) == 1

    target = converter.create_node(
        "path", id=converter.auto_id("target"), stroke="#f00"
    )
    known = {id(node) for node in converter.svg.iter()}
    converter.apply_stroke_effect(layer, target)
    added = [node for node in converter.svg.iter() if id(node) not in known]

    raster = [node for node in added if node.tag == "use"]
    assert len(raster) == 1
    assert raster[0].attrib["opacity"] == vector[0].attrib["stroke-opacity"]


def test_full_opacity_stroke_effect_emits_no_opacity() -> None:
    """A 100% effect leaves the attribute off, which is why this stayed latent."""
    _, converter = _build("effects/stroke-1-vector-color.psd")

    strokes = [node for node in converter.svg.iter() if "stroke" in node.attrib]
    assert len(strokes) == 1
    assert "stroke-opacity" not in strokes[0].attrib


def test_stroke_without_a_style_key_defaults_to_outside() -> None:
    """``Stroke.position`` is ``None`` when the descriptor omits the key.

    psd-tools stopped fabricating a position for such a descriptor, so the
    converter supplies Photoshop's Outside default rather than passing ``None``
    to ``Enum()``.
    """
    psdimage, converter = _build("effects/stroke-1-vector-color.psd")
    layer = next(
        layer
        for layer in psdimage.descendants()
        if isinstance(layer, ShapeLayer) and layer.effects
    )
    effect = next(iter(layer.effects.find("stroke")))
    assert isinstance(effect, Stroke)
    del effect.descriptor[Key.Style]

    assert effect.position is None
    assert stroke_position(effect) == Enum.OutsetFrame

    # Both branches must convert the layer instead of raising on the ``None``.
    vector = converter.create_node("path", id=converter.auto_id("vector"))
    converter.apply_stroke_effect(layer, vector)
    raster = converter.create_node(
        "path", id=converter.auto_id("raster"), stroke="#f00"
    )
    converter.apply_stroke_effect(layer, raster)
