"""Tests for the crop_layers_to_canvas option."""

from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

from PIL import Image
from psd_tools import PSDImage
from psd_tools.api import layers
from psd_tools.constants import BlendMode

from psd2svg import SVGDocument
from psd2svg.core.converter import Converter
from tests.conftest import get_fixture

SVG_NS = "{http://www.w3.org/2000/svg}"


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
        """An in-canvas layer's geometry must be identical either way."""
        psdimage = PSDImage.open(get_fixture("layer-types/smartobject-layer.psd"))

        def image_attrs(crop: bool) -> list[dict[str, str]]:
            document = SVGDocument.from_psd(psdimage, crop_layers_to_canvas=crop)
            svg = ET.fromstring(document.tostring())
            return [
                {
                    k: v
                    for k, v in image.attrib.items()
                    if k in ("x", "y", "width", "height")
                }
                for image in svg.iter(f"{SVG_NS}image")
            ]

        assert image_attrs(False) == image_attrs(True)

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
