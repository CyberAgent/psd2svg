"""Tests for the crop_layers_to_canvas option."""

import sys
from unittest.mock import MagicMock, Mock

import pytest
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api import layers
from psd_tools.constants import BlendMode

import psd2svg.__main__ as cli
from psd2svg import SVGDocument
from psd2svg.core.converter import Converter
from tests.conftest import get_fixture


class TestCropToCanvas:
    """Test Converter._crop_to_canvas() geometry directly."""

    def make_converter(self) -> Converter:
        psdimage = PSDImage.open(get_fixture("layer-types/pixel-layer.psd"))
        return Converter(psdimage)

    def test_bbox_entirely_inside_canvas_is_unchanged(self) -> None:
        converter = self.make_converter()
        image = Image.new("RGBA", (10, 10))
        result = converter._crop_to_canvas(image, 1, 1, 10, 10)
        assert result is not None
        cropped, left, top, width, height = result
        assert (left, top, width, height) == (1, 1, 10, 10)
        assert cropped is image

    def test_bbox_partially_outside_canvas_is_cropped(self) -> None:
        # Canvas is 32x32 (see layer-types/pixel-layer.psd). A bbox that
        # starts before the canvas and extends past it should be cropped to
        # exactly the intersection.
        converter = self.make_converter()
        image = Image.new("RGBA", (40, 40), (1, 2, 3, 4))
        image.putpixel((10, 10), (9, 9, 9, 9))  # inside the future crop
        result = converter._crop_to_canvas(image, -5, -5, 40, 40)
        assert result is not None
        cropped, left, top, width, height = result
        assert (left, top, width, height) == (0, 0, 32, 32)
        assert cropped.size == (32, 32)
        # Original pixel (10, 10) is offset by the crop's (5, 5) origin.
        assert cropped.getpixel((5, 5)) == (9, 9, 9, 9)

    def test_bbox_entirely_outside_canvas_is_dropped(self) -> None:
        converter = self.make_converter()
        image = Image.new("RGBA", (10, 10))
        assert converter._crop_to_canvas(image, -100, -100, 10, 10) is None
        assert converter._crop_to_canvas(image, 1000, 1000, 10, 10) is None


