"""
Mixin module for paint methods, such as fill and stroke.

Photoshop supports the following paint types:

- Solid color
- Gradient (linear and radial)
- Pattern

This module handles paint application for:
- Shape layer fills (VECTOR_STROKE_CONTENT_DATA)
- Shape layer strokes
- Fill adjustment layers
  (SOLID_COLOR_SHEET_SETTING, GRADIENT_FILL_SETTING, PATTERN_FILL_SETTING)

Note layer effects also support similar paint types, but the data
structures and descriptors are different.
"""

import logging
import xml.etree.ElementTree as ET

from psd_tools import PSDImage
from psd_tools.api import adjustments, layers, pil_io
from psd_tools.api.shape import Stroke
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Descriptor, UnitFloat
from psd_tools.terminology import Enum, Key, Klass, Unit

from psd2svg import svg_utils
from psd2svg.core import color_utils
from psd2svg.core.base import ConverterProtocol
from psd2svg.core.gradient import GradientInterpolation

logger = logging.getLogger(__name__)

POINTS_PER_INCH = 72.0


def get_dash_offset_in_pixels(stroke: Stroke) -> float:
    """Return the stroke dash offset in pixels.

    Photoshop stores ``strokeStyleLineDashOffset`` in points. The line width
    is in pixels and the dash set entries are multiples of it, so those two
    need no ppi scale. The offset does: ``strokeStyleResolution`` is the ppi
    the stroke style was authored at, and points and pixels coincide only at
    72 ppi.
    """
    offset = stroke._data.get(
        b"strokeStyleLineDashOffset", UnitFloat(unit=Unit.Points, value=0.0)
    )
    if offset.unit is not Unit.Points:
        if offset.unit is not Unit.Pixels:
            logger.warning(f"Unsupported dash offset unit: {offset.unit}")
        return float(offset)
    resolution = float(stroke._data.get(b"strokeStyleResolution", POINTS_PER_INCH))
    return float(offset) * resolution / POINTS_PER_INCH


