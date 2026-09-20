"""SVG text conversion logic for PSD text layers.

This module contains the TextConverter mixin class that converts Photoshop text layers
(TypeLayer) to SVG text elements. It supports two rendering modes:

1. Native SVG <text> elements (default) - Uses SVG text/tspan for accurate
   text rendering
2. Foreign object mode - Uses <foreignObject> with XHTML for text wrapping support

The TextConverter works with TypeSetting and related data structures from the
typesetting module to extract PSD text data and generate corresponding SVG markup.

Key features:
- Point text and bounding box text
- Paragraph alignment and justification
- Text styling (font, color, size, decoration, etc.)
- Vertical and horizontal text direction
- Letter spacing, tracking, and kerning
- Font effects (superscript, subscript, small caps)

Note: This module re-exports TypeSetting and TextWrappingMode for backward
      compatibility. New code should import these directly from
      psd2svg.core.typesetting.
"""

import logging
import xml.etree.ElementTree as ET
from typing import NamedTuple

from psd_tools.api import layers

from psd2svg import svg_utils
from psd2svg.core.base import ConverterProtocol
from psd2svg.core.typesetting import (
    FontBaseline,
    FontCaps,
    Justification,
    Paragraph,
    Rectangle,
    ShapeType,
    Span,
    TextWrappingMode,
    TypeSetting,
    WritingDirection,
)

logger = logging.getLogger(__name__)

# Threshold for negligible margin values (in pixels).
# Sub-pixel values below this threshold don't meaningfully affect rendering
# and are omitted to produce cleaner SVG output (avoiding "-0px" or "-0.005px").
NEGLIGIBLE_MARGIN_THRESHOLD = 0.01

# Tolerance for comparing scale factors.
# Consistent with Transform.is_translation_only().
SCALE_TOLERANCE = 1e-6

# Width of the faux-bold outline thickening, as a fraction of the em.
#
# Photoshop's faux bold thickens the outline of the specified face; it does not
# switch to a bolder face the way CSS font-weight does. A centred stroke of
# width w grows every stem by exactly w, and the stem growth measured on the
# style-faux-bold*.psd fixtures against their own unthickened line is 2.9-3.2%
# of the em, depending on which scanlines are sampled. See GitHub issue #337.
FAUX_BOLD_STROKE_RATIO = 0.03


class TextScaling(NamedTuple):
    """Font-size decomposition of a PSD horizontal/vertical character scale.

    Attributes:
        font_size: Font size to emit on the span.
        baseline_size: Reference size for offsets perpendicular to the writing
            direction, such as superscript and subscript baseline shifts.
        transform_scale: Residual (sx, sy) scale that could not be expressed with
            the font size, or None when no transform is needed.
    """

    font_size: float
    baseline_size: float
    transform_scale: tuple[float, float] | None


def _common_span_scale(paragraphs: list[Paragraph]) -> tuple[float, float] | None:
    """Return the non-uniform scale shared by every span of a text layer.

    When all spans agree on the same horizontal/vertical scale, the scaling can be
    expressed as a transform on the ``<text>`` element, which every SVG renderer
    supports. See :meth:`TextConverter._calculate_text_scaling` for the per-span
    fallback used otherwise.

    Args:
        paragraphs: Paragraphs of the text layer.

    Returns:
        ``(horizontal_scale, vertical_scale)`` when all spans share the same valid
        non-uniform scale, or None when the spans disagree, the scale is uniform
        (handled by font-size alone), or the values are invalid.
    """
    # Paragraph breaks are separate runs carrying the default scale, and they draw
    # nothing, so they must not defeat the comparison.
    scales = {
        (span.style.horizontal_scale, span.style.vertical_scale)
        for paragraph in paragraphs
        for span in paragraph
        if span.text.strip("\r")
    }
    if len(scales) != 1:
        return None

    horizontal_scale, vertical_scale = scales.pop()
    if horizontal_scale <= 0 or vertical_scale <= 0:
        return None
    if abs(horizontal_scale - vertical_scale) < SCALE_TOLERANCE:
        return None
    return horizontal_scale, vertical_scale


def _scale_about(scale: tuple[float, float], origin: tuple[float, float]) -> str:
    """Build an SVG transform that scales about the given origin point.

    ``transform-origin`` is a CSS property rather than a presentation attribute, so
    the origin is baked into an explicit translation for portability.

    Args:
        scale: (sx, sy) scale factors.
        origin: (ox, oy) point that must stay in place.

    Returns:
        SVG transform string, e.g. ``translate(12.75,0) scale(0.5,1)``.
    """
    sx, sy = scale
    ox, oy = origin
    tx, ty = ox * (1.0 - sx), oy * (1.0 - sy)
    scale_str = f"scale({svg_utils.num2str(sx)},{svg_utils.num2str(sy)})"
    if abs(tx) < SCALE_TOLERANCE and abs(ty) < SCALE_TOLERANCE:
        return scale_str
    translate_str = f"translate({svg_utils.num2str(tx)},{svg_utils.num2str(ty)})"
    return f"{translate_str} {scale_str}"


def _paragraph_advance(
    writing_direction: WritingDirection, leading: float
) -> tuple[float | None, float | None]:
    """Return the relative block-axis advance for a paragraph break.

    Horizontal text advances down the page, while ``vertical-rl`` text advances
    to the left. ``None`` marks the inline axis, which must be reset to the
    paragraph origin instead of moved relatively.
    """
    if writing_direction == WritingDirection.VERTICAL_RL:
        return -leading, None
    return None, leading


def _needs_whitespace_preservation(text: str) -> bool:
    """Check if text needs whitespace preservation.

    Returns True if the text contains:
    - Leading or trailing spaces
    - Multiple consecutive spaces (2 or more)
    - Tabs or other whitespace characters

    When whitespace needs preservation, the xml:space="preserve" attribute is added
    to the SVG element. While MDN recommends the CSS white-space property as the
    modern approach (https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/xml:space),
    we use xml:space for better compatibility with SVG renderers including resvg-py.
    The attribute works equivalently to CSS "white-space: pre".

    Note: Carriage returns (\r) are ignored since they are stripped
    during text processing.

    Args:
        text: Text content to check.

    Returns:
        True if xml:space="preserve" is needed, False otherwise.
    """
    if not text:
        return False

    # Strip carriage returns as they're removed during text processing
    text = text.replace("\r", "")

    if not text:
        return False

    # Check for leading or trailing spaces
    if text != text.strip():
        return True

    # Check for multiple consecutive spaces
    if "  " in text:
        return True

    # Check for tabs or other special whitespace
    if "\t" in text or "\n" in text or "\f" in text:
        return True

    return False


