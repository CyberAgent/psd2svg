import logging
import math
import xml.etree.ElementTree as ET
from typing import cast

from psd_tools import PSDImage
from psd_tools.api import effects, layers
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import UnitFloat
from psd_tools.terminology import Enum, Key, Klass, Unit

from psd2svg import svg_utils
from psd2svg.core import color_utils
from psd2svg.core.base import ConverterProtocol
from psd2svg.core.constants import FILTER_BLEND_MODES
from psd2svg.core.gradient import GradientInterpolation

logger = logging.getLogger(__name__)


class EffectConverter(ConverterProtocol):
    """Effect converter mixin."""

    def apply_background_effects(
        self, layer: layers.Layer, target: ET.Element, insert_before_target: bool = True
    ) -> None:
        """Apply background effects to the target element."""
        self.apply_drop_shadow_effect(
            layer, target, insert_before_target=insert_before_target
        )
        self.apply_outer_glow_effect(
            layer, target, insert_before_target=insert_before_target
        )

    def apply_overlay_effects(self, layer: layers.Layer, target: ET.Element) -> None:
        """Apply overlay effects to the target element."""
        self.apply_pattern_overlay_effect(layer, target)
        self.apply_gradient_overlay_effect(layer, target)
        self.apply_color_overlay_effect(layer, target)
        self.apply_inner_shadow_effect(layer, target)
        self.apply_inner_glow_effect(layer, target)
        self.apply_satin_effect(layer, target)
        self.apply_bevel_emboss_effect(layer, target)

    def composite_overlay_fill(
        self, psd_mode: bytes, filter: ET.Element, use: ET.Element
    ) -> None:
        """Composite a synthesised overlay fill onto the layer it decorates.

        ``filter`` must end with the primitive that produced the fill. Usually the
        fill is just clipped to the layer alpha and ``mix-blend-mode`` on ``use`` does
        the blending. The modes in :data:`FILTER_BLEND_MODES` have no
        ``mix-blend-mode`` equivalent, so those are rewritten into an exact form here
        instead.
        """
        recipe = FILTER_BLEND_MODES.get(psd_mode)
        if recipe is None:
            with self.set_current(filter):
                self.create_node("feComposite", in2="SourceAlpha", operator="in")
            self.set_blend_mode(psd_mode, use)
            return

        # Inverting and summing must happen on sRGB values; the filter default is
        # linearRGB, which gives the wrong numbers.
        svg_utils.set_attribute(filter, "color-interpolation-filters", "sRGB")
        fill = filter[-1]
        with self.set_current(filter):
            if recipe.invert:
                fill = self.create_node("feComponentTransfer")
                with self.set_current(fill):
                    for channel in ("feFuncR", "feFuncG", "feFuncB"):
                        self.create_node(channel, type="table", tableValues="1 0")
            if recipe.css_mode is not None:
                self.create_node("feComposite", in2="SourceAlpha", operator="in")
                svg_utils.add_style(use, "mix-blend-mode", recipe.css_mode)
                return

            # feComposite arithmetic works on premultiplied values, where the
            # constant offset cannot be scaled by the layer alpha. Sum against an
            # opaque copy of the layer and re-apply the alpha afterwards, so that
            # semi-transparent layers blend correctly too.
            svg_utils.set_attribute(fill, "result", "fill")
            opaque = self.create_node(
                "feComponentTransfer", in_="SourceGraphic", result="opaque"
            )
            with self.set_current(opaque):
                self.create_node("feFuncA", type="table", tableValues="1 1")
            self.create_node(
                "feComposite",
                in_="fill",
                in2="opaque",
                operator="arithmetic",
                k1=0,
                k2=1,
                k3=1,
                k4=recipe.offset,
            )
            self.create_node("feComposite", in2="SourceAlpha", operator="in")

    def apply_color_overlay_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None:
        """Apply color overlay effect to the target element."""
        effect_list = list(layer.effects.find("coloroverlay", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.ColorOverlay)

            if isinstance(layer, layers.ShapeLayer):
                use = self.add_vector_color_overlay_effect(effect, target)
            else:
                use = self.add_raster_color_overlay_effect(effect, target)

            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)

    def add_raster_color_overlay_effect(
        self, effect: effects.ColorOverlay, target: ET.Element
    ) -> ET.Element:
        """Add a color overlay filter to the SVG document.

        SVG does not allow coloring a raster image directly, so we create a filter.
        """
        filter = self.create_node("filter", id=self.auto_id("coloroverlay"))
        with self.set_current(filter):
            self.create_node(
                "feFlood",
                flood_color=color_utils.descriptor2hex(effect.color),
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="color-overlay-effect",
        )
        self.composite_overlay_fill(effect.blend_mode, filter, use)
        return use

    def add_vector_color_overlay_effect(
        self, effect: effects.ColorOverlay, target: ET.Element
    ) -> ET.Element:
        """Add a color overlay effect to the current element using vector path."""
        use = self.create_node(
            "use",
            class_="color-overlay-effect",
            href=svg_utils.get_uri(target),
            fill=color_utils.descriptor2hex(effect.color),
        )
        self.set_blend_mode(effect.blend_mode, use)
        return use

    def apply_stroke_effect(self, layer: layers.Layer, target: ET.Element) -> None:
        """Apply stroke effects to the target element."""
        effect_list = list(layer.effects.find("stroke", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.Stroke)

            if not isinstance(layer, layers.ShapeLayer) or "stroke" in target.attrib:
                # NOTE: If there is already a stroke, we need to stroke around
                # the stroke. This case happens when there is a stroke-only shape layer.
                use = self.add_raster_stroke_effect(layer, effect, target)
                if effect.opacity != 100.0:
                    self.set_opacity(effect.opacity / 100.0, use)
            else:
                use = self.add_vector_stroke_effect(layer, effect, target)
                # Vector stroke has stroke-opacity attribute. Skip setting opacity.

            if effect.blend_mode != Enum.Normal:
                self.set_blend_mode(effect.blend_mode, use)

    def add_raster_stroke_effect(
        self, layer: layers.Layer, effect: effects.Stroke, target: ET.Element
    ) -> ET.Element:
        """Add a stroke filter to the SVG document.

        SVG does not allow stroking a raster image directly, so we create a filter.
        """
        filter = self.create_node("filter", id=self.auto_id("stroke"))
        with self.set_current(filter):
            # Create stroke area using morphology and composite.
            if effect.position == Enum.OutsetFrame:
                self.create_node(
                    "feMorphology",
                    operator="dilate",
                    radius=float(effect.size),
                    in_="SourceAlpha",
                )
                self.create_node(
                    "feComposite",
                    operator="xor",
                    in2="SourceAlpha",
                    result="STROKEAREA",
                )
            elif effect.position == Enum.InsetFrame:
                self.create_node(
                    "feMorphology",
                    operator="erode",
                    radius=float(effect.size),
                    in_="SourceAlpha",
                )
                self.create_node(
                    "feComposite",
                    operator="xor",
                    in2="SourceAlpha",
                    result="STROKEAREA",
                )
            elif effect.position == Enum.CenteredFrame:
                self.create_node(
                    "feMorphology",
                    operator="dilate",
                    radius=float(effect.size) / 2.0,
                    in_="SourceAlpha",
                    result="DILATED",
                )
                self.create_node(
                    "feMorphology",
                    operator="erode",
                    radius=float(effect.size) / 2.0,
                    in_="SourceAlpha",
                    result="ERODED",
                )
                self.create_node(
                    "feComposite",
                    operator="xor",
                    in_="DILATED",
                    in2="ERODED",
                    result="STROKEAREA",
                )
            else:
                position_str = (
                    effect.position.decode()
                    if isinstance(effect.position, bytes)
                    else str(effect.position)
                )
                raise ValueError(f"Unsupported stroke position: {position_str}")

            # Gradient and pattern strokes needs feImage.
            if effect.fill_type == Enum.SolidColor:
                self.create_node(
                    "feFlood",
                    flood_color=color_utils.descriptor2hex(effect.color),
                )
            elif effect.fill_type == Enum.Pattern:
                if effect.pattern is None:
                    raise ValueError("Stroke pattern is None for pattern fill type.")
                pattern = self.add_pattern(cast(PSDImage, layer._psd), effect.pattern)
                self.set_pattern_effect_transform(pattern, effect, (0, 0))
                defs = self.create_node("defs")
                with self.set_current(defs):
                    rect = self.create_node(
                        "rect",
                        id=self.auto_id("patternstroke"),
                        width="100%",
                        height="100%",
                        fill=svg_utils.get_funciri(pattern),
                    )
                self.create_node(
                    "feImage",
                    href=svg_utils.get_uri(rect),
                )
            elif effect.fill_type == Enum.GradientFill:
                if effect.gradient is None:
                    raise ValueError("Stroke gradient is None for gradient fill type.")
                gradient = None
                if effect.type == Enum.Linear:
                    gradient = self.add_linear_gradient(effect.gradient)
                elif effect.type == Enum.Radial:
                    gradient = self.add_radial_gradient(effect.gradient)
                else:
                    logger.warning(
                        "Only linear and radial gradient strokes are supported: "
                        f"{effect}"
                    )
                    # Fallback to simple color.
                    flood_color = (
                        color_utils.descriptor2hex(effect.color)
                        if effect.color
                        else "#ffffff"
                    )
                    self.create_node("feFlood", flood_color=flood_color)
                if gradient is not None:
                    self.set_gradient_transform(layer, gradient, effect)
                    defs = self.create_node("defs")
                    with self.set_current(defs):
                        rect = self.create_node(
                            "rect",
                            id=self.auto_id("gradientstroke"),
                            width="100%",
                            height="100%",
                            fill=svg_utils.get_funciri(gradient),
                        )
                    self.create_node(
                        "feImage",
                        href=svg_utils.get_uri(rect),
                    )
            self.create_node(
                "feComposite",
                operator="in",
                in2="STROKEAREA",
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="stroke-effect",
        )
        return use

    def add_vector_stroke_effect(
        self, layer: layers.Layer, effect: effects.Stroke, target: ET.Element
    ) -> ET.Element:
        """Add a stroke effect to the current element using vector path."""

        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            fill="none",
            class_="stroke-effect",
        )
        # Check effect.fill_type.
        if effect.fill_type == Enum.SolidColor:
            if effect.color is None:
                raise ValueError("Stroke color is None for color fill type.")
            color = color_utils.descriptor2hex(effect.color)
            svg_utils.set_attribute(use, "stroke", color)
        elif effect.fill_type == Enum.Pattern:
            if effect.pattern is None:
                raise ValueError("Stroke pattern is None for pattern fill type.")
            pattern = self.add_pattern(cast(PSDImage, layer._psd), effect.pattern)
            self.set_pattern_effect_transform(pattern, effect, (0, 0))
            svg_utils.set_attribute(use, "stroke", svg_utils.get_funciri(pattern))
        elif effect.fill_type == Enum.GradientFill:
            if effect.gradient is None:
                raise ValueError("Stroke gradient is None for gradient fill type.")
            if effect.type == Enum.Linear:
                gradient = self.add_linear_gradient(effect.gradient)
            elif effect.type == Enum.Radial:
                gradient = self.add_radial_gradient(effect.gradient)
            else:
                logger.warning(
                    f"Only linear and radial gradient strokes are supported: {effect}"
                )
                return use
            self.set_gradient_transform(layer, gradient, effect)
            svg_utils.set_attribute(use, "stroke", svg_utils.get_funciri(gradient))

        if effect.opacity != 100.0:
            # Effect opacity is a percentage; stroke-opacity is 0-1.
            svg_utils.set_attribute(use, "stroke-opacity", effect.opacity / 100.0)
        if float(effect.size) != 1.0:
            svg_utils.set_attribute(use, "stroke-width", float(effect.size))

        # NOTE: Check position, phase, and offset.
        if effect.position != Enum.CenteredFrame:
            position = Enum(effect.position)  # For validation.
            logger.info(
                f"Only centered stroke position is supported in SVG: {position.name}"
            )

        return use

    def apply_drop_shadow_effect(
        self,
        layer: layers.Layer,
        target: ET.Element,
        insert_before_target: bool = False,
    ) -> None:
        """Apply drop shadow effect to the current element."""
        effect_list = list(layer.effects.find("dropshadow", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.DropShadow)
            use = self.add_raster_drop_shadow_effect(effect, target)
            if effect.blend_mode != Enum.Normal:
                self.set_blend_mode(effect.blend_mode, use)
            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)
            if insert_before_target:
                # Push the target element after the <use> element.
                self.current.remove(target)
                self.current.append(target)

    def add_raster_drop_shadow_effect(
        self, effect: effects.DropShadow, target: ET.Element
    ) -> ET.Element:
        """Add a drop shadow filter to the SVG document."""
        choke = float(effect.choke)
        size = float(effect.size)
        # NOTE: Adjust the width and height based on size.
        filter = self.create_node(
            "filter",
            id=self.auto_id("dropshadow"),
            x="-25%",
            y="-25%",
            width="150%",
            height="150%",
        )
        with self.set_current(filter):
            self.create_node(
                "feMorphology",
                operator="dilate",
                radius=choke / 100.0 * size,
                in_="SourceAlpha",
            )
            self.create_node(
                "feGaussianBlur",
                stdDeviation=(100.0 - choke) / 100.0 * size / 2.0,
            )
            dx, dy = polar_to_cartesian(float(effect.angle), float(effect.distance))
            self.create_node(
                "feOffset",
                dx=dx,
                dy=dy,
                result="SHADOW",
            )
            self.create_node(
                "feFlood",
                flood_color=color_utils.descriptor2hex(effect.color),
            )
            self.create_node(
                "feComposite",
                operator="in",
                in2="SHADOW",
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="drop-shadow-effect",
        )
        return use

    def apply_outer_glow_effect(
        self,
        layer: layers.Layer,
        target: ET.Element,
        insert_before_target: bool = False,
    ) -> None:
        """Apply outer glow effect to the current element."""
        effect_list = list(layer.effects.find("outerglow", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.OuterGlow)
            use = self.add_raster_outer_glow_effect(effect, target)
            if effect.blend_mode != Enum.Normal:
                self.set_blend_mode(effect.blend_mode, use)
            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)
            if insert_before_target:
                # Push the target element after the <use> element.
                self.current.remove(target)
                self.current.append(target)

    def add_raster_outer_glow_effect(
        self, effect: effects.OuterGlow, target: ET.Element
    ) -> ET.Element:
        """Add an outer glow filter to the SVG document."""
        choke = float(effect.choke)
        size = float(effect.size)
        # NOTE: Adjust the width and height based on size.
        filter = self.create_node(
            "filter",
            id=self.auto_id("outerglow"),
        )
        # NOTE: Adjust radius and stdDeviation, as the rendering quality differs.
        with self.set_current(filter):
            self.create_node(
                "feMorphology",
                operator="dilate",
                radius=choke / 100.0 * size + (100.0 - choke) / 100.0 * size / 6.0,
                in_="SourceAlpha",
            )
            self.create_node(
                "feGaussianBlur",
                stdDeviation=(100.0 - choke) / 100.0 * size / 4.0,
                result="GLOW",
            )
            self.create_node(
                "feFlood",
                flood_color=color_utils.descriptor2hex(effect.color),
            )
            self.create_node(
                "feComposite",
                operator="in",
                in2="GLOW",
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="outer-glow-effect",
        )
        return use

    def apply_gradient_overlay_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None:
        effect_list = list(layer.effects.find("gradientoverlay", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.GradientOverlay)
            if effect.type == Enum.Linear:
                gradient = self.add_linear_gradient(effect.gradient)
            elif effect.type == Enum.Radial:
                gradient = self.add_radial_gradient(effect.gradient)
            else:
                effect_type_str = (
                    effect.type.decode()
                    if isinstance(effect.type, bytes)
                    else str(effect.type)
                )
                logger.warning(
                    "Only linear and radial gradient overlay are supported: "
                    f"{effect_type_str}: '{layer.name}' ({layer.kind})"
                )
                continue
            self.set_gradient_transform(layer, gradient, effect)

            if isinstance(layer, layers.ShapeLayer):
                use = self.add_vector_gradient_overlay_effect(gradient, target, effect)
            else:
                use = self.add_raster_gradient_overlay_effect(gradient, target, effect)

            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)

    def add_raster_gradient_overlay_effect(
        self, gradient: ET.Element, target: ET.Element, effect: effects.GradientOverlay
    ) -> ET.Element:
        # feFlood does not support fill with gradient,
        # so we use feImage and feComposite.
        defs = self.create_node("defs")
        # Rect here should have the target size.
        with self.set_current(defs):
            rect = self.create_node(
                "rect",
                id=self.auto_id("gradientfill"),
                width=target.get("width", "100%"),
                height=target.get("height", "100%"),
                fill=svg_utils.get_funciri(gradient),
            )

        # When gradient is aligned to layer bounds (Aligned=True), use objectBoundingBox
        # coordinates for the filter. Otherwise use userSpaceOnUse.
        # Note: The key is b'Algn', not Key.Aligned (which is b'Algd')
        aligned = bool(effect.value.get(b"Algn", False))
        filter_attrs = {"id": self.auto_id("gradientoverlay")}

        if aligned:
            # Use objectBoundingBox coordinates
            # (filter positioned relative to target element)
            filter_attrs["x"] = "0%"
            filter_attrs["y"] = "0%"
            filter_attrs["width"] = "100%"
            filter_attrs["height"] = "100%"
            filter_attrs["filterUnits"] = "objectBoundingBox"
        else:
            # Use userSpaceOnUse coordinates (filter positioned in absolute coordinates)
            # Get target position if available
            if "x" in target.attrib and "y" in target.attrib:
                x_val = target.get("x")
                y_val = target.get("y")
                filter_attrs["x"] = x_val if x_val is not None else "0"
                filter_attrs["y"] = y_val if y_val is not None else "0"
            else:
                filter_attrs["x"] = "0"
                filter_attrs["y"] = "0"
            filter_attrs["filterUnits"] = "userSpaceOnUse"

        filter = self.create_node("filter", id=filter_attrs["id"])
        for key, value in filter_attrs.items():
            if key != "id":
                svg_utils.set_attribute(filter, key, value)
        with self.set_current(filter):
            self.create_node(
                "feImage",
                href=svg_utils.get_uri(rect),
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="gradient-overlay-effect",
        )
        self.composite_overlay_fill(effect.blend_mode, filter, use)
        return use

    def add_vector_gradient_overlay_effect(
        self, gradient: ET.Element, target: ET.Element, effect: effects.GradientOverlay
    ) -> ET.Element:
        use = self.create_node(
            "use",
            parent=self.current,
            class_="gradient-overlay-effect",
            href=svg_utils.get_uri(target),
            fill=svg_utils.get_funciri(gradient),
        )
        self.set_blend_mode(effect.blend_mode, use)
        return use

    def set_gradient_transform(
        self,
        layer: layers.Layer,
        gradient: ET.Element,
        effect: effects.GradientOverlay | effects.Stroke,
    ) -> None:
        """Set gradient transformations based on the effect properties."""
        transforms = []
        # Note: The key is b'Algn', not Key.Aligned (which is b'Algd')
        aligned = bool(effect.value.get(b"Algn", False))
        if aligned:
            # Gradient aligned to layer bounds.
            landscape = layer.width >= layer.height
            # Adjust the object coordinates.
            if layer.width != layer.height:
                if landscape:
                    scale_x = svg_utils.num2str(layer.height / layer.width, digit=4)
                    transforms.append(f"scale({scale_x} 1)")
                else:
                    scale_y = svg_utils.num2str(layer.width / layer.height, digit=4)
                    transforms.append(f"scale(1 {scale_y})")
            reference = (0.5, 0.5)
        else:
            # Gradient defined in user space (canvas).
            svg_utils.set_attribute(gradient, "gradientUnits", "userSpaceOnUse")
            landscape = self.psd.width >= self.psd.height
            reference = (self.psd.width / 2, self.psd.height / 2)

        # Set the base gradient direction based on the shorter edge.
        if landscape:
            # Vertical gradient.
            svg_utils.set_attribute(gradient, "x2", "0%")
            svg_utils.set_attribute(gradient, "y2", "100%")
        else:
            # Horizontal gradient.
            svg_utils.set_attribute(gradient, "x2", "100%")
            svg_utils.set_attribute(gradient, "y2", "0%")

        # Apply phase offset.
        if effect.offset is not None:
            # offset is b'Pnt ' descriptor with percentage values
            offset = (
                effect.offset[Key.Horizontal].value / 100.0,
                effect.offset[Key.Vertical].value / 100.0,
            )
            if not aligned:
                offset = (offset[0] * self.psd.width, offset[1] * self.psd.height)
            # Only add translate if offset is non-zero
            # (with tolerance for floating point)
            if abs(offset[0]) > 1e-6 or abs(offset[1]) > 1e-6:
                svg_utils.append_attribute(
                    gradient,
                    "gradientTransform",
                    "translate(%s)" % svg_utils.seq2str(offset),
                )

        # Apply angle, scale, and offset transforms.
        angle = -float(effect.angle or 0)
        if landscape:
            angle -= 90
        if effect.reversed:
            angle += 180
        if angle != 0:
            transforms.append(f"rotate({svg_utils.num2str(angle)})")

        scale = float(
            effect.value.get(Key.Scale, UnitFloat(unit=Unit.Percent, value=100.0)).value
        )
        if scale != 100:
            if landscape:
                transforms.append(
                    f"scale(1 {svg_utils.num2str(scale / 100.0, digit=4)})"
                )
            else:
                transforms.append(
                    f"scale({svg_utils.num2str(scale / 100.0, digit=4)} 1)"
                )

        if transforms:
            # Use transform-origin instead of translate-rotate-translate pattern
            svg_utils.set_transform_with_origin(
                gradient, "gradientTransform", transforms, reference
            )

        if b"gs99" in effect.value:
            method = effect.value[b"gs99"]
            if method.enum == Enum.Perceptual:
                logger.info("Perceptual gradient interpolation is not accurate.")
            elif method.enum == Enum.Linear:
                logger.info("Linear gradient interpolation is not accurate.")
            elif method.enum == b"GIMs":  # Stripes
                logger.warning("Stripes gradient interpolation is not supported yet.")
            elif method.enum == b"Gcls":  # Classic
                pass  # Default is classic
            elif method.enum == Key.Smooth:  # Smooth
                logger.info("Smooth gradient interpolation is not accurate.")

    def apply_pattern_overlay_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None:
        effect_list = list(layer.effects.find("patternoverlay", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.PatternOverlay)
            pattern = self.add_pattern(cast(PSDImage, layer._psd), effect.pattern)
            reference = layer.tagged_blocks.get_data(Tag.REFERENCE_POINT, (0, 0))
            self.set_pattern_effect_transform(pattern, effect, reference)

            if isinstance(layer, layers.ShapeLayer):
                use = self.add_vector_pattern_overlay_effect(pattern, target, effect)
            else:
                use = self.add_raster_pattern_overlay_effect(pattern, target, effect)

            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)

    def add_raster_pattern_overlay_effect(
        self, pattern: ET.Element, target: ET.Element, effect: effects.PatternOverlay
    ) -> ET.Element:
        # feFlood does not support fill with pattern, so we use feImage and feComposite.
        defs = self.create_node("defs")

        if "x" not in target.attrib or "y" not in target.attrib:
            logger.debug(
                "Target element for raster pattern overlay effect "
                "does not have 'x' or 'y' attribute. "
                "Assuming (0, 0) as the origin."
            )
        # Rect here should have the target size and location.
        with self.set_current(defs):
            rect = self.create_node(
                "rect",
                id=self.auto_id("patternfill"),
                x=target.get("x", "0"),
                y=target.get("y", "0"),
                width=target.get("width", "100%"),
                height=target.get("height", "100%"),
                fill=svg_utils.get_funciri(pattern),
            )
        # Filter should use the user space coordinates here.
        filter = self.create_node(
            "filter",
            id=self.auto_id("patternoverlay"),
            x=0,
            y=0,
            filterUnits="userSpaceOnUse",
        )
        with self.set_current(filter):
            self.create_node(
                "feImage",
                href=svg_utils.get_uri(rect),
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="pattern-overlay-effect",
        )
        self.composite_overlay_fill(effect.blend_mode, filter, use)
        return use

    def add_vector_pattern_overlay_effect(
        self, pattern: ET.Element, target: ET.Element, effect: effects.PatternOverlay
    ) -> ET.Element:
        use = self.create_node(
            "use",
            parent=self.current,
            class_="pattern-overlay-effect",
            href=svg_utils.get_uri(target),
            fill=svg_utils.get_funciri(pattern),
        )
        self.set_blend_mode(effect.blend_mode, use)
        return use

    def set_pattern_effect_transform(
        self,
        pattern: ET.Element,
        effect: effects.PatternOverlay | effects.Stroke,
        reference: tuple[float, float],
    ) -> None:
        """Set pattern transformations based on the effect properties.

        Note: For patterns, reference and phase are simple translates, not pivot points.
        """
        # Apply reference point as a translate (prepended)
        if reference != (0, 0):
            svg_utils.append_attribute(
                pattern,
                "patternTransform",
                f"translate({svg_utils.seq2str(reference)})",
            )

        # Apply phase offset as a translate (prepended after reference)
        if effect.phase is not None:
            assert effect.phase.classID == Klass.Point
            offset = (
                float(effect.phase[Key.Horizontal].value),
                float(effect.phase[Key.Vertical].value),
            )
            if offset[0] != 0.0 or offset[1] != 0.0:
                svg_utils.append_attribute(
                    pattern,
                    "patternTransform",
                    f"translate({svg_utils.seq2str(offset)})",
                )

        # Scale and rotation (applied after translations)
        scale = float(
            effect.value.get(Key.Scale, UnitFloat(unit=Unit.Percent, value=100.0)).value
        )
        if scale != 100.0:
            svg_utils.append_attribute(
                pattern,
                "patternTransform",
                f"scale({svg_utils.num2str(scale / 100.0)})",
            )

        angle = -float(
            effect.value.get(Key.Angle, UnitFloat(unit=Unit.Angle, value=0.0)).value
        )
        if angle != 0.0:
            svg_utils.append_attribute(
                pattern,
                "patternTransform",
                f"rotate({svg_utils.num2str(angle)})",
            )

    def apply_inner_shadow_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None:
        effect_list = list(layer.effects.find("innershadow", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.InnerShadow)
            use = self.add_raster_inner_shadow_effect(effect, target)
            if effect.blend_mode != Enum.Normal:
                self.set_blend_mode(effect.blend_mode, use)
            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)

    def add_raster_inner_shadow_effect(
        self, effect: effects.InnerShadow, target: ET.Element
    ) -> ET.Element:
        """Add an inner shadow filter to the SVG document."""
        logger.debug(f"Adding raster inner shadow effect: {effect}")
        choke = float(effect.choke)
        size = float(effect.size)
        filter = self.create_node(
            "filter",
            id=self.auto_id("innershadow"),
        )
        with self.set_current(filter):
            self.create_node(
                "feMorphology",
                operator="erode",
                radius=choke / 100.0 * size,
                in_="SourceAlpha",
            )
            self.create_node(
                "feGaussianBlur",
                stdDeviation=(100.0 - choke) / 100.0 * size / 2.0,
            )
            dx, dy = polar_to_cartesian(float(effect.angle), float(effect.distance))
            self.create_node(
                "feOffset",
                dx=dx,
                dy=dy,
                result="SHADOW",
            )
            self.create_node(
                "feFlood",
                flood_color=color_utils.descriptor2hex(effect.color),
            )
            self.create_node(
                "feComposite",
                operator="out",
                in2="SHADOW",
            )
            # Restrict the shadow to the inside of the original shape.
            self.create_node(
                "feComposite",
                operator="in",
                in2="SourceAlpha",
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="inner-shadow-effect",
        )
        return use

    def apply_inner_glow_effect(self, layer: layers.Layer, target: ET.Element) -> None:
        effect_list = list(layer.effects.find("innerglow", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.InnerGlow)
            use = self.add_raster_inner_glow_effect(effect, target)
            if effect.blend_mode != Enum.Normal:
                self.set_blend_mode(effect.blend_mode, use)
            if effect.opacity != 100.0:
                self.set_opacity(effect.opacity / 100.0, use)

    def add_raster_inner_glow_effect(
        self, effect: effects.InnerGlow, target: ET.Element
    ) -> ET.Element:
        """Add an inner glow filter to the SVG document."""
        # TODO: Support different glow types.
        if effect.glow_type != Enum.SoftMatte:
            glow_type_str = (
                effect.glow_type.decode()
                if isinstance(effect.glow_type, bytes)
                else str(effect.glow_type)
            )
            logger.warning(f"Only softer inner glow is supported: {glow_type_str}")
        choke = float(effect.choke)
        size = float(effect.size)

        # Determine glow color: either solid color or gradient
        glow_color = "none"
        if effect.color is not None:
            # Solid color glow
            glow_color = color_utils.descriptor2hex(effect.color)
        elif effect.gradient is not None:
            # Gradient-based glow: use first color stop as approximation
            # TODO: Support full gradient rendering for inner glow
            logger.warning(
                "Gradient-based inner glow is approximated using first color stop"
            )
            try:
                grad_interp = GradientInterpolation(effect.gradient)
                if grad_interp.color_stops:
                    first_color = grad_interp.color_stops[0][1]
                    glow_color = color_utils.descriptor2hex(first_color)
            except Exception as e:
                logger.warning(f"Failed to extract gradient color for inner glow: {e}")
                glow_color = "none"

        # NOTE: Adjust the width and height based on size.
        filter = self.create_node(
            "filter",
            id=self.auto_id("innerglow"),
        )
        # NOTE: Adjust radius and stdDeviation, as the rendering quality differs.
        with self.set_current(filter):
            self.create_node(
                "feMorphology",
                operator="erode",
                radius=choke / 100.0 * size + (100.0 - choke) / 100.0 * size / 6.0,
                in_="SourceAlpha",
            )
            self.create_node(
                "feGaussianBlur",
                stdDeviation=(100.0 - choke) / 100.0 * size / 4.0,
                result="GLOW",
            )
            self.create_node(
                "feFlood",
                flood_color=glow_color,
            )
            self.create_node(
                "feComposite",
                operator="out" if effect.glow_source == Enum.EdgeGlow else "in",
                in2="GLOW",
            )
            self.create_node(
                "feComposite",
                operator="in",
                in2="SourceAlpha",
            )
        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            filter=svg_utils.get_funciri(filter),
            class_="inner-glow-effect",
        )
        return use

    def apply_satin_effect(self, layer: layers.Layer, target: ET.Element) -> None:
        effect_list = list(layer.effects.find("satin", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.Satin)
            logger.warning(
                f"Satin effect is not supported yet: '{layer.name}' ({layer.kind})"
            )

    def apply_bevel_emboss_effect(
        self, layer: layers.Layer, target: ET.Element
    ) -> None:
        effect_list = list(layer.effects.find("bevelemboss", enabled=True))
        for effect in reversed(effect_list):
            assert isinstance(effect, effects.BevelEmboss)
            logger.warning(
                f"Bevel emboss effect is not supported yet: "
                f"'{layer.name}' ({layer.kind})"
            )


def polar_to_cartesian(angle: float, distance: float) -> tuple[float, float]:
    """Convert the polar coordinate to dx and dy."""
    angle_rad = angle * math.pi / 180.0
    return -distance * math.cos(angle_rad), distance * math.sin(angle_rad)
