import contextlib
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, Iterator, Protocol

from PIL import Image
from psd_tools import PSDImage
from psd_tools.api import adjustments, layers
from psd_tools.constants import BlendMode
from psd_tools.psd.descriptor import Descriptor

if TYPE_CHECKING:
    pass


class ConverterProtocol(Protocol):
    """Converter state protocol."""

    psd: PSDImage
    svg: ET.Element
    current: ET.Element
    images: dict[str, Image.Image]
    # Note: fonts dict removed - PostScript names stored directly in SVG

    # Flags to control the conversion.
    enable_live_shapes: bool
    enable_text: bool
    enable_title: bool
    enable_class: bool

    # Text conversion configuration
    text_letter_spacing_offset: float
    text_wrapping_mode: int

    def add_layer(
        self, layer: layers.Layer, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_artboard(
        self, layer: layers.Artboard, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_group(
        self, layer: layers.Group, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_pixel(
        self, layer: layers.Layer, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_shape(
        self, layer: layers.ShapeLayer, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_text(
        self, layer: layers.TypeLayer, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_fill(
        self,
        layer: adjustments.SolidColorFill
        | adjustments.GradientFill
        | adjustments.PatternFill,
        depth: int = 0,
        **attrib: str,
    ) -> ET.Element | None: ...

    # Layer attributes
    def set_layer_attributes(self, layer: layers.Layer, node: ET.Element) -> None: ...
    def set_isolation(self, layer: layers.Layer, node: ET.Element) -> None: ...
    def apply_mask(self, layer: layers.Layer, node: ET.Element) -> ET.Element: ...
    def set_opacity(self, opacity: float, node: ET.Element) -> None: ...
    def set_blend_mode(self, psd_mode: bytes | BlendMode, node: ET.Element) -> None: ...
    def add_linear_gradient(self, setting: Descriptor) -> ET.Element: ...
    def add_radial_gradient(self, setting: Descriptor) -> ET.Element: ...
    def add_pattern(self, psdimage: PSDImage, descriptor: Descriptor) -> ET.Element: ...

    # Shape methods
    def create_shape(self, layer: layers.ShapeLayer, **attrib: Any) -> ET.Element: ...

    # Text methods
    def create_text_node(self, layer: layers.TypeLayer) -> ET.Element: ...

    # Paint methods
    def apply_vector_fill(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, target: ET.Element
    ) -> None: ...
    def apply_vector_stroke(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, target: ET.Element
    ) -> None: ...
    def set_fill(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, node: ET.Element
    ) -> None: ...
    def set_stroke(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, node: ET.Element
    ) -> None: ...

    # Layer effects
    def apply_background_effects(
        self, layer: layers.Layer, target: ET.Element, insert_before_target: bool = True
    ) -> None: ...
    def apply_overlay_effects(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_drop_shadow_effect(
        self,
        layer: layers.Layer,
        target: ET.Element,
        insert_before_target: bool = False,
    ) -> None: ...
    def apply_outer_glow_effect(
        self,
        layer: layers.Layer,
        target: ET.Element,
        insert_before_target: bool = False,
    ) -> None: ...
    def apply_color_overlay_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_gradient_overlay_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_pattern_overlay_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_inner_shadow_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_inner_glow_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_satin_effect(self, layer: layers.Layer, target: ET.Element) -> None: ...
    def apply_bevel_emboss_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None: ...
    def apply_stroke_effect(self, layer: layers.Layer, target: ET.Element) -> None: ...

    # Adjustments
    def add_invert_adjustment(
        self, layer: adjustments.Invert, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_posterize_adjustment(
        self, layer: adjustments.Posterize, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_hue_saturation_adjustment(
        self, layer: adjustments.HueSaturation, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_exposure_adjustment(
        self, layer: adjustments.Exposure, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_brightness_contrast_adjustment(
        self, layer: adjustments.BrightnessContrast, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_threshold_adjustment(
        self, layer: adjustments.Threshold, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_color_balance_adjustment(
        self, layer: adjustments.ColorBalance, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_black_and_white_adjustment(
        self, layer: adjustments.BlackAndWhite, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_channel_mixer_adjustment(
        self, layer: adjustments.ChannelMixer, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_color_lookup_adjustment(
        self, layer: adjustments.ColorLookup, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_curves_adjustment(
        self, layer: adjustments.Curves, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_gradient_map_adjustment(
        self, layer: adjustments.GradientMap, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_levels_adjustment(
        self, layer: adjustments.Levels, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_photo_filter_adjustment(
        self, layer: adjustments.PhotoFilter, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_selective_color_adjustment(
        self, layer: adjustments.SelectiveColor, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...
    def add_vibrance_adjustment(
        self, layer: adjustments.Vibrance, depth: int = 0, **attrib: str
    ) -> ET.Element | None: ...

    # Utilities
    def auto_id(self, prefix: str = "") -> str: ...
    def create_node(
        self,
        tag: str,
        parent: ET.Element | None = None,
        class_: str = "",
        title: str = "",
        text: str = "",
        desc: str = "",
        **kwargs: Any,
    ) -> ET.Element: ...
    @contextlib.contextmanager
    def set_current(self, node: ET.Element) -> Iterator[None]: ...