class TextConverter(ConverterProtocol):
    """Mixin for text layers."""

    def create_text_node(self, layer: layers.TypeLayer) -> ET.Element:
        """Create SVG text node from a TypeLayer."""
        text_setting = TypeSetting(layer._data)

        # Determine if we should use foreignObject
        # Only use for bounding box text when explicitly enabled
        use_foreign_object = (
            self.text_wrapping_mode == TextWrappingMode.FOREIGN_OBJECT
            and text_setting.shape_type == ShapeType.BOUNDING_BOX
        )

        if use_foreign_object:
            return self._create_foreign_object_text(text_setting)
        else:
            return self._create_native_svg_text(text_setting)

    def _create_text_path_node(
        self, text_setting: TypeSetting, text_node: ET.Element
    ) -> ET.Element:
        """Create SVG textPath element from a TypeLayer."""
        defs = self.create_node("defs")
        warp_path = self.create_node(
            "path",
            parent=defs,
            d=text_setting.get_warp_path(),
            id=self.auto_id("warp-path"),
        )
        # NOTE: Due to browser inconsistencies with textLength on textPath,
        # we only set textLength for extreme warp values to better match Photoshop.
        text_length = (
            "100%"
            if text_setting.warp_style == "warpArc"
            and abs(text_setting.warp_value) > 50
            else None
        )
        text_path_node = self.create_node(
            "textPath",
            parent=text_node,
            startOffset="50%",
            href=svg_utils.get_uri(warp_path),
            lengthAdjust="spacingAndGlyphs",
            method="stretch",
            textLength=text_length,
        )
        return text_path_node

    def _create_native_svg_text(self, text_setting: TypeSetting) -> ET.Element:
        """Create native SVG <text> element (current implementation).

        Args:
            text_setting: TypeSetting object with text data.

        Returns:
            text element with nested tspan elements.
        """
        # Use native x, y attributes for translation-only transforms
        transform = text_setting.transform
        uses_native_positioning = (
            transform.is_translation_only() and not text_setting.has_warp()
        )

        paragraphs = list(text_setting)

        # Check if any span needs whitespace preservation
        needs_preserve = any(
            _needs_whitespace_preservation(span.text)
            for paragraph in paragraphs
            for span in paragraph
        )

        if uses_native_positioning:
            # Don't set x/y on parent - each tspan will have its own position
            text_node = self.create_node(
                "text", xml_space="preserve" if needs_preserve else None
            )
        else:
            # Use transform for non-translation transforms
            text_node = self.create_node(
                "text",
                transform=transform.to_svg_matrix(),
                xml_space="preserve" if needs_preserve else None,
            )

        if text_setting.writing_direction == WritingDirection.VERTICAL_RL:
            svg_utils.set_attribute(text_node, "writing-mode", "vertical-rl")

        # Non-uniform scaling shared by every span is applied to the <text> element,
        # where transforms are honored by all renderers.
        text_element_scale = self._apply_text_element_scaling(
            text_setting, text_node, paragraphs, uses_native_positioning
        )

        container_node = text_node
        if text_setting.has_warp():
            container_node = self._create_text_path_node(text_setting, text_node)

        # Paragraph baselines advance along the block axis. Keep the absolute offset
        # so per-span transforms can be anchored at the rendered paragraph origin.
        paragraph_offset_x = 0.0
        paragraph_offset_y = 0.0

        with self.set_current(container_node):
            for i, paragraph in enumerate(paragraphs):
                paragraph_node = self._add_paragraph(
                    text_setting,
                    paragraph,
                    first_paragraph=(i == 0),
                    uses_native_positioning=uses_native_positioning,
                )
                origin_x, origin_y, _ = self._compute_paragraph_position(
                    text_setting, paragraph.get_text_anchor()
                )
                if uses_native_positioning:
                    origin_x += transform.tx
                    origin_y += transform.ty
                if i > 0:
                    advance_x, advance_y = _paragraph_advance(
                        text_setting.writing_direction, paragraph.compute_leading()
                    )
                    paragraph_offset_x += advance_x or 0.0
                    paragraph_offset_y += advance_y or 0.0
                origin_x += paragraph_offset_x
                origin_y += paragraph_offset_y
                previous_font_size: float | None = None
                for span in paragraph:
                    _, emitted_font_size = self._add_text_span(
                        text_setting,
                        paragraph_node,
                        span,
                        paragraph_origin=(origin_x, origin_y),
                        text_element_scale=text_element_scale,
                        kerning_reference_size=previous_font_size,
                    )
                    # Manual kerning belongs to the boundary before the current
                    # character. Empty and carriage-return-only runs do not create
                    # such a boundary and must not replace the preceding size.
                    if span.text.strip("\r"):
                        previous_font_size = emitted_font_size

        if text_setting.has_warp():
            # When there is <textPath>, we can only optimize at the paragraph level.
            for child in container_node:
                svg_utils.merge_common_child_attributes(
                    child,
                    excludes={"x", "y", "dx", "dy", "transform"},
                )
                svg_utils.merge_consecutive_siblings(child)
                svg_utils.merge_offset_siblings(child)
                svg_utils.merge_singleton_children(child)
                svg_utils.merge_attribute_less_children(child)
        else:
            svg_utils.merge_common_child_attributes(
                text_node,
                excludes={"x", "y", "dx", "dy", "transform"},
            )
            svg_utils.merge_consecutive_siblings(text_node)
            svg_utils.merge_offset_siblings(text_node)
            svg_utils.merge_singleton_children(text_node)
            svg_utils.merge_attribute_less_children(text_node)
        return text_node

    def _apply_text_element_scaling(
        self,
        text_setting: TypeSetting,
        text_node: ET.Element,
        paragraphs: list[Paragraph],
        uses_native_positioning: bool,
    ) -> float | None:
        """Apply layer-wide non-uniform text scaling to the <text> element.

        When every span shares the same non-uniform scale, the scaling can be
        expressed as a transform on the ``<text>`` element instead of the spans.
        Unlike ``transform`` on ``<tspan>`` (SVG 2.0 only, ignored by browsers and
        resvg), this renders everywhere, so glyph proportions, advance widths and
        text alignment all match Photoshop.

        Only the inline (advance) axis is scaled here; the cross axis is carried by
        ``font-size`` so that explicit paragraph offsets keep their leading.
        The transform is anchored at the paragraph origin so that text alignment is
        preserved.

        Args:
            text_setting: Type setting object with writing direction and transform.
            text_node: The ``<text>`` element to scale.
            paragraphs: Paragraphs of the text layer.
            uses_native_positioning: Whether native x/y positioning is used.

        Returns:
            The inline-axis scale factor applied to the ``<text>`` element, meaning
            spans must only carry the cross-axis scale in their font-size, or None
            when the scaling has to stay on the spans.
        """
        # Warped text is laid out along a <textPath>; scaling the <text> element
        # would distort the warp path itself.
        if text_setting.has_warp():
            return None

        scale = _common_span_scale(paragraphs)
        if scale is None:
            return None

        # Justify All sets textLength on the paragraph, which the scale would stretch.
        if any(
            paragraph.justification == Justification.JUSTIFY_ALL
            for paragraph in paragraphs
        ):
            return None

        is_horizontal = text_setting.writing_direction == WritingDirection.HORIZONTAL_TB

        # The transform is anchored at a single point, so every paragraph must share
        # the same anchor position on the inline axis. Comparing positions rather
        # than justification is deliberate: scaling about a shared anchor is exact
        # for "start", "middle" and "end" alike, so point text keeps the exact path
        # even when its paragraphs are justified differently.
        anchors = {
            self._compute_paragraph_position(text_setting, paragraph.get_text_anchor())[
                0 if is_horizontal else 1
            ]
            for paragraph in paragraphs
        }
        if len(anchors) != 1:
            return None

        horizontal_scale, vertical_scale = scale
        x, y, _ = self._compute_paragraph_position(
            text_setting, paragraphs[0].get_text_anchor()
        )
        if uses_native_positioning:
            x += text_setting.transform.tx
            y += text_setting.transform.ty

        # font-size carries the cross-axis scale, the transform the inline axis.
        if is_horizontal:
            inline_scale = (horizontal_scale / vertical_scale, 1.0)
        else:
            inline_scale = (1.0, vertical_scale / horizontal_scale)

        svg_utils.append_attribute(
            text_node, "transform", _scale_about(inline_scale, (x, y))
        )
        return inline_scale[0] if is_horizontal else inline_scale[1]

    def _create_foreign_object_text(self, text_setting: TypeSetting) -> ET.Element:
        """Create <foreignObject> with XHTML content for text wrapping.

        This method creates a foreignObject element containing XHTML div/p/span
        elements with CSS styling. This enables proper text wrapping for bounding
        box text, which is not natively supported by SVG.

        Args:
            text_setting: TypeSetting object with text data.

        Returns:
            foreignObject element containing XHTML content.

        Note:
            - Requires XHTML namespace for proper rendering
            - Supported by modern browsers (Chrome, Firefox, Safari, Edge)
            - Not supported by resvg/resvg-py or many other SVG renderers
              (PDF converters, design tools)
        """
        bounds = text_setting.box_bounds
        transform = text_setting.transform

        # Create foreignObject element with bounding box dimensions
        foreign_obj = self.create_node(
            "foreignObject",
            x=transform.tx + bounds.left,
            y=transform.ty + bounds.top,
            width=bounds.width,
            height=bounds.height,
        )

        # Apply non-translation transform if needed
        if not transform.is_translation_only():
            svg_utils.set_attribute(foreign_obj, "transform", transform.to_svg_matrix())

        # Check if any paragraph has auto hyphenation enabled
        # If so, add lang attribute for CSS hyphens to work
        paragraphs = list(text_setting)
        has_hyphenation = any(p.style.auto_hyphenate for p in paragraphs)

        # Create XHTML div container with proper namespace
        container_styles = self._get_foreign_object_container_styles(
            text_setting, bounds
        )
        div = svg_utils.create_xhtml_node(
            "div",
            parent=foreign_obj,
            style=svg_utils.styles_to_string(container_styles),
            lang="en" if has_hyphenation else None,
        )

        # Add paragraphs
        for paragraph in paragraphs:
            self._add_foreign_object_paragraph(div, paragraph, text_setting)

        return foreign_obj

    def _add_paragraph(
        self,
        text_setting: TypeSetting,
        paragraph: Paragraph,
        first_paragraph: bool = False,
        uses_native_positioning: bool = False,
    ) -> ET.Element:
        """Add a paragraph to the text node."""
        line_height = paragraph.compute_leading()
        text_anchor = paragraph.get_text_anchor()

        # Calculate positioning based on shape type and writing direction
        x, y, dominant_baseline = self._compute_paragraph_position(
            text_setting, text_anchor
        )

        # Create paragraph node
        paragraph_node = self._create_paragraph_node(
            text_setting,
            x,
            y,
            line_height,
            text_anchor,
            dominant_baseline,
            first_paragraph,
            uses_native_positioning,
        )

        # Apply justification settings
        self._apply_justification(paragraph, paragraph_node, text_setting)

        return paragraph_node

    def _compute_paragraph_position(
        self,
        text_setting: TypeSetting,
        text_anchor: str | None,
    ) -> tuple[float, float, str | None]:
        """Compute paragraph position based on justification, shape type,
        and writing direction.

        Args:
            text_setting: Type setting object containing bounds and writing direction.
            text_anchor: SVG text-anchor value ("start", "middle", "end", or None).

        Returns:
            Tuple of (x, y, dominant_baseline) for positioning the paragraph.
        """
        x = 0.0
        y = 0.0
        dominant_baseline = None

        if text_setting.shape_type == ShapeType.BOUNDING_BOX:
            # Use "hanging" baseline for bounding box text, which aligns text to
            # the hanging baseline (top of most glyphs). This provides the closest
            # match to Photoshop's bounding box text positioning, though subtle
            # differences may remain due to font rendering variations between
            # Photoshop and browsers.
            dominant_baseline = "hanging"
            if text_setting.writing_direction == WritingDirection.HORIZONTAL_TB:
                if text_anchor == "end":
                    x = text_setting.bounds.right
                elif text_anchor == "middle":
                    x = (text_setting.bounds.left + text_setting.bounds.right) / 2
            elif text_setting.writing_direction == WritingDirection.VERTICAL_RL:
                logger.debug(
                    "Dominant baseline may not be supported by SVG renderers "
                    "for vertical text."
                )
                x = text_setting.bounds.right
                if text_anchor == "end":
                    y = text_setting.bounds.bottom
                elif text_anchor == "middle":
                    y = (text_setting.bounds.top + text_setting.bounds.bottom) / 2

        return x, y, dominant_baseline

    def _create_paragraph_node(
        self,
        text_setting: TypeSetting,
        x: float,
        y: float,
        line_height: float,
        text_anchor: str | None,
        dominant_baseline: str | None,
        first_paragraph: bool,
        uses_native_positioning: bool,
    ) -> ET.Element:
        """Create paragraph node with positioning attributes.

        Paragraphs reset their inline-axis position and advance relatively along
        the block axis: ``x``/``dy`` for horizontal text and ``y``/``dx`` for
        ``vertical-rl`` text.

        Args:
            text_setting: Type setting object containing transform information.
            text_node: Parent text element.
            x: Base x position.
            y: Base y position.
            line_height: Line height used for the paragraph advance.
            text_anchor: SVG text-anchor value.
            dominant_baseline: SVG dominant-baseline value.
            first_paragraph: Whether this is the first paragraph.
            uses_native_positioning: Whether native x/y positioning is used.

        Returns:
            New tspan element with appropriate position attributes.
        """
        # Add transform offset if using native positioning
        if uses_native_positioning:
            transform = text_setting.transform
            x += transform.tx
            y += transform.ty

        is_vertical = text_setting.writing_direction == WritingDirection.VERTICAL_RL

        # Reset the inline axis for every paragraph. The first paragraph also sets
        # the block-axis origin; later paragraphs move from it with dx or dy.
        if is_vertical:
            should_set_x = first_paragraph and (uses_native_positioning or x != 0.0)
            should_set_y = uses_native_positioning or y != 0.0 or not first_paragraph
        elif uses_native_positioning:
            should_set_x = True
            should_set_y = first_paragraph
        else:
            should_set_x = x != 0.0 or not first_paragraph
            should_set_y = y != 0.0 and first_paragraph

        advance_x, advance_y = _paragraph_advance(
            text_setting.writing_direction, line_height
        )

        # Create paragraph node with positioning and baseline attributes.
        # The dominant-baseline="hanging" provides the closest match to Photoshop's
        # bounding box text positioning, though subtle differences may remain due to
        # font rendering variations between Photoshop and browsers.
        return self.create_node(
            "tspan",
            text_anchor=text_anchor,
            x=x if should_set_x else None,
            y=y if should_set_y else None,
            dx=advance_x if not first_paragraph else None,
            dy=advance_y if not first_paragraph else None,
            dominant_baseline=dominant_baseline,
        )

    def _apply_justification(
        self,
        paragraph: Paragraph,
        paragraph_node: ET.Element,
        text_setting: TypeSetting,
    ) -> None:
        """Apply justification settings to paragraph node.

        Args:
            paragraph: Paragraph object containing justification settings.
            paragraph_node: SVG tspan element to apply justification to.
            text_setting: Type setting object containing bounds information.
        """
        if paragraph.justification == Justification.JUSTIFY_ALL:
            logger.info("Justify All is not fully supported in SVG.")
            svg_utils.set_attribute(
                paragraph_node,
                "textLength",
                text_setting.bounds.width,
            )
            svg_utils.set_attribute(paragraph_node, "lengthAdjust", "spacingAndGlyphs")

    def _add_text_span(
        self,
        text_setting: TypeSetting,
        paragraph_node: ET.Element,
        span: Span,
        paragraph_origin: tuple[float, float] = (0.0, 0.0),
        text_element_scale: float | None = None,
        kerning_reference_size: float | None = None,
    ) -> tuple[ET.Element, float]:
        """Add a text span to the paragraph node.

        Args:
            text_setting: Type setting object with writing direction and metrics.
            paragraph_node: Parent paragraph tspan.
            span: Style span to render.
            paragraph_origin: Absolute position of the paragraph, used to anchor
                per-span transforms.
            text_element_scale: Inline-axis scale already applied to the parent
                ``<text>`` element by :meth:`_apply_text_element_scaling`, if any.
            kerning_reference_size: Emitted font size of the preceding drawable
                character, or None at a paragraph boundary.

        Returns:
            The emitted ``<tspan>`` and its effective font size in the local SVG
            coordinate system.
        """
        style = span.style
        # Get PostScript name from font index - no font resolution needed
        postscript_name = text_setting.get_postscript_name(style.font)

        # Handle horizontal and vertical scaling
        scaling = self._calculate_text_scaling(
            style.font_size,
            style.horizontal_scale,
            style.vertical_scale,
            text_setting.writing_direction,
            text_scale_applied=text_element_scale is not None,
        )
        scaled_font_size = scaling.font_size
        emitted_font_size = scaled_font_size
        if style.font_baseline == FontBaseline.SUPERSCRIPT:
            emitted_font_size *= text_setting.superscript_size
        elif style.font_baseline == FontBaseline.SUBSCRIPT:
            emitted_font_size *= text_setting.subscript_size

        # Faux bold thickens the outline of the specified face rather than
        # selecting a bolder one, so emit it as a stroke on the glyph and leave
        # font-weight to the face itself. paint-order="stroke" keeps the
        # thickening outside the fill instead of eating into it.
        stroke = style.get_stroke_color()
        stroke_width: float | None = None
        stroke_linejoin: str | None = None
        paint_order: str | None = None
        if style.faux_bold:
            fill_color = style.get_fill_color()
            if style.stroke_flag and stroke != "none":
                # stroke/stroke-width are already taken by the PSD character
                # stroke, whose own width psd2svg does not read yet.
                logger.warning(
                    "Faux bold is not applied to a span that also has a "
                    "character stroke; the stroke is emitted alone."
                )
            elif fill_color != "none":
                # Thicken the glyph in the colour it is painted in.
                # get_fill_color() returns None both for SVG's default black and
                # for a disabled fill, which psd2svg also renders black today.
                stroke = fill_color if fill_color else "#000000"
                stroke_width = FAUX_BOLD_STROKE_RATIO * emitted_font_size
                # Photoshop offsets the contour, which is round at a convex
                # corner; the default miter join would spike there instead.
                stroke_linejoin = "round"
                paint_order = "stroke"

        with self.set_current(paragraph_node):
            tspan = self.create_node(
                "tspan",
                text=span.text.strip("\r"),  # Remove carriage return characters
                font_size=scaled_font_size,
                font_family=postscript_name,  # Store PostScript name directly
                font_style="italic"
                if style.faux_italic
                else None,  # Only for faux italic
                fill=style.get_fill_color(),
                stroke=stroke,
                stroke_width=stroke_width,
                stroke_linejoin=stroke_linejoin,
                paint_order=paint_order,
                baseline_shift=style.baseline_shift
                if style.baseline_shift != 0.0
                else None,
            )
        if style.font_caps == FontCaps.ALL_CAPS:
            svg_utils.add_style(tspan, "text-transform", "uppercase")
        elif style.font_caps == FontCaps.SMALL_CAPS:
            # NOTE: Using text_settings.small_caps_size with text-transform
            # may be more accurate.
            svg_utils.set_attribute(tspan, "font-variant", "small-caps")

        if style.underline:
            svg_utils.append_attribute(tspan, "text-decoration", "underline")
        if style.strikethrough:
            svg_utils.append_attribute(tspan, "text-decoration", "line-through")

        # Apply ligature settings using font-variant-ligatures
        # Photoshop defaults to ligatures=True (common ligatures enabled)
        # CSS default behavior is 'normal' which enables common ligatures
        # Only set font-variant-ligatures when it differs from the default
        if not style.ligatures and not style.discretionary_ligatures:
            # Both disabled -> none
            svg_utils.add_style(tspan, "font-variant-ligatures", "none")
        elif style.ligatures and not style.discretionary_ligatures:
            # Only common ligatures enabled (Photoshop default, CSS default)
            # Skip setting attribute - this is the default CSS behavior
            pass
        elif not style.ligatures and style.discretionary_ligatures:
            # Only discretionary ligatures enabled (uncommon case)
            svg_utils.add_style(
                tspan, "font-variant-ligatures", "discretionary-ligatures"
            )
        else:
            # Both enabled
            svg_utils.add_style(
                tspan,
                "font-variant-ligatures",
                "common-ligatures discretionary-ligatures",
            )

        # NOTE: Photoshop uses different values for subscript position/size.
        # Using baseline-shift with sub or super will result in inaccurate rendering.
        # NOTE: The baseline shift is perpendicular to the writing direction, so it
        # follows the cross-axis size rather than the emitted font-size.
        if style.font_baseline == FontBaseline.SUPERSCRIPT:
            svg_utils.set_attribute(
                tspan,
                "baseline-shift",
                scaling.baseline_size * text_setting.superscript_position,
            )
            svg_utils.set_attribute(tspan, "font-size", emitted_font_size)
        elif style.font_baseline == FontBaseline.SUBSCRIPT:
            svg_utils.set_attribute(
                tspan,
                "baseline-shift",
                -scaling.baseline_size * text_setting.subscript_position,
            )
            svg_utils.set_attribute(tspan, "font-size", emitted_font_size)

        # Apply letter spacing from tracking, tsume, and optional global offset
        # NOTE: Tracking is in 1/1000 em units.
        # NOTE: Tsume is a percentage (0-1) that reduces spacing
        # by that amount of font size.
        # NOTE: It seems Photoshop applies 1/10 of the tsume value
        # to letter spacing.
        # NOTE: There is a slight offset difference for the first charactor because
        # letter-spacing applies after the character.
        letter_spacing = style.tracking / 1000 * scaled_font_size
        letter_spacing -= style.tsume / 10 * scaled_font_size  # Tsume tightens spacing
        # NOTE: Unlike tracking and tsume, the offset is an absolute value in pixels,
        # so it is divided by the scale of the <text> element to keep it absolute.
        if text_element_scale is not None:
            letter_spacing += self.text_letter_spacing_offset / text_element_scale
        else:
            letter_spacing += self.text_letter_spacing_offset

        # Only set letter-spacing if non-zero (or if offset makes it non-zero)
        if letter_spacing != 0:
            svg_utils.set_attribute(
                tspan,
                "letter-spacing",
                letter_spacing,
            )

        # Apply kerning adjustment (manual kerning in 1/1000 em units)
        # Kerning adjusts the spacing BEFORE the current character
        # (between previous and current).
        # We use dx/dy to shift the character position, which effectively
        # adjusts the space before it.
        # NOTE: letter-spacing adds space AFTER characters,
        # so we can't use it for kerning.
        if (
            style.kerning != 0
            and kerning_reference_size is not None
            and span.text.strip("\r")
        ):
            kerning_offset = style.kerning / 1000 * kerning_reference_size
            # Use dx for horizontal text, dy for vertical text
            if text_setting.writing_direction == WritingDirection.HORIZONTAL_TB:
                svg_utils.set_attribute(tspan, "dx", kerning_offset)
            elif text_setting.writing_direction == WritingDirection.VERTICAL_RL:
                svg_utils.set_attribute(tspan, "dy", kerning_offset)

        # Apply the residual cross-axis scale when spans disagree on their scaling
        # and it could not be applied to the <text> element.
        # (Uniform scaling is already handled via scaled_font_size above.)
        if scaling.transform_scale is not None:
            logger.warning(
                "Non-uniform text scaling on individual spans is not supported by "
                "SVG renderers, which ignore transform on <tspan>. Advance widths "
                "and text positions are preserved, but the glyphs will not be "
                "scaled across the writing direction. Consider using "
                "enable_text=False to rasterize text layers."
            )

            # Anchor the scale at the paragraph position so that it does not shift
            # the text. The optimizer may move this transform up to the <text>
            # element when the paragraph holds a single span, where renderers do
            # honor it; the anchor keeps that promotion correct.
            #
            # Text on a <textPath> follows the path instead of a paragraph baseline,
            # so there is no origin to anchor at. Emitting the scale anyway would
            # displace the run in a renderer that honors it, which is worse than
            # leaving the cross axis unscaled.
            if not text_setting.has_warp():
                svg_utils.append_attribute(
                    tspan,
                    "transform",
                    _scale_about(scaling.transform_scale, paragraph_origin),
                )

        if (
            text_setting.writing_direction == WritingDirection.VERTICAL_RL
            and style.baseline_direction == 1
        ):
            # NOTE: Only Chromium-based browsers support
            # 'text-orientation: upright' for SVG.
            logger.debug(
                "Applying text-orientation: upright, but may not be supported "
                "in SVG renderers."
            )
            svg_utils.add_style(tspan, "text-orientation", "upright")
            # NOTE: glyph-orientation-vertical is deprecated but may help
            # with compatibility.
            # svg_utils.set_attribute(tspan, "glyph-orientation-vertical", "90")
        return tspan, emitted_font_size

    def _calculate_text_scaling(
        self,
        font_size: float,
        horizontal_scale: float,
        vertical_scale: float,
        writing_direction: WritingDirection,
        text_scale_applied: bool = False,
    ) -> TextScaling:
        """Calculate font-size scaling for text spans.

        Non-uniform scaling cannot be expressed on a ``<tspan>``: ``transform`` is
        SVG 2.0 only and is ignored by browsers and resvg alike. The font-size
        therefore carries the scale of the inline (advance) axis - horizontal for
        horizontal text, vertical for vertical text - so that glyph advance widths,
        the position of following characters and center/right alignment match
        Photoshop even when the transform is dropped. The remaining cross-axis
        scale is emitted as a transform for SVG 2.0 renderers.

        When the whole layer shares the same scale, the inline axis is instead
        applied to the ``<text>`` element by :meth:`_apply_text_element_scaling`
        and the font-size only carries the cross axis.

        Args:
            font_size: Base font size in pixels.
            horizontal_scale: Horizontal scale factor (default 1.0).
            vertical_scale: Vertical scale factor (default 1.0).
            writing_direction: Writing direction of the text layer.
            text_scale_applied: Whether the inline-axis scale is already applied to
                the parent ``<text>`` element.

        Returns:
            The font size to emit, the reference size for baseline offsets, and the
            residual (sx, sy) transform, if any.
        """
        has_scaling = vertical_scale != 1.0 or horizontal_scale != 1.0
        is_uniform_scale = abs(vertical_scale - horizontal_scale) < SCALE_TOLERANCE

        if not has_scaling:
            return TextScaling(font_size, font_size, None)

        # Validate scale values and determine approach
        if vertical_scale <= 0 or horizontal_scale <= 0:
            logger.warning(
                f"Invalid scale values: horizontal={horizontal_scale}, "
                f"vertical={vertical_scale}. Using original font-size."
            )
            return TextScaling(font_size, font_size, None)

        if is_uniform_scale:
            # Uniform scaling: scale font-size directly (renderer-compatible)
            scaled_font_size = font_size * horizontal_scale
            return TextScaling(scaled_font_size, scaled_font_size, None)

        # Non-uniform scaling: split the scale between the inline and cross axes.
        # NOTE: For vertical text this assumes upright glyphs, whose advance follows
        # the vertical scale. That holds for every glyph in upright orientation
        # (baseline_direction 1) and for CJK glyphs in the default mixed
        # orientation; Latin runs in mixed orientation are rotated and advance by
        # their horizontal scale instead. Orientation is a per-character property
        # there, so it cannot be decided per span. See docs/limitations.rst.
        if writing_direction == WritingDirection.HORIZONTAL_TB:
            inline_scale, cross_scale = horizontal_scale, vertical_scale
        else:
            inline_scale, cross_scale = vertical_scale, horizontal_scale
        # NOTE: This is the size seen by a renderer that drops the residual
        # transform. A renderer that honors it scales the baseline shift as well.
        baseline_size = font_size * cross_scale

        if text_scale_applied:
            # The <text> element carries the inline axis.
            return TextScaling(baseline_size, baseline_size, None)

        residual = cross_scale / inline_scale
        transform_scale = (
            (1.0, residual)
            if writing_direction == WritingDirection.HORIZONTAL_TB
            else (residual, 1.0)
        )
        return TextScaling(font_size * inline_scale, baseline_size, transform_scale)

    def _get_foreign_object_container_styles(
        self, text_setting: TypeSetting, bounds: Rectangle
    ) -> dict[str, str]:
        """Get CSS styles for foreignObject container div.

        Args:
            text_setting: TypeSetting object with writing direction.
            bounds: Bounding box dimensions.

        Returns:
            Dictionary of CSS property names to values.
        """
        styles = {
            "width": svg_utils.num2str_with_unit(bounds.width),
            "height": svg_utils.num2str_with_unit(bounds.height),
            "margin": "0",
            "padding": "0",
            "overflow": "hidden",  # Match Photoshop clipping behavior
            # Ensure padding (from paragraph indents) is included in width/height,
            # not added to it, matching Photoshop's bounding box behavior
            "box-sizing": "border-box",
        }

        if text_setting.writing_direction == WritingDirection.VERTICAL_RL:
            styles["writing-mode"] = "vertical-rl"

        return styles

    def _add_foreign_object_paragraph(
        self,
        container: ET.Element,
        paragraph: Paragraph,
        text_setting: TypeSetting,
    ) -> None:
        """Add a paragraph as XHTML <p> element.

        Args:
            container: Parent XHTML div element.
            paragraph: Paragraph object containing style and spans.
            text_setting: TypeSetting object for font info lookup.
        """
        # Get paragraph CSS styles
        p_styles = self._get_foreign_object_paragraph_styles(paragraph)

        # Check if any span in this paragraph needs whitespace preservation
        needs_preserve = any(
            _needs_whitespace_preservation(span.text) for span in paragraph
        )

        # Create <p> element
        p_elem = svg_utils.create_xhtml_node(
            "p",
            parent=container,
            xml_space="preserve" if needs_preserve else None,
            style=svg_utils.styles_to_string(p_styles),
        )

        # Add spans
        for span in paragraph:
            self._add_foreign_object_span(p_elem, span, text_setting, paragraph)

    def _get_foreign_object_paragraph_styles(
        self, paragraph: Paragraph
    ) -> dict[str, str]:
        """Convert paragraph settings to CSS styles.

        Supports paragraph formatting properties:
        - Text alignment (justification)
        - Line height (leading)
        - First line indent
        - Start/end indent (left/right padding)
        - Space before/after (top/bottom margins)
        - Hanging punctuation (limited browser support)

        Args:
            paragraph: Paragraph object containing style and formatting.

        Returns:
            Dictionary of CSS property names to values.
        """
        styles = {
            "margin": "0",
            "padding": "0",
        }

        # Text alignment mapping
        # Note: CSS text-align: justify works correctly with display: inline-block
        # spans because the text content inside spans can still wrap and justify.
        # However, CSS lacks direct support for Photoshop's justify variants:
        # - JUSTIFY_LAST_LEFT/RIGHT/CENTER: justify all lines except last
        # - JUSTIFY_ALL: justify all lines including last
        # CSS text-align-last could provide this, but browser support varies.
        # For now, all justify modes map to 'justify' (equivalent to JUSTIFY_LAST_LEFT).
        justification_map = {
            Justification.LEFT: "left",
            Justification.RIGHT: "right",
            Justification.CENTER: "center",
            Justification.JUSTIFY_LAST_LEFT: "justify",
            Justification.JUSTIFY_LAST_RIGHT: "justify",  # Approximation
            Justification.JUSTIFY_LAST_CENTER: "justify",  # Approximation
            Justification.JUSTIFY_ALL: "justify",  # Approximation
        }
        text_align = justification_map.get(paragraph.justification, "left")
        if text_align != "left":  # Skip default
            styles["text-align"] = text_align

        # Line height and margin-top compensation calculation
        leading = paragraph.compute_leading()
        margin_top_compensation = 0.0  # Track compensation for later use

        if leading > 0:
            styles["line-height"] = svg_utils.num2str_with_unit(leading)

            # Calculate half-leading compensation for all paragraphs
            # CSS line-height centers text within a line box, adding unwanted space
            # above each line. We calculate the negative margin as:
            # margin-top = -(leading - font_size) / 2
            # This removes the half-leading space above each paragraph.
            if paragraph.spans:
                # Get font size from the first span
                first_span = paragraph.spans[0]
                font_size = first_span.style.font_size
                if leading > font_size:
                    # Calculate half-leading compensation
                    margin_top_compensation = -(leading - font_size) / 2

        # First line indent
        if paragraph.style.first_line_indent != 0:
            styles["text-indent"] = svg_utils.num2str_with_unit(
                paragraph.style.first_line_indent
            )

        # Start indent (left padding) - overrides padding: 0
        if paragraph.style.start_indent != 0:
            styles["padding-left"] = svg_utils.num2str_with_unit(
                paragraph.style.start_indent
            )

        # End indent (right padding) - overrides padding: 0
        if paragraph.style.end_indent != 0:
            styles["padding-right"] = svg_utils.num2str_with_unit(
                paragraph.style.end_indent
            )

        # Space before paragraph - combine with line-height compensation
        # If we have both space_before and compensation, add them together
        total_margin_top = paragraph.style.space_before + margin_top_compensation
        # Only add margin-top if it exceeds the negligible threshold
        if abs(total_margin_top) > NEGLIGIBLE_MARGIN_THRESHOLD:
            styles["margin-top"] = svg_utils.num2str_with_unit(total_margin_top)

        # Space after paragraph - overrides margin: 0
        if paragraph.style.space_after != 0:
            styles["margin-bottom"] = svg_utils.num2str_with_unit(
                paragraph.style.space_after
            )

        # Hanging punctuation (limited browser support - Safari only as of 2025)
        # Note: Chrome, Firefox, and Edge do not support this CSS property.
        # We include it for future compatibility and Safari users.
        if paragraph.style.hanging:
            styles["hanging-punctuation"] = "first last"

        # Hyphenation
        # Map PSD AutoHyphenate property to CSS hyphens property.
        # CSS hyphens: auto requires the lang attribute to work properly.
        if paragraph.style.auto_hyphenate:
            styles["hyphens"] = "auto"

            # Map hyphenation parameters to CSS hyphenate-limit-chars
            # Format: hyphenate-limit-chars: <word-min> <char-before> <char-after>
            # Browser support: Firefox 43+, Safari 17+, not supported in Chrome
            word_min = paragraph.style.hyphenation_word_size
            char_before = paragraph.style.pre_hyphen
            char_after = paragraph.style.post_hyphen
            styles["hyphenate-limit-chars"] = (
                f"{svg_utils.num2str(word_min)} "
                f"{svg_utils.num2str(char_before)} "
                f"{svg_utils.num2str(char_after)}"
            )

        return styles

    def _add_foreign_object_span(
        self,
        p_elem: ET.Element,
        span: Span,
        text_setting: TypeSetting,
        paragraph: Paragraph,
    ) -> None:
        """Add a text span as XHTML <span> element.

        Args:
            p_elem: Parent XHTML <p> element.
            span: Span object containing text and style.
            text_setting: TypeSetting object for font info lookup.
            paragraph: Parent paragraph object for accessing line-height.
        """
        # Get span CSS styles
        span_styles = self._get_foreign_object_span_styles(
            span, text_setting, paragraph
        )

        # Create <span> element
        # If no styles needed, add text directly to paragraph
        if not span_styles:
            # Append text to parent
            if len(p_elem) > 0:
                # Has children, append to last child's tail
                if p_elem[-1].tail:
                    p_elem[-1].tail += span.text.strip("\r")
                else:
                    p_elem[-1].tail = span.text.strip("\r")
            else:
                # No children, append to parent text
                if p_elem.text:
                    p_elem.text += span.text.strip("\r")
                else:
                    p_elem.text = span.text.strip("\r")
        else:
            svg_utils.create_xhtml_node(
                "span",
                parent=p_elem,
                text=span.text.strip("\r"),
                style=svg_utils.styles_to_string(span_styles),
            )

    def _get_foreign_object_span_styles(
        self, span: Span, text_setting: TypeSetting, paragraph: Paragraph
    ) -> dict[str, str]:
        """Convert span style settings to CSS styles.

        Args:
            span: Span object containing text style information.
            text_setting: TypeSetting object for font info and calculations.
            paragraph: Parent paragraph object for accessing line-height.

        Returns:
            Dictionary of CSS property names to values.
        """
        style = span.style
        # Get PostScript name from font index - no font resolution needed
        postscript_name = text_setting.get_postscript_name(style.font)

        # CSS transforms do not affect layout either, so the font size carries the
        # scale of the inline axis, exactly like the native <text> output.
        scaling = self._calculate_text_scaling(
            style.font_size,
            style.horizontal_scale,
            style.vertical_scale,
            text_setting.writing_direction,
        )

        styles = {}

        # Set display: inline-block and line-height to prevent inline box from
        # expanding parent line height (CSS inline formatting issue).
        # This ensures the paragraph's line-height is respected even when
        # span font-size > line-height. See GitHub issue #273.
        styles["display"] = "inline-block"
        leading = paragraph.compute_leading()
        if leading > 0:
            styles["line-height"] = svg_utils.num2str_with_unit(leading)

        # Font family - use PostScript name directly
        if postscript_name:
            styles["font-family"] = f"'{postscript_name}'"

        # Font size
        if style.font_size:
            styles["font-size"] = svg_utils.num2str_with_unit(scaling.font_size)

        # Font weight is left to the face: the PostScript name encodes it, and
        # faux bold is emitted as an outline thickening below rather than as a
        # heavier weight.

        # Font style - only set for faux italic (PostScript name encodes actual style)
        if style.faux_italic:
            styles["font-style"] = "italic"

        # Color
        fill_color = style.get_fill_color()
        if fill_color and fill_color != "none":
            styles["color"] = fill_color

        # Text decoration
        decorations = []
        if style.underline:
            decorations.append("underline")
        if style.strikethrough:
            decorations.append("line-through")
        if decorations:
            styles["text-decoration"] = " ".join(decorations)

        # Text transform
        if style.font_caps == FontCaps.ALL_CAPS:
            styles["text-transform"] = "uppercase"
        elif style.font_caps == FontCaps.SMALL_CAPS:
            styles["font-variant"] = "small-caps"

        # Letter spacing
        letter_spacing = style.tracking / 1000 * scaling.font_size
        letter_spacing += self.text_letter_spacing_offset
        if letter_spacing != 0:
            styles["letter-spacing"] = svg_utils.num2str_with_unit(letter_spacing)

        # Vertical alignment (superscript/subscript)
        if style.font_baseline == FontBaseline.SUPERSCRIPT:
            styles["vertical-align"] = "super"
            styles["font-size"] = svg_utils.num2str_with_unit(
                scaling.font_size * text_setting.superscript_size
            )
        elif style.font_baseline == FontBaseline.SUBSCRIPT:
            styles["vertical-align"] = "sub"
            styles["font-size"] = svg_utils.num2str_with_unit(
                scaling.font_size * text_setting.subscript_size
            )
        elif style.baseline_shift != 0.0:
            # Custom baseline shift
            styles["vertical-align"] = svg_utils.num2str_with_unit(style.baseline_shift)

        # Horizontal/vertical scale: the inline axis is already in the font size,
        # only the cross axis is left for the (layout-neutral) CSS transform.
        if scaling.transform_scale is not None:
            scale_x, scale_y = scaling.transform_scale
            styles["transform"] = (
                f"scale({svg_utils.num2str(scale_x)}, {svg_utils.num2str(scale_y)})"
            )
            # Note: display: inline-block already set above for all spans
            styles["transform-origin"] = "center"

        # Stroke (text outline) - CSS supports this with -webkit-text-stroke
        stroke_color = style.get_stroke_color()
        if stroke_color and stroke_color != "none":
            # Note: This is a webkit-specific property but widely supported
            styles["-webkit-text-stroke"] = f"1px {stroke_color}"

        # Faux bold is an outline thickening, like in the native <text> path.
        if style.faux_bold:
            fill_color = style.get_fill_color()
            if style.stroke_flag and stroke_color != "none":
                logger.warning(
                    "Faux bold is not applied to a span that also has a "
                    "character stroke; the stroke is emitted alone."
                )
            elif fill_color != "none":
                # The em the span actually renders at, after any sub/superscript
                # reduction applied above.
                em = scaling.font_size
                if style.font_baseline == FontBaseline.SUPERSCRIPT:
                    em *= text_setting.superscript_size
                elif style.font_baseline == FontBaseline.SUBSCRIPT:
                    em *= text_setting.subscript_size
                width = svg_utils.num2str_with_unit(FAUX_BOLD_STROKE_RATIO * em)
                # Thicken the glyph in its own colour, whether the span sets it
                # ("color" above) or inherits it.
                styles["-webkit-text-stroke"] = f"{width} currentColor"
                styles["paint-order"] = "stroke"

        return styles


# Backward compatibility re-exports
__all__ = [
    "TextConverter",
    "TextWrappingMode",  # Re-exported from typesetting
    "TypeSetting",  # Re-exported from typesetting
]
