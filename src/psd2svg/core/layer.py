import contextlib
import logging
from typing import Callable, Iterator
from xml.etree import ElementTree as ET

from psd_tools import PSDImage
from psd_tools.api import adjustments, layers
from psd_tools.constants import BlendMode, Tag

from psd2svg import svg_utils
from psd2svg.core.base import ConverterProtocol
from psd2svg.core.constants import BLEND_MODE, INACCURATE_BLEND_MODES
from psd2svg.resource_limits import WEBP_MAX_DIMENSION

logger = logging.getLogger(__name__)


class LayerConverter(ConverterProtocol):
    """Main layer converter mixin."""

    def add_layer(
        self, layer: layers.Layer, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a layer to the svg document.

        Args:
            layer: The PSD layer to add.
            depth: Current nesting depth (for resource limit checking).
            attrib: Additional attributes to set on the created node.
        """
        if not layer.is_visible():
            # TODO: Option to include hidden layers.
            logger.debug(f"Layer '{layer.name}' ({layer.kind}) is invisible, skipping.")
            return None
        logger.debug(f"Adding layer: '{layer.name}' ({layer.kind})")

        # Simple registry-based dispatch.
        # Note: Type annotation simplified to avoid complex variance issues
        registry: dict[type, Callable] = {
            layers.Artboard: self.add_artboard,
            layers.Group: self.add_group,
            layers.PixelLayer: self.add_pixel,
            layers.ShapeLayer: self.add_shape,
            layers.SmartObjectLayer: self.add_pixel,
            layers.TypeLayer: self.add_text,
            adjustments.BlackAndWhite: self.add_black_and_white_adjustment,
            adjustments.BrightnessContrast: self.add_brightness_contrast_adjustment,
            adjustments.ChannelMixer: self.add_channel_mixer_adjustment,
            adjustments.ColorBalance: self.add_color_balance_adjustment,
            adjustments.ColorLookup: self.add_color_lookup_adjustment,
            adjustments.Curves: self.add_curves_adjustment,
            adjustments.Exposure: self.add_exposure_adjustment,
            adjustments.GradientFill: self.add_fill,
            adjustments.GradientMap: self.add_gradient_map_adjustment,
            adjustments.HueSaturation: self.add_hue_saturation_adjustment,
            adjustments.Invert: self.add_invert_adjustment,
            adjustments.Levels: self.add_levels_adjustment,
            adjustments.PatternFill: self.add_fill,
            adjustments.PhotoFilter: self.add_photo_filter_adjustment,
            adjustments.Posterize: self.add_posterize_adjustment,
            adjustments.SelectiveColor: self.add_selective_color_adjustment,
            adjustments.SolidColorFill: self.add_fill,
            adjustments.Threshold: self.add_threshold_adjustment,
            adjustments.Vibrance: self.add_vibrance_adjustment,
        }
        # Default layer_fn is a plain pixel layer.
        layer_fn = registry.get(type(layer), self.add_pixel)
        return layer_fn(layer, depth=depth, **attrib)  # type: ignore[call-arg]

    def add_artboard(
        self, layer: layers.Artboard, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add an artboard layer to the svg document."""
        node = self.create_node(
            "svg",
            class_=layer.kind,
            title=layer.name,
            x=layer.left,
            y=layer.top,
            width=layer.width,
            height=layer.height,
            viewBox=svg_utils.seq2str(
                [layer.left, layer.top, layer.width, layer.height]
            ),
            id=self.auto_id("artboard") if layer.has_effects() else None,
            **attrib,  # type: ignore[arg-type]
        )
        with self.set_current(node):
            self.add_children(layer, depth=depth + 1)
        return node

    def add_group(
        self, layer: layers.Group, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a group layer to the svg document."""
        fill_opacity = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255)

        # Fill opacity applies to the group content but not to its effects, so
        # when both are present the content has to be defined in <defs> and
        # referenced by a separate <use> carrying the fill opacity. Effects then
        # reference the definition and keep the original alpha.
        if self.has_separate_fill(layer):
            defs = self.create_node("defs")
            node = self.create_node(
                "g",
                parent=defs,
                class_=layer.kind,
                title=layer.name,
                id=self.auto_id("group"),
                **attrib,  # type: ignore[arg-type]
            )
            with self.set_current(node):
                self.add_children(layer, depth=depth + 1)

            self.set_opacity(layer.opacity / 255, node)
            # Reduced fill opacity makes a group composite on its own, so
            # pass-through blending no longer applies to the content.
            svg_utils.add_style(node, "isolation", "isolate")
            node = self.apply_mask(layer, node)

            self.apply_background_effects(layer, node, insert_before_target=False)
            self.apply_raster_fill(layer, node)
            self.apply_overlay_effects(layer, node)
            self.apply_stroke_effect(layer, node)
            return node

        node = self.create_node(
            "g",
            class_=layer.kind,
            title=layer.name,
            id=self.auto_id("group") if layer.has_effects() else None,
            **attrib,  # type: ignore[arg-type]
        )
        with self.set_current(node):
            self.add_children(layer, depth=depth + 1)

        self.apply_background_effects(layer, node, insert_before_target=True)
        self.apply_overlay_effects(layer, node)
        self.apply_stroke_effect(layer, node)
        # Without effects, fill opacity and layer opacity simply multiply.
        self.set_opacity(fill_opacity / 255, node)
        self.set_layer_attributes(layer, node)
        node = self.apply_mask(layer, node)
        return node

    def add_children(
        self, group: layers.Group | layers.Artboard | PSDImage, depth: int = 0
    ) -> None:
        """Add child layers to the current node.

        Args:
            group: Group/Artboard/PSDImage to process.
            depth: Current nesting depth (for resource limit checking).

        Raises:
            ValueError: If depth exceeds resource_limits.max_layer_depth.
        """
        # Check depth limit
        if (
            hasattr(self, "resource_limits")
            and self.resource_limits
            and self.resource_limits.is_layer_depth_limited()
        ):
            if depth >= self.resource_limits.max_layer_depth:
                raise ValueError(
                    f"Layer depth {depth} exceeds limit {self.resource_limits.max_layer_depth}. "  # noqa: E501
                    f"PSD has deeply nested layer groups. "
                    f"To process: set PSD2SVG_MAX_LAYER_DEPTH={depth + 50} environment variable, "  # noqa: E501
                    f"or use ResourceLimits(max_layer_depth={depth + 50}) in Python API."  # noqa: E501
                )

        for layer in group:
            if layer.clipping or not layer.is_visible():
                continue

            if layer.has_clip_layers(visible=True):
                with self.add_clipping_target(layer) as attrib:
                    for clip_layer in layer.clip_layers:
                        self.add_layer(clip_layer, depth=depth + 1, **attrib)
            else:
                # Regular layer.
                self.add_layer(layer, depth=depth)

    def add_pixel(
        self, layer: layers.Layer, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a general pixel-based layer to the svg document."""
        if not layer.has_pixels():
            logger.warning(
                f"Layer has no pixels, skipping: '{layer.name}' ({layer.kind})."
            )
            return None

        # Validate image dimensions
        if (
            hasattr(self, "resource_limits")
            and self.resource_limits
            and self.resource_limits.is_image_dimension_limited()
        ):
            max_dim = self.resource_limits.max_image_dimension
            if layer.width > max_dim or layer.height > max_dim:
                # Check if this is the WebP hard limit
                if max_dim == WEBP_MAX_DIMENSION:
                    raise ValueError(
                        f"Layer '{layer.name}' dimensions {layer.width}x{layer.height} exceed limit {max_dim}x{max_dim}. "  # noqa: E501
                        f"WebP has a {WEBP_MAX_DIMENSION}px hard limit. "
                        f"To process images larger than this, use image_format='png' and, if necessary, "  # noqa: E501
                        f"increase PSD2SVG_MAX_IMAGE_DIMENSION (for example, to {max(layer.width, layer.height) + 1000})."  # noqa: E501
                    )
                else:
                    raise ValueError(
                        f"Layer '{layer.name}' dimensions {layer.width}x{layer.height} exceed limit {max_dim}x{max_dim}. "  # noqa: E501
                        f"To process: set PSD2SVG_MAX_IMAGE_DIMENSION={max(layer.width, layer.height) + 1000} environment variable, "  # noqa: E501
                        f"or use ResourceLimits(max_image_dimension={max(layer.width, layer.height) + 1000}) in Python API."  # noqa: E501
                    )

        # We will later fill in the href attribute when embedding images.
        image = layer.topil()
        if image is None:
            logger.warning(
                f"Layer has no image data, skipping: '{layer.name}' ({layer.kind})."
            )
            return None

        # Generate image ID before creating the <image> element
        image_id = self.auto_id("image")
        self.images[image_id] = image.convert("RGBA")

        # Raster layers can have both fill opacity and overall opacity.
        fill_opacity = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255)

        # When the layer has effects, we need to create a separate <image>
        # to handle fill opacity.
        if self.has_separate_fill(layer):
            defs = self.create_node("defs")
            node = self.create_node(
                "image",
                parent=defs,
                x=layer.left,
                y=layer.top,
                width=layer.width,
                height=layer.height,
                title=layer.name,
                class_=layer.kind,
                id=image_id,
                **attrib,
            )
            self.set_opacity(layer.opacity / 255, node)
            node = self.apply_mask(layer, node)

            self.apply_background_effects(layer, node, insert_before_target=False)
            self.apply_raster_fill(layer, node)
            self.apply_overlay_effects(layer, node)
            self.apply_stroke_effect(layer, node)
        else:
            node = self.create_node(
                "image",
                id=image_id,
                x=layer.left,
                y=layer.top,
                width=layer.width,
                height=layer.height,
                title=layer.name,
                class_=layer.kind,
                **attrib,  # type: ignore[arg-type]
            )
            if fill_opacity < 255:
                self.set_opacity(fill_opacity / 255, node)
            self.set_layer_attributes(layer, node)
            node = self.apply_mask(layer, node)
        return node

    def add_shape(
        self, layer: layers.ShapeLayer, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a shape layer to the svg document."""
        if self.has_separate_fill(layer):
            # We need to split the shape definition and effects.
            defs = self.create_node("defs")
            with self.set_current(defs):
                node = self.create_shape(
                    layer,
                    title=layer.name,
                    id=self.auto_id("shape"),
                    class_=layer.kind,
                    **attrib,
                )
                self.set_opacity(layer.opacity / 255.0, node)
                node = self.apply_mask(layer, node)

            # We need to set stroke for the shape here when fill is none.
            # Otherwise, effects won't use the correct alpha.
            if (
                layer.has_stroke()
                and layer.stroke is not None
                and layer.stroke.enabled
                and not layer.stroke.fill_enabled
            ):
                svg_utils.set_attribute(node, "fill", "none")
                self.set_stroke(layer, node)

            self.apply_background_effects(layer, node, insert_before_target=False)
            self.apply_vector_fill(layer, node)  # main filled shape.
            self.apply_overlay_effects(layer, node)
            self.apply_vector_stroke(layer, node)  # main stroke.
            self.apply_stroke_effect(layer, node)
        else:
            # We can directly create the shape.
            node = self.create_shape(
                layer, title=layer.name, class_=layer.kind, **attrib
            )
            self.set_fill(layer, node)
            self.set_stroke(layer, node)
            self.set_layer_attributes(layer, node)
            node = self.apply_mask(layer, node)
        return node

    def add_text(
        self, layer: layers.TypeLayer, depth: int = 0, **attrib: str
    ) -> ET.Element | None:
        """Add a text layer to the svg document."""
        if not self.enable_text:
            return self.add_pixel(layer, depth=depth, **attrib)

        # Check if layer has effects
        if self.has_separate_fill(layer):
            # Create defs section and target node with ID
            defs = self.create_node("defs")
            with self.set_current(defs):
                node = self.create_text_node(layer)
                svg_utils.set_attribute(node, "id", self.auto_id("text"))
                if self.enable_class:
                    svg_utils.append_attribute(node, "class", layer.kind)
                # Apply any additional attributes
                for key, value in attrib.items():
                    svg_utils.set_attribute(node, key, value)

                # Set opacity on the base text node
                self.set_opacity(layer.opacity / 255.0, node)
                node = self.apply_mask(layer, node)

            # Apply effects in order (text already has fill/stroke from _add_text_span)
            self.apply_background_effects(layer, node, insert_before_target=False)

            # Create main visible text using <use>
            self.apply_raster_fill(layer, node)

            self.apply_overlay_effects(layer, node)
            self.apply_stroke_effect(layer, node)
            return node
        else:
            # No effects - simple path
            node = self.create_text_node(layer)
            self.set_layer_attributes(layer, node)
            node = self.apply_mask(layer, node)
            return node

    @contextlib.contextmanager
    def add_clipping_target(self, layer: layers.Layer | layers.Group) -> Iterator[dict]:
        """Context manager to handle clipping target."""
        # NOTE: We decide between clip-path and mask based on content.
        # <clipPath> has bad interactions with <mask> in SVG renderers.
        if isinstance(layer, layers.ShapeLayer) and not layer.has_mask():
            with self.add_clip_path(layer) as clip_attrib:
                yield clip_attrib
        else:
            with self.add_clip_mask(layer) as clip_attrib:
                yield clip_attrib

    @contextlib.contextmanager
    def add_clip_path(self, layer: layers.ShapeLayer) -> Iterator[dict]:
        """Add a clipping path and associated elements.

        Usage::

            with self.add_clip_path(layer) as clip_attrib:
                # Create elements inside the clipping mask.
                for clip_layer in layer.clip_layers:
                    self.add_layer(clip_layer, ..., **clip_attrib)

        Args:
            layer: The shape layer to use as a clipping path.

        Yields:
            Dictionary with clip-path attribute to apply to clipped elements.

        NOTE: Due to the bad interactions between clip-path and masks in SVG,
              we recommend using add_clip_mask instead of this method.
        """
        if not layer.has_vector_mask():
            raise ValueError(f"Layer has no vector mask: '{layer.name}'")

        # Create a clipping path definition.
        defs = self.create_node("defs")
        with self.set_current(defs):
            clip_path = self.create_node(
                "clipPath", id=self.auto_id("clip"), class_="clipping"
            )
        with self.set_current(clip_path):
            target = self.create_shape(
                layer,
                title=layer.name,
                id=self.auto_id("shape"),
                class_=f"{layer.kind} clipping-base",
            )
            self.set_opacity(layer.opacity / 255.0, target)
            self.apply_mask(layer, target)

        # NOTE: We actually need to apply the mask to the <clipPath> node
        # to combine effects, but SVG viewers have poor support for that.

        self.apply_background_effects(layer, target, insert_before_target=False)
        self.apply_vector_fill(layer, target)  # main filled shape.
        self.apply_overlay_effects(layer, target)
        # Yield to the context block.
        yield {"clip-path": svg_utils.get_funciri(clip_path)}
        self.apply_vector_stroke(layer, target)
        self.apply_stroke_effect(layer, target)

    @contextlib.contextmanager
    def add_clip_mask(self, layer: layers.Layer | layers.Group) -> Iterator[dict]:
        """Add a clipping mask and associated elements.

        Usage::

            with self.add_clip_mask(layer) as clip_attrib:
                # Create elements inside the clipping mask.
                for clip_layer in layer.clip_layers:
                    self.add_layer(clip_layer, ..., **clip_attrib)

        Args:
            layer: The layer to use as a clipping mask.

        Yields:
            Dictionary with mask attribute to apply to clipped elements.
        """

        # Create a clipping mask definition.
        defs = self.create_node("defs")
        with self.set_current(defs):
            mask = self.create_node(
                "mask",
                class_="clipping",
                id=self.auto_id("mask"),
                mask_type="alpha",
            )
        with self.set_current(mask):
            target = self.add_layer(layer)
            if target is None:
                raise ValueError(
                    f"Failed to create clipping target for layer: '{layer.name}'"
                )
            # NOTE: Maybe move clip-path or mask out of the outer mask container?

        if self.enable_class:
            svg_utils.append_attribute(target, "class", "clipping-base")
        if "id" not in target.attrib:
            target.set("id", self.auto_id("clippingbase"))

        self.apply_background_effects(layer, target, insert_before_target=False)
        # Paint the base again outside the mask. A base that keeps its content
        # in <defs> has to repeat its main fill here; referencing the bare
        # definition would drop the fill opacity, the blend mode and, for a
        # vector layer, the paint.
        vector_base: layers.ShapeLayer | layers.FillLayer | None = None
        if not self.has_separate_fill(layer):
            # The target itself carries the fill opacity and the blend mode.
            self.create_node("use", href=svg_utils.get_uri(target))
        elif isinstance(layer, (layers.ShapeLayer, layers.FillLayer)):
            vector_base = layer
            self.apply_vector_fill(layer, target)
        else:
            self.apply_raster_fill(layer, target)
        self.apply_overlay_effects(layer, target)
        # Yield to the context block.
        yield {"mask": svg_utils.get_funciri(mask)}
        if vector_base is not None:
            # The stroke of the base paints over the clipped layers.
            self.apply_vector_stroke(vector_base, target)
        self.apply_stroke_effect(layer, target)

    def has_separate_fill(self, layer: layers.Layer) -> bool:
        """Whether the layer keeps its content separate from its main fill.

        A layer with effects keeps its content in <defs> so that the effects can
        reference it at the original alpha, and paints a separate main fill that
        carries the fill opacity, the blend mode and, for a vector layer, the
        paint. A group only needs the split once its fill opacity is reduced.
        """
        if not layer.has_effects():
            return False
        if isinstance(layer, (layers.Artboard, layers.AdjustmentLayer)):
            # Artboards and adjustments paint their content in place instead.
            return False
        if isinstance(layer, layers.Group):
            return layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255) < 255
        return True

    def add_fill(
        self,
        layer: adjustments.SolidColorFill
        | adjustments.GradientFill
        | adjustments.PatternFill,
        **attrib: str,
    ) -> ET.Element | None:
        """Add fill node to the given element."""
        logger.debug(f"Adding fill layer: '{layer.name}'")
        viewbox = layer.bbox
        if viewbox == (0, 0, 0, 0):
            viewbox = (0, 0, self.psd.width, self.psd.height)
        if self.has_separate_fill(layer):
            defs = self.create_node("defs", parent=self.current)
            node = self.create_node(
                "rect",
                parent=defs,
                x=viewbox[0],
                y=viewbox[1],
                width=viewbox[2] - viewbox[0],
                height=viewbox[3] - viewbox[1],
                title=layer.name,
                class_=layer.kind,
                id=self.auto_id("fill"),
                **attrib,
            )

            self.set_opacity(layer.opacity / 255.0, node)
            node = self.apply_mask(layer, node)
            self.apply_background_effects(layer, node, insert_before_target=False)
            self.apply_vector_fill(layer, node)  # main filled shape.
            self.apply_overlay_effects(layer, node)
            self.apply_vector_stroke(layer, node)
            self.apply_stroke_effect(layer, node)
        else:
            node = self.create_node(
                "rect",
                parent=self.current,
                x=viewbox[0],
                y=viewbox[1],
                width=viewbox[2] - viewbox[0],
                height=viewbox[3] - viewbox[1],
                title=layer.name,
                class_=layer.kind,
                **attrib,
            )
            self.set_fill(layer, node)
            self.set_layer_attributes(layer, node)
            node = self.apply_mask(layer, node)
        return node

    def apply_raster_fill(self, layer: layers.Layer, node: ET.Element) -> ET.Element:
        """Add a raster main fill to the svg document."""
        use = self.create_node(
            "use",
            parent=self.current,
            class_="fill",
            href=svg_utils.get_uri(node),
        )
        fill_opacity = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255)
        if fill_opacity < 255:
            self.set_opacity(fill_opacity / 255, use)
        self.set_blend_mode(layer.blend_mode, use)
        return use

    def set_layer_attributes(self, layer: layers.Layer, node: ET.Element) -> None:
        """Set common layer attributes to a layer node."""
        self.set_opacity(layer.opacity / 255, node)
        self.set_blend_mode(layer.blend_mode, node)
        self.set_isolation(layer, node)

    def set_opacity(self, opacity: float, node: ET.Element) -> None:
        """Set opacity style to the node."""
        if opacity < 1.0:
            if "opacity" in node.attrib:
                # Combine opacities if already set.
                existing_opacity = float(node.attrib["opacity"])
                opacity *= existing_opacity
            svg_utils.set_attribute(node, "opacity", svg_utils.num2str(opacity))

    def set_blend_mode(self, psd_mode: bytes | BlendMode, node: ET.Element) -> None:
        """Set blend mode style to the node.

        Args:
            psd_mode: The Photoshop blend mode to convert.
            node: The XML element to apply the blend mode to.

        Raises:
            ValueError: If the blend mode is not supported.
        """
        if psd_mode not in BLEND_MODE:
            raise ValueError(f"Unsupported blend mode: {psd_mode!r}")

        # Warn if the blend mode is not accurately supported in SVG
        if psd_mode in INACCURATE_BLEND_MODES:
            blend_mode = BLEND_MODE[psd_mode]
            # Format the mode name for display
            mode_name = (
                psd_mode.name
                if hasattr(psd_mode, "name")
                else psd_mode.decode()
                if isinstance(psd_mode, bytes)
                else str(psd_mode)
            )
            logger.warning(
                f"Blend mode '{mode_name}' is not accurately supported in SVG. "
                f"Using approximation '{blend_mode}' instead."
            )

        svg_mode = BLEND_MODE[psd_mode]
        if svg_mode not in ("normal", "pass-through"):
            svg_utils.add_style(node, "mix-blend-mode", svg_mode)

    def set_isolation(self, layer: layers.Layer, node: ET.Element) -> None:
        """Add isolation to a group.

        NOTE:
          1. The default blending mode of a PSD group is passthrough,
             which corresponds to SVG isolation: auto (default)
          2. When the group has blending mode normal,
             it corresponds to SVG isolation: isolate.
          3. Other blending modes also isolate the group, and in SVG setting
             mix-blend-mode on a <g> to a value other than normal isolates
             the group by default.
        """
        if (
            isinstance(layer, layers.Group)
            and layer.blend_mode != BlendMode.PASS_THROUGH
        ):
            svg_utils.add_style(node, "isolation", "isolate")

    def apply_mask(self, layer: layers.Layer, target: ET.Element) -> ET.Element:
        """Add a layer mask to the target node."""
        if (
            not layer.has_mask()
            or layer.mask is None
            or layer.mask.disabled
            or layer.mask.width == 0
            or layer.mask.height == 0
        ):
            return target
        logger.debug(f"Adding mask: '{layer.name}' ({layer.kind})")

        # If the target already has a mask or a clip-path,
        # we need to transfer them to the content.
        # NOTE: Nested mask references like <mask mask="url(#id)">
        # don't work reliably in browsers.
        # Instead, we apply the existing mask/clip-path to the mask content
        # elements themselves, creating a proper composition hierarchy
        # where masking operations combine at the content level.
        context: dict[str, str] = {}
        if "mask" in target.attrib:
            context["mask"] = target.attrib.pop("mask")
        if "clip-path" in target.attrib:
            context["clip-path"] = target.attrib.pop("clip-path")

        # Viewbox for the mask. If the mask is empty, use the full canvas.
        viewbox = layer.bbox
        if viewbox == (0, 0, 0, 0):
            viewbox = (0, 0, self.psd.width, self.psd.height)

        # Create the mask node.
        defs = self.create_node("defs")
        with self.set_current(defs):
            mask = self.create_node(
                "mask",
                class_="layer-mask",
                id=self.auto_id("mask"),
            )

        # If the mask has a background color (invert mask), add a white rectangle first.
        if layer.mask.background_color > 0:
            with self.set_current(mask):
                self.create_node(
                    "rect",
                    x=viewbox[0],
                    y=viewbox[1],
                    width=viewbox[2] - viewbox[0],
                    height=viewbox[3] - viewbox[1],
                    fill="#ffffff",
                    **context,  # type: ignore[arg-type]
                )

        # Mask image.
        mask_image = layer.mask.topil()
        if mask_image is not None:
            image_id = self.auto_id("image")
            self.images[image_id] = mask_image.convert("L")
            with self.set_current(mask):
                self.create_node(
                    "image",
                    id=image_id,
                    x=layer.mask.left,
                    y=layer.mask.top,
                    width=layer.mask.width,
                    height=layer.mask.height,
                    **context,  # type: ignore[arg-type]
                )

        # If the target has a transform, we cannot directly apply it to the mask.
        if "transform" in target.attrib:
            if "id" not in target.attrib:
                target.set("id", self.auto_id(target.tag.lower()))
            if self.current.tag != "defs":
                defs = self.create_node("defs")
                svg_utils.wrap_element(target, self.current, defs)
            return self.create_node(
                "use",
                href=svg_utils.get_uri(target),
                mask=svg_utils.get_funciri(mask),
                id=self.auto_id("use"),
            )

        svg_utils.set_attribute(target, "mask", svg_utils.get_funciri(mask))
        return target