class PaintConverter(ConverterProtocol):
    """Mixin for paint methods."""

    def apply_vector_fill(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, target: ET.Element
    ) -> None:
        """Apply fill effects to the target element."""
        if (
            layer.has_stroke()
            and layer.stroke is not None
            and not layer.stroke.fill_enabled
        ):
            logger.debug(f"Fill is disabled for layer: '{layer.name}'")
            return

        use = self.create_node("use", href=svg_utils.get_uri(target), class_="fill")
        self.set_fill(layer, use)
        self.set_blend_mode(layer.blend_mode, use)

    def apply_vector_stroke(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, target: ET.Element
    ) -> None:
        """Apply stroke effects to the target element."""
        if not layer.has_stroke() or layer.stroke is None or not layer.stroke.enabled:
            logger.debug(f"Layer has no stroke: '{layer.name}'")
            return

        if "stroke" in target.attrib:
            logger.debug(f"Stroke already set for layer: '{layer.name}'")

        use = self.create_node(
            "use",
            href=svg_utils.get_uri(target),
            fill="none",
            class_="stroke",
        )
        self.set_stroke(layer, use)
        if layer.stroke.blend_mode != Enum.Normal:
            self.set_blend_mode(layer.stroke.blend_mode, use)

    def set_fill(
        self, layer: layers.ShapeLayer | adjustments.FillLayer, node: ET.Element
    ) -> None:
        """Set fill attribute to the given element."""
        # No fill when stroke is enabled but fill is disabled.
        if (
            layer.has_stroke()
            and layer.stroke is not None
            and not layer.stroke.fill_enabled
        ):
            logger.debug("Fill is disabled; setting fill to none.")
            svg_utils.set_attribute(node, "fill", "none")
            return

        # Shapes have the following tagged blocks for fill content.
        if Tag.VECTOR_STROKE_CONTENT_DATA in layer.tagged_blocks:
            if isinstance(layer, layers.ShapeLayer):
                self.set_fill_stroke_content(layer, node)
            return

        # Fill layers have a dedicated tagged block.
        self.set_fill_setting(layer, node)

    def set_fill_stroke_content(
        self, layer: layers.ShapeLayer, node: ET.Element
    ) -> None:
        """Set fill or stroke content from VECTOR_STROKE_CONTENT_DATA."""
        content_data = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)
        if Key.Color in content_data:
            color = color_utils.descriptor2hex(content_data[Key.Color])
            svg_utils.set_attribute(node, "fill", color)
        elif Key.Gradient in content_data:
            gradient = self.add_gradient_definition(layer, content_data)
            if gradient is not None:
                svg_utils.set_attribute(node, "fill", svg_utils.get_funciri(gradient))
        elif Enum.Pattern in content_data:
            pattern = self.add_pattern(self.psd, content_data[Enum.Pattern])
            if pattern is not None:
                self.set_pattern_transform(layer, content_data, pattern)
                svg_utils.set_attribute(node, "fill", svg_utils.get_funciri(pattern))
        else:
            logger.warning(f"Unsupported fill content: {content_data}")
        self.set_fill_opacity(layer, node)

    def set_fill_setting(
        self, layer: adjustments.FillLayer | layers.ShapeLayer, node: ET.Element
    ) -> None:
        """Set fill attribute from fill settings tagged blocks."""
        if Tag.SOLID_COLOR_SHEET_SETTING in layer.tagged_blocks:
            setting = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
            color = color_utils.descriptor2hex(setting[Klass.Color])
            svg_utils.set_attribute(node, "fill", color)
        elif Tag.PATTERN_FILL_SETTING in layer.tagged_blocks:
            # classID is null for pattern fill setting.
            setting = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
            if Enum.Pattern not in setting:
                raise ValueError(f"No pattern found in setting: {setting}.")
            pattern = self.add_pattern(self.psd, setting[Enum.Pattern])
            if pattern is not None:
                self.set_pattern_transform(layer, setting, pattern)
                svg_utils.set_attribute(node, "fill", svg_utils.get_funciri(pattern))
        elif Tag.GRADIENT_FILL_SETTING in layer.tagged_blocks:
            # classID is null for gradient fill setting.
            setting = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
            gradient = self.add_gradient_definition(layer, setting)
            if gradient is not None:
                svg_utils.set_attribute(node, "fill", svg_utils.get_funciri(gradient))
        else:
            logger.debug(f"No fill information found: {layer}.")
        self.set_fill_opacity(layer, node)

    def set_fill_opacity(self, layer: layers.Layer, node: ET.Element) -> None:
        """Set fill opacity to the given element."""
        fill_opacity = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255) / 255.0
        if fill_opacity < 1.0:
            svg_utils.set_attribute(node, "fill-opacity", fill_opacity)

    def set_stroke(self, layer: layers.Layer, node: ET.Element) -> None:
        """Add stroke style to the path node."""
        if not layer.has_stroke() or layer.stroke is None or not layer.stroke.enabled:
            logger.debug("Layer has no stroke: %s", layer.name)
            return

        stroke = layer.stroke
        if stroke.line_alignment != "center":
            logger.warning("Inner or outer stroke is not supported yet.")
            # TODO: Perhaps use clipPath to simulate this.
        if stroke.line_width != 1.0:
            svg_utils.set_attribute(node, "stroke-width", stroke.line_width)

        if stroke.content.classID == b"patternLayer":
            if Enum.Pattern not in stroke.content:
                raise ValueError(
                    f"No pattern found in stroke content: {stroke.content}."
                )
            pattern = self.add_pattern(self.psd, stroke.content[Enum.Pattern])
            if pattern is not None:
                self.set_pattern_transform(layer, stroke.content, pattern)
                svg_utils.set_attribute(node, "stroke", svg_utils.get_funciri(pattern))
        elif stroke.content.classID == b"gradientLayer":
            gradient = self.add_gradient_definition(layer, stroke.content)
            if gradient is not None:
                svg_utils.set_attribute(node, "stroke", svg_utils.get_funciri(gradient))
        elif stroke.content.classID == b"solidColorLayer":
            color = color_utils.descriptor2hex(stroke.content[Klass.Color])
            svg_utils.set_attribute(node, "stroke", color)
        else:
            logger.warning(f"Unsupported stroke content: {stroke.content}")

        if not stroke.fill_enabled:
            svg_utils.set_attribute(node, "fill", "none")

        if stroke.opacity.value < 100:
            svg_utils.set_attribute(
                node, "stroke-opacity", stroke.opacity.value / 100.0
            )

        if stroke.line_cap_type != "butt":
            svg_utils.set_attribute(node, "stroke-linecap", stroke.line_cap_type)
        if stroke.line_join_type != "miter":
            svg_utils.set_attribute(node, "stroke-linejoin", stroke.line_join_type)
        if stroke.line_dash_set:
            line_dash_set = [
                float(x.value) * stroke.line_width for x in stroke.line_dash_set
            ]
            svg_utils.set_attribute(node, "stroke-dasharray", line_dash_set)
            svg_utils.set_attribute(
                node, "stroke-dashoffset", get_dash_offset_in_pixels(stroke)
            )
        # NOTE: Stroke blend mode is handled in apply_vector_stroke() for the <use>
        # element. The strokeStyleBlendMode field exists in PSD format but is not
        # settable via Photoshop UI (as of recent versions), so it typically remains
        # Normal. The implementation supports it for future-proofing and compatibility
        # with programmatically-generated PSD files.

    def add_gradient_definition(
        self, layer: layers.Layer, descriptor: Descriptor
    ) -> ET.Element | None:
        """Add gradient definition to the SVG document."""
        if Key.Gradient not in descriptor:
            raise ValueError(f"No gradient found in descriptor: {descriptor}")
        if descriptor[Key.Type].enum == Enum.Linear:
            node = self.add_linear_gradient(descriptor[Key.Gradient])
        elif descriptor[Key.Type].enum == Enum.Radial:
            node = self.add_radial_gradient(descriptor[Key.Gradient])
        else:
            logger.warning("Only linear and radial gradients are supported yet.")
            return None
        self.set_gradient_attributes(layer, descriptor, node)
        return node

    def add_linear_gradient(self, gradient: Descriptor) -> ET.Element:
        """Add linear gradient definition to the SVG document."""
        node = self.create_node("linearGradient", id=self.auto_id("gradient"))
        self.set_gradient_stops(gradient, node)
        return node

    def add_radial_gradient(self, gradient: Descriptor) -> ET.Element:
        """Add radial gradient definition to the SVG document."""
        node = self.create_node("radialGradient", id=self.auto_id("gradient"))
        self.set_gradient_stops(gradient, node)
        return node

    def set_gradient_stops(self, gradient: Descriptor, node: ET.Element) -> ET.Element:
        """Set gradient stops to the given gradient element."""
        interpolator = GradientInterpolation(gradient)
        with self.set_current(node):
            for location, color, opacity in interpolator:
                # Both values are fractions in 0.0-1.0, scaled here rather
                # than left to create_node: num2str keeps its digits after
                # the decimal point, so formatting the fraction would round
                # every stop to the nearest whole percent, and Photoshop
                # stores positions on a 0-4096 scale that rarely lands on one.
                self.create_node(
                    "stop",
                    offset=svg_utils.num2str_with_unit(location * 100, "%"),
                    stop_color=color_utils.descriptor2hex(color),
                    stop_opacity=svg_utils.num2str_with_unit(opacity * 100, "%"),
                )

        # TODO: Midpoint support?
        if any(stop[Key.Midpoint] != 50 for stop in gradient[Key.Colors]) or any(
            stop[Key.Midpoint] != 50 for stop in gradient[Key.Transparency]
        ):
            logger.debug("Gradient midpoint is not supported.")

        return node

    def set_gradient_attributes(
        self, layer: layers.Layer, setting: Descriptor, gradient: ET.Element
    ) -> None:
        """Set gradient settings such as angle to the gradient element."""
        transforms = []

        # Coordinate system for gradient.
        aligned = Key.Alignment not in setting or setting[Key.Alignment].value is True
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

        # Apply angle, scale transforms.
        angle = -float(
            setting.get(Key.Angle, UnitFloat(unit=Unit.Angle, value=0.0)).value
        )
        if landscape:
            angle -= 90
        if Key.Reverse in setting and setting[Key.Reverse].value:
            angle += 180
        if angle != 0:
            transforms.append(f"rotate({svg_utils.num2str(angle)})")

        scale = float(
            setting.get(Key.Scale, UnitFloat(unit=Unit.Percent, value=100.0)).value
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

        # Apply offset transform.
        # Note: Offset must be applied AFTER rotation/scale with transform-origin,
        # as it operates in a different coordinate space.
        has_offset = Key.Offset in setting
        if has_offset:
            # Offset is given in percentage of layer size.
            offset = (
                setting[Key.Offset][Key.Horizontal].value / 100.0,
                setting[Key.Offset][Key.Vertical].value / 100.0,
            )
            if not aligned:
                offset = (offset[0] * layer._psd.width, offset[1] * layer._psd.height)
            # Prepend the offset translate to the transform list
            svg_utils.append_attribute(
                gradient,
                "gradientTransform",
                "translate(%s)" % svg_utils.seq2str(offset, digit=4),
            )

        if transforms:
            # Use transform-origin for rotate/scale, appended after offset
            svg_utils.set_transform_with_origin(
                gradient, "gradientTransform", transforms, reference
            )

        if b"gradientsInterpolationMethod" in setting:
            method = setting[b"gradientsInterpolationMethod"]
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

    def add_pattern(self, psdimage: PSDImage, descriptor: Descriptor) -> ET.Element:
        """Add pattern definition to the SVG document."""
        assert descriptor.classID == Enum.Pattern
        pattern_id = descriptor[Key.ID].value.rstrip("\x00")
        pattern_data = psdimage._get_pattern(pattern_id)
        if pattern_data is None:
            raise ValueError(f"Pattern data not found: {pattern_id}")
        # A pattern bitmap is not bounded by the canvas. Its size is in the
        # record, so check it before convert_pattern_to_pil() allocates.
        name = pattern_data.name.rstrip("\x00") or pattern_id
        description = f"Pattern '{name}'"
        top, left, bottom, right = pattern_data.data.rectangle
        self.check_image_dimension(right - left, bottom - top, description=description)

        image = pil_io.convert_pattern_to_pil(pattern_data)
        image_id = self.register_image(image, description=description)

        node = self.create_node(
            "pattern",
            id=self.auto_id("pattern"),
            width=image.width,
            height=image.height,
            patternUnits="userSpaceOnUse",
        )
        with self.set_current(node):
            # We will later fill in the href attribute when embedding images.
            self.create_node(
                "image",
                id=image_id,
                width=image.width,
                height=image.height,
            )
        return node

    def set_pattern_transform(
        self, layer: layers.Layer, setting: Descriptor, pattern: ET.Element
    ) -> None:
        """Set pattern transform to the pattern element.

        The order is likely the following in Photoshop:

        1. Reference point translation (prepended)
        2. Scale
        3. Rotation

        Note: For patterns, the reference point is a simple translate,
              not a pivot point.
        """
        # Reference point is prepended as a translate (not a pivot)
        reference = tuple(layer.tagged_blocks.get_data(Tag.REFERENCE_POINT, (0.0, 0.0)))
        if reference != (0.0, 0.0):
            svg_utils.append_attribute(
                pattern,
                "patternTransform",
                f"translate({svg_utils.seq2str(reference)})",
            )

        # Scale and rotation (applied after reference translation)
        transforms = []

        # NOTE: Maybe check the valid values for pattern fill settings.
        scale = (
            float(
                setting.get(Key.Scale, UnitFloat(unit=Unit.Percent, value=100.0)).value
            )
            / 100.0
        )
        if scale != 1.0:
            transforms.append(f"scale({svg_utils.num2str(scale, digit=4)})")

        angle = -float(
            setting.get(Key.Angle, UnitFloat(unit=Unit.Angle, value=0.0)).value
        )
        if angle != 0.0:
            transforms.append(f"rotate({svg_utils.num2str(angle, digit=4)})")

        if transforms:
            svg_utils.append_attribute(
                pattern, "patternTransform", " ".join(transforms)
            )