class TestCropLayersToCanvasOption:
    """Test the crop_layers_to_canvas option threaded through SVGDocument."""

    def test_defaults_to_false(self) -> None:
        psdimage = PSDImage.open(get_fixture("layer-types/pixel-layer.psd"))
        converter = Converter(psdimage)
        assert converter.crop_layers_to_canvas is False

    def test_in_bounds_layer_is_unaffected(self) -> None:
        """An in-canvas layer's output, including pixels, must be identical.

        Comparing the full serialized SVG (data URIs and all), not just the
        <image> geometry, so a crop that altered embedded pixel data while
        preserving x/y/width/height would also be caught.
        """
        psdimage = PSDImage.open(get_fixture("layer-types/smartobject-layer.psd"))

        def render(crop: bool) -> str:
            document = SVGDocument.from_psd(psdimage, crop_layers_to_canvas=crop)
            return document.tostring()

        assert render(False) == render(True)

    def test_cli_crop_layers_to_canvas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pass --crop-layers-to-canvas from the CLI to convert()."""
        mock_convert = Mock()
        monkeypatch.setattr(cli, "convert", mock_convert)
        monkeypatch.setattr(
            sys,
            "argv",
            ["psd2svg", "input.psd", "output.svg", "--crop-layers-to-canvas"],
        )

        cli.main()

        assert mock_convert.call_args.kwargs["crop_layers_to_canvas"] is True

    def test_oversized_layer_is_cropped_through_add_pixel(self) -> None:
        """An out-of-bounds layer is cropped when driven through add_pixel().

        Canvas is 32x32 (see layer-types/pixel-layer.psd). No fixture has a
        naturally oversized layer, so a synthetic layer stands in for one.
        """
        psdimage = PSDImage.open(get_fixture("layer-types/pixel-layer.psd"))
        converter = Converter(psdimage, crop_layers_to_canvas=True)

        layer = MagicMock(spec=layers.PixelLayer)
        layer.name = "Oversized"
        layer.kind = "pixel"
        layer.left, layer.top, layer.width, layer.height = -100, -100, 200, 200
        layer.opacity = 255
        layer.blend_mode = BlendMode.NORMAL
        layer.has_pixels.return_value = True
        layer.has_effects.return_value = False
        layer.has_mask.return_value = False
        layer.topil.return_value = Image.new("RGBA", (200, 200), (5, 6, 7, 8))
        layer.tagged_blocks.get_data.return_value = 255

        node = converter.add_pixel(layer)

        assert node is not None
        assert (node.get("x"), node.get("y")) == ("0", "0")
        assert (node.get("width"), node.get("height")) == ("32", "32")
        [image] = converter.images.values()
        assert image.size == (32, 32)

    def test_adjustment_layer_with_effects_is_never_cropped(self) -> None:
        """An AdjustmentLayer/Artboard with effects must not be cropped.

        Regression: the crop gate used to key off has_separate_fill(),
        which returns False for an Artboard or AdjustmentLayer regardless
        of has_effects() (they paint their content in place instead). If
        such a layer ever reached add_pixel() with effects, that made it
        look exempt-from-effects and thus eligible for cropping. The gate
        must check has_effects() directly.
        """
        psdimage = PSDImage.open(get_fixture("layer-types/pixel-layer.psd"))
        converter = Converter(psdimage, crop_layers_to_canvas=True)

        layer = MagicMock(spec=layers.AdjustmentLayer)
        layer.name = "Adjustment"
        layer.kind = "adjustmentlayer"
        # Canvas is 32x32; this bbox lies far outside it.
        layer.left, layer.top, layer.width, layer.height = -100, -100, 200, 200
        layer.opacity = 255
        layer.blend_mode = BlendMode.NORMAL
        layer.has_pixels.return_value = True
        layer.has_effects.return_value = True
        layer.has_mask.return_value = False
        layer.topil.return_value = Image.new("RGBA", (200, 200), (5, 6, 7, 8))
        layer.tagged_blocks.get_data.return_value = 255

        assert converter.has_separate_fill(layer) is False

        node = converter.add_pixel(layer)

        assert node is not None
        assert (node.get("x"), node.get("y")) == ("-100", "-100")
        assert (node.get("width"), node.get("height")) == ("200", "200")

    def make_pixel_layer(
        self,
        *,
        name: str,
        left: int,
        top: int,
        width: int,
        height: int,
        has_effects: bool = False,
    ) -> MagicMock:
        layer = MagicMock(spec=layers.PixelLayer)
        layer.name = name
        layer.kind = "pixel"
        layer.left, layer.top, layer.width, layer.height = left, top, width, height
        layer.opacity = 255
        layer.blend_mode = BlendMode.NORMAL
        layer.has_pixels.return_value = True
        layer.has_effects.return_value = has_effects
        layer.has_mask.return_value = False
        layer.has_vector_mask.return_value = False
        layer.topil.return_value = Image.new("RGBA", (width, height), (1, 2, 3, 4))
        layer.tagged_blocks.get_data.return_value = 255
        return layer

    def test_offcanvas_layer_used_as_clip_base_does_not_raise(self) -> None:
        """An off-canvas clipping base must not crash add_clipping_target().

        Regression: add_pixel() used to return None for a layer entirely
        outside the canvas, and add_clipping_target()/add_clip_mask() raise
        ValueError whenever the base returns None.
        """
        psdimage = PSDImage.open(get_fixture("layer-types/pixel-layer.psd"))
        converter = Converter(psdimage, crop_layers_to_canvas=True)
        # Canvas is 32x32; this base lies entirely outside it.
        layer = self.make_pixel_layer(
            name="outside", left=40, top=40, width=10, height=10
        )

        with converter.add_clipping_target(layer) as clip_attrib:
            assert "mask" in clip_attrib

        # The in-memory tree uses bare tag names; the SVG namespace is only
        # attached to elements once serialized via document.tostring().
        rect = converter.svg.find(".//rect")
        assert rect is not None
        assert (rect.get("width"), rect.get("height")) == ("0", "0")

    def test_effects_layer_is_never_cropped(self) -> None:
        """A layer with effects is exempted from cropping regardless.

        drop-shadow-1.psd (canvas 128x128) has two pixel layers: 'Background'
        (no effects, full-canvas bbox) and 'Star 1' (has effects, in-bounds
        bbox). Only a layer without effects may ever reach the crop helper.
        """
        psdimage = PSDImage.open(get_fixture("effects/drop-shadow-1.psd"))
        converter = Converter(psdimage, crop_layers_to_canvas=True)
        real_crop_to_canvas = converter._crop_to_canvas
        spy = MagicMock(side_effect=real_crop_to_canvas)
        converter._crop_to_canvas = spy  # type: ignore[method-assign]

        converter.build()

        assert spy.call_count == 1
        _, left, top, width, height = spy.call_args.args
        assert (left, top, width, height) == (0, 0, 128, 128)

    def test_child_of_effects_group_is_never_cropped_directly(self) -> None:
        """A child beneath a group with effects is exempted, even in bounds.

        Regression: the effects exemption only checked the layer's own
        effects. A group's effects (e.g. a drop shadow) consume the
        composited alpha of its children, so a child must stay uncropped
        even when it has no effects of its own.
        """
        psdimage = PSDImage.open(get_fixture("layer-types/pixel-layer.psd"))
        converter = Converter(psdimage, crop_layers_to_canvas=True)
        group = MagicMock(spec=layers.Group)
        group.has_effects.return_value = True
        # Canvas is 32x32; this child lies far outside it.
        child = self.make_pixel_layer(
            name="child", left=-100, top=-100, width=200, height=200
        )

        with converter._track_effects_ancestor(group):
            node = converter.add_pixel(child)

        assert node is not None
        assert (node.get("x"), node.get("y")) == ("-100", "-100")
        assert (node.get("width"), node.get("height")) == ("200", "200")

    def test_group_with_effects_exempts_its_children_from_cropping(self) -> None:
        """End-to-end: a real effects group's children never reach the crop.

        color-overlay-10-group-fill-opacity.psd has two top-level pixel
        layers ('Background', 'Base') with no effects ancestor, and three
        groups with a color overlay effect, each with one effect-free pixel
        child. Only the two top-level layers may reach the crop helper.
        """
        psdimage = PSDImage.open(
            get_fixture("effects/color-overlay-10-group-fill-opacity.psd")
        )
        converter = Converter(psdimage, crop_layers_to_canvas=True)
        real_crop_to_canvas = converter._crop_to_canvas
        spy = MagicMock(side_effect=real_crop_to_canvas)
        converter._crop_to_canvas = spy  # type: ignore[method-assign]

        converter.build()

        assert spy.call_count == 2
        assert converter._effects_ancestor_depth == 0
